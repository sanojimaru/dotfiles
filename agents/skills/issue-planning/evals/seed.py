"""種（評価用リポジトリの Issue と、代役の orca の状態）を立てる・読む。"""
import datetime
import hashlib
import json
import re
import threading
from pathlib import Path

import fake_gh
from common import HERE, OWNER, check_eval_repo, gh

# 評価用リポジトリごとに、立ててある種（ケース・番号・読んだときの状態）を覚える。試行の後は、エージェントが変えたものだけを戻す
STATE_FILE = Path.home() / ".cache/issue-planning-eval/repo-state.json"
_LOCK = threading.Lock()


def reset_repo(repo):
    check_eval_repo(repo)
    r = f"{OWNER}/{repo}"
    nums = json.loads(gh("issue", "list", "-R", r, "--state", "all", "--limit", "1000", "--json", "number") or "[]")
    for n in nums:
        gh("issue", "delete", str(n["number"]), "-R", r, "--yes")


def subst(text, nums, *, defer=False):
    two_days = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    text = text.replace("<<date-2d>>", two_days)
    return re.sub(r"<<([a-z0-9]+)>>", lambda m: str(nums.get(m[1], m[0]) if defer else nums[m[1]]), text)


def seed_repo(repo, case):
    check_eval_repo(repo)
    r = f"{OWNER}/{repo}"
    have = {x["name"] for x in json.loads(gh("label", "list", "-R", r, "--limit", "200", "--json", "name"))}
    for lab in case["seed"].get("labels", []):  # ラベルは使い回す（作成の回数が GitHub の二次レート制限に効くため）
        if lab["name"] not in have:
            gh("label", "create", lab["name"], "-R", r, "--description", lab.get("description", ""))
    prs = case["seed"].get("prs", [])
    keys = [item["key"] for item in [*prs, *case["seed"]["issues"]]]
    if len(set(keys)) != len(keys):
        raise ValueError("種の Issue と PR の key は重複できません")
    nums = {pr["key"]: 1_000_000 + i for i, pr in enumerate(prs, 1)}
    seeded = case["seed"]["issues"]
    deferred = []
    for iss in seeded:
        title, body = (subst(iss[field], nums, defer=True) for field in ("title", "body"))
        args = ["issue", "create", "-R", r, "--title", title, "--body", body]
        if iss.get("type"):
            args += ["--type", iss["type"]]
        for lab in iss.get("labels", []):
            args += ["--label", lab]
        if iss.get("parent"):
            args += ["--parent", str(nums[iss["parent"]])]
        url = gh(*args).strip()
        nums[iss["key"]] = int(url.rsplit("/", 1)[1])
        if "<<" in title or "<<" in body:
            deferred.append((iss["key"], title, body))
    for key, title, body in deferred:
        gh("issue", "edit", str(nums[key]), "-R", r, "--title", subst(title, nums), "--body", subst(body, nums))
    for iss in seeded:
        for body in iss.get("comments", []):
            gh("issue", "comment", str(nums[iss["key"]]), "-R", r, "--body", subst(body, nums))
        if iss.get("state") == "closed":
            gh("issue", "close", str(nums[iss["key"]]), "-R", r, "--reason", "completed")
    return nums


def seed_local(case, repo):
    """`seed_repo` と同じ種を、GitHub でなく代役の状態に立てる。(番号, 状態) を返す。"""
    state = fake_gh.new_state(f"{OWNER}/{repo}", case["seed"].get("labels", []))
    prs = case["seed"].get("prs", [])
    keys = [item["key"] for item in [*prs, *case["seed"]["issues"]]]
    if len(set(keys)) != len(keys):
        raise ValueError("種の Issue と PR の key は重複できません")
    nums = {pr["key"]: 1_000_000 + i for i, pr in enumerate(prs, 1)}
    # 番号は、立てる前に決まる（GitHub と違い、種の中で互いを指す本文を 1 回で書ける）
    nums.update({iss["key"]: state["next_number"] + i for i, iss in enumerate(case["seed"]["issues"])})
    for iss in case["seed"]["issues"]:
        fake_gh.add_issue(state, subst(iss["title"], nums), subst(iss["body"], nums), labels=iss.get("labels", []),
                          type_=iss.get("type"), parent=nums[iss["parent"]] if iss.get("parent") else None)
    for iss in case["seed"]["issues"]:
        issue = fake_gh.find(state, nums[iss["key"]])
        for body in iss.get("comments", []):
            fake_gh.add_comment(state, issue, subst(body, nums))
        if iss.get("state") == "closed":
            fake_gh.set_state(issue, True)
    return nums, state


