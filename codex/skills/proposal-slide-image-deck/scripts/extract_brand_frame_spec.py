#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import posixpath
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from statistics import mean
import sys
from zipfile import ZipFile
import xml.etree.ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def fail(message: str, exit_code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def normalize_zip_path(base_dir: str, target: str) -> str:
    return posixpath.normpath(str(PurePosixPath(base_dir) / target))


def pct_box(x: int, y: int, width: int, height: int, slide_width: int, slide_height: int) -> dict[str, float]:
    return {
        "left_pct": round((x / slide_width) * 100, 1),
        "top_pct": round((y / slide_height) * 100, 1),
        "width_pct": round((width / slide_width) * 100, 1),
        "height_pct": round((height / slide_height) * 100, 1),
    }


def read_xml(archive: ZipFile, path: str) -> ET.Element:
    return ET.fromstring(archive.read(path))


def extract_theme_colors(theme_root: ET.Element) -> dict[str, str]:
    scheme = theme_root.find(".//a:clrScheme", NS)
    if scheme is None:
        return {}

    colors: dict[str, str] = {}
    for child in scheme:
        key = child.tag.split("}")[-1]
        srgb = child.find(".//a:srgbClr", NS)
        sys_color = child.find(".//a:sysClr", NS)
        if srgb is not None:
            colors[key] = srgb.attrib["val"]
        elif sys_color is not None:
            colors[key] = sys_color.attrib.get("lastClr", "000000")
    return colors


def extract_theme_font_name(theme_root: ET.Element) -> str:
    latin = theme_root.find(".//a:minorFont/a:latin", NS)
    if latin is not None and latin.attrib.get("typeface"):
        return latin.attrib["typeface"]
    return "Arial"


def resolve_fill_color(rpr: ET.Element | None, theme_colors: dict[str, str], fallback: str) -> str:
    if rpr is None:
        return fallback

    solid_fill = rpr.find(".//a:solidFill", NS)
    if solid_fill is None:
        return fallback

    srgb = solid_fill.find("a:srgbClr", NS)
    if srgb is not None and srgb.attrib.get("val"):
        return srgb.attrib["val"]

    scheme = solid_fill.find("a:schemeClr", NS)
    if scheme is not None and scheme.attrib.get("val"):
        return theme_colors.get(scheme.attrib["val"], fallback)

    return fallback


def text_from_shape(shape: ET.Element) -> str:
    values: list[str] = []
    for paragraph in shape.findall(".//a:p", NS):
        parts = []
        for run in paragraph.findall("./a:r", NS):
            text = run.findtext("a:t", default="", namespaces=NS)
            if text:
                parts.append(text)
        for fld in paragraph.findall("./a:fld", NS):
            text = fld.findtext("a:t", default="", namespaces=NS)
            if text:
                parts.append(text)
        if parts:
            values.append("".join(parts))
    return "\n".join(values).strip()


def find_footer_spec(master_root: ET.Element, slide_width: int, slide_height: int, theme_colors: dict[str, str], font_name: str) -> dict[str, object]:
    for shape in master_root.findall(".//p:sp", NS):
        text = text_from_shape(shape)
        if "Spike Studio" not in text:
            continue

        xfrm = shape.find(".//a:xfrm", NS)
        if xfrm is None:
            continue
        off = xfrm.find("a:off", NS)
        ext = xfrm.find("a:ext", NS)
        if off is None or ext is None:
            continue

        first_run = shape.find(".//a:r/a:rPr", NS)
        end_run = shape.find(".//a:endParaRPr", NS)
        size_source = first_run if first_run is not None else end_run
        font_size_pt = 8.0
        if size_source is not None and size_source.attrib.get("sz"):
            font_size_pt = round(int(size_source.attrib["sz"]) / 100, 1)

        return {
            "text": text.strip(),
            "font_name": font_name,
            "font_size_pt": font_size_pt,
            "color_hex": resolve_fill_color(first_run or end_run, theme_colors, "BABABA"),
            "alignment": "left",
            "box_pct": pct_box(
                int(off.attrib["x"]),
                int(off.attrib["y"]),
                int(ext.attrib["cx"]),
                int(ext.attrib["cy"]),
                slide_width,
                slide_height,
            ),
        }

    fail("slide master からコピーライトフッターを抽出できませんでした。")


def find_slide_number_spec(master_root: ET.Element, slide_width: int, slide_height: int, theme_colors: dict[str, str], font_name: str) -> dict[str, object]:
    for shape in master_root.findall(".//p:sp", NS):
        placeholder = shape.find("./p:nvSpPr/p:nvPr/p:ph", NS)
        if placeholder is None or placeholder.attrib.get("type") != "sldNum":
            continue

        xfrm = shape.find(".//a:xfrm", NS)
        if xfrm is None:
            continue
        off = xfrm.find("a:off", NS)
        ext = xfrm.find("a:ext", NS)
        if off is None or ext is None:
            continue

        default_rpr = shape.find(".//a:lvl1pPr/a:defRPr", NS)
        font_size_pt = 10.0
        if default_rpr is not None and default_rpr.attrib.get("sz"):
            font_size_pt = round(int(default_rpr.attrib["sz"]) / 100, 1)

        return {
            "font_name": font_name,
            "font_size_pt": font_size_pt,
            "color_hex": resolve_fill_color(default_rpr, theme_colors, "158158"),
            "alignment": "right",
            "box_pct": pct_box(
                int(off.attrib["x"]),
                int(off.attrib["y"]),
                int(ext.attrib["cx"]),
                int(ext.attrib["cy"]),
                slide_width,
                slide_height,
            ),
        }

    fail("slide master からページ番号プレースホルダを抽出できませんでした。")


def layout_picture_occurrences(archive: ZipFile, layout_name: str, slide_width: int, slide_height: int) -> list[dict[str, object]]:
    layout_path = f"ppt/slideLayouts/{layout_name}"
    rels_path = f"ppt/slideLayouts/_rels/{layout_name}.rels"
    layout_root = read_xml(archive, layout_path)
    rels_root = read_xml(archive, rels_path)
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root.findall("./rel:Relationship", NS)
    }

    results: list[dict[str, object]] = []
    for picture in layout_root.findall(".//p:pic", NS):
        blip = picture.find(".//a:blip", NS)
        if blip is None:
            continue

        rel_id = blip.attrib.get(f"{{{NS['r']}}}embed")
        target = rel_map.get(rel_id)
        if not target:
            continue

        xfrm = picture.find(".//a:xfrm", NS)
        if xfrm is None:
            continue
        off = xfrm.find("a:off", NS)
        ext = xfrm.find("a:ext", NS)
        if off is None or ext is None:
            continue

        results.append(
            {
                "layout_name": layout_name,
                "target": target,
                "target_zip_path": normalize_zip_path("ppt/slideLayouts", target),
                "box_pct": pct_box(
                    int(off.attrib["x"]),
                    int(off.attrib["y"]),
                    int(ext.attrib["cx"]),
                    int(ext.attrib["cy"]),
                    slide_width,
                    slide_height,
                ),
            }
        )
    return results


