from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Any
from urllib.parse import urlparse

import requests
from openai import OpenAI
from langchain_core.tools import BaseTool

from .tools import search_wikipedia, read_wikipedia_page, search_windows_wikipedia

import logging
import json
import time

logging.basicConfig(
    filename="agent.log",
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    encoding="utf-8",
    force=True,
)


logger = logging.getLogger("agent")

SYSTEM_PROMPT = """

Ты — саркастичный участник холивара Linux vs Microsoft Windows. Твоя задача — остроумно защищать Windows, проверяя утверждения пользователя по Wikipedia.

Структура каждого ответа — строго в следующем порядке:

1. Театральное вступление. Начни с короткой, яркой шутки, ироничного комментария или преувеличенно драматичной реакции на заявление пользователя. Не начинай с сухих фактов, оговорок или описания результатов поиска. Вступление должно звучать как начало стендап-выступления на техническом холиваре.
2. Разбор аргумента. Объясни с юмором, в чём может заключаться преувеличение пользователя. Если утверждение ещё не проверено, не выдавай предположение за установленный факт.
3. Доказательная часть. Приведи конкретные результаты проверки в Wikipedia: названия страниц, прямые ссылки и краткое объяснение того, что именно они подтверждают или не подтверждают.
4. Финальный вердикт. В конце сформулируй краткий, запоминающийся вывод с шуткой в духе Linux vs Windows. Если найдены сопоставимые возможности Windows, приведи ссылки на соответствующие материалы. Если доказательств недостаточно, честно скажи об этом.


Сами разделы подписывать не надо, просто аргночно и лаконично выстраивый ответ. 

Правила проверки фактов:

- Сначала получи результаты необходимых инструментов, а затем формируй окончательный ответ. Шуточное вступление не должно заменять проверку.
- Если пользователь прислал ссылку на Wikipedia, проверь соответствующую страницу. Остальные URL игнорируй.
- Если утверждение голословное, ищи подтверждения через MediaWiki API.
- Если абсолютное утверждение не подтверждается, различай отсутствие подтверждения и доказанное опровержение.
- Если преимущество Linux подтверждено, найди сопоставимые возможности Windows в Wikipedia и приведи ссылки, если такие материалы обнаружены.
- Не выдумывай источники, цитаты, характеристики ОС или результаты поиска.
- Если API вернул ошибку или данные неполные, явно укажи ограничение проверки.
- Сарказм должен быть острым и театральным, но направленным на аргументы, технические мифы и мемы, а не на реальные личные качества пользователя.

Стиль: стендап-комик, который слишком серьёзно относится к компьютерным операционным системам. Метафоры, гиперболы и каламбуры приветствуются. Сухой академический тон — только в доказательной части. Финал должен быть смешным, но фактически честным.

"""

TOOLS: list[BaseTool] = [
    search_wikipedia,
    read_wikipedia_page,
    search_windows_wikipedia,
]


def _schema_for(tool: BaseTool) -> dict:
    schema = tool.args_schema.model_json_schema()
    schema.pop("title", None)
    schema.pop("$defs", None)
    # DeepSeek tool calling expects JSON Schema parameters.
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": schema,
        },
    }


def _extract_wikipedia_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s<>()]+", text)
    allowed = []
    for url in urls:
        url = url.rstrip(".,!?;:»\"'")
        host = (urlparse(url).hostname or "").lower()
        if host == "wikipedia.org" or host.endswith(".wikipedia.org"):
            allowed.append(url)
        # All other links are deliberately ignored.
    return list(dict.fromkeys(allowed))


