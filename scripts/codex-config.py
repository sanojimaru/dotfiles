#!/usr/bin/env python3
"""~/.codex/config.toml の「共有してよい部分」だけをリポジトリで管理する。

Codex アプリは config.toml を常時書き換え、案件のパス ([projects.*]) や
フックのハッシュ、端末固有のパスも書き込む。そのままリンク/コミットすると
案件名が公開リポジトリに漏れるため、共有部分だけを codex/config.shared.toml に持つ。

  codex-config.py extract   # ~/.codex/config.toml -> codex/config.shared.toml
  codex-config.py apply     # codex/config.shared.toml を ~/.codex/config.toml へマージ
                            #   (共有部分は上書き、それ以外の端末固有部分は保持。事前にバックアップ)

共有する範囲は SHARED_* で定義する。ここに無いセクションは何も触らない。
"""
import re
import shutil
import sys
import time
import tomllib
from pathlib import Path

LIVE = Path.home() / ".codex" / "config.toml"
SHARED = Path(__file__).resolve().parent.parent / "codex" / "config.shared.toml"

# 共有するセクション (前方一致)。[projects.*] [hooks.state*] [tui*] などは含めない
SHARED_PREFIXES = ("plugins.",)
SHARED_EXACT = {
    "features",
    "desktop",
    "mcp_servers.codegraph",
    "mcp_servers.openaiDeveloperDocs",
    "mcp_servers.obsidian_local_rest_api_with_mcp",
    "marketplaces.helix",
    "marketplaces.intake-flow",
}
# 共有するトップレベルキー (端末固有の notify などは除く)
SHARED_TOP_KEYS = {"model", "model_reasoning_effort", "personality", "service_tier"}
# 共有セクション内でも落とす行 (更新のたびに変わる値)
DROP_LINE = re.compile(r"^(last_updated|last_revision)\s*=")

HEADER = re.compile(r"^\[(.+)\]\s*$")


def parse(text):
    """(preamble_lines, [(header, [lines])]) に分割する。"""
    pre, blocks, cur = [], [], None
    for line in text.splitlines():
        m = HEADER.match(line)
        if m:
            cur = (m.group(1).strip(), [line])
            blocks.append(cur)
        elif cur is None:
            pre.append(line)
        else:
            cur[1].append(line)
    return pre, blocks


def is_shared(header):
    return header in SHARED_EXACT or header.startswith(SHARED_PREFIXES)


def key_of(line):
    m = re.match(r"^([A-Za-z0-9_\-\"\.]+)\s*=", line)
    return m.group(1) if m else None


def trim(lines):
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def extract():
    pre, blocks = parse(LIVE.read_text())
    out = [l for l in pre if key_of(l) in SHARED_TOP_KEYS]
    for header, lines in blocks:
        if is_shared(header):
            body = [l for l in lines if not DROP_LINE.match(l)]
            out += [""] + trim(body)
    SHARED.parent.mkdir(exist_ok=True)
    SHARED.write_text("\n".join(out).strip() + "\n")
    tomllib.loads(SHARED.read_text())
    print(f"wrote {SHARED}")


def apply():
    spre, sblocks = parse(SHARED.read_text())
    lpre, lblocks = parse(LIVE.read_text())
    shared = {h: ls for h, ls in sblocks}

    # トップレベル: 共有キーだけ差し替え、無ければ追加
    top = {key_of(l): l for l in spre if key_of(l)}
    new_pre, seen = [], set()
    for l in lpre:
        k = key_of(l)
        if k in top:
            new_pre.append(top[k]); seen.add(k)
        else:
            new_pre.append(l)
    for k, l in top.items():
        if k not in seen:
            new_pre.insert(0, l)

    # セクション: 共有分は差し替え、ライブにだけ有るものは保持、共有にだけ有るものは追加
    out_blocks, present = [], set()
    for h, ls in lblocks:
        if h in shared:
            keep = [l for l in ls if DROP_LINE.match(l)]  # 更新日時などはライブ側を保持
            out_blocks.append((h, trim(list(shared[h])) + keep + [""]))
            present.add(h)
        else:
            out_blocks.append((h, ls))
    for h, ls in sblocks:
        if h not in present:
            out_blocks.append((h, trim(list(ls)) + [""]))

    text = "\n".join(trim(new_pre) + [""] + [l for _, ls in out_blocks for l in ls]).rstrip() + "\n"
    tomllib.loads(text)  # 壊れた TOML は書かない
    bak = LIVE.with_name(f"config.toml.bak.{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(LIVE, bak)
    LIVE.write_text(text)
    print(f"applied. backup: {bak}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"extract": extract, "apply": apply}.get(cmd, lambda: sys.exit(__doc__))()