def pr_state(case, nums, repo):
    """両方の PR 読み取りが共有する、`gh pr --json` の形の種。"""
    rows = []
    for pr in case["seed"].get("prs", []):
        number = nums[pr["key"]]
        state = pr.get("state", "OPEN").upper()
        created = pr.get("createdAt", f"{datetime.date.today().isoformat()}T00:00:00Z")
        closed = pr.get("closedAt", created) if state != "OPEN" else None
        rows.append({
            "body": "", "baseRefName": "main", "headRefName": pr["key"],
            "author": {"login": OWNER}, "mergedBy": {"login": OWNER} if state == "MERGED" else None,
            "labels": [], "comments": [], "commits": [], "files": [], "isDraft": False,
            "reviewDecision": "", "statusCheckRollup": [], "headRefOid": "",
            **{k: subst(v, nums) if isinstance(v, str) else v for k, v in pr.items() if k not in {"key", "closes"}},
            "state": state, "closed": state != "OPEN", "number": number,
            "createdAt": created, "closedAt": closed, "mergedAt": closed if state == "MERGED" else None,
            "mergeCommit": pr.get("mergeCommit"),
            "url": f"https://github.com/{OWNER}/{repo}/pull/{number}",
            "closingIssuesReferences": [{"number": nums[key]} for key in pr.get("closes", [])],
        })
    return rows


def snapshot(repo):
    check_eval_repo(repo)
    fields = "number,title,body,state,stateReason,labels,issueType,comments,parent,subIssues"
    rows = json.loads(gh("issue", "list", "-R", f"{OWNER}/{repo}", "--state", "all", "--limit", "1000", "--json", fields))
    return {
        r["number"]: {
            "title": r["title"], "body": r["body"], "state": r["state"], "stateReason": None if r["state"] == "OPEN" else r.get("stateReason"),  # 開き直した Issue の REOPENED は、元の状態と同じとみなす
            "labels": sorted(label["name"] for label in r["labels"]),
            "type": (r.get("issueType") or {}).get("name"),
            "comments": [c["body"] for c in r["comments"]],
            "comment_ids": [int(c["url"].rsplit("-", 1)[1]) for c in r["comments"]],
            "parent": (r.get("parent") or {}).get("number"),
            "subIssues": sorted(s["number"] for s in ((r.get("subIssues") or {}).get("nodes") or [])),
        }
        for r in rows
    }


def orca_state(case, nums, clone, repo):
    o = case["orca"]
    wts = [{"issue": None, "name": "main", "path": str(clone), "identity": "wt2:local:main"}]
    for w in o["worktrees"]:
        issue = nums[w["issue"]]
        name = subst(w["name"], nums)
        wts.append({"issue": issue, "name": name, "path": f"/fake/worktrees/{name}", "identity": f"wt2:local:{name}"})
    recordings = json.loads((HERE / "orca-recordings.json").read_text())
    rid = o["run_id"]
    messages = [orca_message(recordings, message, nums, rid, i) for i, message in enumerate(o.get("messages", []), 1)]
    reply = o.get("ask_reply")
    return {
        "repo_id": "fake-repo", "run_id": o["run_id"], "run_objective": subst(o["run_objective"].replace("<<repo>>", f"{OWNER}/{repo}"), nums), "worktrees": wts,
        "workers": [{"issue": nums[w["issue"]], "liveness": w["liveness"], "state": w["state"]} for w in o["workers"]],
        "tasks": o.get("tasks", []),
        "messages": messages,
        "next_run_id": o.get("next_run_id"),
        "ask_reply": orca_message(recordings, {"kind": "reply", **reply}, nums, rid, len(messages) + 1) if reply else None,
    }


