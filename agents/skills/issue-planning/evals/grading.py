"""採点: 終状態と呼び出しの記録はコードで、返事は別の会社のモデルの判定器で採点する。"""
import json
import os
import re
import subprocess
from pathlib import Path

from common import JUDGE_MODEL, STRIP_ENV, sh


def read_calls(log):
    return [json.loads(l) for l in open(log)] if Path(log).exists() else []


def is_comment_on(call, n):
    a = call["argv"]
    if call["tool"] != "gh" or call.get("rc") != 0:  # 失敗したコメントは、書かれていない
        return False
    if a[:2] == ["issue", "comment"]:
        return any(x == str(n) or x.rstrip("/").endswith(f"/issues/{n}") for x in a[2:] if not x.startswith("-"))
    if a[:1] != ["api"] or not any(re.search(rf"/issues/{n}/comments", x) for x in a):
        return False
    method = next((a[i + 1].upper() for i, x in enumerate(a[:-1]) if x in ("-X", "--method")), None)
    method = method or next((re.sub(r"^(--method=|-X=?)", "", x).upper() for x in a if re.match(r"(--method=|-X.)", x)), None)
    has_body = any(re.match(r"(-f|-F|--field|--raw-field|--input)", x) for x in a)  # `-fbody=x`・`--field=body=x` も本文
    return (method or ("POST" if has_body else "GET")) == "POST"


def selector_hits(sel, wt):
    kind, _, val = sel.partition(":")
    return (kind == "issue" and val == str(wt["issue"])) or (kind == "path" and val == wt["path"]) or \
           (kind == "identity" and val == wt["identity"]) or (kind == "name" and val == wt["name"]) or (kind == "branch" and val.endswith(wt["name"]))


def run_check(chk, ctx):
    calls = None
    if chk["type"] == "calls":  # success: true は、成功した呼び出しだけ数える。無ければ、失敗した試みも数える（二重起動の検査）
        calls = [c for c in ctx["calls"] if c["tool"] == "orca" and c["argv"][:len(chk["match"])] == chk["match"]
                 and "--help" not in c["argv"] and "-h" not in c["argv"]  # ヘルプは起動の試みではない
                 and (not chk.get("success") or c.get("rc") == 0)]
    t = chk["type"]
    if t == "calls":
        if len(calls) != chk["count"]:
            return False
        if "worktree_of" in chk:
            wt = next(w for w in ctx["state"]["worktrees"] if w["issue"] == ctx["nums"][chk["worktree_of"]])
            return all(any(selector_hits(c["argv"][i + 1], wt) for i, a in enumerate(c["argv"][:-1]) if a == "--worktree") for c in calls)
        return True
    if t == "comment_before_call":
        n = ctx["nums"][chk["issue"]]
        starts = [c["ts"] for c in ctx["calls"] if c["tool"] == "orca" and c["argv"][:len(chk["match"])] == chk["match"] and c.get("rc") == 0
                  and "--help" not in c["argv"] and "-h" not in c["argv"]]  # ヘルプや失敗した呼び出しは起動ではない
        comments = [c.get("end", c["ts"]) for c in ctx["calls"] if is_comment_on(c, n)]  # コメントが終わった時刻を、起動の呼び出しの時刻と比べる
        return bool(starts) and bool(comments) and min(comments) < min(starts)
    if t == "unchanged":
        return all(ctx["before"][ctx["nums"][k]] == ctx["after"].get(ctx["nums"][k]) for k in chk["issues"])
    if t == "state":
        issue = ctx["after"].get(ctx["nums"][chk["issue"]])  # エージェントが Issue を消したときは、失敗
        return issue is not None and issue["state"].lower() == chk["state"]
    raise ValueError(t)


def judge_item(agent, reply, question, out):
    """yes なら True、no なら False。判定器が動かない・答えが読めないときは、被験の失敗にせず RuntimeError にする。"""
    kind, model = JUDGE_MODEL[agent]
    prompt = f"次は、AI エージェントが利用者に返した返事です。\n---\n{reply}\n---\n問い: {question}\nyes か no の 1 語だけで答えてください。"
    env = {k: v for k, v in os.environ.items() if not STRIP_ENV.match(k)}
    try:
        if kind == "codex":
            f = out / f"judge-{abs(hash(question))}.txt"
            r = sh(["codex", "exec", "-m", model, "-s", "read-only", "--skip-git-repo-check", "--ephemeral", "-o", str(f), prompt], env=env, cwd=out)
            ans = f.read_text() if f.exists() else ""
        else:
            env.update(CLAUDE_CODE_DISABLE_CLAUDE_MDS="1", CLAUDE_CODE_DISABLE_AUTO_MEMORY="1")
            r = sh(["claude", "-p", prompt, "--model", model, "--setting-sources", "project,local", "--strict-mcp-config", "--tools", ""], env=env, cwd=out)
            ans = r.stdout
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"判定器が時間内に終わらなかった: {e}") from e
    m = re.search(r"\b(yes|no)\b", ans.strip().lower())
    if r.returncode != 0 or not m:
        raise RuntimeError(f"判定器の答えを読めなかった（終了コード {r.returncode}）: {ans.strip()[:100]} {r.stderr.strip()[:200]}")
    return m.group(1) == "yes"


def grade(case, ctx, reply, agent, out, use_judge=True):
    checks = {c["id"]: run_check(c, ctx) for c in case["expect"]["checks"]}
    fail_on_any = [c["id"] for c in case["expect"]["checks"] if c.get("fail_on_any") and not checks[c["id"]]]
    judge = {}
    if use_judge:
        judge = {j["id"]: judge_item(agent, reply, j["q"], out) for j in case["expect"].get("judge", [])}
    pass_code = all(checks.values())
    return {"checks": checks, "judge": judge, "judge_calibrated": False, "fail_on_any": fail_on_any, "pass_code": pass_code,
            "pass_all": pass_code and all(v is True for v in judge.values())}
