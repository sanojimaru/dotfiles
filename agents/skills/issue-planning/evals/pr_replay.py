"""種に含まれる PR の読み取りを、GitHub に接続せず再生する。"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit


def replay(argv, repo, endpoint):
    is_pr = argv[0] == "pr"
    path = urlsplit(endpoint)
    pulls = re.fullmatch(rf"repos/{re.escape(repo)}/pulls(?:/(\d+))?/?", path.path)
    if not is_pr and not pulls and not path.path.startswith(f"repos/{repo}/pulls/"):
        return None
    if "--help" in argv or "-h" in argv:
        return None
    try:
        records = json.loads(Path(os.environ["IPE_PR_STATE"]).read_text())
        if is_pr:
            return cli(argv[1:], records)
        if not pulls:
            raise ValueError("再生する REST エンドポイントは pulls と pulls/<番号> です")
        return api(argv[1:], path, pulls[1], records)
    except SystemExit as exc:  # argparse の失敗も gh_guard のログに残す。
        return exc.code
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"gh_guard (PR の再生): {exc}", file=sys.stderr)
        return 1


def select(records, state, head=None, base=None):
    if state not in {"open", "closed", "merged", "all"}:
        raise ValueError(f"不明な state: {state}")
    matching = [
        pr for pr in records
        if (state == "all" or pr["state"].lower() == state or state == "closed" and pr["closed"])
        and (head is None or pr["headRefName"] == head)
        and (base is None or pr["baseRefName"] == base)
    ]
    return sorted(matching, key=lambda pr: (pr["createdAt"], pr["number"]), reverse=True)


def output(data, jq=None):
    raw = json.dumps(data, ensure_ascii=False)
    if jq is not None:
        return subprocess.run(["jq", "-r", jq], input=raw, text=True).returncode
    print(raw)
    return 0


def cli(argv, records):
    parser = argparse.ArgumentParser(prog="gh pr", add_help=False)
    parser.add_argument("command", choices=("list", "ls", "view"))
    parser.add_argument("selector", nargs="?")
    parser.add_argument("-R", "--repo")
    parser.add_argument("-s", "--state", default="open")
    parser.add_argument("-H", "--head")
    parser.add_argument("-B", "--base")
    parser.add_argument("-L", "--limit", type=int, default=30)
    parser.add_argument("-S", "--search")
    parser.add_argument("-A", "--author")
    parser.add_argument("-l", "--label", action="append", default=[])
    parser.add_argument("-c", "--comments", action="store_true")
    parser.add_argument("--json", dest="fields")
    parser.add_argument("-q", "--jq")
    args = parser.parse_intermixed_args(argv)
    if args.command == "view":
        ref = args.selector or subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
        if match := re.match(r"^https://github\.com/[^/]+/[^/]+/pull/(\d+)(?:[/?#]|$)", ref):
            ref = match[1]
        if re.fullmatch(r"#\d+", ref):
            ref = ref[1:]
        pr = next((p for p in records if ref in {str(p["number"]), p["url"], p["headRefName"]}), None)
        if pr is None:
            raise ValueError(f"PR {ref} が見つかりません")
        if args.fields:
            return output(project(pr, args.fields), args.jq)
        if args.comments:
            for comment in pr["comments"]:
                print(comment["body"])
            return 0
        print(f'title:\t{pr["title"]}\nstate:\t{pr["state"]}\nnumber:\t{pr["number"]}\nurl:\t{pr["url"]}\n--\n{pr["body"]}')
        return 0
    results = select(records, args.state, args.head, args.base)
    if args.author:
        author = os.environ["GH_GUARD_REPO"].split("/")[0] if args.author == "@me" else args.author
        results = [p for p in results if p["author"]["login"] == author]
    if args.label:
        labels = set(",".join(args.label).split(","))
        results = [p for p in results if labels <= {label["name"] for label in p["labels"]}]
    if args.search:
        terms = shlex.split(args.search.lower())
        results = [p for p in results if all(matches(p, term) for term in terms)]
    if args.limit <= 0:
        raise ValueError("--limit は正の整数を指定してください")
    results = results[:args.limit]
    if args.fields:
        return output([project(p, args.fields) for p in results], args.jq)
    for p in results:
        print(f'{p["number"]}\t{p["title"]}\t{p["headRefName"]}\t{p["state"]}\t{p["createdAt"]}')
    return 0


def matches(pr, term):
    if term in ("is:open", "is:closed", "is:merged"):
        return pr["closed"] if term == "is:closed" else pr["state"].lower() == term[3:]
    if re.fullmatch(r"(?:closes:|linked:)?#\d+", term):
        issue = int(term.split("#")[1])
        return any(ref["number"] == issue for ref in pr["closingIssuesReferences"])
    if term.isdecimal():
        return term == str(pr["number"]) or any(term == str(ref["number"]) for ref in pr["closingIssuesReferences"])
    return any(term in str(value).lower() for value in (
        pr["title"], pr["body"], pr["headRefName"], (pr["mergeCommit"] or {}).get("oid", ""),
    ))


def project(record, fields):
    names = fields.split(",")
    if unknown := set(names) - record.keys():
        raise ValueError(f"種に無いフィールド: {', '.join(sorted(unknown))}")
    return {name: record[name] for name in names}


def api(argv, endpoint, number, records):
    parser = argparse.ArgumentParser(prog="gh api", add_help=False)
    parser.add_argument("endpoint")
    parser.add_argument("-X", "--method")
    parser.add_argument("-H", "--header", action="append")
    parser.add_argument("-F", "--field", "-f", "--raw-field", action="append", default=[])
    parser.add_argument("-q", "--jq")
    parser.add_argument("--cache")  # 種は試行中に変わらない。
    parser.add_argument("--paginate", action="store_true")
    parser.add_argument("--slurp", action="store_true")
    parser.add_argument("--silent", action="store_true")
    args = parser.parse_intermixed_args(argv)
    method = args.method or ("POST" if args.field else "GET")
    if method.upper() != "GET":
        raise ValueError("PR の変更は評価中は使えません")
    query = dict([*parse_qsl(endpoint.query), *[p.split("=", 1) for p in args.field]])
    if number:
        record = next((p for p in records if str(p["number"]) == number), None)
        if record is None:
            raise ValueError(f"PR {number} が見つかりません")
        data = rest(record, detail=True)
    else:
        state = query.get("state", "open")
        head = query.get("head")
        rows = select(records, state, head.split(":")[-1] if head else None, query.get("base"))
        data = [rest(p, detail=False) for p in rows]
        if not args.paginate:
            size, page = int(query.get("per_page", "30")), int(query.get("page", "1"))
            data = data[(page - 1) * size:page * size]
    if not args.silent:
        return output([data] if args.slurp else data, args.jq)
    return 0


def rest(pr, *, detail):
    record = {
        "number": pr["number"], "title": pr["title"], "body": pr["body"], "html_url": pr["url"],
        "state": "closed" if pr["closed"] else "open", "draft": pr["isDraft"],
        "head": {"ref": pr["headRefName"]}, "base": {"ref": pr["baseRefName"]},
        "created_at": pr["createdAt"], "closed_at": pr["closedAt"], "merged_at": pr["mergedAt"],
        "merge_commit_sha": (pr["mergeCommit"] or {}).get("oid"),
    }
    if detail:
        record["merged"] = pr["state"] == "MERGED"
    return record
