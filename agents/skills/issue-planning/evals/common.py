"""評価の実行器の共通部分（定数・gh の呼び出し）。"""
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
OWNER = "sanojimaru"
CLAUDE_MODEL = "claude-opus-5-5"
CODEX_MODEL = "gpt-6.1-sol"
JUDGE_MODEL = {"claude": ("codex", CODEX_MODEL), "codex": ("claude", "claude-sonnet-5-5")}
CLAUDE_TOOLS = "Bash,Read,Write,Edit,Glob,Grep,Skill"
WALL_SECONDS = 40 * 60
BUDGET_USD = 3
STRIP_ENV = re.compile(r"^(CLAUDECODE|CLAUDE_CODE_.*|CLAUDE_PID|CLAUDE_EFFORT|CLAUDE_AGENT_SDK_VERSION|ORCA_.*)$")


def real_gh():
    """mise の shim は PATH から `gh` を引き直すので、見張りの `gh` に戻って無限に自分を呼ぶ。shim でない実体を探す。"""
    path = os.pathsep.join(d for d in os.environ["PATH"].split(os.pathsep) if "mise/shims" not in d)
    found = shutil.which("gh", path=path)
    if found:
        return found
    hits = sorted((Path.home() / ".local/share/mise/installs/gh").glob("*/**/bin/gh")) or sorted((Path.home() / ".local/share/mise/installs/gh").glob("*/**/gh"))
    return str(hits[-1])


REAL_GH = real_gh()
LEAK = re.compile(r"秘書のお姉さん|高い知性と言語力|/Users/sanojimaru/(orca|dotfiles)|smdam-datadream|structworker_")
REAL_ORCA = os.environ.get("ORCA_REAL_BIN") or shutil.which("orca") or "/Applications/Orca.app/Contents/Resources/bin/orca"


def sh(argv, **kw):
    kw.setdefault("stdin", subprocess.DEVNULL)  # codex は stdin が閉じるまで待つ
    kw.setdefault("timeout", 600)
    return subprocess.run(argv, capture_output=True, text=True, **kw)


def gh(*args, input=None, check=True, env=None):
    """評価の準備に使う gh。作成が続くと GitHub の二次レート制限に当たるので、当たったら待って繰り返す。"""
    for attempt in range(8):
        r = sh([REAL_GH, *args], input=input, env=env)
        if r.returncode == 0 or not re.search(r"rate limit|abuse|secondary|too quickly", r.stderr, re.I):
            break
        time.sleep(30 * (attempt + 1))
    if check and r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:4])} 失敗: {r.stderr.strip()[:300]}")
    return r.stdout


def check_eval_repo(repo):
    """破壊的な操作（Issue の全削除）が評価用リポジトリの外へ向かわないよう、名前を `ipe-<数字>` に限る。"""
    if not re.fullmatch(r"ipe-\d+", repo):
        raise ValueError(f"評価用リポジトリ（ipe-<数字>）ではありません: {repo}")
