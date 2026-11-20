"""種（評価用リポジトリの Issue と、代役の orca の状態）を立てる・読む。"""
import datetime
import hashlib
import json
import re
import threading
from pathlib import Path

from common import OWNER, check_eval_repo, gh

# 評価用リポジトリごとに、立ててある種（ケース・番号・読んだときの状態）を覚える。試行の後は、エージェントが変えたものだけを戻す
STATE_FILE = Path.home() / ".cache/issue-planning-eval/repo-state.json"
_LOCK = threading.Lock()


def reset_repo(repo):
    check_eval_repo(repo)
    r = f"{OWNER}/{repo}"
    nums = json.loads(gh("issue", "list", "-R", r, "--state", "all", "--limit", "1000", "--json", "number") or "[]")
    for n in nums:
        gh("issue", "delete", str(n["number"]), "-R", r, "--yes")


def subst(text, nums):
    two_days = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    text = text.replace("<<date-2d>>", two_days)
    return re.sub(r"<<([a-z0-9]+)>>", lambda m: str(nums[m.group(1)]), text)


def seed_repo(repo, case):
    check_eval_repo(repo)
    r = f"{OWNER}/{repo}"
    have = {x["name"] for x in json.loads(gh("label", "list", "-R", r, "--limit", "200", "--json", "name"))}
    for lab in case["seed"].get("labels", []):  # ラベルは使い回す（作成の回数が GitHub の二次レート制限に効くため）
        if lab["name"] not in have:
            gh("label", "create", lab["name"], "-R", r, "--description", lab.get("description", ""))
    nums = {}
    for iss in case["seed"]["issues"]:
        args = ["issue", "create", "-R", r, "--title", subst(iss["title"], nums), "--body", subst(iss["body"], nums)]
        if iss.get("type"):
            args += ["--type", iss["type"]]
        for lab in iss.get("labels", []):
            args += ["--label", lab]
        if iss.get("parent"):
            args += ["--parent", str(nums[iss["parent"]])]
        url = gh(*args).strip()
        nums[iss["key"]] = int(url.rsplit("/", 1)[1])
        for body in iss.get("comments", []):
            gh("issue", "comment", str(nums[iss["key"]]), "-R", r, "--body", subst(body, nums))
        if iss.get("state") == "closed":
            gh("issue", "close", str(nums[iss["key"]]), "-R", r, "--reason", "completed")
    return nums


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


def orca_state(case, nums, clone):
    o = case["orca"]
    wts = [{"issue": None, "name": "main", "path": str(clone), "identity": "wt2:local:main"}]
    for w in o["worktrees"]:
        issue = nums[w["issue"]]
        name = subst(w["name"], nums)
        wts.append({"issue": issue, "name": name, "path": f"/fake/worktrees/{name}", "identity": f"wt2:local:{name}"})
    return {
        "repo_id": "fake-repo", "run_id": o["run_id"], "run_objective": o["run_objective"], "worktrees": wts,
        "workers": [{"issue": nums[w["issue"]], "liveness": w["liveness"], "state": w["state"]} for w in o["workers"]],
    }


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
