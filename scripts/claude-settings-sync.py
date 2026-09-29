#!/usr/bin/env python3
"""~/.claude/settings.json が実ファイルに戻っていたら、リポジトリへ取り込んでリンクを張り直す。

Claude Code は設定を書き換える際にシンボリックリンクを実ファイルへ置き換えることがある。
pre-commit から呼ばれ、リンクのままなら何もしない。env に鍵らしいキーがあれば取り込まない。
終了コード: 0=変更なし/取り込み済み, 2=鍵らしいものを検出して中止
"""
import json, os, re, shutil, sys, time
from pathlib import Path

home = Path(os.environ.get("CLAUDE_SYNC_HOME", Path.home()))
live = home / ".claude" / "settings.json"
repo = Path(__file__).resolve().parent.parent / "claude" / "settings.json"
SECRET = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.I)

if live.is_symlink() or not live.exists():
    sys.exit(0)

d = json.loads(live.read_text())
d.pop("feedbackSurveyState", None)  # 端末状態
bad = [k for k in d.get("env", {}) if SECRET.search(k)]
if bad:
    print(f"warn: settings.json の env に鍵らしいキー {bad} があるため取り込みを中止 (~/.env へ移してください)", file=sys.stderr)
    sys.exit(2)

repo.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
bak = live.with_name(f"settings.json.bak.{time.strftime('%Y%m%d-%H%M%S')}")
shutil.move(live, bak)
live.symlink_to(repo)
print("settings.json を取り込み、リンクを張り直しました")