def presentation_layout_usage(archive: ZipFile) -> tuple[Counter[str], str]:
    presentation_root = read_xml(archive, "ppt/presentation.xml")
    presentation_rels = read_xml(archive, "ppt/_rels/presentation.xml.rels")
    presentation_rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in presentation_rels.findall("./rel:Relationship", NS)
    }

    layout_counter: Counter[str] = Counter()
    first_slide_layout = ""
    for index, slide_id in enumerate(presentation_root.findall(".//p:sldId", NS), start=1):
        rel_id = slide_id.attrib[f"{{{NS['r']}}}id"]
        slide_target = normalize_zip_path("ppt", presentation_rel_map[rel_id])
        slide_rels_path = slide_target.replace("slides/", "slides/_rels/") + ".rels"
        slide_rels_root = read_xml(archive, slide_rels_path)
        layout_rel = next(
            (
                rel.attrib["Target"]
                for rel in slide_rels_root.findall("./rel:Relationship", NS)
                if "../slideLayouts/" in rel.attrib.get("Target", "")
            ),
            None,
        )
        if not layout_rel:
            continue

        layout_name = PurePosixPath(layout_rel).name
        layout_counter[layout_name] += 1
        if index == 1:
            first_slide_layout = layout_name

    if not first_slide_layout:
        fail("先頭スライドの layout を特定できませんでした。")
    return layout_counter, first_slide_layout


def is_small_brand_candidate(occurrences: list[dict[str, object]]) -> bool:
    widths = [item["box_pct"]["width_pct"] for item in occurrences]
    heights = [item["box_pct"]["height_pct"] for item in occurrences]
    return mean(widths) <= 25.0 and mean(heights) <= 10.0


