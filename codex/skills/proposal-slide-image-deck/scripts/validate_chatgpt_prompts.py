#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path


REQUIRED_PROMPT_HEADERS = [
    "デザインの方向:",
    "レイアウト:",
    "必ず入れたい文字:",
    "スライドに載せる説明文:",
    "ビジュアル指示:",
    "ブランドフレーム前提:",
    "避けること:",
    "配色と文字組み:",
    "仕上がり条件:",
]

FORBIDDEN_TOKENS = [
    "materials/",
    "work/",
    "skills/",
    "#slide-",
]

REQUIRED_FRAME_TOKENS = [
    ("confidential", "`CONFIDENTIAL`"),
    ("spike studio", "`SPIKE STUDIO`"),
    ("ページ番号", "`ページ番号`"),
]

REQUIRED_FRAME_ACTION_TOKENS = [
    ("合成", "`合成`"),
    ("描画しない", "`描画しない`"),
]


@dataclass
class SlideValidationResult:
    slide_no: int
    title: str
    errors: list[str]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u3000", " ")
    return text.strip()


def split_slides(text: str) -> list[tuple[int, str]]:
    parts = re.split(r"^### Slide (\d+)\n", text, flags=re.MULTILINE)
    slides: list[tuple[int, str]] = []
    for idx in range(1, len(parts), 2):
        slides.append((int(parts[idx]), parts[idx + 1]))
    return slides


def extract_title(slide_text: str, fallback: str) -> str:
    heading_match = re.search(r"^#### タイトル\n\n`([^`]+)`", slide_text, flags=re.MULTILINE)
    if heading_match:
        return heading_match.group(1)

    match = re.search(r"- タイトル案:\n  - `([^`]+)`", slide_text)
    return match.group(1) if match else fallback


def extract_prompt_block(slide_text: str) -> str:
    match = re.search(r"#### ChatGPT入力用完成プロンプト\n\n```text\n(.*?)\n```", slide_text, flags=re.DOTALL)
    return match.group(1) if match else ""


def extract_markdown_bullets(slide_text: str, header: str) -> list[str]:
    match = re.search(
        rf"^- {re.escape(header)}:\n((?:  - .*\n)+)",
        slide_text,
        flags=re.MULTILINE,
    )
    if not match:
        return []

    values: list[str] = []
    for raw_line in match.group(1).splitlines():
        if not raw_line.startswith("  - "):
            continue
        item = raw_line[4:].strip()
        if item.startswith("`") and item.endswith("`") and len(item) >= 2:
            item = item[1:-1]
        if item:
            values.append(normalize(item))
    return values


def get_observed_lines(slide_text: str) -> list[str]:
    match = re.search(r"- 観測本文全文:\n```text\n(.*?)\n```", slide_text, flags=re.DOTALL)
    if not match:
        return []

    lines: list[str] = []
    for raw_line in match.group(1).splitlines():
        stripped = raw_line.rstrip()
        if stripped.strip():
            lines.append(normalize(stripped))
    return lines


