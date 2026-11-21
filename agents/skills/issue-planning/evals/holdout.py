"""非公開の test ケースは、被験プロセスを起こす前にメモリへ取得する。"""
import base64
import json
import os
import re
import sys

from common import gh


def load_holdout(repo, names):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("--holdout-repo は owner/repo で指定してください")
    token = sys.stdin.readline().strip()
    if not token:
        raise ValueError("test ケースの読み取り専用トークンを標準入力に渡してください")
    env = dict(os.environ, GH_TOKEN=token)
    path = f"repos/{repo}"
    metadata = json.loads(gh("api", path, env=env))
    if not metadata["private"]:
        raise ValueError("--holdout-repo は非公開リポジトリである必要があります")
    # 通常の GitHub 認証でも読める配置だと、同じ環境でスキルを書く側に test が見える。
    probe = gh("api", path, "--include", check=False).split("\n", 1)[0]
    if not re.fullmatch(r"HTTP/\S+ 404(?: .*)?\r?", probe):
        raise ValueError("通常の GitHub 認証で holdout が 404 になることを確認できません")
    cases = []
    for name in names:
        encoded = gh("api", f"{path}/contents/cases/{name}.json", "--jq", ".content", env=env)
        if not encoded.strip():
            raise ValueError(f"holdout の {name} が空か、GitHub Contents API の 1 MB 制限を超えています")
        case = json.loads(base64.b64decode(encoded))
        if case.get("id") != name or case.get("split") != "test":
            raise ValueError(f"holdout にある {name} の id または split が正しくありません")
        cases.append(case)
    return cases
