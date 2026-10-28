from __future__ import annotations

import os
import re
import time
from html import unescape
from urllib.parse import urlparse, unquote
from urllib.parse import quote, urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from langchain_core.tools import tool

API = "https://en.wikipedia.org/w/api.php"
DEFAULT_CONTACT = "https://github.com/katessss/git_for_labs"
TIMEOUT = (5, 20)


def _new_session() -> requests.Session:
    retry = Retry(
        total=0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers.update({"User-Agent": _user_agent()})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _user_agent() -> str:
    # Wikimedia requires a descriptive client identity with contact details.
    contact = os.getenv("WIKIPEDIA_CONTACT", DEFAULT_CONTACT)
    return f"LinuxWindowsDebateLab/1.1 ({contact})"


_SESSION = _new_session()
_API_UNAVAILABLE_UNTIL = 0.0


def _api(params: dict) -> dict:
    global _API_UNAVAILABLE_UNTIL
    if time.monotonic() < _API_UNAVAILABLE_UNTIL:
        raise requests.RequestException("Wikipedia Action API temporarily unavailable")
    _SESSION.headers["User-Agent"] = _user_agent()
    response = _SESSION.get(
        API,
        params={"format": "json", "maxlag": 5, **params},
        timeout=TIMEOUT,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        if response.status_code in (429, 500, 502, 503, 504):
            if response.status_code == 503:
                _API_UNAVAILABLE_UNTIL = time.monotonic() + 60
            retry_after = response.headers.get("Retry-After", "absent")
            squid_error = response.headers.get("X-Squid-Error", "absent")
            body = re.sub(r"\s+", " ", response.text[:300]).strip()
            raise requests.HTTPError(
                f"Wikipedia HTTP {response.status_code}; "
                f"Retry-After={retry_after}; X-Squid-Error={squid_error}; "
                f"response body={body or '[empty]'}",
                response=response,
            ) from exc
        raise
    data = response.json()
    # MediaWiki can return application-level errors (for example, maxlag)
    # inside an HTTP 200 response. Surface those as errors rather than passing
    # an empty result to the model as if the search succeeded.
    if "error" in data:
        error = data["error"]
        raise requests.RequestException(
            f"Wikipedia API error {error.get('code', 'unknown')}: "
            f"{error.get('info', 'no details')}"
        )
    return data


def _search_page(query: str) -> list[dict[str, str]]:
    """Use Wikipedia's web search when its Action API is unavailable."""
    response = _SESSION.get(
        "https://en.wikipedia.org/w/index.php",
        params={"search": query, "ns0": 1},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    matches = re.findall(
        r'<div class="mw-search-result-heading">\s*<a href="([^"]+)" title="([^"]+)"[^>]*>.*?</a>.*?</div>\s*<div class="searchresult">(.*?)</div>',
        response.text,
        re.DOTALL,
    )
    return [
        {
            "title": unescape(title),
            "url": urljoin("https://en.wikipedia.org", unescape(href)),
            "snippet": unescape(re.sub(r"<[^>]+>", "", snippet)),
        }
        for href, title, snippet in matches[:5]
        if href.startswith("/wiki/")
    ]


def _page_summary(title: str) -> dict:
    response = _SESSION.get(
        "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(title.replace(" ", "_"), safe=""),
        timeout=TIMEOUT,
    )
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
    try:
        data = _api({
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 5,
            "srnamespace": 0,
        })
        results = data.get("query", {}).get("search", [])
    except requests.RequestException:
        results = _search_page(query)
    if not results:
        return f"В Wikipedia не найдено страниц по запросу: {query!r}. Это не доказывает ложность утверждения."
    lines = []
    for item in results:
        title = item["title"]
        url = item.get("url") or "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
        snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
        lines.append(f"- {title}\n  URL: {url}\n  Фрагмент: {snippet}")
    return "\n".join(lines)


@tool
def read_wikipedia_page(url: str) -> str:
    """Читает страницу Wikipedia по ссылке пользователя. Разрешены только домены wikipedia.org; прочие ссылки отклоняются."""
    title = _title_from_url(url)
    try:
        data = _api({
            "action": "query",
            "prop": "extracts|info",
            "explaintext": 1,
            "exsectionformat": "plain",
            "inprop": "url",
            "redirects": 1,
            "titles": title,
        })
    except requests.RequestException:
        summary = _page_summary(title)
        return (
            f"Заголовок: {summary.get('title', title)}\n"
            f"Канонический URL: {summary.get('content_urls', {}).get('desktop', {}).get('page', url)}\n"
            f"Краткое содержание Wikipedia:\n{summary.get('extract', '')}"
        )
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
