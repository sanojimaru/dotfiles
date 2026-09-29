#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


TESSERACT_CANDIDATES = [Path("/opt/homebrew/bin/tesseract"), Path("/usr/bin/tesseract"), Path("tesseract")]


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def area(self) -> float:
        return max(self.width, 0.0) * max(self.height, 0.0)


@dataclass(frozen=True)
class OCRLine:
    text: str
    confidence: float
    rect: Rect


def fail(message: str, exit_code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="提案スライド raw/final 画像の簡易レイアウト検査を行う",
    )
    parser.add_argument("--manifest", required=True, help="slide-image manifest.json")
    parser.add_argument("--slide", required=True, type=int, help="対象 slide_no")
    parser.add_argument(
        "--image",
        help="検査対象画像。未指定なら manifest の raw_target_path を使う",
    )
    parser.add_argument(
        "--mode",
        choices=["raw", "final"],
        default="raw",
        help="--image 未指定時に raw_target_path / target_path のどちらを使うか",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON だけを stdout へ出力する",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"JSON が見つかりません: {path}")
    except json.JSONDecodeError as exc:
        fail(f"JSON 解析に失敗しました: {path}: {exc}")


def run_ocr(image_path: Path) -> tuple[int, int, list[OCRLine]]:
    tool_path = next((path for path in TESSERACT_CANDIDATES if path.exists()), None)
    if tool_path is None:
        fail("`tesseract` が見つかりません。layout QA を実行できません。")

    result = subprocess.run(
        [
            str(tool_path),
            str(image_path),
            "stdout",
            "--psm",
            "11",
            "-l",
            "eng",
            "tsv",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(
            "Tesseract OCR の実行に失敗しました。\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    rows = [
        row.rstrip("\n").split("\t")
        for row in result.stdout.splitlines()
        if row.strip()
    ]
    if len(rows) < 2:
        fail("Tesseract OCR の TSV 出力が空です。")

    header = rows[0]
    index_map = {name: idx for idx, name in enumerate(header)}
    required_columns = {
        "level",
        "page_num",
        "block_num",
        "par_num",
        "line_num",
        "left",
        "top",
        "width",
        "height",
        "conf",
        "text",
    }
    if not required_columns.issubset(index_map):
        fail("Tesseract OCR の TSV 列が不足しています。")

    image_width = image_height = None
    grouped_words: dict[tuple[int, int, int, int], list[dict[str, str]]] = {}
    for row in rows[1:]:
        if len(row) < len(header):
            row.extend([""] * (len(header) - len(row)))
        level = int(row[index_map["level"]] or 0)
        if level == 1:
            image_width = int(row[index_map["width"]] or 0)
            image_height = int(row[index_map["height"]] or 0)
            continue
        if level != 5:
            continue
        key = (
            int(row[index_map["block_num"]] or 0),
            int(row[index_map["par_num"]] or 0),
            int(row[index_map["line_num"]] or 0),
            int(row[index_map["page_num"]] or 0),
        )
        grouped_words.setdefault(key, []).append(
            {
                "text": row[index_map["text"]],
                "conf": row[index_map["conf"]],
                "left": row[index_map["left"]],
                "top": row[index_map["top"]],
                "width": row[index_map["width"]],
                "height": row[index_map["height"]],
            }
        )

    if not image_width or not image_height:
        fail("Tesseract OCR から画像サイズを取得できませんでした。")

    lines: list[OCRLine] = []
    for key_words in grouped_words.values():
        texts = [normalize_text(item["text"]) for item in key_words if normalize_text(item["text"])]
        if not texts:
            continue
        left = min(float(item["left"]) for item in key_words)
        top = min(float(item["top"]) for item in key_words)
        right = max(float(item["left"]) + float(item["width"]) for item in key_words)
        bottom = max(float(item["top"]) + float(item["height"]) for item in key_words)
        confidences = [float(item["conf"]) for item in key_words if item["conf"] not in {"", "-1"}]
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        lines.append(
            OCRLine(
                text=" ".join(texts),
                confidence=confidence,
                rect=Rect(
                    left=left,
                    top=top,
                    width=right - left,
                    height=bottom - top,
                ),
            )
        )

    lines.sort(key=lambda item: (round(item.rect.top / 4.0), item.rect.left))
    return image_width, image_height, lines


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def intersection_area(left: Rect, right: Rect) -> float:
    width = min(left.right, right.right) - max(left.left, right.left)
    height = min(left.bottom, right.bottom) - max(left.top, right.top)
    if width <= 0 or height <= 0:
        return 0.0
    return width * height


def overlap_ratio(left: Rect, right: Rect) -> float:
    overlap = intersection_area(left, right)
    if overlap <= 0:
        return 0.0
    return overlap / max(min(left.area, right.area), 1.0)


def union_rect(rects: list[Rect]) -> Rect | None:
    if not rects:
        return None
    return Rect(
        left=min(rect.left for rect in rects),
        top=min(rect.top for rect in rects),
        width=max(rect.right for rect in rects) - min(rect.left for rect in rects),
        height=max(rect.bottom for rect in rects) - min(rect.top for rect in rects),
    )


def slide_box_pct_to_rect(box_pct: dict, image_width: int, image_height: int) -> Rect:
    return Rect(
        left=image_width * float(box_pct["left_pct"]) / 100.0,
        top=image_height * float(box_pct["top_pct"]) / 100.0,
        width=image_width * float(box_pct["width_pct"]) / 100.0,
        height=image_height * float(box_pct["height_pct"]) / 100.0,
    )


def parse_expected_bullet_count(prompt: str) -> int:
    return sum(1 for line in prompt.splitlines() if line.lstrip().startswith("- "))


def parse_left_primary_pct(prompt: str) -> float | None:
    matched = re.search(r"左側\s*(\d+(?:\.\d+)?)\s*%", prompt)
    if not matched:
        return None
    return float(matched.group(1)) / 100.0


def has_left_label_strip(prompt: str) -> bool:
    return "左端の黄色ラベル" in prompt or "左端ラベル" in prompt


def keep_line(line: OCRLine) -> bool:
    text = normalize_text(line.text)
    if not text:
        return False
    if line.rect.width < 8 or line.rect.height < 8:
        return False
    if line.confidence < 0.15 and len(text) <= 2:
        return False
    return True


def pct(value: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return value / total


def summarize_issue(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def inspect_layout(
    manifest: dict,
    slide: dict,
    mode: str,
    image_path: Path,
    image_width: int,
    image_height: int,
    lines: list[OCRLine],
) -> dict:
    prompt = str(slide.get("final_prompt", "")).strip()
    expected_bullet_count = parse_expected_bullet_count(prompt)
    left_primary_pct = parse_left_primary_pct(prompt)
    left_label_strip = has_left_label_strip(prompt)
    filtered_lines = [line for line in lines if keep_line(line)]
    filtered_rects = [line.rect for line in filtered_lines]

    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    safe_zone_rects: list[tuple[str, Rect]] = []
    spec_path = Path(str(manifest.get("brand_frame_spec_path", "")))
    variant = str(slide.get("frame_variant", "body"))
    if spec_path.exists():
        spec = load_json(spec_path)
        variant_data = spec.get("variants", {}).get(variant, {})
        for item in variant_data.get("safe_zones", []):
            safe_zone_rects.append(
                (
                    str(item.get("label", "safe-zone")),
                    slide_box_pct_to_rect(item["box_pct"], image_width, image_height),
                )
            )

    if mode == "raw":
        for label, zone_rect in safe_zone_rects:
            for line in filtered_lines:
                ratio = overlap_ratio(line.rect, zone_rect)
                if ratio >= 0.06:
                    issues.append(
                        summarize_issue(
                            "safe_zone_overlap",
                            f"`{line.text}` がブランド安全領域 `{label}` に重なっています (ratio={ratio:.2f})",
                        )
                    )

    edge_margin_x = image_width * 0.012
    edge_margin_y = image_height * 0.012
    for line in filtered_lines:
        if (
            line.rect.left < edge_margin_x
            or line.rect.top < edge_margin_y
            or line.rect.right > image_width - edge_margin_x
            or line.rect.bottom > image_height - edge_margin_y
        ):
            issues.append(
                summarize_issue(
                    "edge_intrusion",
                    f"`{line.text}` が画像端に近すぎます",
                )
            )

    for index, left in enumerate(filtered_lines):
        for right in filtered_lines[index + 1 :]:
            ratio = overlap_ratio(left.rect, right.rect)
            if ratio >= 0.12:
                issues.append(
                    summarize_issue(
                        "text_overlap",
                        f"`{left.text}` と `{right.text}` の OCR 領域が重なっています (ratio={ratio:.2f})",
                    )
                )

    content_rect = union_rect(filtered_rects)
    content_height_pct = 0.0
    content_width_pct = 0.0
    content_area_pct = 0.0
    if content_rect:
        content_height_pct = pct(content_rect.height, image_height)
        content_width_pct = pct(content_rect.width, image_width)
        content_area_pct = pct(content_rect.area, image_width * image_height)

    line_count = len(filtered_lines)
    if expected_bullet_count >= 6:
        min_expected_lines = max(6, math.floor(expected_bullet_count * 0.7))
        if line_count < min_expected_lines:
            warnings.append(
                summarize_issue(
                    "missing_text_density",
                    f"OCR 行数が少なめです (ocr={line_count}, expected_bullets={expected_bullet_count})",
                )
            )
        if content_height_pct < 0.34:
            warnings.append(
                summarize_issue(
                    "vertical_whitespace",
                    f"文字領域の縦方向使用率が低めです ({content_height_pct:.2%})",
                )
            )

    if left_primary_pct is not None and filtered_lines:
        left_lines = [
            line
            for line in filtered_lines
            if (line.rect.left + line.rect.width / 2.0) < image_width * 0.5
            and line.rect.top >= image_height * 0.18
        ]
        if not left_lines:
            left_lines = [
                line for line in filtered_lines if (line.rect.left + line.rect.width / 2.0) < image_width * 0.5
            ]
        left_rect = union_rect([line.rect for line in left_lines])
        if left_rect and len(left_lines) >= 6:
            left_width_pct = pct(left_rect.width, image_width)
            if left_width_pct < left_primary_pct * 0.75:
                warnings.append(
                    summarize_issue(
                        "left_column_underused",
                        f"左カラムの文字使用幅が狭めです ({left_width_pct:.2%} < expected ~{left_primary_pct * 0.75:.2%})",
                    )
                )

    if left_label_strip and filtered_lines:
        right_body_lines = [
            line
            for line in filtered_lines
            if (line.rect.left + line.rect.width / 2.0) >= image_width * 0.55
            and line.rect.top >= image_height * 0.16
            and line.rect.width >= image_width * 0.12
        ]
        if right_body_lines:
            right_body_left_pct = pct(
                min(line.rect.left for line in right_body_lines),
                image_width,
            )
            if right_body_left_pct < 0.58:
                issues.append(
                    summarize_issue(
                        "label_body_overlap_risk",
                        f"右側カード本文の開始位置が左ラベル帯に近すぎます ({right_body_left_pct:.2%} < 58.00%)",
                    )
                )

    status = "pass"
    if issues:
        status = "fail"
    elif warnings:
        status = "warn"

    return {
        "status": status,
        "imagePath": str(image_path),
        "imageWidthPx": image_width,
        "imageHeightPx": image_height,
        "mode": mode,
        "slideNo": int(slide["slide_no"]),
        "frameVariant": variant,
        "expected": {
            "bulletCount": expected_bullet_count,
            "leftPrimaryPct": left_primary_pct,
        },
        "metrics": {
            "ocrLineCount": line_count,
            "contentWidthPct": content_width_pct,
            "contentHeightPct": content_height_pct,
            "contentAreaPct": content_area_pct,
        },
        "issues": issues,
        "warnings": warnings,
        "ocrPreview": [
            {
                "text": line.text,
                "confidence": round(line.confidence, 3),
                "leftPx": round(line.rect.left, 1),
                "topPx": round(line.rect.top, 1),
                "widthPx": round(line.rect.width, 1),
                "heightPx": round(line.rect.height, 1),
            }
            for line in filtered_lines[:40]
        ],
    }


def render_text_report(result: dict) -> str:
    lines = [
        f"STATUS: {result['status']}",
        f"IMAGE: {result['imagePath']}",
        f"OCR_LINES: {result['metrics']['ocrLineCount']}",
        "METRICS:",
        f"- content_width_pct: {result['metrics']['contentWidthPct']:.2%}",
        f"- content_height_pct: {result['metrics']['contentHeightPct']:.2%}",
        f"- content_area_pct: {result['metrics']['contentAreaPct']:.2%}",
        f"- expected_bullets: {result['expected']['bulletCount']}",
    ]
    if result["expected"]["leftPrimaryPct"] is not None:
        lines.append(f"- expected_left_primary_pct: {result['expected']['leftPrimaryPct']:.2%}")

    if result["issues"]:
        lines.append("ISSUES:")
        lines.extend(f"- {issue['code']}: {issue['detail']}" for issue in result["issues"])
    else:
        lines.append("ISSUES: none")

    if result["warnings"]:
        lines.append("WARNINGS:")
        lines.extend(f"- {warning['code']}: {warning['detail']}" for warning in result["warnings"])
    else:
        lines.append("WARNINGS: none")

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    manifest_path = Path(args.manifest).resolve()
    manifest = load_json(manifest_path)
    slides = manifest.get("slides", [])
    slide = next((item for item in slides if int(item["slide_no"]) == args.slide), None)
    if not slide:
        fail(f"slide_no={args.slide} が manifest に見つかりません。")

    image_path = (
        Path(args.image).resolve()
        if args.image
        else Path(
            slide["raw_target_path"] if args.mode == "raw" else slide["target_path"]
        ).resolve()
    )
    if not image_path.exists():
        fail(f"検査対象画像が見つかりません: {image_path}")

    image_width, image_height, lines = run_ocr(image_path)
    result = inspect_layout(
        manifest=manifest,
        slide=slide,
        mode=args.mode,
        image_path=image_path,
        image_width=image_width,
        image_height=image_height,
        lines=lines,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(render_text_report(result))


if __name__ == "__main__":
    main()