def pick_logo_target(occurrences_by_target: dict[str, list[dict[str, object]]]) -> str:
    candidates = [
        target
        for target, items in occurrences_by_target.items()
        if is_small_brand_candidate(items)
    ]
    if not candidates:
        fail("ロゴ候補となる小サイズ画像を PPTX から見つけられませんでした。")

    def score(target: str) -> tuple[int, float]:
        items = occurrences_by_target[target]
        top_band_lefts = [
            item["box_pct"]["left_pct"]
            for item in items
            if item["box_pct"]["top_pct"] <= 15.0
        ]
        average_left = mean(top_band_lefts) if top_band_lefts else 0.0
        return (len(items), average_left)

    return max(candidates, key=score)


def pick_confidential_target(occurrences_by_target: dict[str, list[dict[str, object]]], logo_target: str) -> str:
    logo_layouts = {item["layout_name"] for item in occurrences_by_target[logo_target]}
    candidates = [
        target
        for target, items in occurrences_by_target.items()
        if target != logo_target and is_small_brand_candidate(items)
    ]
    if not candidates:
        fail("CONFIDENTIAL 候補となる画像を PPTX から見つけられませんでした。")

    def score(target: str) -> tuple[int, int, float]:
        items = occurrences_by_target[target]
        overlap_layouts = {item["layout_name"] for item in items} & logo_layouts
        average_left = mean(item["box_pct"]["left_pct"] for item in items)
        return (len(overlap_layouts), len(items), average_left)

    return max(candidates, key=score)


def pick_variant_layout(
    layout_usage: Counter[str],
    layout_occurrences: dict[str, list[dict[str, object]]],
    logo_target: str,
    confidential_target: str,
    cover_layout: str,
    require_confidential: bool,
) -> str:
    candidates: list[str] = []
    for layout_name, occurrences in layout_occurrences.items():
        if layout_name == cover_layout:
            continue
        targets = {item["target"] for item in occurrences}
        has_logo = logo_target in targets
        has_confidential = confidential_target in targets
        if require_confidential and has_logo and has_confidential:
            candidates.append(layout_name)
        if not require_confidential and has_logo and not has_confidential:
            candidates.append(layout_name)

    if not candidates:
        return cover_layout if require_confidential else cover_layout

    return max(candidates, key=lambda name: layout_usage[name])


def filter_variant_images(layout_name: str, layout_occurrences: dict[str, list[dict[str, object]]], logo_target: str, confidential_target: str) -> list[dict[str, object]]:
    items = layout_occurrences[layout_name]
    results: list[dict[str, object]] = []
    for item in items:
        if item["target"] == logo_target:
            results.append({"asset": "logo.png", "box_pct": item["box_pct"]})
        elif item["target"] == confidential_target:
            results.append({"asset": "confidential.png", "box_pct": item["box_pct"]})
    return results


def safe_zone(label: str, box_pct: dict[str, float]) -> dict[str, object]:
    return {
        "label": label,
        "box_pct": box_pct,
    }


