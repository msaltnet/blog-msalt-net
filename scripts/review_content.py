#!/usr/bin/env python3
"""Compare visible source text with migrated Markdown and audit embeds/attachments."""

from __future__ import annotations

import csv
import difflib
import json
import re
import sys
import unicodedata
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from migrate import ContentExtractor


ROOT = Path(__file__).resolve().parents[1]
ATTACHMENT = re.compile(r"\.(?:zip|pdf|docx?|hwp|pptx?|xlsx?|mp4|mov|avi|m4v)(?:$|[?#])", re.IGNORECASE)
BLOCK_TAGS = {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr", "blockquote"}


class ContentAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.ignored_depth = 0
        self.ignored_tags: list[str] = []
        self.iframes: list[str] = []
        self.attachments: list[str] = []
        self.media: Counter[str] = Counter()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if self.ignored_depth:
            if tag not in {"img", "br", "hr", "source", "track", "meta", "link", "input"}:
                self.ignored_depth += 1
                self.ignored_tags.append(tag)
            return
        if tag in {"script", "style", "noscript"}:
            self.ignored_depth = 1
            self.ignored_tags = [tag]
            return
        if tag in BLOCK_TAGS:
            self.text.append("\n")
        if tag == "iframe":
            self.iframes.append(values.get("src", ""))
        if tag in {"video", "audio", "source", "object", "embed"}:
            self.media[tag] += 1
        if tag == "a":
            href = values.get("href", "")
            if ATTACHMENT.search(urlparse(href).path + ("?" + urlparse(href).query if urlparse(href).query else "")):
                self.attachments.append(href)

    def handle_endtag(self, tag: str) -> None:
        if self.ignored_depth:
            if tag in self.ignored_tags:
                self.ignored_tags.remove(tag)
                self.ignored_depth -= 1
            return
        if tag in BLOCK_TAGS:
            self.text.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.text.append(data)


def visible_text(fragment: str) -> ContentAudit:
    parsed = ContentAudit()
    parsed.feed(fragment)
    parsed.close()
    return parsed


def markdown_body(markdown: str) -> str:
    if markdown.startswith("---\n"):
        sections = markdown.split("---", 2)
        markdown = sections[2] if len(sections) == 3 else markdown
    markdown = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", markdown)
    markdown = re.sub(r"\[([^\]]*)\]\(([^)]*)\)", r"\1", markdown)
    markdown = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", markdown)
    markdown = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", markdown)
    markdown = re.sub(r"(?m)^\s{0,3}>+\s?", "", markdown)
    markdown = re.sub(r"(?m)^\s*(?:[-+*]|\d+[.)])\s+", "", markdown)
    markdown = re.sub(r"(?m)^\s*(?:```+|~~~+)[^\n]*\n?", "", markdown)
    markdown = re.sub(r"(?<!\\)(\*\*|__|~~|`)", "", markdown)
    markdown = re.sub(r"(?<!\\)(?<!\w)(\*|_)([^*_\n]+)\1(?!\w)", r"\2", markdown)
    return markdown


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, str(ROOT / "scripts"))
    with (ROOT / "migration/posts.csv").open(newline="", encoding="utf-8-sig") as handle:
        posts = [row for row in csv.DictReader(handle) if row.get("status") == "ok"]

    results: list[dict[str, object]] = []
    source_iframes: Counter[str] = Counter()
    migrated_iframes: Counter[str] = Counter()
    source_media: Counter[str] = Counter()
    migrated_media: Counter[str] = Counter()
    attachment_domains: Counter[str] = Counter()
    text_by_id: dict[str, tuple[str, str]] = {}
    for post in posts:
        post_id = post["id"]
        original = (ROOT / "backup/html" / f"{post_id}.html").read_text(encoding="utf-8", errors="replace")
        extractor = ContentExtractor()
        original_fragment = extractor.extract(original)
        source_audit = visible_text(original_fragment)
        source_iframes.update(urlparse(url).netloc for url in source_audit.iframes)
        source_media.update(source_audit.media)
        for link in source_audit.attachments:
            attachment_domains[urlparse(link).netloc or "relative"] += 1

        markdown = (ROOT / "src/content/posts" / f"{post_id}.md").read_text(encoding="utf-8")
        converted_fragment = markdown_body(markdown)
        migrated_audit = visible_text(converted_fragment)
        migrated_iframes.update(urlparse(url).netloc for url in migrated_audit.iframes)
        migrated_media.update(migrated_audit.media)

        expected = normalize("".join(source_audit.text))
        actual = normalize("".join(migrated_audit.text))
        text_by_id[post_id] = (expected, actual)
        similarity = difflib.SequenceMatcher(None, expected, actual, autojunk=True).ratio() if expected or actual else 1.0
        results.append({
            "id": post_id,
            "title": post.get("title", ""),
            "source_chars": len(expected),
            "markdown_chars": len(actual),
            "text_similarity": round(similarity, 5),
            "source_images": len(re.findall(r"<img\b", original_fragment, re.IGNORECASE)),
            "markdown_local_images": len(re.findall(r"/images/posts/", markdown)),
        })

    low_similarity = [item for item in results if item["text_similarity"] < 0.97]
    for item in low_similarity:
        expected, actual = text_by_id[str(item["id"])]
        matcher = difflib.SequenceMatcher(None, expected, actual, autojunk=True)
        differences = []
        for operation, source_start, source_end, migrated_start, migrated_end in matcher.get_opcodes():
            if operation == "equal":
                continue
            source_excerpt = expected[source_start:source_end].strip()[:160]
            migrated_excerpt = actual[migrated_start:migrated_end].strip()[:160]
            if source_excerpt or migrated_excerpt:
                differences.append({"source_only": source_excerpt, "markdown_only": migrated_excerpt})
            if len(differences) == 5:
                break
        item["text_diff_samples"] = differences
    report = {
        "posts_reviewed": len(results),
        "text_similarity_threshold": 0.97,
        "below_threshold": low_similarity,
        "source_iframes_by_host": dict(source_iframes),
        "markdown_iframes_by_host": dict(migrated_iframes),
        "source_media_elements": dict(source_media),
        "markdown_media_elements": dict(migrated_media),
        "downloadable_attachment_links_by_host": dict(attachment_domains),
    }
    output = ROOT / "migration/content-review.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Posts compared: {len(results)}")
    print(f"Posts below 97% visible-text similarity: {len(low_similarity)}")
    for item in sorted(low_similarity, key=lambda value: value["text_similarity"]):
        print(f"  {item['id']}: {item['text_similarity']:.1%} ({item['source_chars']} source chars, {item['markdown_chars']} Markdown chars) {item['title']}")
        for difference in item.get("text_diff_samples", []):
            print(f"    source only: {difference['source_only']!r}")
            print(f"    Markdown only: {difference['markdown_only']!r}")
    print(f"Source iframes by host: {dict(source_iframes)}")
    print(f"Migrated iframes by host: {dict(migrated_iframes)}")
    print(f"Downloadable attachment links by host: {dict(attachment_domains)}")
    print(f"Report: {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
