#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


PROMPT_HEADINGS = (
    "デザインの方向:",
    "レイアウト:",
    "必ず入れたい文字:",
    "スライドに載せる説明文:",
    "ビジュアル指示:",
    "ブランドフレーム前提:",
    "避けること:",
    "配色と文字組み:",
    "仕上がり条件:",
)
TOP_LEVEL_HEADINGS = (
    "0. 本資料の目的",
    "0.1 根拠台帳",
    "1. スライド全体の方針",
    "2. スライド構成",
    "3. スライド別プロンプト",
)
REQUIRED_SLIDE_FIELDS = (
    "slide_no",
    "title",
    "frame_variant",
    "message",
    "evidence_refs",
    "layout",
    "must_include",
    "visuals",
    "safe_zone_notes",
)


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def section(text: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def code_json(block: str, label: str, errors: list[str]) -> dict:
    match = re.search(r"```json\n(.*?)\n```", block, flags=re.DOTALL)
    if not match:
        errors.append(f"{label} に JSON コードブロックがありません。")
        return {}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        errors.append(f"{label} の JSON が不正です: {exc.msg}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{label} の JSON はオブジェクトである必要があります。")
        return {}
    return data


def string_field(data: dict, field: str, label: str, errors: list[str]) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}.{field} は空でない文字列である必要があります。")
        return ""
    return value.strip()


def string_list(data: dict, field: str, label: str, errors: list[str], allow_empty: bool = False) -> list[str]:
    value = data.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{label}.{field} は文字列の配列である必要があります。")
        return []
    if not value and not allow_empty:
        errors.append(f"{label}.{field} は一件以上必要です。")
    return [item.strip() for item in value]


def resolve(path_value: str, parent: Path) -> Path:
    path = Path(path_value).expanduser()
    return path if path.is_absolute() else (parent / path).resolve()


def validate_ledger(ledger: dict, parent: Path, errors: list[str]) -> tuple[set[str], dict]:
    source_ids: set[str] = set()
    fact_ids: set[str] = set()
    hypothesis_ids: set[str] = set()

    sources = ledger.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("根拠台帳.sources は一件以上必要です。")
    else:
        for index, item in enumerate(sources, start=1):
            if not isinstance(item, dict):
                errors.append(f"sources[{index}] はオブジェクトである必要があります。")
                continue
            source_id = string_field(item, "source_id", f"sources[{index}]", errors)
            string_field(item, "locator", f"sources[{index}]", errors)
            string_field(item, "retrieved_at", f"sources[{index}]", errors)
            if source_id in source_ids:
                errors.append(f"source_id が重複しています: {source_id}")
            source_ids.add(source_id)

    facts = ledger.get("confirmed_facts")
    if not isinstance(facts, list) or not facts:
        errors.append("根拠台帳.confirmed_facts は一件以上必要です。")
    else:
        for index, item in enumerate(facts, start=1):
            if not isinstance(item, dict):
                errors.append(f"confirmed_facts[{index}] はオブジェクトである必要があります。")
                continue
            fact_id = string_field(item, "fact_id", f"confirmed_facts[{index}]", errors)
            string_field(item, "statement", f"confirmed_facts[{index}]", errors)
            string_field(item, "as_of", f"confirmed_facts[{index}]", errors)
            refs = string_list(item, "source_ids", f"confirmed_facts[{index}]", errors)
            for ref in refs:
                if ref not in source_ids:
                    errors.append(f"confirmed_facts[{index}].source_ids の `{ref}` が sources にありません。")
            if fact_id in fact_ids:
                errors.append(f"fact_id が重複しています: {fact_id}")
            fact_ids.add(fact_id)

    hypotheses = ledger.get("proposal_hypotheses", [])
    if not isinstance(hypotheses, list):
        errors.append("根拠台帳.proposal_hypotheses は配列である必要があります。")
    else:
        for index, item in enumerate(hypotheses, start=1):
            if not isinstance(item, dict):
                errors.append(f"proposal_hypotheses[{index}] はオブジェクトである必要があります。")
                continue
            hypothesis_id = string_field(item, "hypothesis_id", f"proposal_hypotheses[{index}]", errors)
            string_field(item, "statement", f"proposal_hypotheses[{index}]", errors)
            based_on = string_list(item, "based_on", f"proposal_hypotheses[{index}]", errors)
            string_field(item, "validation", f"proposal_hypotheses[{index}]", errors)
            if item.get("display_as_hypothesis") is not True:
                errors.append(f"proposal_hypotheses[{index}].display_as_hypothesis は true である必要があります。")
            for ref in based_on:
                if ref not in fact_ids:
                    errors.append(f"proposal_hypotheses[{index}].based_on の `{ref}` が confirmed_facts にありません。")
            if hypothesis_id in hypothesis_ids:
                errors.append(f"hypothesis_id が重複しています: {hypothesis_id}")
            hypothesis_ids.add(hypothesis_id)

    issues = ledger.get("open_issues", [])
    if not isinstance(issues, list):
        errors.append("根拠台帳.open_issues は配列である必要があります。")
    else:
        for index, item in enumerate(issues, start=1):
            if not isinstance(item, dict):
                errors.append(f"open_issues[{index}] はオブジェクトである必要があります。")
                continue
            for field in ("issue_id", "question", "impact", "owner", "decision_gate"):
                string_field(item, field, f"open_issues[{index}]", errors)

    brand = ledger.get("brand_profile")
    if not isinstance(brand, dict):
        errors.append("根拠台帳.brand_profile はオブジェクトである必要があります。")
        return fact_ids | hypothesis_ids, {}
    validate_brand_profile(brand, parent, errors)
    return fact_ids | hypothesis_ids, brand


