#!/usr/bin/env python3
"""Discover Tistory post URLs and write a deterministic migration inventory."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, unquote, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen


POST_PATH = re.compile(r"^/(\d+)/?$")
USER_AGENT = "msalt-blog-migration-inventory/1.0 (+https://blog.msalt.net/)"
MAX_PAGE_BYTES = 20 * 1024 * 1024


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.metas: dict[str, str] = {}
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "a" and values.get("href"):
            self._anchor_href = values["href"]
            self._anchor_text = []
        elif tag.lower() == "meta":
            key = values.get("property") or values.get("name")
            content = values.get("content")
            if key and content:
                self.metas[key.lower()] = content.strip()

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._anchor_href is not None:
            text = " ".join(" ".join(self._anchor_text).split())
            self.links.append((self._anchor_href, text))
            self._anchor_href = None
            self._anchor_text = []


@dataclass(frozen=True)
class Post:
    id: str
    url: str
    title: str
    date: str
    category: str
    tags: str
    description: str
    comments_count: str
    status: str
    error: str


def canonicalize(url: str) -> str:
    parsed = urlparse(url)
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)), doseq=True)
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, ""))


def fetch(url: str, timeout: float) -> tuple[str, bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"})
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get_content_type()
        data = response.read(MAX_PAGE_BYTES + 1)
        if len(data) > MAX_PAGE_BYTES:
            raise ValueError(f"response exceeds {MAX_PAGE_BYTES} bytes")
        charset = response.headers.get_content_charset() or "utf-8"
        return data.decode(charset, errors="replace"), data, content_type


def same_site(url: str, host: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == host.lower()


def classify_path(path: str) -> str:
    if path in {"", "/"}:
        return "home"
    if POST_PATH.match(path):
        return "post"
    if path.startswith("/category/") or path == "/category":
        return "category"
    if path.startswith("/tag/") or path == "/tag":
        return "tag"
    if path.startswith("/archive/"):
        return "archive"
    if path.startswith("/m/"):
        return "mobile"
    if path.startswith("/search/") or path == "/search":
        return "search"
    if path.lower() in {"/rss", "/atom.xml", "/sitemap.xml", "/robots.txt"}:
        return "feed-or-technical"
    return "other"


def should_visit(url: str, host: str) -> bool:
    parsed = urlparse(url)
    if not same_site(url, host):
        return False
    kind = classify_path(parsed.path)
    if kind == "post":
        return True
    if kind == "home":
        # This Tistory theme exposes hundreds of one-post home pages; category
        # listings provide a much smaller complete index of the same posts.
        return not parsed.query
    if kind in {"category", "tag", "archive", "mobile", "search"}:
        return not parsed.query or all(k == "page" for k, _ in parse_qsl(parsed.query))
    return False


def category_name(path: str) -> str:
    prefix = "/category/"
    if path.startswith(prefix):
        return unquote(path[len(prefix):]).strip("/")
    return ""


def category_from_links(links: list[tuple[str, str]], page_url: str, host: str) -> str:
    for href, text in links:
        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)
        if same_site(absolute, host) and parsed.path.startswith("/category/"):
            name = category_name(parsed.path)
            if name and name not in {"category"}:
                return name
    return ""


def inspect_post(item: tuple[str, str, str, float]) -> Post:
    url, post_id, host, timeout = item
    try:
        html, _, content_type = fetch(url, timeout)
        if "html" not in content_type:
            raise ValueError(f"expected HTML, got {content_type}")
        parser = LinkParser()
        parser.feed(html)
        title = parser.metas.get("og:title") or parser.metas.get("twitter:title") or ""
        if not title:
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""
        date = next((value for key, value in parser.metas.items() if key in {"article:published_time", "date", "pubdate"}), "")
        category = category_from_links(parser.links, url, host)
        tag_values = {unquote(urlparse(urljoin(url, href)).path[len("/tag/"):]).strip("/") for href, _ in parser.links if urlparse(urljoin(url, href)).path.startswith("/tag/")}
        tag_values.update(value for key, value in parser.metas.items() if key in {"article:tag", "tag"} and value)
        comments_match = re.search(rf'id="commentCount{re.escape(post_id)}_0"[^>]*>(\d+)', html, re.I)
        comments_count = comments_match.group(1) if comments_match else ""
        description = parser.metas.get("description") or parser.metas.get("og:description") or ""
        return Post(post_id, url, title, date, category, json.dumps(sorted(tag_values), ensure_ascii=False), description, comments_count, "ok", "")
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        return Post(post_id, url, "", "", "", "[]", "", "", "error", f"{type(exc).__name__}: {exc}")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> int:
    start = canonicalize(args.base_url.rstrip("/") + "/")
    host = urlparse(start).netloc
    queue: deque[str] = deque([start])
    seen_pages: set[str] = set()
    post_urls: dict[str, str] = {}
    url_rows: dict[str, dict[str, str]] = {}
    categories: dict[str, str] = {}
    tags: dict[str, str] = {}
    errors: list[dict[str, str]] = []

    while queue:
        url = queue.popleft()
        if url in seen_pages:
            continue
        seen_pages.add(url)
        kind = classify_path(urlparse(url).path)
        if kind == "post":
            url_rows[url] = {"url": url, "type": kind, "status": "discovered", "title": ""}
            match = POST_PATH.match(urlparse(url).path)
            if match:
                post_urls.setdefault(match.group(1), url)
            continue
        try:
            html, _, content_type = fetch(url, args.timeout)
            if "html" not in content_type:
                url_rows[url] = {"url": url, "type": "feed-or-technical", "status": "ok", "title": ""}
                continue
            parser = LinkParser()
            parser.feed(html)
            page_title = parser.metas.get("og:title", "")
            url_rows[url] = {"url": url, "type": kind, "status": "ok", "title": page_title}
            for href, text in parser.links:
                absolute = canonicalize(urljoin(url, href))
                if not same_site(absolute, host):
                    continue
                parsed = urlparse(absolute)
                if parsed.path == "/" and parse_qsl(parsed.query) and all(key == "page" for key, _ in parse_qsl(parsed.query)):
                    url_rows.setdefault(absolute, {"url": absolute, "type": "homepage-pagination", "status": "discovered", "title": ""})
                match = POST_PATH.match(parsed.path)
                if match:
                    post_urls.setdefault(match.group(1), urlunparse((parsed.scheme, parsed.netloc, f"/{match.group(1)}", "", "", "")))
                if parsed.path.startswith("/category/"):
                    name = category_name(parsed.path)
                    if name:
                        categories[name] = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
                if parsed.path.startswith("/tag/"):
                    name = unquote(parsed.path[len("/tag/"):]).strip("/")
                    if name:
                        tags[name] = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
                if should_visit(absolute, host) and absolute not in seen_pages:
                    queue.append(absolute)
            if args.delay:
                time.sleep(args.delay)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            row = {"url": url, "type": kind, "status": "error", "title": ""}
            url_rows[url] = row
            errors.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})

    jobs = [(url, post_id, host, args.timeout) for post_id, url in sorted(post_urls.items(), key=lambda item: int(item[0]))]
    posts: list[Post] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(inspect_post, job): job[1] for job in jobs}
        for future in as_completed(futures):
            post = future.result()
            posts.append(post)
            url_rows[post.url] = {"url": post.url, "type": "post", "status": post.status, "title": post.title}
            if post.status == "error":
                errors.append({"url": post.url, "error": post.error})
    posts.sort(key=lambda post: int(post.id), reverse=True)

    out = Path(args.output)
    write_csv(out / "posts.csv", list(Post.__dataclass_fields__), [asdict(post) for post in posts])
    write_csv(out / "categories.csv", ["name", "url"], [{"name": name, "url": url} for name, url in sorted(categories.items())])
    for post in posts:
        for name in json.loads(post.tags):
            tags.setdefault(name, f"https://{host}/tag/{quote(name, safe='')}")
    write_csv(out / "tags.csv", ["name", "url"], [{"name": name, "url": url} for name, url in sorted(tags.items())])
    write_csv(out / "images.csv", ["post_id", "source_url", "alt", "title", "caption"], [])
    write_csv(out / "urls.csv", ["url", "type", "status", "title"], [url_rows[url] for url in sorted(url_rows)])
    (out / "errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Pages visited: {len(seen_pages)}")
    print(f"Posts found: {len(posts)} ({sum(post.status == 'ok' for post in posts)} fetched successfully)")
    print(f"Categories found: {len(categories)}")
    print(f"Errors: {len(errors)}; details: {out / 'errors.json'}")
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://blog.msalt.net/", help="Tistory site root")
    parser.add_argument("--output", default="migration", help="Inventory output directory")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between index-page requests")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent post metadata requests")
    args = parser.parse_args()
    try:
        return run(args)
    except KeyboardInterrupt:
        print("Interrupted; no successful inventory has been declared.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