class Orchestrator:
    """Owns the agent loop; LangChain @tool only describes/exposes tools."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_steps: int = 8,
        max_tool_calls: int = 10,
        max_history_messages: int = 32,
    ):
        self.client = OpenAI(
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.max_steps = max(1, max_steps)
        self.max_tool_calls = max(1, max_tool_calls)
        # Leave room for the fixed prompt and one complete tool-call batch.
        self.max_history_messages = max(6 + 2 * self.max_tool_calls, max_history_messages)
        self.tools = {tool.name: tool for tool in TOOLS}
        self.tool_specs = [_schema_for(tool) for tool in TOOLS]

    def run(self, user_text: str) -> str:
        urls = _extract_wikipedia_urls(user_text)
        if urls:
            # User supplied Wikipedia links: read those pages first.
            # Non-Wikipedia URLs are never passed to any tool.
            initial_instruction = (
                "Проверь утверждение по указанным ссылкам Wikipedia. Сначала вызови "
                "read_wikipedia_page для каждой ссылки. Не делай поиск по голословному "
                "утверждению, пока пользователь дал wiki-ссылку. После проверки действуй по правилам."
                f"\nРазрешённые ссылки:\n" + "\n".join(urls)
            )
        else:
            initial_instruction = (
                "Ссылок Wikipedia в сообщении нет (прочие ссылки игнорируются). "
                "Сначала выдели проверяемое утверждение о Linux и вызови search_wikipedia."
            )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
            {"role": "system", "content": initial_instruction},
        ]
        calls = 0
        seen = Counter()
        wikipedia_unavailable = False

        for _step in range(self.max_steps):
            messages = self._trim_history(messages)

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tool_specs,
                tool_choice="auto",
                temperature=0.7,
                max_tokens=1400,
                # DeepSeek's tool-calling examples use non-thinking mode for
                # broad compatibility with tool_choice=auto.
                extra_body={"thinking": {"type": "disabled"}},
            )
            message = response.choices[0].message

            if not message.tool_calls:
                return message.content or "Кажется, агент потерял дар сарказма. Попробуйте ещё раз."

            # Keep the assistant's tool-call message in conversation history.
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in message.tool_calls
                ],
            })

            for call in message.tool_calls:
                calls += 1
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                    signature = (name, json.dumps(args, sort_keys=True, ensure_ascii=False))
                    seen[signature] += 1

                    if wikipedia_unavailable:
                        result = "Пропущено: Wikipedia API уже сообщил о временной ошибке."
                    elif calls > self.max_tool_calls:
                        result = "Остановлено защитным лимитом вызовов инструментов."
                    elif seen[signature] > 2:
                        result = "Этот же вызов уже повторялся дважды. Выбери другой шаг или сформируй вывод."
                    elif name not in self.tools:
                        result = f"Неизвестный инструмент: {name}"
                    elif name == "read_wikipedia_page":
                        # Defense in depth: enforce Wikipedia-only URLs outside the model.
                        url = str(args.get("url", ""))
                        if url not in urls and not _is_wikipedia(url):
                            result = "Ссылка отклонена: разрешён только домен wikipedia.org."
                        else:
                            result = self.tools[name].invoke(args)
                    else:
                        result = self.tools[name].invoke(args)
                except Exception as exc:
                    result = f"Ошибка инструмента ({type(exc).__name__}): {exc}"
                    is_transient_http_error = (
                        isinstance(exc, requests.HTTPError)
                        and exc.response is not None
                        and exc.response.status_code in (429, 500, 502, 503, 504)
                    )
                    if isinstance(exc, requests.RequestException) and (
                        is_transient_http_error or name in self.tools
                    ):
                        wikipedia_unavailable = True
                        result = (
                            "Оба маршрута Wikipedia временно недоступны. "
                            "Дальнейшие вызовы Wikipedia в этой пачке будут пропущены. "
                            + str(exc)
                        )

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": str(result)[:12000],
                })

            tool_limit_reached = calls >= self.max_tool_calls
            if wikipedia_unavailable:
                messages.append({
                    "role": "system",
                    "content": "Wikipedia вернула временную ошибку. Больше не вызывай инструменты; сформируй финальный ответ с указанием ограничения проверки.",
                })
            if tool_limit_reached:
                messages.append({
                    "role": "system",
                    "content": "Лимит инструментов исчерпан. Используй уже собранные данные и дай финальный ответ без новых вызовов.",
                })
            if wikipedia_unavailable or tool_limit_reached:
                break

        # One final no-tools call ensures a graceful ending if the step limit is hit.
        messages = self._trim_history(messages)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages + [{
                "role": "system",
                "content": (
                    "Wikipedia недоступна. Дай финальный ответ только на основе уже полученных результатов "
                    "и прямо укажи, что проверку завершить не удалось; не вызывай инструменты."
                    if wikipedia_unavailable
                    else "Лимит шагов или инструментов исчерпан. Дай финальный ответ только на основе уже полученных результатов; не вызывай инструменты."
                ),
            }],
            tool_choice="none",
            temperature=0.7,
            max_tokens=1400,
            extra_body={"thinking": {"type": "disabled"}},
        )
        return response.choices[0].message.content or "Лимит шагов достигнут — даже спор об ОС требует перерыва."

    def _trim_history(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep the initial instructions and newest complete tool-call batches."""
        if len(messages) <= self.max_history_messages:
            return messages

        prefix = messages[:3]
        history = messages[3:]
        batches: list[list[dict[str, Any]]] = []
        index = 0
        while index < len(history):
            start = index
            item = history[index]
            index += 1
            if item.get("role") == "assistant" and item.get("tool_calls"):
                expected = len(item["tool_calls"])
                found = 0
                while index < len(history) and found < expected:
                    if history[index].get("role") == "tool":
                        found += 1
                    index += 1
            # Keep any system guidance attached to this completed batch.
            while index < len(history) and history[index].get("role") == "system":
                index += 1
            batches.append(history[start:index])

        budget = self.max_history_messages - len(prefix)
        kept: list[list[dict[str, Any]]] = []
        used = 0
        for batch in reversed(batches):
            if used + len(batch) > budget:
                break
            kept.append(batch)
            used += len(batch)
        kept.reverse()
        return prefix + [item for batch in kept for item in batch]


def _is_wikipedia(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "wikipedia.org" or host.endswith(".wikipedia.org")
