from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool
from trafilatura import extract

SEARCH_ENDPOINT = "https://duckduckgo.com/html/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
DEFAULT_TOP_K = 5
FETCH_TIMEOUT_SECONDS = 10.0
CONTENT_PREVIEW_CHARS = 600


@dataclass
class WebResult:
    title: str
    url: str
    snippet: str | None = None
    preview: str | None = None


def normalize_result_url(href: str) -> str:
    """
    DuckDuckGo wraps outbound links with /l/?uddg=<encoded_url>.
    Decode those wrappers so downstream fetches hit the target domain.
    """
    absolute = urljoin(SEARCH_ENDPOINT, href)
    parsed = urlparse(absolute)
    if parsed.netloc.endswith("duckduckgo.com"):
        uddg_values = parse_qs(parsed.query).get("uddg")
        target = uddg_values[0] if uddg_values else None
        if target:
            decoded = unquote(target)
            if decoded:
                return decoded
    return absolute


def search_duckduckgo(query: str, limit: int) -> List[WebResult]:
    params = {"q": query, "ia": "web"}
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(
        headers=headers,
        timeout=httpx.Timeout(FETCH_TIMEOUT_SECONDS),
        follow_redirects=True,
    ) as client:
        response = client.get(SEARCH_ENDPOINT, params=params)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        results: List[WebResult] = []
        for result in soup.select("div.result"):
            if len(results) >= limit:
                break
            link = result.select_one("a.result__a")
            if not link or not link.text:
                continue
            href = link.get("href")
            if not href:
                continue
            absolute_url = normalize_result_url(href)
            snippet_tag = result.select_one("a.result__snippet, div.result__snippet")
            snippet_text = snippet_tag.get_text(" ", strip=True) if snippet_tag else None
            results.append(WebResult(title=link.get_text(" ", strip=True), url=absolute_url, snippet=snippet_text))

    return results


def fetch_preview(url: str) -> str | None:
    headers = {"User-Agent": USER_AGENT}
    try:
        with httpx.Client(
            headers=headers,
            timeout=httpx.Timeout(FETCH_TIMEOUT_SECONDS),
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
    except Exception:
        return None

    text = None
    try:
        text = extract(response.text, url=url)
    except Exception:
        text = None
    if not text:
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
        text = paragraphs or soup.get_text(" ", strip=True)

    if not text:
        return None

    normalized = " ".join(text.split())
    if len(normalized) > CONTENT_PREVIEW_CHARS:
        normalized = normalized[: CONTENT_PREVIEW_CHARS].rstrip() + "…"
    return normalized


def format_results(results: Iterable[WebResult]) -> str:
    lines: List[str] = []
    for idx, item in enumerate(results, start=1):
        header = f"{idx}. {item.title} ({item.url})"
        lines.append(header)
        if item.snippet:
            lines.append(item.snippet)
        if item.preview:
            lines.append(item.preview)
        lines.append("")
    return "\n".join(lines).strip()


@tool("web")
def web_tool(query: str, top_k: int = DEFAULT_TOP_K) -> str:
    """
    Search the public web for recent information and retrieve content snippets.

    The tool returns a numbered list with title, URL, search snippet, and a short
    preview extracted from the landing page when possible.
    """
    if not query or not query.strip():
        return "Please provide a search query."

    sanitized_query = query.strip()

    try:
        search_results = search_duckduckgo(sanitized_query, top_k)
    except Exception as exc:
        return f"Web search error: {exc}"

    if not search_results:
        return "No search results found."

    for result in search_results:
        preview = fetch_preview(result.url)
        if preview:
            result.preview = preview

    return format_results(search_results)