from __future__ import annotations

import re
from urllib.parse import urlparse, unquote

import requests
from langchain_core.tools import tool

API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "LinuxWindowsDebateLab/1.0 (educational project)"}
TIMEOUT = 12


def _api(params: dict) -> dict:
    response = requests.get(API, params={"format": "json", **params},
                            headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def _is_wikipedia_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
        return host == "wikipedia.org" or host.endswith(".wikipedia.org")
    except ValueError:
        return False


def _title_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not _is_wikipedia_url(url):
        raise ValueError("Разрешены только ссылки с домена wikipedia.org")
    if not parsed.path.startswith("/wiki/"):
        raise ValueError("Ожидалась ссылка на статью Wikipedia вида /wiki/Название")
    title = unquote(parsed.path[len("/wiki/"):]).replace("_", " ").strip()
    if not title or ":" in title.split("/", 1)[0]:
        raise ValueError("Ссылка не похожа на обычную страницу статьи Wikipedia")
    return title


@tool
def search_wikipedia(query: str) -> str:
    """Ищет в англоязычной Википедии статьи по утверждению пользователя о Linux или по аргументам о Windows. Возвращает заголовки, выдержки и ссылки."""
    data = _api({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 5,
        "srnamespace": 0,
    })
    results = data.get("query", {}).get("search", [])
    if not results:
        return f"В Wikipedia не найдено страниц по запросу: {query!r}. Это не доказывает ложность утверждения."
    lines = []
    for item in results:
        title = item["title"]
        url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
        snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
        lines.append(f"- {title}\n  URL: {url}\n  Фрагмент: {snippet}")
    return "\n".join(lines)


@tool
def read_wikipedia_page(url: str) -> str:
    """Читает страницу Wikipedia по ссылке пользователя. Разрешены только домены wikipedia.org; прочие ссылки отклоняются."""
    title = _title_from_url(url)
    data = _api({
        "action": "query",
        "prop": "extracts|info",
        "explaintext": 1,
        "exsectionformat": "plain",
        "inprop": "url",
        "redirects": 1,
        "titles": title,
    })
    pages = data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    if "missing" in page:
        return f"Страница не найдена: {url}"
    extract = page.get("extract", "")[:9000]
    return (
        f"Заголовок: {page.get('title', title)}\n"
        f"Канонический URL: {page.get('fullurl', url)}\n"
        f"Текст страницы (начало, до 9000 символов):\n{extract}"
    )


@tool
def search_windows_wikipedia(query: str) -> str:
    """Ищет в Wikipedia материалы о возможностях Microsoft Windows, которые можно сопоставить с подтверждённым преимуществом Linux."""
    return search_wikipedia.invoke({"query": f"Microsoft Windows {query}"})
