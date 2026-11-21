#!/usr/bin/env python3
"""評価用の `gh` の見張り。PATH の先頭に `gh` として置く。

被験のエージェントが評価用リポジトリ（GH_GUARD_REPO）の外を触らないようにする。GH_REPO を固定し、
リポジトリ・認証などのコマンドと、評価用リポジトリ以外を指す引数（`-R`・`--repo=`・GitHub の URL・api のパス）を断る。
GraphQL は、読み取り（query）だけ通す。呼び出しの結果（終了コード）を ORCA_FAKE_LOG に記録する。
これは評価中の取り違えを防ぐ見張りで、悪意のあるエージェントを閉じ込める境界ではない（本物の gh を絶対パスで呼ぶ、などは防げない）。
OS の境界が要るときは、評価専用の macOS ユーザーで流す。
"""
import json
import os
import re
import subprocess
import sys
import time
from pr_replay import replay

REPO = os.environ["GH_GUARD_REPO"]
GH_REAL = "@@GH_REAL@@"  # 試行ごとにコピーするとき、本物の gh のパスを埋める（環境変数に出すと、エージェントが直接呼べてしまう）
# 通すのは、評価で使うコマンドだけ（`issue transfer`・`issue delete`・`repo delete`・`auth` などは通さない）
ALLOW = {
    "issue": {"list", "view", "comment", "close", "reopen", "edit", "create", "status"},
    "pr": {"list", "ls", "view"},
    "label": {"list", "create"},
    "repo": {"view"},
    "api": None,
}
VALUE_FLAGS = {"-X", "--method", "-H", "--header", "-f", "--raw-field", "-F", "--field", "-q", "--jq", "-t", "--template", "--input", "--cache", "--hostname"}


def deny(msg):
    print(f"gh_guard: {msg}", file=sys.stderr)
    return 1


def api_path(argv):
    skip = False
    for a in argv[1:]:
        if skip:
            skip = False
        elif a in VALUE_FLAGS:
            skip = True
        elif not a.startswith("-"):
            owner, _, name = REPO.partition("/")
            return a.lstrip("/").replace("{owner}", owner).replace("{repo}", name)
    return ""


def check(argv):
    """通してよければ None、断るなら理由を返す。"""
    if argv[:1] in (["--version"], ["version"]):
        return None
    if not argv or argv[0] not in ALLOW or (ALLOW[argv[0]] is not None and argv[1:2] and argv[1] not in ALLOW[argv[0]]):
        return f"`gh {' '.join(argv[:2])}` は評価中は使えません"
    for i, a in enumerate(argv):
        target = None
        if a in ("-R", "--repo") and i + 1 < len(argv):
            target = argv[i + 1]
        elif a.startswith(("--repo=", "-R=")):
            target = a.split("=", 1)[1]
        elif re.match(r"-R.+", a):  # `-Rowner/repo` の付けた形
            target = a[2:]
        if target is not None and target.removeprefix("https://github.com/") != REPO:
            return f"{REPO} 以外のリポジトリは触れません"
        for owner_repo in re.findall(r"github\.com/([\w.-]+/[\w.-]+)", a):
            if owner_repo != REPO:
                return f"{REPO} 以外のリポジトリは触れません"
    if argv[:1] == ["api"]:
        path = api_path(argv)
        if path == "graphql":
            joined = " ".join(argv)
            if any(a == "--input" or a.startswith("--input=") for a in argv) or re.search(r"query=@|query=-", joined):
                return "GraphQL の本文をファイルや標準入力から渡す形は評価中は使えません。query を引数に直接書いてください"
            if re.search(r"\bmutation\b", joined, re.I):
                return "GraphQL の mutation は評価中は使えません。gh の issue・label コマンドか REST を使ってください"
        elif not re.fullmatch(rf"repos/{re.escape(REPO)}(/.*)?", path.split("?")[0]):
            return f"api は repos/{REPO} 以下か graphql の query だけ使えます"
        else:
            method = next((argv[i + 1].upper() for i, a in enumerate(argv[:-1]) if a in ("-X", "--method")), "")
            method = method or next((re.sub(r"^(--method=|-X=?)", "", a).upper() for a in argv if re.match(r"(--method=|-X.)", a)), "")
            if method == "DELETE" or (method not in ("", "GET") and re.fullmatch(rf"repos/{re.escape(REPO)}/?", path.split("?")[0])):
                return "リポジトリそのものの変更と DELETE は評価中は使えません"
    return None


def main():
    if os.environ.get("GH_GUARD_ACTIVE"):
        sys.exit(deny("見張りが自分を呼んでいます（本物の gh のパスが見張り自身を指している）"))
    argv = sys.argv[1:]
    started = time.time()
    reason = check(argv)
    rc = deny(reason) if reason else replay(argv, REPO, api_path(argv) if argv[0] == "api" else "")
    if rc is None:
        rc = subprocess.call([GH_REAL] + argv, env=dict(os.environ, GH_REPO=REPO, GH_GUARD_ACTIVE="1"))
    with open(os.environ["ORCA_FAKE_LOG"], "a") as f:
        f.write(json.dumps({"ts": started, "end": time.time(), "tool": "gh", "argv": argv, "rc": rc}, ensure_ascii=False) + "\n")
    sys.exit(rc)


if __name__ == "__main__":
    main()
