#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "custom-brand"


def main() -> None:
    parser = argparse.ArgumentParser(description="ブランド frame spec から設計 Markdown 用 brand_profile を作る")
    parser.add_argument("--frame-spec", required=True, help="frame-spec.json のパス")
    parser.add_argument("--brand-id", help="ブランド識別子。未指定時は frame spec の親フォルダ名を使う")
    args = parser.parse_args()

    spec_path = Path(args.frame_spec).expanduser().resolve()
    if not spec_path.is_file():
        fail(f"frame spec が見つかりません: {spec_path}")

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"frame spec が JSON ではありません: {exc}")

    variants = spec.get("variants")
    if not isinstance(variants, dict) or not variants:
        fail("frame spec に variants がありません。")

    slide_size = spec.get("slide_size", {})
    defaults = spec.get("render_defaults", {})
    width = defaults.get("canvas_width_px")
    height = defaults.get("canvas_height_px")
    if not isinstance(width, int) or not isinstance(height, int):
        fail("frame spec に canvas_width_px / canvas_height_px がありません。")

    variant_profiles: dict[str, dict[str, object]] = {}
    for name, definition in variants.items():
        if not isinstance(definition, dict):
            fail(f"variant `{name}` がオブジェクトではありません。")
        safe_zones = definition.get("safe_zones")
        if not isinstance(safe_zones, list):
            fail(f"variant `{name}` に safe_zones がありません。")
        variant_profiles[name] = {"safe_zones": safe_zones}

    digest = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    brand_id = args.brand_id or slugify(spec_path.parent.name)
    profile = {
        "brand_id": brand_id,
        "frame_spec": {
            "path": str(spec_path),
            "schema_version": spec.get("schema_version", ""),
            "sha256": digest,
        },
        "canvas": {
            "aspect_ratio": slide_size.get("aspect_ratio", ""),
            "width_px": width,
            "height_px": height,
            "coordinate_system": "percent",
        },
        "allowed_frame_variants": list(variants.keys()),
        "variants": variant_profiles,
        "overlay": {
            "mode": "post-generate",
            "do_not_render": ["logo", "confidential", "copyright", "page_number"],
        },
    }
    print(json.dumps(profile, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
