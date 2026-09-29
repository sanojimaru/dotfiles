#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from brand_frame_common import fail, run_brand_frame_tool


def load_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"manifest が見つかりません: {path}")
    except json.JSONDecodeError as exc:
        fail(f"manifest のJSON解析に失敗しました: {exc}")


def apply_single(
    spec_path: Path,
    input_path: Path,
    output_path: Path,
    variant: str,
    page: int,
    total: int,
    page_format: str | None,
) -> None:
    if not input_path.exists():
        fail(f"raw スライド画像が見つかりません: {input_path}")

    arguments = [
        "--mode",
        "composite",
        "--spec",
        str(spec_path),
        "--variant",
        variant,
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--page",
        str(page),
        "--total",
        str(total),
    ]
    if page_format:
        arguments.extend(["--page-format", page_format])
    run_brand_frame_tool(arguments)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="raw の提案スライド画像へ Spike Studio ブランドフレームを後合成する")
    parser.add_argument("--manifest", help="extract_slide_prompts.py が出力した manifest.json")
    parser.add_argument("--slide", type=int, help="manifest モード時に特定 slide_no だけ処理する")
    parser.add_argument("--spec", help="single mode 用の frame-spec.json")
    parser.add_argument("--input", help="single mode 用の raw 画像")
    parser.add_argument("--output", help="single mode 用の framed 出力先")
    parser.add_argument("--variant", help="single mode 用の frame variant")
    parser.add_argument("--page", type=int, help="single mode 用の現在ページ番号")
    parser.add_argument("--total", type=int, help="single mode 用の総ページ数")
    parser.add_argument(
        "--page-format",
        help="ページ番号の表示形式。number-only / zero-padded / current-total / zero-padded-total",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.manifest:
        manifest_path = Path(args.manifest).resolve()
        manifest = load_manifest(manifest_path)
        spec_path = Path(manifest.get("brand_frame_spec_path", "")).resolve()
        if not spec_path.exists():
            fail(f"manifest が指す brand frame spec が見つかりません: {spec_path}")

        slides = manifest.get("slides", [])
        if not slides:
            fail("manifest に slides がありません。")

        selected = [
            slide
            for slide in slides
            if args.slide is None or int(slide["slide_no"]) == args.slide
        ]
        if not selected:
            fail("対象 slide が manifest に見つかりません。")

        total = len(slides)
        for slide in sorted(selected, key=lambda item: int(item["slide_no"])):
            apply_single(
                spec_path=spec_path,
                input_path=Path(slide["raw_target_path"]).resolve(),
                output_path=Path(slide["target_path"]).resolve(),
                variant=str(slide.get("frame_variant", "body")),
                page=int(slide["slide_no"]),
                total=total,
                page_format=args.page_format,
            )
            print(f"OK: ブランドフレームを合成しました: slide {slide['slide_no']} -> {slide['target_path']}")
        return

    required = {
        "spec": args.spec,
        "input": args.input,
        "output": args.output,
        "variant": args.variant,
        "page": args.page,
        "total": args.total,
    }
    missing = [key for key, value in required.items() if value in (None, "")]
    if missing:
        fail(
            "single mode で使う場合は "
            + ", ".join(f"--{key}" for key in missing)
            + " を指定してください。"
        )

    apply_single(
        spec_path=Path(args.spec).resolve(),
        input_path=Path(args.input).resolve(),
        output_path=Path(args.output).resolve(),
        variant=str(args.variant),
        page=int(args.page),
        total=int(args.total),
        page_format=args.page_format,
    )
    print(f"OK: ブランドフレームを合成しました: {args.output}")


if __name__ == "__main__":
    main()
