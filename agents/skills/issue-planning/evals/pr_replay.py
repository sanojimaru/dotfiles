"""種に含まれる PR の読み取りを、GitHub に接続せず再生する。"""
import argparse
import datetime
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit


def api_method(argv):
    separate = next((argv[i + 1] for i, arg in enumerate(argv[:-1]) if arg in ("-X", "--method")), "")
    attached = next((re.sub(r"^(--method=|-X=?)", "", arg) for arg in argv if re.match(r"(--method=|-X.)", arg)), "")
    return (separate or attached).upper()


def replay(argv, repo, endpoint, event, fields=None):
    is_pr = argv[0] in ("pr", "stack")
    path = urlsplit(endpoint)
    pulls = re.fullmatch(rf"repos/{re.escape(repo)}/pulls(?:/(\d+)(/merge(?:-async)?)?)?/?", path.path)
    if not is_pr and not pulls and not path.path.startswith(f"repos/{repo}/pulls/"):
        return None
    if "--help" in argv or "-h" in argv:
        return None
    try:
        records = json.loads(Path(os.environ["IPE_PR_STATE"]).read_text())
        if is_pr:
            if argv[0] == "stack" and argv[1:2] in (["sync"], ["view"]):
                layers = [pr for pr in records if "replay_checks" in pr]
                if not layers:
                    raise ValueError("この試行には再生するスタックがありません")
                active = [pr for pr in layers if pr["state"] == "OPEN"]
                for pr in active:
                    print(f"#{pr['number']}\t{pr['headRefName']}\t{pr['state']}")
                if not active:
                    print("残りのスタック層はありません。")
                return 0
            if argv[1:2] == ["close"]:
                return close(argv[2:], records, event)
            if argv[1:2] in (["checks"], ["diff"], ["merge"]):
                return lifecycle(argv[1:], records, event)
            return cli(argv[1:], records, event)
        if not pulls:
            raise ValueError("再生する REST エンドポイントは pulls と pulls/<番号> です")
        if pulls[2]:
            method = api_method(argv) or ("POST" if fields else "GET")
            if method == "PUT":
                options = ["--match-head-commit", fields["sha"]] if fields and "sha" in fields else []
                return lifecycle(["merge", pulls[1], *options], records, event, rest_output=True)
            if method != "GET":
                raise ValueError("PR のマージ状況の取得には GET、マージの実行には PUT を指定してください")
            return 0 if find_pr(records, pulls[1])["state"] == "MERGED" else 1
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
        return subprocess.run(["jq", "-r", "-c", jq], input=raw, text=True).returncode  # gh の --jq と同じく、1 行で出す
    print(raw)
    return 0


def find_pr(records, selector=None):
    ref = selector or subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    if match := re.match(r"^https://github\.com/[^/]+/[^/]+/pull/(\d+)(?:[/?#]|$)", ref):
        ref = match[1]
    if re.fullmatch(r"#\d+", ref):
        ref = ref[1:]
    pr = next((p for p in records if ref in {str(p["number"]), p["url"], p["headRefName"]}), None)
    if pr is None:
        raise ValueError(f"PR {ref!r} が見つかりません")
    return pr


def lifecycle(argv, records, event, rest_output=False):
    parser = argparse.ArgumentParser(prog="gh pr")
    parser.add_argument("command")
    parser.add_argument("selector", nargs="?")
    parser.add_argument("-R", "--repo")
    parser.add_argument("--json", dest="fields")
    parser.add_argument("-q", "--jq")
    parser.add_argument("--match-head-commit")
    parser.add_argument("--merge-method")
    parser.add_argument("-b", "--body")
    parser.add_argument("-F", "--body-file")
    parser.add_argument("-t", "--subject")
    parser.add_argument("-i", "--interval")
    parser.add_argument("--color")
    parser.add_argument("-A", "--author-email")
    for flag in ("--watch", "--required", "--fail-fast", "--name-only", "--patch", "--yes", "-y", "--admin"):
        parser.add_argument(flag, action="store_true")
    parser.add_argument("-m", "--merge", action="store_true")
    parser.add_argument("-s", "--squash", action="store_true")
    parser.add_argument("-r", "--rebase", action="store_true")
    parser.add_argument("-d", "--delete-branch", action="store_true")
    args = parser.parse_intermixed_args(argv)
    pr = find_pr(records, args.selector)
    if "replay_checks" not in pr:
        raise ValueError("この PR の CI とマージは再生しません")
    checks = pr["replay_checks"]
    passed = all(c["bucket"] == "pass" for c in checks)
    if args.command == "checks":
        if args.fields:
            return output([project(c, args.fields) for c in checks], args.jq)
        for check in checks:
            print(f"{check['name']}\t{check['state']}\t{check.get('description', '')}")
        if any(c["bucket"] == "pending" for c in checks):
            return 8
        return int(not passed)
    if args.command == "diff":
        print("\n".join(f["path"] for f in pr["files"]) if args.name_only else pr.get("replay_diff", ""))
        return 0
    event.update(event="merge_attempted", issue=pr["number"])
    if not passed or pr["state"] != "OPEN" or pr["isDraft"] or any(label["name"] == "hold-merge" for label in pr["labels"]) or (
        args.match_head_commit and args.match_head_commit != pr["headRefOid"]
    ):
        raise ValueError("PR はマージできる状態ではありません")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    pr.update(state="MERGED", closed=True, mergedAt=now, closedAt=now,
              mergedBy=pr["author"], mergeCommit={"oid": pr["headRefOid"]})
    Path(os.environ["IPE_PR_STATE"]).write_text(json.dumps(records, ensure_ascii=False))
    event.update(event="merged", issue=pr["number"])
    if rest_output:
        output({"merged": True, "sha": pr["mergeCommit"]["oid"], "message": "Pull Request successfully merged"})
    else:
        print(f"Merged #{pr['number']}: {pr['title']}")
    return 0


def close(argv, records, event):
    """取り下げの片付けで、マージしない PR を閉じる（dotfiles#190 の S7-C1）。"""
    parser = argparse.ArgumentParser(prog="gh pr close")
    parser.add_argument("selector")  # 本物も、番号・URL・ブランチのどれかを要る
    parser.add_argument("-R", "--repo")
    parser.add_argument("-c", "--comment")
    parser.add_argument("-d", "--delete-branch", action="store_true")
    args = parser.parse_intermixed_args(argv)
    if args.delete_branch:  # ブランチの削除は再生しない。黙って成功させると、片付けが済んだと読まれる
        raise ValueError("評価では `gh pr close --delete-branch` を再生しません。ブランチは git で消してください")
    pr = find_pr(records, args.selector)
    if pr["state"] != "OPEN":
        raise ValueError(f"Pull request #{pr['number']} is already {pr['state'].lower()}")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    pr.update(state="CLOSED", closed=True, closedAt=now)
    if args.comment:
        pr.setdefault("comments", []).append({"body": args.comment, "author": pr["author"]})
    Path(os.environ["IPE_PR_STATE"]).write_text(json.dumps(records, ensure_ascii=False))
    event.update(event="pr_closed", issue=pr["number"])
    print(f"✓ Closed pull request #{pr['number']} ({pr['title']})")
    return 0


def cli(argv, records, event):
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
        pr = find_pr(records, args.selector)
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
    event["rows"] = len(results)  # GitHub の予算の見積もり（grading.graphql_points）に使う
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
