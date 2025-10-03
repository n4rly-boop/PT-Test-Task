import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set, Tuple

import httpx
from bs4 import BeautifulSoup
from contextlib import contextmanager
import trafilatura


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


@dataclass
class Page:
    url: str
    title: str
    text: str


def fetch(url: str, timeout: float = 20.0, retries: int = 2, cookies: Optional[str] = None) -> Optional[str]:
    last_err: Optional[Exception] = None
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if cookies:
        headers["Cookie"] = cookies
    for attempt in range(retries + 1):
        try:
            with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
                resp = client.get(url)
                if resp.status_code == 200 and resp.text:
                    return resp.text
                last_err = RuntimeError(f"HTTP {resp.status_code}")
        except Exception as e:
            last_err = e
        time.sleep(0.8 * (attempt + 1))
    print(f"Failed to fetch {url}: {last_err}", file=sys.stderr)
    return None


def clean_text(html: str) -> Tuple[str, str]:
    soup = BeautifulSoup(html, "html5lib")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    main = soup.find("main") or soup.find("article") or soup.body
    text = main.get_text("\n", strip=True) if main else soup.get_text("\n", strip=True)
    text = re.sub(r"\n{2,}", "\n\n", text)
    if not text or len(text) < 200:
        # Fallback to trafilatura extraction
        try:
            extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
            if extracted and len(extracted) > len(text):
                text = extracted
        except Exception:
            pass
    return title, text


def get_base_dir(url: str) -> str:
    # For PT help, keep everything under .../projects/<proj>/<ver>/help
    m = re.match(r"^(https?://[^/]+/.*/projects/[^/]+/[^/]+/help)", url)
    if m:
        return m.group(1)
    # Fallback to site root
    m2 = re.match(r"^(https?://[^/]+)", url)
    return m2.group(1) if m2 else url


def should_follow(base_dir: str, url: str) -> bool:
    return url.startswith(base_dir)


def extract_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html5lib")
    links: Set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("http"):
            links.add(href)
        elif href.startswith("/"):
            # Same host absolute path
            root = re.match(r"^(https?://[^/]+)/", base_url)
            if root:
                links.add(root.group(1) + href)
    return sorted(links)


def crawl(start_url: str, same_path_only: bool = True, max_pages: int = 15, cookies: Optional[str] = None, render: bool = False) -> List[Page]:
    base_dir = get_base_dir(start_url.rstrip("/"))
    if render:
        return crawl_rendered(start_url, same_path_only=same_path_only, max_pages=max_pages, cookies=cookies)
    html = fetch(start_url, cookies=cookies)
    if not html:
        return []
    title, text = clean_text(html)
    pages: List[Page] = [Page(url=start_url, title=title, text=text)]

    if not same_path_only and max_pages <= 1:
        return pages

    links = extract_links(html, start_url)
    seen: Set[str] = {start_url}
    for link in links:
        if same_path_only and not should_follow(base_dir, link):
            continue
        if link in seen:
            continue
        if len(pages) >= max_pages:
            break
        seen.add(link)
        html2 = fetch(link, cookies=cookies)
        if not html2:
            continue
        if render:
            rendered2 = render_js(link, cookies=cookies)
            if rendered2:
                html2 = rendered2
        t, txt = clean_text(html2)
        pages.append(Page(url=link, title=t, text=txt))
    return pages


def save_jsonl(pages: List[Page], output_path: str, chunk: bool = True) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for p in pages:
            rec = {"url": p.url, "title": p.title, "text": p.text}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


@contextmanager
def _playwright_context():
    from playwright.sync_api import sync_playwright  # type: ignore
    p = sync_playwright().start()
    try:
        yield p
    finally:
        p.stop()


def render_js(url: str, cookies: Optional[str] = None, wait_ms: int = 2500) -> Optional[str]:
    try:
        with _playwright_context() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            if cookies:
                # naive cookie header via extra HTTP headers
                context.set_extra_http_headers({"Cookie": cookies})
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            # Give Angular app time to bootstrap and fetch content
            page.wait_for_load_state("networkidle")
            if wait_ms > 0:
                page.wait_for_timeout(wait_ms)

            # Try to expand common accordion/dropdown patterns
            try:
                # Open all <details> elements
                page.evaluate(
                    """
                    document.querySelectorAll('details:not([open])').forEach(d => d.setAttribute('open','true'));
                    """
                )
            except Exception:
                pass

            # Click any aria-expanded toggles that are closed
            try:
                headers = page.locator('[aria-expanded="false"]')
                count = headers.count()
                for i in range(min(count, 200)):
                    try:
                        headers.nth(i).click(timeout=500)
                    except Exception:
                        continue
            except Exception:
                pass

            # Angular Material expansion panels
            try:
                mat_headers = page.locator('.mat-expansion-panel-header[aria-expanded="false"]')
                mcount = mat_headers.count()
                for i in range(min(mcount, 200)):
                    try:
                        mat_headers.nth(i).click(timeout=500)
                    except Exception:
                        continue
            except Exception:
                pass

            # Try any "Expand all" buttons by text in RU/EN
            for label in ["Развернуть всё", "Развернуть все", "Expand all", "Show more"]:
                try:
                    page.get_by_role("button", name=label).click(timeout=500)
                except Exception:
                    continue

            # Scroll to trigger lazy-load content
            try:
                for _ in range(12):
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(250)
            except Exception:
                pass

            content = page.content()
            browser.close()
            return content
    except Exception as e:
        print(f"Playwright render failed for {url}: {e}", file=sys.stderr)
        return None


