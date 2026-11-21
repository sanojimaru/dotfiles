"""採点: 終状態と呼び出しの記録はコードで、返事は別の会社のモデルの判定器で採点する。"""
import json
import os
import re
import subprocess
from pathlib import Path

from common import JUDGE_MODEL, STRIP_ENV, sh
from seed import subst


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


def option(argv, flag):
    for i, arg in enumerate(argv):
        if arg == flag:
            return argv[i + 1] if i + 1 < len(argv) else ""
        if arg.startswith(flag + "="):
            return arg.split("=", 1)[1]
    return None


def orca_calls(ctx, spec):
    prefix = spec["match"]
    for call in ctx["calls"]:
        argv = call["argv"]
        if call["tool"] != "orca" or argv[:len(prefix)] != prefix or {"--help", "-h"}.intersection(argv):
            continue
        if spec.get("success") and call.get("rc") != 0:
            continue
        if any(not any(arg == flag or arg.startswith(flag + "=") for arg in argv) for flag in spec.get("flags", [])):
            continue
        if any(option(argv, flag) != subst(value, ctx["nums"]) for flag, value in spec.get("options", {}).items()):
            continue
        yield call


def matching_issues(spec, ctx):
    nums, after = ctx["nums"], ctx["after"]
    if "issue" in spec:
        n = nums[spec["issue"]]
        rows = [(n, after[n])] if n in after else []
    else:
        rows = [(n, issue) for n, issue in after.items() if n not in ctx["before"] or not spec.get("new")]
    return [(n, issue) for n, issue in rows if all(
        issue[field] == (nums[value] if field == "parent" and value is not None else value)
        for field, value in spec.get("fields", {}).items()
    ) and set(spec.get("labels", [])) <= set(issue["labels"])
        and not set(spec.get("without_labels", [])).intersection(issue["labels"])]


def event_times(event, ctx):
    n = ctx["nums"].get(event.get("issue"))
    if event["event"] == "orca":
        return [c["ts"] for c in orca_calls(ctx, {**event, "success": True})]
    if event["event"] == "comment":
        return [c.get("end", c["ts"]) for c in ctx["calls"] if is_comment_on(c, n)]
    if event["event"] == "linked":
        targets = {str(k) for k, _ in matching_issues(event["targets"], ctx)}
        return [c["end"] for c in ctx["calls"] if ((c.get("event") == "updated" and c.get("issue") == n) or is_comment_on(c, n)) and
                targets.intersection(re.findall(r"(?:#|/issues/)(\d+)\b", c.get("body", c.get("comment_body", ""))))]
    return [c["ts"] for c in ctx["calls"] if c.get("event") == event["event"] and c.get("issue") == n]


