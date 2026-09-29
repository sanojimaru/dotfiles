#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


CHATGPT_HEADING = "ChatGPT入力用完成プロンプト"
GEMINI_HEADING = "Gemini貼り付け用最終ブロック"
FRAME_VARIANTS = {
    "cover",
    "body",
    "body-confidential",
}


def fail(message: str, exit_code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def clean_inline(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`") and len(value) >= 2:
        value = value[1:-1].strip()
    return value


def clean_bullets(block: str) -> list[str]:
    items: list[str] = []
    for raw_line in block.splitlines():
        stripped = raw_line.rstrip()
        match = re.match(r"^\s*-\s+(.*)$", stripped)
        if not match:
            continue
        item = clean_inline(match.group(1))
        if item:
            items.append(item)
    return items


def extract_h1_title(text: str) -> str:
    match = re.search(r"^# (.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def extract_scope_metadata(path: Path) -> tuple[str, str]:
    parts = path.parts
    if "customers" in parts:
        idx = parts.index("customers")
        if idx + 1 >= len(parts):
            fail("customer_slug を入力パスから解釈できませんでした。")
        return "customer", parts[idx + 1]

    if "sales" in parts:
        return "sales", "zuno-sales"

    # This portable skill accepts a slide-design document from any directory.
    # Preserve the familiar metadata for ZUNO workspaces when available.
    return "generic", path.parent.name or "unscoped"


def extract_top_level_section(text: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def extract_subsection_items(section_text: str, heading: str) -> list[str]:
    match = re.search(
        rf"^### [^\n]*{re.escape(heading)}\n(.*?)(?=^### |\Z)",
        section_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        return []
    return clean_bullets(match.group(1))


def build_deck_style_prompt(text: str) -> tuple[str, dict[str, list[str]]]:
    section = extract_top_level_section(text, "1. スライド全体の方針")
    tone_items = extract_subsection_items(section, "トンマナ")
    avoid_items = extract_subsection_items(section, "画像生成で避けること")
    common_rule_items = extract_subsection_items(section, "生成時の共通ルール")
    count_items = extract_subsection_items(section, "想定枚数")

    lines = [
        "これは同一提案デッキ内の連番スライド画像を順番に生成する作業です。",
        "この会話の中で他ページも連続生成する前提で、配色、余白、タイポグラフィ、アイコン密度、B2B提案資料らしい落ち着いた雰囲気を揃えてください。",
        "レイアウトは各ページ固有の指示に従い、別ページの構図をそのまま流用しすぎないでください。",
        "ブランド要素は画像生成時に描かず、生成後に Spike Studio ブランドフレームを上から合成する前提で扱ってください。",
    ]

    if count_items:
        lines.append(f"想定枚数: {' / '.join(count_items)}")
    if tone_items:
        lines.append("デッキ全体のトンマナ:")
        lines.extend(f"- {item}" for item in tone_items)
    if avoid_items:
        lines.append("デッキ全体で避けること:")
        lines.extend(f"- {item}" for item in avoid_items)
    if common_rule_items:
        lines.append("デッキ全体の共通ルール:")
        lines.extend(f"- {item}" for item in common_rule_items)

    return "\n".join(lines), {
        "tone_items": tone_items,
        "avoid_items": avoid_items,
        "common_rule_items": common_rule_items,
        "count_items": count_items,
    }


def split_slides(text: str) -> list[tuple[int, str]]:
    parts = re.split(r"^### Slide (\d+)\n", text, flags=re.MULTILINE)
    slides: list[tuple[int, str]] = []
    for idx in range(1, len(parts), 2):
        slides.append((int(parts[idx]), parts[idx + 1]))
    return slides


def extract_bullet_block_value(slide_text: str, label: str) -> str:
    match = re.search(
        rf"^- {re.escape(label)}:\n((?:  - .*\n)+)",
        slide_text,
        flags=re.MULTILINE,
    )
    if not match:
        return ""
    items = clean_bullets(match.group(1))
    return "\n".join(items).strip()


def extract_heading_block_value(slide_text: str, heading: str) -> str:
    match = re.search(
        rf"^#### {re.escape(heading)}\n(.*?)(?=^#### |\Z)",
        slide_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        return ""

    lines: list[str] = []
    for raw_line in match.group(1).splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("```"):
            continue
        lines.append(clean_inline(stripped))
    return "\n".join(lines).strip()


def extract_title(slide_text: str, slide_no: int) -> str:
    value = extract_heading_block_value(slide_text, "タイトル")
    if value:
        return value.splitlines()[0]

    for label in ("タイトル案", "タイトル"):
        value = extract_bullet_block_value(slide_text, label)
        if value:
            return value.splitlines()[0]

    return f"Slide {slide_no}"


def extract_purpose(slide_text: str) -> str:
    value = extract_heading_block_value(slide_text, "このスライドで言い切ること")
    if value:
        return value.splitlines()[0]

    value = extract_bullet_block_value(slide_text, "このスライドで言い切ること")
    if value:
        return value.splitlines()[0]

    return ""


def extract_prompt_block(slide_text: str) -> tuple[str, str]:
    for heading, block_type in (
        (CHATGPT_HEADING, "chatgpt"),
        (GEMINI_HEADING, "gemini"),
    ):
        match = re.search(
            rf"^#### {re.escape(heading)}\n\n```(?:text)?\n(.*?)\n```",
            slide_text,
            flags=re.MULTILINE | re.DOTALL,
        )
        if match:
            return match.group(1).strip(), block_type

    return "", ""


def extract_structured_json(slide_text: str) -> dict:
    match = re.search(
        r"#### 構造化スライド定義 \(JSON\)\n\n```json\n(.*?)\n```",
        slide_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def normalize_frame_variant(value: str) -> str:
    normalized = clean_inline(value).strip().lower()
    if normalized in FRAME_VARIANTS:
        return normalized
    return ""


def extract_frame_variant(slide_no: int, slide_text: str, title: str) -> str:
    data = extract_structured_json(slide_text)
    explicit = normalize_frame_variant(str(data.get("frame_variant", "")))
    if explicit:
        return explicit

    explicit = normalize_frame_variant(extract_bullet_block_value(slide_text, "ブランドフレーム種別"))
    if explicit:
        return explicit

    if slide_no == 1:
        return "cover"

    if re.search(r"(中表紙|章|セクション|section)", title, flags=re.IGNORECASE):
        return "body-confidential"

    return "body"


def derive_output_base(stem: str) -> str:
    for suffix in ("_提案スライド設計", "_ChatGPT画像生成プロンプト"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def next_version_path(base_path: Path) -> Path:
    if not base_path.exists():
        return base_path

    version = 2
    while True:
        candidate = base_path.parent / f"{base_path.name}-v{version}"
        if not candidate.exists():
            return candidate
        version += 1


def build_final_prompt(
    deck_style_prompt: str,
    original_prompt: str,
    slide_no: int,
    slide_count: int,
    title: str,
    frame_variant: str,
) -> str:
    return "\n\n".join(
        [
            deck_style_prompt,
            (
                f"今回生成するのは Slide {slide_no}/{slide_count} 「{title}」です。"
                " すでに同じ会話内で生成した他ページと、配色・余白・文字組み・図形密度を揃えてください。"
            ),
            f"このスライドはブランドフレーム `{frame_variant}` を後合成する前提です。",
            "以下のスライド固有プロンプトを満たしてください。",
            original_prompt,
        ]
    ).strip()


def default_brand_frame_spec_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "assets"
        / "spike-studio-brand-frame"
        / "frame-spec.json"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="提案スライド設計または画像生成プロンプトMarkdownから、順序付きmanifest.jsonを作成する",
    )
    parser.add_argument("--file", required=True, help="入力の Markdown ファイル")
    parser.add_argument(
        "--output-dir",
        help="画像保存フォルダを明示する場合の出力先。未指定なら入力ファイル名から自動決定する",
    )
    parser.add_argument(
        "--allow-existing-output",
        action="store_true",
        help="--output-dir で指定したフォルダが既に存在していても利用する",
    )
    parser.add_argument(
        "--brand-frame-spec",
        help="PPTX から抽出したブランドフレーム spec JSON。未指定ならスキル同梱の既定値を使う",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    source_path = Path(args.file).resolve()
    if not source_path.exists():
        fail(f"入力ファイルが見つかりません: {source_path}")

    text = source_path.read_text(encoding="utf-8")
    slides = split_slides(text)
    if not slides:
        fail("`### Slide n` 形式のスライドが見つかりません。")

    source_scope, customer_slug = extract_scope_metadata(source_path)
    deck_title = extract_h1_title(text) or source_path.stem
    deck_style_prompt, deck_style_items = build_deck_style_prompt(text)

    brand_frame_spec_path = Path(args.brand_frame_spec).resolve() if args.brand_frame_spec else default_brand_frame_spec_path().resolve()
    if not brand_frame_spec_path.exists():
        fail(
            "ブランドフレーム spec が見つかりません。"
            " 先に extract_brand_frame_spec.py / render_brand_frame_assets.py を実行するか、"
            " --brand-frame-spec を指定してください。"
        )

    output_dir: Path
    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
        if output_dir.exists() and not args.allow_existing_output:
            fail(
                "--output-dir で指定したフォルダが既に存在します。既存フォルダを使う場合は --allow-existing-output を付けてください。"
            )
    else:
        output_base = derive_output_base(source_path.stem)
        output_dir = next_version_path(source_path.parent / f"{output_base}_slide-images").resolve()

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_output_dir = output_dir / "raw"
    raw_output_dir.mkdir(parents=True, exist_ok=True)

    pdf_output = output_dir.parent / f"{output_dir.name}.pdf"
    manifest_path = output_dir / "manifest.json"

    slide_count = len(slides)
    width = max(2, len(str(slide_count)))
    manifest_slides: list[dict[str, object]] = []
    block_type_counts: dict[str, int] = {"chatgpt": 0, "gemini": 0}

    for slide_no, slide_text in slides:
        title = extract_title(slide_text, slide_no)
        purpose = extract_purpose(slide_text)
        original_prompt, block_type = extract_prompt_block(slide_text)
        if not original_prompt:
            fail(f"Slide {slide_no} に {CHATGPT_HEADING} / {GEMINI_HEADING} が見つかりません。")

        frame_variant = extract_frame_variant(slide_no, slide_text, title)
        block_type_counts[block_type] = block_type_counts.get(block_type, 0) + 1

        target_filename = f"slide-{slide_no:0{width}d}.png"
        raw_target_path = raw_output_dir / target_filename
        target_path = output_dir / target_filename
        final_prompt = build_final_prompt(
            deck_style_prompt=deck_style_prompt,
            original_prompt=original_prompt,
            slide_no=slide_no,
            slide_count=slide_count,
            title=title,
            frame_variant=frame_variant,
        )

        manifest_slides.append(
            {
                "slide_no": slide_no,
                "title": title,
                "purpose": purpose,
                "prompt_block_type": block_type,
                "frame_variant": frame_variant,
                "original_prompt": original_prompt,
                "final_prompt": final_prompt,
                "raw_target_filename": target_filename,
                "raw_target_path": str(raw_target_path),
                "target_filename": target_filename,
                "target_path": str(target_path),
            }
        )

    manifest = {
        "schema_version": "zuno.proposal-slide-imagegen-manifest.v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(source_path),
        "deck_title": deck_title,
        "source_scope": source_scope,
        "customer_slug": customer_slug,
        "output_dir": str(output_dir),
        "raw_output_dir": str(raw_output_dir),
        "pdf_output": str(pdf_output),
        "deck_style_prompt": deck_style_prompt,
        "deck_style_items": deck_style_items,
        "brand_frame_spec_path": str(brand_frame_spec_path),
        "brand_frame_assets_dir": str(brand_frame_spec_path.parent),
        "slides": manifest_slides,
    }

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"OK: manifest を作成しました: {manifest_path}")
    print(f"  source_file: {source_path}")
    print(f"  deck_title: {deck_title}")
    print(f"  output_dir: {output_dir}")
    print(f"  raw_output_dir: {raw_output_dir}")
    print(f"  brand_frame_spec_path: {brand_frame_spec_path}")
    print(f"  pdf_output: {pdf_output}")
    print(f"  slides: {slide_count}")
    print(
        "  prompt_blocks: "
        + ", ".join(f"{key}={value}" for key, value in sorted(block_type_counts.items()))
    )


if __name__ == "__main__":
    main()
