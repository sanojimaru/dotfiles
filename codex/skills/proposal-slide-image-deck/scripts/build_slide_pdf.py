#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="slide-image manifest を読み、保存済み画像を順番どおり1本のPDFに束ねる",
    )
    parser.add_argument("--manifest", required=True, help="extract_slide_prompts.py が出力した manifest.json")
    parser.add_argument("--out", help="出力PDFパス。未指定なら manifest の pdf_output を使う")
    parser.add_argument("--force", action="store_true", help="既存の出力PDFを上書きする")
    return parser.parse_args()


def load_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"manifest.json のJSON解析に失敗しました: {exc}")


def get_slide_image_paths(manifest: dict) -> list[Path]:
    slides = manifest.get("slides", [])
    if not slides:
        fail("manifest に slides がありません。")

    image_paths: list[Path] = []
    for slide in sorted(slides, key=lambda item: item["slide_no"]):
        path = Path(slide["target_path"]).resolve()
        if not path.exists():
            fail(f"保存済み画像が見つかりません: {path}")
        image_paths.append(path)
    return image_paths


def is_jpeg(path: Path) -> bool:
    header = path.read_bytes()[:3]
    return header == b"\xff\xd8\xff"


def jpeg_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if not data.startswith(b"\xff\xd8"):
        fail(f"JPEGとして読めません: {path}")

    offset = 2
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }

    while offset < len(data):
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break

        marker = data[offset]
        offset += 1

        if marker in {0xD8, 0xD9}:
            continue

        if offset + 2 > len(data):
            break
        segment_length = int.from_bytes(data[offset : offset + 2], "big")
        if segment_length < 2:
            break

        if marker in sof_markers:
            start = offset + 2
            if start + 5 >= len(data):
                break
            height = int.from_bytes(data[start + 1 : start + 3], "big")
            width = int.from_bytes(data[start + 3 : start + 5], "big")
            return width, height

        offset += segment_length

    fail(f"JPEGのサイズを取得できませんでした: {path}")


def sips_dimensions(path: Path) -> tuple[int, int]:
    sips_path = shutil.which("sips")
    if not sips_path:
        fail(f"画像サイズ取得に必要な sips が見つかりません: {path}")

    command = [sips_path, "-g", "pixelWidth", "-g", "pixelHeight", str(path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        fail(
            "sips による画像サイズ取得に失敗しました: "
            f"{path}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    width_match = re.search(r"pixelWidth:\s+(\d+)", result.stdout)
    height_match = re.search(r"pixelHeight:\s+(\d+)", result.stdout)
    if not width_match or not height_match:
        fail(f"sips の出力から画像サイズを読めませんでした: {path}")

    return int(width_match.group(1)), int(height_match.group(1))


def convert_to_jpeg(source_path: Path, temp_dir: Path, index: int) -> Path:
    sips_path = shutil.which("sips")
    if not sips_path:
        fail(
            f"JPEG以外の画像をPDF化するには macOS の sips が必要です。未検出の入力: {source_path}"
        )

    output_path = temp_dir / f"slide-{index:02d}.jpg"
    command = [sips_path, "-s", "format", "jpeg", str(source_path), "--out", str(output_path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        fail(
            "sips によるJPEG変換に失敗しました: "
            f"{source_path}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    return output_path


class PdfBuilder:
    def __init__(self) -> None:
        self.objects: list[bytes | None] = []

    def reserve(self) -> int:
        self.objects.append(None)
        return len(self.objects)

    def add(self, content: bytes) -> int:
        obj_no = self.reserve()
        self.set(obj_no, content)
        return obj_no

    def set(self, obj_no: int, content: bytes) -> None:
        self.objects[obj_no - 1] = content

    def render(self, root_obj: int) -> bytes:
        for idx, content in enumerate(self.objects, start=1):
            if content is None:
                fail(f"PDFオブジェクト {idx} が未設定です。")

        chunks = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
        offsets: list[int] = []
        cursor = len(chunks[0])

        for obj_no, content in enumerate(self.objects, start=1):
            offsets.append(cursor)
            obj_bytes = (
                f"{obj_no} 0 obj\n".encode("ascii")
                + content
                + b"\nendobj\n"
            )
            chunks.append(obj_bytes)
            cursor += len(obj_bytes)

        xref_offset = cursor
        xref_lines = [f"xref\n0 {len(self.objects) + 1}\n".encode("ascii"), b"0000000000 65535 f \n"]
        for offset in offsets:
            xref_lines.append(f"{offset:010d} 00000 n \n".encode("ascii"))
        xref_block = b"".join(xref_lines)

        trailer = (
            f"trailer\n<< /Size {len(self.objects) + 1} /Root {root_obj} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")

        return b"".join(chunks) + xref_block + trailer


def pdf_stream(stream_bytes: bytes) -> bytes:
    return (
        f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
        + stream_bytes
        + b"\nendstream"
    )


def image_xobject(jpeg_bytes: bytes, width: int, height: int) -> bytes:
    header = (
        f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
        "/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode "
        f"/Length {len(jpeg_bytes)} >>\nstream\n"
    ).encode("ascii")
    return header + jpeg_bytes + b"\nendstream"


def build_pdf_bytes(image_paths: list[Path]) -> bytes:
    builder = PdfBuilder()
    catalog_obj = builder.reserve()
    pages_obj = builder.reserve()
    page_obj_nos: list[int] = []

    with tempfile.TemporaryDirectory(prefix="slide-pdf-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)

        for index, source_path in enumerate(image_paths, start=1):
            jpeg_path = source_path if is_jpeg(source_path) else convert_to_jpeg(source_path, temp_dir, index)
            width, height = sips_dimensions(jpeg_path) if shutil.which("sips") else jpeg_dimensions(jpeg_path)
            jpeg_bytes = jpeg_path.read_bytes()

            image_obj = builder.add(image_xobject(jpeg_bytes, width, height))
            content_stream = f"q {width} 0 0 {height} 0 0 cm /Im0 Do Q".encode("ascii")
            content_obj = builder.add(pdf_stream(content_stream))
            page_obj = builder.reserve()
            page_obj_nos.append(page_obj)

            page_dict = (
                f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 {width} {height}] "
                f"/Resources << /XObject << /Im0 {image_obj} 0 R >> >> "
                f"/Contents {content_obj} 0 R >>"
            ).encode("ascii")
            builder.set(page_obj, page_dict)

    kids = " ".join(f"{obj_no} 0 R" for obj_no in page_obj_nos)
    builder.set(
        pages_obj,
        f"<< /Type /Pages /Count {len(page_obj_nos)} /Kids [{kids}] >>".encode("ascii"),
    )
    builder.set(catalog_obj, f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode("ascii"))
    return builder.render(root_obj=catalog_obj)


def main() -> None:
    args = parse_args()

    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.exists():
        fail(f"manifest が見つかりません: {manifest_path}")

    manifest = load_manifest(manifest_path)
    raw_output_path = args.out or manifest.get("pdf_output")
    if not raw_output_path:
        fail("出力PDFパスを決定できませんでした。manifest の pdf_output か --out を指定してください。")
    output_path = Path(raw_output_path).resolve()

    if output_path.exists() and not args.force:
        fail(f"出力PDFが既に存在します: {output_path}。上書きする場合は --force を付けてください。")

    image_paths = get_slide_image_paths(manifest)
    pdf_bytes = build_pdf_bytes(image_paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pdf_bytes)

    print(f"OK: PDF を作成しました: {output_path}")
    print(f"  pages: {len(image_paths)}")
    print(f"  manifest: {manifest_path}")


if __name__ == "__main__":
    main()
