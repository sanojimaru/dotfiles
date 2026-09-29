from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


TOOL_SOURCE_PATH = Path(__file__).with_name("brand_frame_tool.m")
TOOL_BUILD_DIR = Path("/private/tmp/proposal-slide-image-deck")
TOOL_CACHE_DIR = TOOL_BUILD_DIR / "objc-cache"
TOOL_OUTPUT_PATH = TOOL_BUILD_DIR / "brand_frame_tool"


def fail(message: str, exit_code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def load_spec(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"ブランドフレーム spec が見つかりません: {path}")
    except json.JSONDecodeError as exc:
        fail(f"ブランドフレーム spec のJSON解析に失敗しました: {exc}")


def ensure_brand_frame_tool() -> Path:
    TOOL_BUILD_DIR.mkdir(parents=True, exist_ok=True)
    TOOL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    needs_rebuild = not TOOL_OUTPUT_PATH.exists() or TOOL_OUTPUT_PATH.stat().st_mtime < TOOL_SOURCE_PATH.stat().st_mtime
    if not needs_rebuild:
        return TOOL_OUTPUT_PATH

    command = [
        "clang",
        "-fmodules",
        "-fobjc-arc",
        "-framework",
        "AppKit",
        "-framework",
        "Foundation",
        f"-fmodules-cache-path={TOOL_CACHE_DIR}",
        str(TOOL_SOURCE_PATH),
        "-o",
        str(TOOL_OUTPUT_PATH),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        fail(
            "ブランドフレーム描画ツールのコンパイルに失敗しました。\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return TOOL_OUTPUT_PATH


def run_brand_frame_tool(arguments: list[str]) -> None:
    tool_path = ensure_brand_frame_tool()
    result = subprocess.run([str(tool_path), *arguments], capture_output=True, text=True)
    if result.returncode != 0:
        fail(
            "ブランドフレーム描画ツールの実行に失敗しました。\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
