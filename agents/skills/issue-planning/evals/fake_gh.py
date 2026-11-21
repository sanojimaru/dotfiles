"""種の Issue とラベルを、GitHub に接続せずに返す（評価の既定）。書き込みは手元の状態（IPE_GH_STATE）に記録する。

gh_guard が、PR の再生の次にここへ渡す。代役が返せないコマンドは断り、本物の GitHub へは流さない。
GitHub の API の上限は利用者の全リポジトリ・全エージェントで共有しているため、評価の試行では本物を呼ばない（dotfiles#138）。
本物とのずれは、`run_eval.py --gh real` で少数の試行を流して確かめる（README）。
"""
import argparse
import contextlib
import datetime
import fcntl
import json
import os
import re
import shlex
import sys
from pathlib import Path

from pr_replay import api_method, output

OWNER = "sanojimaru"
# 評価用リポジトリにある既定のラベルと Issue の type（種のラベルは、これに足す）
DEFAULT_LABELS = ["bug", "documentation", "duplicate", "enhancement", "good first issue", "help wanted", "invalid",
                  "question", "wontfix"]
TYPES = {"Task": "A specific piece of work", "Bug": "An unexpected problem or behavior",
         "Feature": "A request, idea, or new functionality"}
FIELDS = ["assignees", "author", "body", "closed", "closedAt", "closedByPullRequestsReferences", "comments", "createdAt",
          "id", "isPinned", "issueType", "labels", "milestone", "number", "parent", "projectCards", "projectItems",
          "reactionGroups", "state", "stateReason", "subIssues", "subIssuesSummary", "title", "updatedAt", "url"]


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_state(repo, labels, start=1):
    names = list(dict.fromkeys([*DEFAULT_LABELS, *(label["name"] for label in labels)]))
    described = {label["name"]: label.get("description", "") for label in labels}
    return {"repo": repo, "labels": [{"name": n, "description": described.get(n, ""), "color": "ededed"} for n in names],
            "issues": [], "next_number": start, "next_comment": 7_100_000_000}


def add_issue(state, title, body, *, labels=(), type_=None, parent=None, created=None):
    known = {label["name"] for label in state["labels"]}
    if missing := [name for name in labels if name not in known]:
        raise ValueError(f"could not add label: '{missing[0]}' not found")
    if type_ is not None and type_ not in TYPES:
        raise ValueError(f"issue type '{type_}' not found")
    if parent is not None:
        find(state, parent)
    n = state["next_number"]
    state["next_number"] += 1
    stamp = created or now()
    issue = {"number": n, "title": title, "body": body, "state": "OPEN", "stateReason": None, "labels": list(labels),
             "type": type_, "parent": parent, "comments": [], "createdAt": stamp, "updatedAt": stamp, "closedAt": None}
    state["issues"].append(issue)
    return issue


def add_comment(state, issue, body):
    state["next_comment"] += 1
    issue["comments"].append({"id": state["next_comment"], "body": body, "createdAt": now()})
    issue["updatedAt"] = now()
    return issue["comments"][-1]


def set_state(issue, closed, reason=None):
    issue.update(state="CLOSED" if closed else "OPEN", updatedAt=now(),
                 stateReason=(reason or "COMPLETED") if closed else "REOPENED", closedAt=now() if closed else None)


def snapshot(state):
    """`seed.snapshot()` と同じ形（採点の before・after）。"""
    return {
        i["number"]: {
            "title": i["title"], "body": i["body"], "state": i["state"],
            "stateReason": None if i["state"] == "OPEN" else i["stateReason"],
            "labels": sorted(i["labels"]), "type": i["type"],
            "comments": [c["body"] for c in i["comments"]], "comment_ids": [c["id"] for c in i["comments"]],
            "parent": i["parent"], "subIssues": sorted(s["number"] for s in children(state, i["number"])),
        }
        for i in state["issues"]
    }


def load():
    return json.loads(Path(os.environ["IPE_GH_STATE"]).read_text())


def save(state):
    path = Path(os.environ["IPE_GH_STATE"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False))
    tmp.replace(path)  # 読む側に書きかけの JSON を見せない