def write_asset(archive: ZipFile, zip_path: str, output_path: Path) -> None:
    output_path.write_bytes(archive.read(zip_path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Spike Studio 提案サンプル PPTX からブランドフレーム spec を抽出する")
    parser.add_argument("--pptx", required=True, help="抽出元のサンプル PPTX")
    parser.add_argument("--out-dir", required=True, help="spec と抽出アセットの出力先")
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存 out-dir を上書きする",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    pptx_path = Path(args.pptx).resolve()
    if not pptx_path.exists():
        fail(f"PPTX が見つかりません: {pptx_path}")

    out_dir = Path(args.out_dir).resolve()
    if out_dir.exists():
        if not args.force:
            fail(f"出力先が既に存在します: {out_dir}。上書きする場合は --force を付けてください。")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with ZipFile(pptx_path) as archive:
        presentation_root = read_xml(archive, "ppt/presentation.xml")
        slide_size = presentation_root.find(".//p:sldSz", NS)
        if slide_size is None:
            fail("presentation.xml から slide size を取得できませんでした。")
        slide_width = int(slide_size.attrib["cx"])
        slide_height = int(slide_size.attrib["cy"])

        theme_root = read_xml(archive, "ppt/theme/theme1.xml")
        theme_colors = extract_theme_colors(theme_root)
        font_name = extract_theme_font_name(theme_root)

        master_root = read_xml(archive, "ppt/slideMasters/slideMaster1.xml")
        footer = find_footer_spec(master_root, slide_width, slide_height, theme_colors, font_name)
        page_number = find_slide_number_spec(master_root, slide_width, slide_height, theme_colors, font_name)

        layout_usage, cover_layout = presentation_layout_usage(archive)
        layout_occurrences: dict[str, list[dict[str, object]]] = {}
        occurrences_by_target: dict[str, list[dict[str, object]]] = defaultdict(list)

        for layout_name in layout_usage:
            occurrences = layout_picture_occurrences(archive, layout_name, slide_width, slide_height)
            layout_occurrences[layout_name] = occurrences
            for item in occurrences:
                occurrences_by_target[item["target"]].append(item)

        logo_target = pick_logo_target(occurrences_by_target)
        confidential_target = pick_confidential_target(occurrences_by_target, logo_target)

        body_layout = pick_variant_layout(
            layout_usage=layout_usage,
            layout_occurrences=layout_occurrences,
            logo_target=logo_target,
            confidential_target=confidential_target,
            cover_layout=cover_layout,
            require_confidential=False,
        )
        body_confidential_layout = pick_variant_layout(
            layout_usage=layout_usage,
            layout_occurrences=layout_occurrences,
            logo_target=logo_target,
            confidential_target=confidential_target,
            cover_layout=cover_layout,
            require_confidential=True,
        )
        if body_confidential_layout == cover_layout:
            body_confidential_layout = body_layout

        write_asset(archive, occurrences_by_target[logo_target][0]["target_zip_path"], out_dir / "logo.png")
        write_asset(archive, occurrences_by_target[confidential_target][0]["target_zip_path"], out_dir / "confidential.png")

    cover_images = filter_variant_images(cover_layout, layout_occurrences, logo_target, confidential_target)
    body_images = filter_variant_images(body_layout, layout_occurrences, logo_target, confidential_target)
    body_confidential_images = filter_variant_images(body_confidential_layout, layout_occurrences, logo_target, confidential_target)

    footer_zone = safe_zone("footer", footer["box_pct"])
    page_zone = safe_zone("page-number", page_number["box_pct"])

    spec = {
        "schema_version": "zuno.proposal-slide-brand-frame.v1",
        "source_pptx": str(pptx_path),
        "slide_size": {
            "cx_emu": slide_width,
            "cy_emu": slide_height,
            "aspect_ratio": "16:9",
        },
        "footer": footer,
        "page_number": page_number,
        "render_defaults": {
            "canvas_width_px": 1920,
            "canvas_height_px": 1080,
            "page_number_format": "number-only",
            "page_number_min_digits": 2,
        },
        "variants": {
            "cover": {
                "layout_name": cover_layout,
                "used_slide_count": layout_usage[cover_layout],
                "images": cover_images,
                "safe_zones": [
                    *[safe_zone(f"cover-{index + 1}", item["box_pct"]) for index, item in enumerate(cover_images)],
                    footer_zone,
                    page_zone,
                ],
            },
            "body": {
                "layout_name": body_layout,
                "used_slide_count": layout_usage[body_layout],
                "images": body_images,
                "safe_zones": [
                    *[safe_zone(f"body-{index + 1}", item["box_pct"]) for index, item in enumerate(body_images)],
                    footer_zone,
                    page_zone,
                ],
            },
            "body-confidential": {
                "layout_name": body_confidential_layout,
                "used_slide_count": layout_usage[body_confidential_layout],
                "images": body_confidential_images,
                "safe_zones": [
                    *[
                        safe_zone(f"body-confidential-{index + 1}", item["box_pct"])
                        for index, item in enumerate(body_confidential_images)
                    ],
                    footer_zone,
                    page_zone,
                ],
            },
        },
        "source_assets": {
            "logo_target": logo_target,
            "confidential_target": confidential_target,
        },
    }

    spec_path = out_dir / "frame-spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"OK: ブランドフレーム spec を抽出しました: {spec_path}")
    print(f"  source_pptx: {pptx_path}")
    print(f"  cover_layout: {cover_layout}")
    print(f"  body_layout: {body_layout}")
    print(f"  body_confidential_layout: {body_confidential_layout}")
    print(f"  logo_target: {logo_target}")
    print(f"  confidential_target: {confidential_target}")


if __name__ == "__main__":
    main()
