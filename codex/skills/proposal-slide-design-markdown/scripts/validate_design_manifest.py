#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


SCHEMA_VERSION = "zuno.proposal-slide-imagegen-manifest.v2"
SLIDE_FIELDS = ("slide_no", "frame_variant", "final_prompt", "raw_target_path", "target_path")


def main() -> None:
    parser = argparse.ArgumentParser(description="提案スライド設計から生成した manifest の実行契約を検証する")
    parser.add_argument("--manifest", required=True, help="manifest.json のパス")
    parser.add_argument("--design", help="対応する *_提案スライド設計.md。指定時は brand_profile との一致も検証する")
    args = parser.parse_args()

    path = Path(args.manifest).expanduser().resolve()
    errors: list[str] = []
    if not path.is_file():
        print(f"ERROR: manifest が見つかりません: {path}", file=sys.stderr)
        raise SystemExit(2)

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: manifest が JSON ではありません: {exc}", file=sys.stderr)
        raise SystemExit(2)

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version は `{SCHEMA_VERSION}` である必要があります。")

    spec_value = manifest.get("brand_frame_spec_path")
    spec_path = Path(spec_value).expanduser() if isinstance(spec_value, str) else None
    if not spec_path or not spec_path.is_file():
        errors.append("brand_frame_spec_path が実在する frame spec を指していません。")
        variants: set[str] = set()
    else:
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            variants = set(spec.get("variants", {}).keys())
        except json.JSONDecodeError:
            errors.append("brand_frame_spec_path の JSON を読めません。")
            variants = set()

    if args.design:
        design_path = Path(args.design).expanduser().resolve()
        if not design_path.is_file():
            errors.append(f"design が見つかりません: {design_path}")
        else:
            design_text = design_path.read_text(encoding="utf-8")
            ledger_match = re.search(
                r"^## 0\.1 根拠台帳\n.*?```json\n(.*?)\n```",
                design_text,
                flags=re.MULTILINE | re.DOTALL,
            )
            if not ledger_match:
                errors.append("design の根拠台帳 JSON を読めません。")
            else:
                try:
                    profile = json.loads(ledger_match.group(1)).get("brand_profile", {})
                    frame = profile.get("frame_spec", {})
                    design_spec = Path(frame.get("path", "")).expanduser()
                    if not design_spec.is_absolute():
                        design_spec = (design_path.parent / design_spec).resolve()
                    expected_digest = frame.get("sha256")
                    if not isinstance(expected_digest, str) or not expected_digest:
                        errors.append("design の brand_profile.frame_spec.sha256 がありません。")
                    elif spec_path and spec_path.is_file():
                        actual_digest = hashlib.sha256(spec_path.read_bytes()).hexdigest()
                        if actual_digest != expected_digest:
                            errors.append("manifest の frame spec が design の brand_profile digest と一致しません。")
                    if spec_path and design_spec != spec_path.resolve():
                        errors.append("manifest の brand_frame_spec_path が design の brand_profile と一致しません。")
                except json.JSONDecodeError:
                    errors.append("design の根拠台帳 JSON が不正です。")

    slides = manifest.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("slides は一件以上の配列である必要があります。")
        slides = []

    raw_paths: set[str] = set()
    target_paths: set[str] = set()
    observed_numbers: list[int] = []
    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            errors.append(f"slides[{index}] がオブジェクトではありません。")
            continue
        for field in SLIDE_FIELDS:
            if field not in slide or slide[field] in (None, ""):
                errors.append(f"slides[{index}].{field} がありません。")
        number = slide.get("slide_no")
        if not isinstance(number, int) or number < 1:
            errors.append(f"slides[{index}].slide_no は 1 以上の整数である必要があります。")
        else:
            observed_numbers.append(number)
        variant = slide.get("frame_variant")
        if isinstance(variant, str) and variants and variant not in variants:
            errors.append(f"slides[{index}] の frame_variant `{variant}` が frame spec にありません。")
        for field, seen in (("raw_target_path", raw_paths), ("target_path", target_paths)):
            value = slide.get(field)
            if isinstance(value, str) and value:
                if value in seen:
                    errors.append(f"{field} が重複しています: {value}")
                seen.add(value)
        if slide.get("raw_target_path") == slide.get("target_path"):
            errors.append(f"slides[{index}] の raw_target_path と target_path が同じです。")

    if observed_numbers and observed_numbers != list(range(1, len(observed_numbers) + 1)):
        errors.append("slide_no は 1 始まりの連番である必要があります。")

    pdf_output = manifest.get("pdf_output")
    if not isinstance(pdf_output, str) or not pdf_output:
        errors.append("pdf_output がありません。")

    if errors:
        print(f"NG: {path} の manifest に問題があります。")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print(f"OK: {path} の manifest は {len(slides)} スライドの実行契約を満たします。")


if __name__ == "__main__":
    main()
