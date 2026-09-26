#!/usr/bin/env python3
"""Check migration coverage, localized body images, and generated routes."""

from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    posts = [row for row in read_csv(ROOT / "migration/posts.csv") if row.get("status") == "ok"]
    categories = read_csv(ROOT / "migration/categories.csv")
    errors: list[str] = []
    post_ids = {row["id"] for row in posts}
    markdown_ids = {path.stem for path in (ROOT / "src/content/posts").glob("*.md")}
    backup_ids = {path.stem for path in (ROOT / "backup/html").glob("*.html")}
    if markdown_ids != post_ids:
        errors.append(f"Markdown coverage differs: {len(markdown_ids)} files for {len(post_ids)} inventory posts")
    if backup_ids != post_ids:
        errors.append(f"HTML backup coverage differs: {len(backup_ids)} files for {len(post_ids)} inventory posts")

    localized_references: set[str] = set()
    remote_images: list[str] = []
    for post_id in post_ids:
        markdown = ROOT / "src/content/posts" / f"{post_id}.md"
        if not markdown.is_file():
            continue
        body = markdown.read_text(encoding="utf-8")
        for url in re.findall(r"(?:!\[[^\]]*\]\(|<img[^>]+src=[\"'])([^)\"']+)", body, re.IGNORECASE):
            if url.startswith("/images/"):
                localized_references.add(url)
                if not (ROOT / "public" / url.lstrip("/")).is_file():
                    errors.append(f"Missing local asset in post {post_id}: {url}")
            elif url.startswith(("http://", "https://")):
                remote_images.append(f"{post_id}: {url}")

    conversion_path = ROOT / "migration/conversion-report.json"
    conversion = json.loads(conversion_path.read_text(encoding="utf-8")) if conversion_path.exists() else {}
    if conversion.get("errors"):
        errors.append(f"Conversion report contains {len(conversion['errors'])} errors")
    if conversion.get("posts_generated") != len(posts):
        errors.append("Conversion report post count does not match inventory")

    dist = ROOT / "dist"
    if not dist.is_dir():
        errors.append("No dist/ directory; build the Astro site before route verification")
    else:
        for post_id in post_ids:
            route = dist / f"{post_id}.html"
            if not route.is_file():
                errors.append(f"Missing generated post route: /{post_id}")
                continue
            html = route.read_text(encoding="utf-8", errors="replace")
            canonical = f'<link rel="canonical" href="https://blog.msalt.net/{post_id}"'
            if canonical not in html:
                errors.append(f"Incorrect canonical URL for /{post_id}")
            if re.search(r"<script[^>]+src=[\"'][^\"']*(?:tistory|kakaocdn)", html, re.IGNORECASE):
                errors.append(f"Tistory runtime script remains on /{post_id}")

        try:
            sitemap = ET.parse(dist / "sitemap.xml").getroot()
            sitemap_urls = {node.text for node in sitemap.findall(".//{*}loc")}
            expected_post_urls = {f"https://blog.msalt.net/{post_id}" for post_id in post_ids}
            if not expected_post_urls.issubset(sitemap_urls):
                errors.append(f"Sitemap is missing {len(expected_post_urls - sitemap_urls)} post URLs")
            if len(sitemap_urls) != 1 + len(categories) + len({tag for row in posts for tag in json.loads(row.get("tags") or "[]")}) + len(posts):
                errors.append(f"Sitemap URL count looks wrong: {len(sitemap_urls)}")
        except (OSError, ET.ParseError) as exc:
            errors.append(f"Sitemap is missing or invalid XML: {exc}")

        try:
            feed = ET.parse(dist / "rss").getroot()
            feed_items = feed.findall("./channel/item")
            if not feed_items or len(feed_items) > 50:
                errors.append(f"RSS item count is unexpected: {len(feed_items)}")
        except (OSError, ET.ParseError) as exc:
            errors.append(f"RSS is missing or invalid XML: {exc}")

        tag_count = len({tag for row in posts for tag in json.loads(row.get("tags") or "[]")})
        generated_tag_routes = len(list((dist / "tag").glob("*.html"))) if (dist / "tag").is_dir() else 0
        if generated_tag_routes != tag_count:
            errors.append(f"Generated tag route count differs: {generated_tag_routes} files for {tag_count} tags")

    print(f"Inventory posts: {len(posts)}; categories: {len(categories)}")
    print(f"HTML backups: {len(backup_ids)}; Markdown posts: {len(markdown_ids)}")
    print(f"Localized image references: {len(localized_references)}; remote image references: {len(remote_images)}")
    if (ROOT / "dist").is_dir():
        print(f"Static output: {len(list((ROOT / 'dist').glob('*.html')))} root HTML pages; tag routes: {len(list((ROOT / 'dist/tag').glob('*.html')))}")
    if remote_images:
        print(f"Remote image references requiring review: {len(remote_images)}")
        for value in remote_images[:20]:
            print(f"  {value}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Migration data coverage: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