def extract_structured_json(slide_text: str) -> dict:
    match = re.search(r"#### 構造化スライド定義 \(JSON\)\n\n```json\n(.*?)\n```", slide_text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def expected_must_include(slide_text: str, title: str, observed_lines: list[str]) -> list[str]:
    explicit = extract_markdown_bullets(slide_text, "必ず入れたい文字")
    if explicit:
        return explicit

    items = [normalize(title)]
    for line in observed_lines:
        if line.startswith("[") and line.endswith("]"):
            continue
        items.append(normalize(line.lstrip("- ").strip()))

    results: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            seen.add(item)
            results.append(item)
        if len(results) >= 8:
            break
    return results


def expected_description_lines(slide_text: str, observed_lines: list[str]) -> list[str]:
    explicit = extract_markdown_bullets(slide_text, "スライドに載せる説明文案")
    if explicit:
        return explicit

    results: list[str] = []
    for line in observed_lines:
        if line.startswith("[") and line.endswith("]"):
            continue
        cleaned = normalize(line.lstrip("- ").strip())
        if cleaned:
            results.append(cleaned)
    return results[:4]


def expected_frame_variant(slide_no: int, slide_text: str) -> str:
    explicit = extract_markdown_bullets(slide_text, "ブランドフレーム種別")
    if explicit:
        return normalize(explicit[0])

    data = extract_structured_json(slide_text)
    variant = normalize(str(data.get("frame_variant", "")))
    if variant:
        return variant

    if slide_no == 1:
        return "cover"
    return "body"


def validate_slide(slide_no: int, slide_text: str) -> SlideValidationResult:
    title = extract_title(slide_text, f"Slide {slide_no}")
    errors: list[str] = []

    prompt_block = extract_prompt_block(slide_text)
    if not prompt_block:
        errors.append("ChatGPT入力用完成プロンプトが見つかりません。")
        return SlideValidationResult(slide_no, title, errors)

    if "16:9" not in prompt_block:
        errors.append("プロンプトに `16:9` の指定がありません。")
    if "日本語" not in prompt_block:
        errors.append("プロンプトに `日本語` の指定がありません。")
    if normalize(title) not in normalize(prompt_block):
        errors.append("プロンプトにスライドタイトルが入っていません。")

    for header in REQUIRED_PROMPT_HEADERS:
        if re.search(rf"^{re.escape(header)}$", prompt_block, flags=re.MULTILINE) is None:
            errors.append(f"プロンプトに必須見出し `{header}` がありません。")

    normalized_prompt = normalize(prompt_block)
    normalized_prompt_lower = normalized_prompt.lower()
    for token in FORBIDDEN_TOKENS:
        if token in prompt_block:
            errors.append(f"プロンプトに参照不能トークン `{token}` が残っています。")

    for token, label in REQUIRED_FRAME_TOKENS:
        if token not in normalized_prompt_lower and token not in normalized_prompt:
            errors.append(f"プロンプトにブランドフレーム前提の要素 {label} がありません。")

    for token, label in REQUIRED_FRAME_ACTION_TOKENS:
        if token not in normalized_prompt:
            errors.append(f"プロンプトにブランドフレーム処理の説明 {label} がありません。")

    if "safe zone" not in normalized_prompt_lower and "空ける" not in normalized_prompt and "予約" not in normalized_prompt:
        errors.append("プロンプトにブランドフレーム用の safe zone 指示がありません。")

    variant = expected_frame_variant(slide_no, slide_text)
    if variant and variant not in normalized_prompt:
        errors.append(f"プロンプトに想定ブランドフレーム種別 `{variant}` が入っていません。")

    observed_lines = get_observed_lines(slide_text)
    must_include = expected_must_include(slide_text, title, observed_lines)
    descriptions = expected_description_lines(slide_text, observed_lines)
    avoid_rules = extract_markdown_bullets(slide_text, "画像生成で避けること")

    prompt_lines = [
        normalize(raw_line.rstrip())
        for raw_line in prompt_block.splitlines()
        if normalize(raw_line.rstrip())
    ]
    prompt_counter = Counter(prompt_lines)

    for item in must_include:
        if normalize(item) not in normalized_prompt:
            errors.append(f"`必ず入れたい文字` がプロンプトに入っていません: {item}")

    for item in descriptions:
        if normalize(item) not in normalized_prompt:
            errors.append(f"`スライドに載せる説明文案` がプロンプトに入っていません: {item}")

    for item in avoid_rules:
        if normalize(item) not in normalized_prompt:
            errors.append(f"`画像生成で避けること` がプロンプトに入っていません: {item}")

    if len(prompt_lines) < 10:
        errors.append("プロンプトの情報量が少なすぎます。")

    if prompt_counter["ビジュアル指示:"] <= 0:
        errors.append("`ビジュアル指示:` セクションが空か、読み取れません。")

    return SlideValidationResult(slide_no, title, errors)


def main() -> None:
    parser = argparse.ArgumentParser(description="提案スライド設計の ChatGPT入力用完成プロンプトを検証する")
    parser.add_argument("--file", required=True, help="検証対象の Markdown ファイル")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)

    text = path.read_text(encoding="utf-8")
    slides = split_slides(text)
    if not slides:
        print("ERROR: `### Slide n` 形式のスライドが見つかりません。", file=sys.stderr)
        sys.exit(2)

    results = [validate_slide(slide_no, slide_text) for slide_no, slide_text in slides]
    failed = [result for result in results if result.errors]

    if not failed:
        print(f"OK: {path} の ChatGPT入力用完成プロンプトは {len(results)} スライドすべて検証を通過しました。")
        return

    print(f"NG: {path} の ChatGPT入力用完成プロンプトに問題があります。")
    for result in failed:
        print(f"\n[Slide {result.slide_no}] {result.title}")
        for error in result.errors:
            print(f"- {error}")
    sys.exit(1)


if __name__ == "__main__":
    main()
