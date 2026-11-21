"""非公開の test ケースは、被験プロセスを起こす前にメモリへ取得する。"""
import base64
import json
import os
import re

from common import gh


def load_holdout(repo, names):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("--holdout-repo は owner/repo で指定してください")
    token = os.environ.get("IPE_HOLDOUT_TOKEN")
    if not token:
        raise ValueError("test ケースを取得するには IPE_HOLDOUT_TOKEN が必要です")
    env = dict(os.environ, GH_TOKEN=token)
    path = f"repos/{repo}"
    metadata = json.loads(gh("api", path, env=env))
    if not metadata["private"]:
        raise ValueError("--holdout-repo は非公開リポジトリである必要があります")
    # 通常の GitHub 認証でも読める配置だと、同じ環境でスキルを書く側に test が見える。
    if gh("api", path, "--jq", ".full_name", check=False).strip() == metadata["full_name"]:
        raise ValueError("通常の GitHub 認証で holdout を読めます。test 専用のアクセス権を使ってください")
    cases = []
    for name in names:
        encoded = gh("api", f"{path}/contents/cases/{name}.json", "--jq", ".content", env=env)
        case = json.loads(base64.b64decode(encoded))
        if case.get("id") != name or case.get("split") != "test":
            raise ValueError(f"holdout にある {name} の id または split が正しくありません")
        cases.append(case)
    return cases
