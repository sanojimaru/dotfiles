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
from pathlib import Path

from pr_replay import api_method, replay

REPO = os.environ["GH_GUARD_REPO"]
GH_REAL = "@@GH_REAL@@"  # 試行ごとにコピーするとき、本物の gh のパスを埋める（環境変数に出すと、エージェントが直接呼べてしまう）
# 通すのは、評価で使うコマンドだけ（`issue transfer`・`issue delete`・`repo delete`・`auth` などは通さない）
ALLOW = {
    "issue": {"list", "view", "comment", "close", "reopen", "edit", "create", "status"},
    "pr": {"list", "ls", "view", "checks", "diff", "merge"},
    "stack": {"merge", "sync", "view"},
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
    if argv in (["--version"], ["version"], ["stack", "--help"], ["stack", "-h"]):
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
            method = api_method(argv)
            if method == "DELETE" or (method not in ("", "GET") and re.fullmatch(rf"repos/{re.escape(REPO)}/?", path.split("?")[0])):
                return "リポジトリそのものの変更と DELETE は評価中は使えません"
    return None


def api_fields(argv, input_body):
    fields = {}
    for i, arg in enumerate(argv):
        following = argv[i + 1] if i + 1 < len(argv) else ""
        if arg == "--input" or arg.startswith("--input="):
            path = arg.split("=", 1)[1] if "=" in arg else following
            body = json.loads(input_body if path == "-" else Path(path).read_text())
            if not isinstance(body, dict):
                raise ValueError("API request body is not an object")
            fields.update(body)
        flag = re.fullmatch(r"(-[fF]|--(?:raw-)?field)(?:=)?(.*)", arg)
        if flag:
            key, equals, value = (flag[2] or following).partition("=")
            if equals:
                if flag[1] in ("-F", "--field") and value.startswith("@"):
                    value = input_body if value == "@-" else Path(value[1:]).read_text()
                fields[key] = value
    return fields


def issue_number(args):
    takes_value = {"-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--title", "-c", "--comment", "-r", "--reason",
                   "--type", "--add-label", "--remove-label", "--add-assignee", "--remove-assignee", "--milestone"}
    positional = (arg for i, arg in enumerate(args) if not arg.startswith("-") and (i == 0 or args[i - 1] not in takes_value))
    for arg in positional:
        if match := re.search(r"(?:^#?|/issues/)(\d+)(?:/?$|[#?])", arg):
            return int(match[1])
    return None


def issue_event(argv, endpoint, input_body):
    api_issues = re.fullmatch(r"repos/[^/]+/[^/]+/issues(?:/(\d+)(/comments)?)?", endpoint.split("?", 1)[0].rstrip("/"))
    fields = api_fields(argv, input_body) if api_issues else {}
    if argv[:2] == ["issue", "create"] or (api_issues and not api_issues[1] and "title" in fields):
        return {"event": "created"}
    if argv[:2] in (["issue", "comment"], ["issue", "edit"], ["issue", "close"]):
        number = issue_number(argv[2:])
        metadata = {"issue": number}
        if argv[1] == "close" and number is not None:
            metadata.update(event="closed", state_reason="COMPLETED")
        for i, arg in enumerate(argv[2:], 2):
            flag, equal, value = arg.partition("=")
            val = value if equal else (argv[i + 1] if i + 1 < len(argv) else "")
            text = val if flag in ("--body", "-b") else None
            if flag in ("--body-file", "-F"):
                if val == "-":
                    text = input_body
                elif Path(val).is_file():
                    text = Path(val).read_text()
            if text is not None:
                if argv[1] == "comment":
                    return {**metadata, "comment_body": text}
                if argv[1] == "edit" and number is not None:
                    return {**metadata, "event": "updated", "body": text}
            if argv[1] == "close" and flag in ("--comment", "-c"):
                metadata["comment_body"] = val
            if argv[1] == "close" and flag in ("--reason", "-r"):
                metadata["state_reason"] = val.upper().replace(" ", "_")
        return metadata
    if api_issues and api_issues[1]:
        if api_issues[2] and "body" in fields:
            return {"issue": int(api_issues[1]), "comment_body": fields["body"]}
        if fields.get("state") == "closed":
            return {"event": "closed", "issue": int(api_issues[1]), "state_reason": str(fields.get("state_reason") or "completed").upper()}
        if not api_issues[2] and "body" in fields:
            return {"event": "updated", "issue": int(api_issues[1]), "body": fields["body"]}
    return {}


def main():
    if os.environ.get("GH_GUARD_ACTIVE"):
        sys.exit(deny("見張りが自分を呼んでいます（本物の gh のパスが見張り自身を指している）"))
    argv = sys.argv[1:]
    started = time.time()
    reason = check(argv)
    endpoint = api_path(argv) if argv[:1] == ["api"] else ""
    input_body = None
    if not reason and any((argv[0] == "api" and arg.endswith("=@-")) or arg in ("--input=-", "--body-file=-") or
                           (arg == "-" and argv[i - 1] in ("--input", "--body-file", "-F")) for i, arg in enumerate(argv[1:], 1)):
        input_body = sys.stdin.read()
    metadata = {}
    pr_fields = None
    if not reason and re.search(r"/pulls/\d+/merge(?:-async)?$", endpoint.split("?", 1)[0].rstrip("/")):
        try:
            pr_fields = api_fields(argv, input_body)
        except (OSError, ValueError) as exc:
            reason = f"PR マージの入力を読めません: {exc}"
    rc = deny(reason) if reason else replay(argv, REPO, endpoint, metadata, pr_fields)
    if rc is None:
        rc = subprocess.run([GH_REAL] + argv, input=input_body, text=True,
                            env=dict(os.environ, GH_REPO=REPO, GH_GUARD_ACTIVE="1")).returncode
    extra = metadata
    if rc == 0 and not extra:
        try:
            extra = issue_event(argv, endpoint, input_body)
        except (OSError, TypeError, ValueError) as exc:
            extra = {"observation_error": str(exc)}
    with open(os.environ["ORCA_FAKE_LOG"], "a") as f:
        f.write(json.dumps({"ts": started, "end": time.time(), "tool": "gh", "argv": argv, "rc": rc, **extra}, ensure_ascii=False) + "\n")
    sys.exit(rc)


if __name__ == "__main__":
    main()
