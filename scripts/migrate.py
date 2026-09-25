#!/usr/bin/env python3
"""Convert saved Tistory HTML backups into Markdown posts and local assets."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path


VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
RAW_TAGS = {"table", "iframe", "video", "audio", "object", "svg", "math", "pre", "blockquote"}
DROP_TAGS = {"script", "style"}


class ContentExtractor(HTMLParser):
    """Capture the full contents_style subtree without normalizing source markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.depth = 0
        self.capturing = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if not self.capturing and tag.lower() == "div" and "contents_style" in values.get("class", "").split():
            self.capturing = True
            self.depth = 1
            self.parts.append(self.get_starttag_text() or "<div>")
            return
        if self.capturing:
            self.parts.append(self.get_starttag_text() or f"<{tag}>")
            if tag.lower() not in VOID_TAGS:
                self.depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.capturing:
            self.parts.append(self.get_starttag_text() or f"<{tag}/>")

    def handle_endtag(self, tag: str) -> None:
        if self.capturing:
            self.parts.append(f"</{tag}>")
            if tag.lower() not in VOID_TAGS:
                self.depth -= 1
                if self.depth <= 0:
                    self.capturing = False

    def handle_data(self, data: str) -> None:
        if self.capturing:
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self.capturing:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self.capturing:
            self.parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        if self.capturing:
            self.parts.append(f"<!--{data}-->")

    def extract(self, source: str) -> str:
        self.feed(source)
        self.close()
        return "".join(self.parts)