def orca_message(recordings, spec, nums, run_id, sequence):
    kind = spec["kind"]
    # escalation の本文・payload はケースから渡し、共通のメッセージフィールドは録画を使う。
    record = dict(recordings["send" if kind == "escalation" else kind])
    record.update(run_id=run_id, id=f'{record["id"]}_{sequence}')
    if kind == "escalation":
        record.update(type=kind, from_handle="dispatch:ctx_eval")
    if kind in ("ask", "worker_done", "escalation"):
        payload = spec.get("payload") or {}
        record["to_handle"] = f"run:{run_id}"
        if isinstance(payload, dict) and payload.get("dispatchId"):
            record["from_handle"] = f'dispatch:{payload["dispatchId"]}'
    else:
        record["from_handle"] = f"run:{run_id}"
    record.update({k: subst(v, nums) if isinstance(v, str) else v for k, v in spec.items() if k != "kind"})
    if isinstance(record["payload"], dict):
        record["payload"] = subst(json.dumps(record["payload"], ensure_ascii=False), nums)
    record["sequence"] = sequence
    return record


def _load_state():
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def _save_state(st):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False))


def _norm(snap):
    return json.loads(json.dumps(snap))  # JSON に保存した形（キーが文字列）に合わせる


def seed_hash(case):
    """ケースの種と今日の日付（「2 日前」の日付が入るので、日が変わると立て直す）から作る。"""
    raw = json.dumps(case["seed"], sort_keys=True, ensure_ascii=False) + datetime.date.today().isoformat()
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def ensure_seed(repo, case):
    """種が立っていて、中身が記録と一致すれば使い回す。違えば全部消して立て直す。(番号, 立て直したか) を返す。"""
    check_eval_repo(repo)
    with _LOCK:
        cur = _load_state().get(repo)
    if cur and cur["case"] == case["id"] and cur["hash"] == seed_hash(case) and _norm(snapshot(repo)) == cur["snapshot"]:
        return cur["nums"], False
    reset_repo(repo)
    nums = seed_repo(repo, case)
    with _LOCK:
        st = _load_state()
        st[repo] = {"case": case["id"], "hash": seed_hash(case), "nums": nums, "snapshot": _norm(snapshot(repo))}
        _save_state(st)
    return nums, True


def restore(repo):
    """試行の後に、エージェントが変えたものだけを種の状態へ戻す。エージェントが新しく作った Issue は削除する。
    戻せない変更（種の Issue の削除・type・親子の変更、種のコメントの削除）があれば、記録を捨てて、次の試行で全部立て直す。
    戻せたら True。"""
    check_eval_repo(repo)
    r = f"{OWNER}/{repo}"
    with _LOCK:
        cur = _load_state().get(repo)
    if not cur:
        return False
    target, clean = cur["snapshot"], True
    try:
        live = _norm(snapshot(repo))
        for n, t in target.items():
            lv = live.get(n)
            if lv is None or any(lv[k] != t[k] for k in ("type", "parent", "subIssues")) or not set(t["comment_ids"]) <= set(lv["comment_ids"]):
                clean = False
                continue
            for cid in set(lv["comment_ids"]) - set(t["comment_ids"]):
                gh("api", "-X", "DELETE", f"repos/{r}/issues/comments/{cid}")
            if lv["title"] != t["title"] or lv["body"] != t["body"]:
                gh("issue", "edit", n, "-R", r, "--title", t["title"], "--body", t["body"])
            add, rem = set(t["labels"]) - set(lv["labels"]), set(lv["labels"]) - set(t["labels"])
            if add or rem:
                gh("issue", "edit", n, "-R", r, *(["--add-label", ",".join(sorted(add))] if add else []), *(["--remove-label", ",".join(sorted(rem))] if rem else []))
            if lv["state"] != t["state"]:
                if t["state"] == "OPEN":
                    gh("issue", "reopen", n, "-R", r)
                else:
                    gh("issue", "close", n, "-R", r, "--reason", "completed")
        for n in set(live) - set(target):
            gh("issue", "delete", n, "-R", r, "--yes")
        clean = clean and _norm(snapshot(repo)) == target
    except RuntimeError:
        clean = False
    if not clean:
        with _LOCK:
            st = _load_state()
            st.pop(repo, None)
            _save_state(st)
    return clean
