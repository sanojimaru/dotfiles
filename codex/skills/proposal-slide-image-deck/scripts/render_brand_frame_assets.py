#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from brand_frame_common import load_spec, run_brand_frame_tool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ブランドフレーム spec から透過フレーム PNG を生成する")
    parser.add_argument("--spec", required=True, help="extract_brand_frame_spec.py が出力した frame-spec.json")
    parser.add_argument(
        "--out-dir",
        help="透過フレーム PNG の出力先。未指定なら spec と同じディレクトリ",
    )
    parser.add_argument(
        "--variants",
        default="cover,body,body-confidential",
        help="生成する variant をカンマ区切りで指定する",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    spec_path = Path(args.spec).resolve()
    spec = load_spec(spec_path)
    out_dir = Path(args.out_dir).resolve() if args.out_dir else spec_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    available_variants = spec.get("variants", {})
    requested_variants = [item.strip() for item in args.variants.split(",") if item.strip()]
    for variant in requested_variants:
        if variant not in available_variants:
            raise SystemExit(f"ERROR: spec に存在しない variant です: {variant}")

        output_path = out_dir / f"frame-{variant}.png"
        run_brand_frame_tool(
            [
                "--mode",
                "frame",
                "--spec",
                str(spec_path),
                "--variant",
                variant,
                "--output",
                str(output_path),
            ]
        )
        print(f"OK: 透過フレームを生成しました: {output_path}")


if __name__ == "__main__":
    main()