class MarkdownConverter(HTMLParser):
    def __init__(self, post_id: str, image_rows: dict[tuple[str, str], dict[str, str]], asset_root: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.post_id = post_id
        self.image_rows = image_rows
        self.asset_root = asset_root
        self.parts: list[str] = []
        self.asset_paths: list[str] = []
        self.inline_stack: list[str] = []
        self.list_stack: list[dict[str, int | str]] = []
        self.dropped_tag: str | None = None
        self.drop_depth = 0
        self.raw_tag: str | None = None
        self.raw_depth = 0

    def _append(self, value: str) -> None:
        if self.raw_tag:
            self.parts.append(value)
        else:
            self.parts.append(value)

    def _block(self) -> None:
        if self.parts and not self.parts[-1].endswith("\n\n"):
            self.parts.append("\n\n")

    def _attributes(self, attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key.lower(): value or "" for key, value in attrs}

    def _safe_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        values = self._attributes(attrs)
        values = {key: value for key, value in values.items() if not key.startswith("on")}
        if tag == "img":
            source = values.get("src") or values.get("data-src") or values.get("data-original") or values.get("data-lazy-src")
            mapped = self._map_image(source) if source else ""
            if mapped:
                values["src"] = mapped
                for key in ("data-src", "data-original", "data-lazy-src"):
                    values.pop(key, None)
        return "<" + tag + "".join(f' {key}="{html.escape(value, quote=True)}"' for key, value in values.items()) + ">"

    def _map_image(self, source: str) -> str:
        absolute = html.unescape(source.strip())
        row = self.image_rows.get((self.post_id, absolute))
        if not row:
            return absolute
        backup_path = Path(row.get("backup_path", ""))
        if not backup_path.is_file():
            return absolute
        destination = self.asset_root / self.post_id / backup_path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(backup_path, destination)
        local_url = f"/images/posts/{self.post_id}/{backup_path.name}"
        if local_url not in self.asset_paths:
            self.asset_paths.append(local_url)
        return local_url

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self.dropped_tag:
            if tag not in VOID_TAGS:
                self.drop_depth += 1
            return
        if tag in DROP_TAGS:
            self.dropped_tag, self.drop_depth = tag, 1
            return
        if self.raw_tag:
            self.parts.append(self._safe_tag(tag, attrs))
            if tag not in VOID_TAGS:
                self.raw_depth += 1
            return
        if tag in RAW_TAGS:
            self._block()
            self.raw_tag, self.raw_depth = tag, 1
            self.parts.append(self._safe_tag(tag, attrs))
            return
        values = self._attributes(attrs)
        if tag in {"p", "div", "section", "figure", "figcaption", "ul", "ol", "li", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}:
            self._block()
        if tag.startswith("h") and len(tag) == 2 and tag[1].isdigit():
            self.parts.append("#" * int(tag[1]) + " ")
        elif tag in {"strong", "b"}:
            self.parts.append("**")
            self.inline_stack.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("*")
            self.inline_stack.append("*")
        elif tag in {"del", "s", "strike"}:
            self.parts.append("~~")
            self.inline_stack.append("~~")
        elif tag == "code":
            self.parts.append("`")
            self.inline_stack.append("`")
        elif tag == "a":
            self.parts.append("[")
            self.inline_stack.append("](" + values.get("href", "") + ")")
        elif tag == "img":
            source = values.get("src") or values.get("data-src") or values.get("data-original") or values.get("data-lazy-src")
            self.parts.append(f"![{values.get('alt', '')}]({self._map_image(source) if source else ''})")
        elif tag == "br":
            self.parts.append("  \n")
        elif tag == "hr":
            self.parts.append("---\n\n")
        elif tag == "ul":
            self.list_stack.append({"kind": "ul", "number": 0})
        elif tag == "ol":
            try:
                number = int(values.get("start", "1"))
            except ValueError:
                number = 1
            self.list_stack.append({"kind": "ol", "number": number})
        elif tag == "li":
            depth = max(0, len(self.list_stack) - 1)
            item = self.list_stack[-1] if self.list_stack else {"kind": "ul", "number": 0}
            if item["kind"] == "ol":
                marker = f"{item['number']}. "
                item["number"] = int(item["number"]) + 1
            else:
                marker = "- "
            self.parts.append("  " * depth + marker)
        elif tag == "blockquote":
            self.parts.append("> ")
        elif tag in {"p", "div", "section", "figure", "figcaption", "span", "article", "main"}:
            pass
        elif tag not in VOID_TAGS:
            self.parts.append(self._safe_tag(tag, attrs))
            self.inline_stack.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.dropped_tag:
            if tag == self.dropped_tag:
                self.drop_depth -= 1
                if self.drop_depth <= 0:
                    self.dropped_tag = None
            elif tag not in VOID_TAGS:
                self.drop_depth = max(1, self.drop_depth - 1)
            return
        if self.raw_tag:
            self.parts.append(f"</{tag}>")
            if tag not in VOID_TAGS:
                self.raw_depth -= 1
                if self.raw_depth <= 0:
                    self.raw_tag = None
            return
        if tag in {"p", "div", "section", "figure", "figcaption", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}:
            if tag in {"ul", "ol"} and self.list_stack:
                self.list_stack.pop()
            self._block()
            return
        if tag in {"p", "div", "section", "figure", "figcaption", "span", "article", "main"}:
            self._block()
            return
        if tag in {"strong", "b", "em", "i", "del", "s", "strike", "code", "a"} and self.inline_stack:
            self.parts.append(self.inline_stack.pop())
            return
        if tag not in VOID_TAGS and tag not in {"span", "article", "main"}:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self.dropped_tag:
            return
        self.parts.append(data)

    def convert(self, fragment: str) -> tuple[str, list[str]]:
        self.feed(fragment)
        self.close()
        body = "".join(self.parts)
        body = re.sub(r"[ \t]+\n", "\n", body)
        body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"
        return body, self.asset_paths


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def frontmatter(post: dict[str, str], tags: list[str], cover_image: str, body: str) -> str:
    title = post.get("title", "").strip()
    date = post.get("date", "").strip()
    description = post.get("description", "").strip()
    category = post.get("category", "").strip()
    id_value = post["id"].strip()
    tag_values = ", ".join(yaml_string(tag) for tag in tags)
    data = [
        "---",
        f"id: {yaml_string(id_value)}",
        f"title: {yaml_string(title)}",
        f"date: {yaml_string(date)}",
        f"category: {yaml_string(category)}",
        f"tags: [{tag_values}]",
        f"description: {yaml_string(description)}",
        f"legacyUrl: {yaml_string('/' + id_value)}",
        f"originalUrl: {yaml_string(post.get('url', ''))}",
        f"coverImage: {yaml_string(cover_image)}",
        "draft: false",
        "---",
        "",
        body,
    ]
    return "\n".join(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", default="migration/posts.csv")
    parser.add_argument("--images", default="migration/images.csv")
    parser.add_argument("--backup", default="backup")
    parser.add_argument("--posts", default="src/content/posts")
    parser.add_argument("--assets", default="public/images/posts")
    parser.add_argument("--comments", default="src/data/comments")
    args = parser.parse_args()

    with Path(args.inventory).open(newline="", encoding="utf-8-sig") as handle:
        posts = list(csv.DictReader(handle))
    image_rows: dict[tuple[str, str], dict[str, str]] = {}
    image_path = Path(args.images)
    if image_path.exists():
        with image_path.open(newline="", encoding="utf-8-sig") as handle:
            image_rows = {(row.get("post_id", ""), row.get("source_url", "")): row for row in csv.DictReader(handle)}
    comment_file = Path(args.backup) / "metadata" / "comments.json"
    comments_by_post: dict[str, list[dict[str, str]]] = defaultdict(list)
    if comment_file.exists():
        for record in json.loads(comment_file.read_text(encoding="utf-8")):
            comments_by_post[str(record.get("post_id", ""))].append(record)

    post_root = Path(args.posts)
    asset_root = Path(args.assets)
    comment_root = Path(args.comments)
    post_root.mkdir(parents=True, exist_ok=True)
    comment_root.mkdir(parents=True, exist_ok=True)
    errors: list[dict[str, str]] = []
    generated = 0
    copied_assets: set[str] = set()
    for post in posts:
        post_id = post.get("id", "").strip()
        if not post_id or post.get("status") != "ok":
            continue
        source_html = Path(args.backup) / "html" / f"{post_id}.html"
        if not source_html.is_file():
            errors.append({"id": post_id, "error": f"Missing HTML backup: {source_html}"})
            continue
        try:
            extractor = ContentExtractor()
            fragment = extractor.extract(source_html.read_text(encoding="utf-8", errors="replace"))
            if not fragment:
                raise ValueError("No .contents_style block found")
            converter = MarkdownConverter(post_id, image_rows, asset_root)
            body, local_assets = converter.convert(fragment)
            copied_assets.update(local_assets)
            tags = json.loads(post.get("tags") or "[]")
            cover_image = local_assets[0] if local_assets else ""
            markdown = frontmatter(post, tags, cover_image, body)
            (post_root / f"{post_id}.md").write_text(markdown, encoding="utf-8")
            (comment_root / f"{post_id}.json").write_text(json.dumps(comments_by_post.get(post_id, []), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            generated += 1
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"id": post_id, "error": f"{type(exc).__name__}: {exc}"})

    report = {
        "posts_in_inventory": len(posts),
        "posts_generated": generated,
        "body_assets_localized": len(copied_assets),
        "comments_exported": sum(len(records) for records in comments_by_post.values()),
        "errors": errors,
    }
    report_path = Path("migration/conversion-report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Posts: {generated}/{len(posts)}; body assets localized: {len(copied_assets)}; comments: {report['comments_exported']}; errors: {len(errors)} ({report_path})")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