def validate_brand_profile(brand: dict, parent: Path, errors: list[str]) -> None:
    string_field(brand, "brand_id", "brand_profile", errors)
    frame = brand.get("frame_spec")
    if not isinstance(frame, dict):
        errors.append("brand_profile.frame_spec はオブジェクトである必要があります。")
        return
    frame_path_value = string_field(frame, "path", "brand_profile.frame_spec", errors)
    expected_schema = string_field(frame, "schema_version", "brand_profile.frame_spec", errors)
    digest = string_field(frame, "sha256", "brand_profile.frame_spec", errors)
    if not frame_path_value:
        return
    frame_path = resolve(frame_path_value, parent)
    if not frame_path.is_file():
        errors.append(f"brand_profile.frame_spec.path が実在しません: {frame_path}")
        return
    actual_digest = hashlib.sha256(frame_path.read_bytes()).hexdigest()
    if digest != actual_digest:
        errors.append("brand_profile.frame_spec.sha256 が現在の frame spec と一致しません。")
    try:
        spec = json.loads(frame_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        errors.append("brand_profile.frame_spec.path の JSON を読めません。")
        return
    if spec.get("schema_version") != expected_schema:
        errors.append("brand_profile.frame_spec.schema_version が frame spec と一致しません。")

    canvas = brand.get("canvas")
    if not isinstance(canvas, dict):
        errors.append("brand_profile.canvas はオブジェクトである必要があります。")
    else:
        if canvas.get("aspect_ratio") != spec.get("slide_size", {}).get("aspect_ratio"):
            errors.append("brand_profile.canvas.aspect_ratio が frame spec と一致しません。")
        defaults = spec.get("render_defaults", {})
        for field, expected in (("width_px", defaults.get("canvas_width_px")), ("height_px", defaults.get("canvas_height_px"))):
            if canvas.get(field) != expected:
                errors.append(f"brand_profile.canvas.{field} が frame spec と一致しません。")
        if canvas.get("coordinate_system") != "percent":
            errors.append("brand_profile.canvas.coordinate_system は `percent` である必要があります。")

    allowed = brand.get("allowed_frame_variants")
    if not isinstance(allowed, list) or not allowed or any(not isinstance(value, str) for value in allowed):
        errors.append("brand_profile.allowed_frame_variants は一件以上の文字列配列である必要があります。")
        allowed = []
    spec_variants = spec.get("variants", {})
    for variant in allowed:
        if variant not in spec_variants:
            errors.append(f"brand_profile.allowed_frame_variants の `{variant}` が frame spec にありません。")

    profile_variants = brand.get("variants")
    if not isinstance(profile_variants, dict):
        errors.append("brand_profile.variants はオブジェクトである必要があります。")
    else:
        for variant in allowed:
            expected_zones = spec_variants.get(variant, {}).get("safe_zones")
            observed_zones = profile_variants.get(variant, {}).get("safe_zones") if isinstance(profile_variants.get(variant), dict) else None
            if observed_zones != expected_zones:
                errors.append(f"brand_profile.variants.{variant}.safe_zones が frame spec と一致しません。")

    overlay = brand.get("overlay")
    if not isinstance(overlay, dict) or overlay.get("mode") != "post-generate":
        errors.append("brand_profile.overlay.mode は `post-generate` である必要があります。")
    elif not isinstance(overlay.get("do_not_render"), list) or not overlay["do_not_render"]:
        errors.append("brand_profile.overlay.do_not_render は一件以上の配列である必要があります。")


def extract_heading_value(slide_text: str, heading: str) -> str:
    match = re.search(
        rf"^#### {re.escape(heading)}\n\n?(.*?)(?=^#### |\Z)",
        slide_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        return ""
    lines = [line.strip().strip("`") for line in match.group(1).splitlines() if line.strip() and not line.startswith("```")]
    return normalize(lines[0]) if lines else ""


def extract_prompt(slide_text: str) -> str:
    match = re.search(
        r"^#### ChatGPT入力用完成プロンプト\n\n```text\n(.*?)\n```",
        slide_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def validate_slides(text: str, evidence_ids: set[str], brand: dict, errors: list[str]) -> None:
    slides = list(re.finditer(r"^### Slide (\d+)\s*$", text, flags=re.MULTILINE))
    if not slides:
        errors.append("`### Slide n` 形式のスライドがありません。")
        return
    structure = section(text, "2. スライド構成")
    rows = {
        int(match.group(1)): (normalize(match.group(2)), normalize(match.group(3)), match.group(4))
        for match in re.finditer(r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*([a-z-]+)\s*\|", structure, flags=re.MULTILINE)
    }
    allowed = set(brand.get("allowed_frame_variants", []))
    for expected_no, match in enumerate(slides, start=1):
        slide_no = int(match.group(1))
        if slide_no != expected_no:
            errors.append("Slide 見出しは 1 始まりの連番である必要があります。")
        end = slides[expected_no].start() if expected_no < len(slides) else len(text)
        slide_text = text[match.end():end]
        label = f"Slide {slide_no}"
        json_match = re.search(
            r"^#### 構造化スライド定義 \(JSON\)\n\n```json\n(.*?)\n```",
            slide_text,
            flags=re.MULTILINE | re.DOTALL,
        )
        if not json_match:
            errors.append(f"{label} に構造化スライド定義の JSON コードブロックがありません。")
            continue
        try:
            data = json.loads(json_match.group(1))
        except json.JSONDecodeError as exc:
            errors.append(f"{label} の JSON が不正です: {exc.msg}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{label} の JSON はオブジェクトである必要があります。")
            continue
        for field in REQUIRED_SLIDE_FIELDS:
            if field not in data:
                errors.append(f"{label}.{field} がありません。")
        if data.get("slide_no") != slide_no:
            errors.append(f"{label}.slide_no が見出し番号と一致しません。")
        title = extract_heading_value(slide_text, "タイトル")
        message = extract_heading_value(slide_text, "このスライドで言い切ること")
        if normalize(str(data.get("title", ""))) != title:
            errors.append(f"{label}.title がタイトル見出しと一致しません。")
        if normalize(str(data.get("message", ""))) != message:
            errors.append(f"{label}.message が主張見出しと一致しません。")
        variant = data.get("frame_variant")
        if not isinstance(variant, str) or variant not in allowed:
            errors.append(f"{label}.frame_variant は brand_profile の許可値から明示的に選ぶ必要があります。")
        if rows.get(slide_no) != (title, message, variant):
            errors.append(f"構成表の Slide {slide_no} がタイトル、主張、frame_variant と一致しません。")
        refs = string_list(data, "evidence_refs", label, errors)
        for ref in refs:
            if ref not in evidence_ids:
                errors.append(f"{label}.evidence_refs の `{ref}` が根拠台帳にありません。")
        string_field(data, "layout", label, errors)
        must_include = string_list(data, "must_include", label, errors)
        string_list(data, "visuals", label, errors)
        notes = string_field(data, "safe_zone_notes", label, errors)
        if notes and "safe zone" not in notes.lower() and "空け" not in notes:
            errors.append(f"{label}.safe_zone_notes に safe zone の指示がありません。")
        prompt = extract_prompt(slide_text)
        if not prompt:
            errors.append(f"{label} に ChatGPT入力用完成プロンプトがありません。")
            continue
        for required in ("16:9", "日本語", title, message, str(variant), "合成", "描画しない"):
            if required and required not in prompt:
                errors.append(f"{label} のプロンプトに `{required}` がありません。")
        if "safe zone" not in prompt.lower() and "空け" not in prompt:
            errors.append(f"{label} のプロンプトに safe zone 指示がありません。")
        for heading in PROMPT_HEADINGS:
            if not re.search(rf"^{re.escape(heading)}$", prompt, flags=re.MULTILINE):
                errors.append(f"{label} のプロンプトに見出し `{heading}` がありません。")
        for value in must_include:
            if value not in prompt:
                errors.append(f"{label} のプロンプトに must_include の `{value}` がありません。")
        if brand.get("brand_id") != "spike-studio" and "SPIKE STUDIO" in prompt:
            errors.append(f"{label} のプロンプトに別ブランドの `SPIKE STUDIO` が残っています。")


def main() -> None:
    parser = argparse.ArgumentParser(description="提案スライド設計 Markdown の根拠、構造、ブランド、プロンプト契約を検証する")
    parser.add_argument("--file", required=True, help="検証する *_提案スライド設計.md")
    args = parser.parse_args()

    path = Path(args.file).expanduser().resolve()
    if not path.is_file():
        print(f"ERROR: 設計 Markdown が見つかりません: {path}", file=sys.stderr)
        raise SystemExit(2)
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    for heading in TOP_LEVEL_HEADINGS:
        if not re.search(rf"^## {re.escape(heading)}$", text, flags=re.MULTILINE):
            errors.append(f"トップレベル見出し `## {heading}` がありません。")
    if not re.search(r"^# .+提案スライド設計$", text, flags=re.MULTILINE):
        errors.append("H1 は `{デッキ名} 提案スライド設計` 形式である必要があります。")
    for placeholder in re.findall(r"\{[A-Za-zぁ-んァ-ン一-龯][^{}\n]{0,119}\}", text):
        errors.append(f"未置換プレースホルダーが残っています: {placeholder}")
    ledger = code_json(section(text, "0.1 根拠台帳"), "根拠台帳", errors)
    evidence_ids, brand = validate_ledger(ledger, path.parent, errors) if ledger else (set(), {})
    validate_slides(text, evidence_ids, brand, errors)
    if errors:
        print(f"NG: {path} の設計契約に問題があります。")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    slide_count = len(re.findall(r"^### Slide \d+\s*$", text, flags=re.MULTILINE))
    print(f"OK: {path} は根拠、構造、ブランド、プロンプトの設計契約を満たします。 ({slide_count} スライド)")


if __name__ == "__main__":
    main()