@contextlib.contextmanager
def locked():
    """被験エージェントは gh を並行で呼ぶので、読んでから書くまでを 1 つずつにする。"""
    with open(os.environ["IPE_GH_STATE"] + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def url(state, n):
    return f"https://github.com/{state['repo']}/issues/{n}"


def find(state, selector):
    ref = str(selector)
    if match := re.match(r"^https://github\.com/[^/]+/[^/]+/issues/(\d+)", ref):
        ref = match[1]
    ref = ref.lstrip("#")
    issue = next((i for i in state["issues"] if str(i["number"]) == ref), None)
    if issue is None:
        raise ValueError(f"GraphQL: Could not resolve to an issue or pull request with the number of {ref}. (repository.issue)")
    return issue


def children(state, n):
    return [i for i in state["issues"] if i["parent"] == n]


def node(state, issue):
    return {"id": f"I_eval{issue['number']}", "number": issue["number"], "state": issue["state"],
            "title": issue["title"], "url": url(state, issue["number"])}


def graphql_view(state, issue, field):
    n = issue["number"]
    if field == "number":
        return n
    if field in ("title", "body", "state", "createdAt", "updatedAt", "closedAt"):
        return issue[field]
    if field == "stateReason":
        return issue["stateReason"] or ""
    if field == "closed":
        return issue["state"] == "CLOSED"
    if field == "id":
        return f"I_eval{n}"
    if field == "url":
        return url(state, n)
    if field == "author":
        return {"id": "U_eval", "is_bot": False, "login": OWNER, "name": ""}
    if field in ("assignees", "projectCards", "projectItems", "reactionGroups"):
        return []
    if field in ("milestone",):
        return None
    if field == "isPinned":
        return False
    if field == "labels":
        described = {label["name"]: label for label in state["labels"]}
        return [{"id": f"LA_eval_{name}", "name": name, "description": described[name]["description"],
                 "color": described[name]["color"]} for name in issue["labels"]]
    if field == "issueType":
        t = issue["type"]
        return {"id": f"IT_eval_{t}", "name": t, "description": TYPES[t], "color": "GRAY"} if t else None
    if field == "comments":
        return [{"id": f"IC_eval{c['id']}", "author": {"login": OWNER}, "authorAssociation": "OWNER", "body": c["body"],
                 "createdAt": c["createdAt"], "includesCreatedEdit": False, "isMinimized": False, "minimizedReason": "",
                 "reactionGroups": [], "url": f"{url(state, n)}#issuecomment-{c['id']}", "viewerDidAuthor": True}
                for c in issue["comments"]]
    if field == "parent":
        return node(state, find(state, issue["parent"])) if issue["parent"] else None
    if field == "subIssues":
        nodes = [node(state, s) for s in children(state, n)]
        return {"nodes": nodes, "totalCount": len(nodes)}
    if field == "subIssuesSummary":
        subs = children(state, n)
        done = sum(s["state"] == "CLOSED" for s in subs)
        return {"completed": done, "percentCompleted": done * 100 // len(subs) if subs else 0, "total": len(subs)}
    if field == "closedByPullRequestsReferences":
        records = json.loads(Path(os.environ["IPE_PR_STATE"]).read_text()) if os.environ.get("IPE_PR_STATE") else []
        return [{"id": f"PR_eval{p['number']}", "number": p["number"], "url": p["url"]} for p in records
                if any(ref["number"] == n for ref in p.get("closingIssuesReferences", []))]
    raise KeyError(field)


def project(state, issue, fields):
    names = [f.strip() for f in fields.split(",") if f.strip()]
    if unknown := [f for f in names if f not in FIELDS]:
        raise ValueError(f'Unknown JSON field: "{unknown[0]}"\nAvailable fields:\n  ' + "\n  ".join(FIELDS))
    return {f: graphql_view(state, issue, f) for f in names}


def labels_of(values):
    return [name.strip() for value in values for name in value.split(",") if name.strip()]



def parser(prog, *flags, **valued):
    p = argparse.ArgumentParser(prog=prog, add_help=False)
    p.add_argument("-R", "--repo")
    for flag in flags:
        p.add_argument(*flag.split("|"), action="store_true")
    for name, spec in valued.items():
        names, kwargs = (spec, {}) if isinstance(spec, str) else spec
        if names.startswith("-"):
            p.add_argument(*names.split("|"), dest=name, **kwargs)
        else:
            p.add_argument(names, **kwargs)  # 位置引数は、名前がそのまま dest になる
    return p


def handle(argv, input_body=None):
    """返したら終了コード。`--help` は本物の説明を出すため None を返す。"""
    if "--help" in argv or "-h" in argv or argv in (["--version"], ["version"]):
        return None
    try:
        with locked():
            return dispatch(argv, input_body)
    except SystemExit as exc:  # argparse の失敗も gh_guard のログに残す
        return exc.code
    except (KeyError, OSError, ValueError) as exc:
        print(f"gh_guard (Issue の代役): {exc}", file=sys.stderr)
        return 1


def dispatch(argv, input_body):
    state = load()
    if argv[:1] == ["issue"] and len(argv) > 1:
        rc = issue_cmd(state, argv[1], argv[2:], input_body)
    elif argv[:2] == ["label", "list"]:
        rc = label_list(state, argv[2:])
    else:
        raise ValueError(f"`gh {' '.join(argv[:2])}` は評価の代役では使えません")
    return rc


def issue_cmd(state, cmd, argv, input_body):
    if cmd in ("list", "ls"):
        args = parser("gh issue list", "-w|--web", state=("-s|--state", {"default": "open"}),
                      label=("-l|--label", {"action": "append", "default": []}), type_="--type",
                      limit=("-L|--limit", {"type": int, "default": 30}), search="-S|--search", author="-A|--author",
                      assignee="-a|--assignee", app="--app", milestone="-m|--milestone", mention="--mention",
                      fields="--json", jq="-q|--jq", template="-t|--template").parse_intermixed_args(argv)
        if args.template or args.web:
            raise ValueError("--template と --web は評価の代役では使えません。--json と --jq を使ってください")
        if args.state not in ("open", "closed", "all"):
            raise ValueError(f'invalid argument "{args.state}" for "-s, --state" flag: valid values are {{open|closed|all}}')
        if args.limit <= 0:
            raise ValueError(f"invalid limit: {args.limit}")
        rows = [i for i in state["issues"] if args.state == "all" or i["state"].lower() == args.state]
        if wanted := set(labels_of(args.label)):
            rows = [i for i in rows if wanted <= set(i["labels"])]
        if args.type_:
            rows = [i for i in rows if (i["type"] or "").lower() == args.type_.lower()]
        if args.assignee or args.mention or args.milestone or args.app or args.author not in (None, OWNER, "@me"):
            rows = []  # 種の Issue は、すべて OWNER が立てたもので、担当者・メンション・マイルストーンが無い
        if args.search:
            rows = [i for i in rows if all(matches(state, i, term) for term in shlex.split(args.search))]
        rows = sorted(rows, key=lambda i: i["number"], reverse=True)[:args.limit]
        if args.fields:
            return output([project(state, i, args.fields) for i in rows], args.jq)
        for i in rows:
            print(f"{i['number']}\t{i['state']}\t{i['title']}\t{', '.join(i['labels'])}\t{i['updatedAt']}")
        return 0
    if cmd == "view":
        args = parser("gh issue view", "-c|--comments", "-w|--web", selector=("selector", {"nargs": "?"}),
                      fields="--json", jq="-q|--jq", template="-t|--template").parse_intermixed_args(argv)
        if args.template or args.web:
            raise ValueError("--template と --web は評価の代役では使えません。--json と --jq を使ってください")
        if not args.selector:
            raise ValueError("argument required: issue number or URL")
        issue = find(state, args.selector)
        if args.fields:
            return output(project(state, issue, args.fields), args.jq)
        labels = ", ".join(issue["labels"])
        print(f"title:\t{issue['title']}\nstate:\t{issue['state']}\nauthor:\t{OWNER}\nlabels:\t{labels}\n"
              f"comments:\t{len(issue['comments'])}\nassignees:\t\nprojects:\t\nmilestone:\t\nnumber:\t{issue['number']}\n--")
        print(issue["body"])
        if args.comments:
            for c in issue["comments"]:
                print(f"--\nauthor:\t{OWNER}\nassociation:\towner\nedited:\tfalse\nstatus:\tnone\n--\n{c['body']}")
        return 0
    if cmd == "status":
        print(f"Relevant issues in {state['repo']}\n\nIssues assigned to you\n  There are no issues assigned to you")
        return 0
    raise ValueError(f"`gh issue {cmd}` は評価の代役では使えません")


def matches(state, issue, term):
    """`gh issue list --search` の、種で判定できる修飾子と語句。"""
    negate = term.startswith("-")
    key, _, value = term.lstrip("-").partition(":")
    value = value.strip('"').lower()
    if not _:
        text = " ".join([issue["title"], issue["body"], *(c["body"] for c in issue["comments"])]).lower()
        return term.lower() in text
    if key in ("is", "state"):
        hit = value in ("issue", issue["state"].lower()) or (value == "closed" and issue["state"] == "CLOSED")
    elif key == "label":
        hit = value in {name.lower() for name in issue["labels"]}
    elif key == "type":
        hit = (issue["type"] or "").lower() == value
    elif key in ("no", "has"):
        present = {"label": bool(issue["labels"]), "type": bool(issue["type"]), "parent-issue": bool(issue["parent"]),
                   "sub-issue": bool(children(state, issue["number"])), "assignee": False, "milestone": False}
        if value not in present:
            raise ValueError(f"評価の代役は `{term}` に対応していません")
        hit = present[value] if key == "has" else not present[value]
    elif key == "parent-issue":
        hit = issue["parent"] is not None and value.split("#")[-1] == str(issue["parent"])
    elif key in ("repo", "sort", "in"):
        return True
    else:
        raise ValueError(f"評価の代役は `{term}` に対応していません")
    return hit != negate


def label_list(state, argv):
    args = parser("gh label list", "-w|--web", limit=("-L|--limit", {"type": int, "default": 30}), search="-S|--search",
                  fields="--json", jq="-q|--jq", order="--order", sort="--sort").parse_intermixed_args(argv)
    rows = [label for label in state["labels"] if not args.search or args.search.lower() in
            (label["name"] + label["description"]).lower()][:args.limit]
    if args.fields:
        names = args.fields.split(",")
        return output([{f: {"id": f"LA_eval_{label['name']}", "isDefault": label["name"] in DEFAULT_LABELS,
                            "url": f"https://github.com/{state['repo']}/labels/{label['name']}",
                            "createdAt": "", "updatedAt": "", **label}.get(f) for f in names} for label in rows], args.jq)
    for label in rows:
        print(f"{label['name']}\t{label['description']}\t#{label['color']}")
    return 0
