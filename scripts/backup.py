#!/usr/bin/env python3
"""Back up original post HTML and referenced images from an inventory CSV."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen


USER_AGENT = "msalt-blog-migration-backup/1.0 (+https://blog.msalt.net/)"
MAX_HTML_BYTES = 30 * 1024 * 1024
MAX_IMAGE_BYTES = 80 * 1024 * 1024
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[dict[str, str]] = []
        self._current_image: dict[str, str] | None = None
        self._capture_caption = False
        self._caption: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "img":
            source = values.get("src") or values.get("data-src") or values.get("data-original") or values.get("data-lazy-src")
            if source:
                self._current_image = {
                    "source_url": source.strip(),
                    "alt": values.get("alt", "").strip(),
                    "title": values.get("title", "").strip(),
                    "caption": "",
                }
                self.images.append(self._current_image)
        elif tag.lower() in {"figcaption", "caption"}:
            self._capture_caption = True
            self._caption = []

    def handle_data(self, data: str) -> None:
        if self._capture_caption:
            self._caption.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"figcaption", "caption"} and self._capture_caption:
            caption = " ".join(" ".join(self._caption).split())
            if self._current_image is not None:
                self._current_image["caption"] = caption
            self._capture_caption = False
            self._caption = []
        elif tag.lower() == "img":
            self._current_image = None


@dataclass
class BackupResult:
    id: str
    url: str
    html_path: str
    html_status: str
    image_count: int
    images_downloaded: int
    errors: list[str]
    images: list[dict[str, str]]


def fetch(url: str, timeout: float, limit: int) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(request, timeout=timeout) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError(f"response exceeds {limit} bytes")
        return data, response.headers.get("Content-Type", "")


def safe_extension(url: str, content_type: str) -> str:
    suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        return suffix
    mime = content_type.split(";", 1)[0].strip().lower()
    known = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp", "image/svg+xml": ".svg", "image/avif": ".avif"}
    return known.get(mime, ".bin")


def download_post(row: dict[str, str], root: Path, timeout: float, delay: float, prior_images: dict[tuple[str, str], dict[str, str]]) -> BackupResult:
    post_id = row["id"].strip()
    url = row["url"].strip()
    errors: list[str] = []
    post_dir = root / "images" / post_id
    html_path = root / "html" / f"{post_id}.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    post_dir.mkdir(parents=True, exist_ok=True)
    try:
        if html_path.exists():
            html = html_path.read_bytes()
        else:
            html, _ = fetch(url, timeout, MAX_HTML_BYTES)
            html_path.write_bytes(html)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        return BackupResult(post_id, url, str(html_path), "error", 0, 0, [f"HTML: {type(exc).__name__}: {exc}"], [])

    parser = AssetParser()
    parser.feed(html.decode("utf-8", errors="replace"))
    image_map: list[dict[str, str]] = []
    downloaded = 0
    unique_images: dict[str, dict[str, str]] = {}
    for image in parser.images:
        absolute = urljoin(url, image["source_url"])
        if urlparse(absolute).scheme not in {"https", "http"}:
            continue
        unique_images.setdefault(absolute, image)

    for index, (source_url, metadata) in enumerate(unique_images.items(), start=1):
        if delay:
            time.sleep(delay)
        try:
            previous = prior_images.get((post_id, source_url), {})
            old_path = Path(previous.get("backup_path", "")) if previous.get("backup_path") else None
            if old_path and old_path.exists():
                filename = old_path.name
                backup_path = old_path
            else:
                content, content_type = fetch(source_url, timeout, MAX_IMAGE_BYTES)
                filename = f"{index:03d}{safe_extension(source_url, content_type)}"
                backup_path = post_dir / filename
                backup_path.write_bytes(content)
            downloaded += 1
            image_map.append({**metadata, "source_url": source_url, "backup_path": str(backup_path)})
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            errors.append(f"Image {source_url}: {type(exc).__name__}: {exc}")
            image_map.append({**metadata, "source_url": source_url, "backup_path": "", "error": errors[-1]})

    return BackupResult(post_id, url, str(html_path), "ok", len(unique_images), downloaded, errors, image_map)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", default="migration/posts.csv")
    parser.add_argument("--backup", default="backup")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--delay", type=float, default=0.1, help="Delay between downloads per post")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    with Path(args.inventory).open(newline="", encoding="utf-8-sig") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("id") and row.get("url")]
    root = Path(args.backup)
    root.mkdir(parents=True, exist_ok=True)
    results: list[BackupResult] = []
    image_rows: list[dict[str, str]] = []
    error_rows: list[dict[str, str]] = []
    prior_images: dict[tuple[str, str], dict[str, str]] = {}
    image_index = Path("migration/images.csv")
    if image_index.exists():
        with image_index.open(newline="", encoding="utf-8-sig") as handle:
            prior_images = {(row.get("post_id", ""), row.get("source_url", "")): row for row in csv.DictReader(handle)}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download_post, row, root, args.timeout, args.delay, prior_images): row["id"] for row in rows}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(f"/{result.id}: HTML {result.html_status}, images {result.images_downloaded}/{result.image_count}")
            image_rows.extend({"post_id": result.id, **image} for image in result.images)
            if result.errors:
                error_rows.extend({"post_id": result.id, "error": error} for error in result.errors)
    results.sort(key=lambda result: int(result.id), reverse=True)

    meta_dir = root / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "posts.json").write_text(json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (meta_dir / "errors.json").write_text(json.dumps(error_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    migration_dir = Path("migration")
    migration_dir.mkdir(parents=True, exist_ok=True)
    image_columns = ["post_id", "source_url", "alt", "title", "caption", "backup_path", "error"]
    with (migration_dir / "images.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=image_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(image_rows)
    failed = sum(result.html_status != "ok" or bool(result.errors) for result in results)
    print(f"Posts: {len(results)}; download errors: {failed}; details: {meta_dir / 'errors.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