def run_check(chk, ctx):
    t = chk["type"]
    if t == "calls":
        calls = list(orca_calls(ctx, chk))
        if len(calls) != chk["count"]:
            return False
        if "worktree_of" in chk:
            wt = next((w for w in ctx["state"]["worktrees"] if w["issue"] == ctx["nums"][chk["worktree_of"]]), None)
            return not calls or (wt is not None and all(selector_hits(option(c["argv"], "--worktree") or "", wt) for c in calls))
        return True
    if t == "comment_before_call":
        n = ctx["nums"][chk["issue"]]
        starts = [c["ts"] for c in ctx["calls"] if c["tool"] == "orca" and c["argv"][:len(chk["match"])] == chk["match"] and c.get("rc") == 0
                  and "--help" not in c["argv"] and "-h" not in c["argv"]]  # ヘルプや失敗した呼び出しは起動ではない
        comments = [c.get("end", c["ts"]) for c in ctx["calls"] if is_comment_on(c, n)]  # コメントが終わった時刻を、起動の呼び出しの時刻と比べる
        return bool(starts) and bool(comments) and min(comments) < min(starts)
    if t == "unchanged":
        return all(ctx["before"][ctx["nums"][k]] == ctx["after"].get(ctx["nums"][k]) for k in chk["issues"])
    if t == "all_issues_unchanged":
        return ctx["before"] == ctx["after"]
    if t == "state":
        issue = ctx["after"].get(ctx["nums"][chk["issue"]])  # エージェントが Issue を消したときは、失敗
        return issue is not None and issue["state"].lower() == chk["state"]
    if t == "issues":
        count = len(matching_issues(chk, ctx))
        return count == chk["count"] if "count" in chk else count >= chk["minimum"]
    if t == "workers":
        expected = {n for n, _ in matching_issues(chk["issues"], ctx)}
        started = [w for w in ctx["state"]["workers"] if w.get("dispatch_id")]
        matched = [w for w in started if w["issue"] in expected and w["issue"] is not None]
        if chk.get("top_level") and any(w["worktree"].get("has_parent") for w in matched):
            return False
        return len(started) == chk["count"] == len(matched) == len({w["issue"] for w in matched})
    if t == "worktree":
        n = ctx["nums"][chk["issue"]]
        return any(w["issue"] == n and (not w.get("checkout") or Path(w["path"]).is_dir())
                   for w in ctx["state"]["worktrees"]) == chk["present"]
    if t == "file":
        path = ctx["clone"] / chk["path"]
        return path.is_file() and path.read_text() == chk["text"]
    if t == "no_close":
        # 閉じてから開き直しても違反として数える。
        n = ctx["nums"][chk["issue"]]
        source = "first_calls" if chk.get("before_followup") else "calls"
        return not any(c.get("event") == "closed" and c.get("issue") == n
                       and c.get("state_reason") == chk["reason"] for c in ctx.get(source, []))
    if t == "no_first_issues":
        return not any(c.get("event") == "created" for c in ctx.get("first_calls", []))
    if t == "order":
        last = float("-inf")
        for event in chk["events"]:
            last = min((ts for ts in event_times(event, ctx) if ts > last), default=float("inf"))
        return last != float("inf")
    if t == "comment_matches_message":
        n = ctx["nums"][chk["issue"]]
        before = ctx["before"][n]["comments"]
        after = ctx["after"].get(n, {}).get("comments", [])
        messages = list(orca_calls(ctx, {**chk, "success": True}))
        if not messages and chk.get("if_called"):
            return True
        comments = [c for c in ctx["calls"] if is_comment_on(c, n)]
        return any(
            (body := option(message["argv"], chk.get("body_flag", "--body"))) and
            body.strip() in {text.strip() for text in after[len(before):]} and
            any(c.get("end", c["ts"]) < message["ts"] and body.strip() == c.get("comment_body", "").strip() for c in comments)
            for message in messages
        )
    raise ValueError(t)


def evidence(item, ctx, reply):
    source = item.get("source", "reply")
    if source == "reply":
        return reply
    if source == "first_reply":
        return ctx.get("first_reply", "")
    if source == "issues":
        rows = {}
        for n, issue in matching_issues(item["issues"], ctx):
            rows[n] = {field: issue[field] for field in item.get("fields", ["title", "body", "comments"])}
            if item.get("new_comments"):
                rows[n]["comments"] = issue["comments"][len(ctx["before"].get(n, {}).get("comments", [])):]
        return json.dumps(rows, ensure_ascii=False) if rows else ""
    if source == "orca":
        return "\n".join(" ".join(c["argv"]) + ("\n" + c["spec"] if "spec" in c else "") for c in orca_calls(ctx, item))
    if source == "combined":
        return "\n".join(evidence(part, ctx, reply) for part in item["parts"])
    raise ValueError(source)


def judge_item(agent, reply, question, out):
    """yes なら True、no なら False。判定器が動かない・答えが読めないときは、被験の失敗にせず RuntimeError にする。"""
    kind, model = JUDGE_MODEL[agent]
    prompt = f"次は、AI エージェントが残した評価の証拠です。\n---\n{reply}\n---\n問い: {question}\nyes か no の 1 語だけで答えてください。"
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
        for item in case["expect"].get("judge", []):
            content = evidence(item, ctx, reply)
            question = subst(item["q"], ctx["nums"])
            passed = judge_item(agent, content, question, out) if content.strip() else item.get("allow_empty", False)
            judge[item["id"]] = passed
            if item.get("fail_on_any") and not passed:
                fail_on_any.append(item["id"])
    pass_code = all(checks.values())
    return {"checks": checks, "judge": judge, "judge_calibrated": False, "fail_on_any": fail_on_any, "pass_code": pass_code,
            "pass_all": pass_code and all(v is True for v in judge.values())}