def _expand_ui(page) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)
    try:
        page.evaluate("document.querySelectorAll('details:not([open])').forEach(d => d.setAttribute('open','true'));")
    except Exception:
        pass
    try:
        headers = page.locator('[aria-expanded="false"]')
        for i in range(min(headers.count(), 300)):
            try:
                headers.nth(i).click(timeout=300)
            except Exception:
                continue
    except Exception:
        pass
    try:
        mat_headers = page.locator('.mat-expansion-panel-header[aria-expanded="false"]')
        for i in range(min(mat_headers.count(), 300)):
            try:
                mat_headers.nth(i).click(timeout=300)
            except Exception:
                continue
    except Exception:
        pass
    for label in ["Развернуть всё", "Развернуть все", "Expand all", "Show more"]:
        try:
            page.get_by_role("button", name=label).click(timeout=400)
        except Exception:
            continue
    try:
        for _ in range(14):
            page.mouse.wheel(0, 5000)
            page.wait_for_timeout(200)
    except Exception:
        pass


def _extract_composed_links(page, base_url: str) -> List[str]:
    # Traverse shadow DOM to gather all anchors
    anchors = page.evaluate(
        """
        (() => {
          const out = [];
          function walk(root) {
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
            let n;
            while (n = walker.nextNode()) {
              if (n.tagName === 'A' && n.href) { out.push(n.href); }
              if (n.shadowRoot) { walk(n.shadowRoot); }
            }
          }
          walk(document);
          return out;
        })()
        """
    )
    if not anchors:
        anchors = []
    # Filter duplicates and non-http
    links = []
    seen = set()
    for href in anchors:
        if not href or not isinstance(href, str):
            continue
        if not href.startswith("http"):
            continue
        if href in seen:
            continue
        seen.add(href)
        links.append(href)
    return links


def _extract_composed_text(page) -> str:
    # Collect text including shadow DOM
    text = page.evaluate(
        """
        (() => {
          function getText(node) {
            let t = '';
            if (node.nodeType === Node.TEXT_NODE) {
              const s = node.textContent.trim();
              if (s) t += s + '\n';
            }
            if (node.shadowRoot) {
              t += getText(node.shadowRoot);
            }
            const kids = node.childNodes || [];
            for (let i = 0; i < kids.length; i++) {
              t += getText(kids[i]);
            }
            return t;
          }
          return getText(document.documentElement);
        })()
        """
    )
    return text or ""


def crawl_rendered(start_url: str, same_path_only: bool, max_pages: int, cookies: Optional[str]) -> List[Page]:
    pages: List[Page] = []
    from playwright.sync_api import sync_playwright  # type: ignore
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        if cookies:
            context.set_extra_http_headers({"Cookie": cookies})
        page = context.new_page()
        queue = [start_url]
        seen: Set[str] = set()
        base_dir = get_base_dir(start_url.rstrip('/'))
        while queue and len(pages) < max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            try:
                page.goto(url, wait_until="domcontentloaded")
                _expand_ui(page)
                title = page.title() or ''
                # Prefer cleaned HTML from rendered content for stable extraction
                rendered_html = page.content()
                t2, text2 = clean_text(rendered_html)
                text = text2 if text2 else _extract_composed_text(page)
                pages.append(Page(url=url, title=(t2 or title), text=text or ''))
                # Merge links from shadow DOM traversal and static HTML parsing
                links_dom = _extract_composed_links(page, url)
                links_html = extract_links(rendered_html, url)
                links = list({*links_dom, *links_html})
                for link in links:
                    if same_path_only and not link.startswith(base_dir):
                        continue
                    if link not in seen and link not in queue and len(queue) + len(pages) < max_pages:
                        queue.append(link)
            except Exception:
                continue
        browser.close()
    return pages


def main():
    parser = argparse.ArgumentParser(description="Parse PT Security documentation into JSONL chunks")
    parser.add_argument("--url", default="https://help.ptsecurity.com/ru-RU/projects/mp10/27.4/help/93816075")
    parser.add_argument("--out", default="data/docs/pt_doc.jsonl")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--full-site", action="store_true")
    parser.add_argument("--cookies", type=str, default=None, help="Cookie header value if needed")
    parser.add_argument("--render", action="store_true", help="Render JS via Playwright")
    args = parser.parse_args()

    pages = crawl(
        args.url,
        same_path_only=not args.full_site,
        max_pages=args.max_pages,
        cookies=args.cookies,
        render=args.render,
    )
    save_jsonl(pages, args.out, chunk=True)
    print(f"Saved {len(pages)} pages to {args.out}")


if __name__ == "__main__":
    main()

