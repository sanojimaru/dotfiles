#!/usr/bin/env python3
"""issue-planning の評価の実行器（#88 の基準。dotfiles#91）。

  run_eval.py check  <case> [--repo ipe-1]            種を立て、何もしない手本（null）・正解の手本（oracle）・誤った手本（bad）を採点する
  run_eval.py trial  <case> --cond with|without --agent claude|codex [--repo ipe-1]
  run_eval.py batch  <case,case,...> --n 3 [--cond with,without] [--agent claude] [--repos ipe-1,ipe-2] [--out DIR]
  run_eval.py report <DIR...>
  run_eval.py labels <DIR...> --out DIR                 判定器の較正のために、返事を人が yes/no を付けられる形（labels.md）に出す
  run_eval.py agreement <human.json> <answers.json>     人のラベルと判定器の一致率（90% 以上で使う）

固定の評価用リポジトリ（非公開の `ipe-N`）を使い回す。種が立っていれば使い回し、試行の後は、エージェントが変えたものだけを戻す
（戻せないときだけ、Issue を全部削除して種を立て直す）。
`gh` は見張り（gh_guard.py）、`orca` は代役（fake_orca.py）を PATH の先頭に置く。
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from common import (BUDGET_USD, CLAUDE_MODEL, CLAUDE_TOOLS, CODEX_MODEL, HERE, LEAK, REAL_GH, REAL_ORCA, SKILL_DIR, OWNER,
                    STRIP_ENV, WALL_SECONDS, gh)
from calibrate import cmd_agreement, cmd_labels
from grading import grade, read_calls
from holdout import load_holdout
from seed import ensure_seed, orca_state, pr_state, reset_repo, restore, seed_repo, snapshot, subst


def make_workdir(repo, case, nums, cond, agent, root):
    clone = root / "clone"
    gh("repo", "clone", f"{OWNER}/{repo}", str(clone), "--", "--quiet")
    skills_root = clone / (".claude/skills" if agent == "claude" else ".agents/skills")
    skills_root.mkdir(parents=True)
    shutil.copytree(Path.home() / ".agents/skills/orchestration", skills_root / "orchestration")
    if cond == "with":
        dst = skills_root / "issue-planning"
        dst.mkdir()
        shutil.copy(SKILL_DIR / "SKILL.md", dst / "SKILL.md")
        if (SKILL_DIR / "references").is_dir():
            shutil.copytree(SKILL_DIR / "references", dst / "references")
    bindir = root / "bin"
    bindir.mkdir()
    for name, src in (("orca", "fake_orca.py"), ("gh", "gh_guard.py")):
        text = (HERE / src).read_text().replace("@@GH_REAL@@", REAL_GH).replace("@@ORCA_REAL@@", REAL_ORCA)
        (bindir / name).write_text(text)
        (bindir / name).chmod(0o755)
    state = root / "orca-state.json"
    state.write_text(json.dumps(orca_state(case, nums, clone), ensure_ascii=False))
    shutil.copy(HERE / "pr_replay.py", bindir)
    (root / "pr-state.json").write_text(json.dumps(pr_state(case, nums, repo), ensure_ascii=False))
    return clone, bindir, state


def draft_for(cond):
    text = (HERE / "agents-md-draft.md").read_text()
    return text_for(text, cond)


def text_for(text, cond):
    if cond == "with":
        return text.replace("<!--skill-->", "").replace("<!--/skill-->", "")
    return re.sub(r"<!--skill-->.*?<!--/skill-->", "", text, flags=re.S)


def agent_env(bindir, state, log, repo, extra=None):
    env = {k: v for k, v in os.environ.items() if not STRIP_ENV.match(k)}
    env.update({
        "PATH": f"{bindir}:{env['PATH']}", "ORCA_FAKE_STATE": str(state), "ORCA_FAKE_LOG": str(log),
        "GH_GUARD_REPO": f"{OWNER}/{repo}", "IPE_PR_STATE": str(state.with_name("pr-state.json")), "GIT_TERMINAL_PROMPT": "0",
    })
    env.update(extra or {})
    return env


def run_claude(prompt, clone, env, cond, out, history=None):
    draft = out / "agents-md.md"
    draft.write_text(draft_for(cond))
    env = dict(env, CLAUDE_CODE_DISABLE_CLAUDE_MDS="1", CLAUDE_CODE_DISABLE_AUTO_MEMORY="1")
    argv = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--model", CLAUDE_MODEL,
            "--setting-sources", "project,local", "--strict-mcp-config", "--permission-mode", "bypassPermissions",
            "--append-system-prompt-file", str(draft), "--max-budget-usd", str(BUDGET_USD)]

    def launch(text, path, session_id=None, warmup=False):
        resume = ["--resume", session_id] if session_id else []
        return run_proc([*argv, *resume, "--tools", "" if warmup else CLAUDE_TOOLS, "--", text], clone, env, path)

    return run_session("claude", prompt, history, out, launch)


def run_codex(prompt, clone, env, cond, out, history=None):
    home = out / "codex-home"
    home.mkdir()
    (home / "AGENTS.md").write_text(draft_for(cond))
    (home / "auth.json").symlink_to(Path.home() / ".codex/auth.json")
    user_home = out / "codex-user"
    user_home.mkdir()
    gh_config = os.environ.get("GH_CONFIG_DIR") or str(Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "gh")
    # HOME を変えると mise の shim が元のランタイムを見つけないため、評価の代役に必要な実体を固定する。
    bindir = out / "bin"
    (bindir / "python3").symlink_to(sys.executable)
    jq = shutil.which("jq")
    if jq and "mise/shims" in jq:
        try:
            install = Path(subprocess.check_output(["mise", "where", "jq"], text=True).strip())
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError("Codex の評価で使う jq の実体が見つかりません") from exc
        jq = next((str(p) for p in (install / "bin/jq", install / "jq") if p.is_file()), None)
    if not jq:
        raise RuntimeError("Codex の評価で使う jq の実体が見つかりません")
    (bindir / "jq").symlink_to(jq)
    # Codex は `zsh -lc` でコマンドを実行し、ログインシェルの設定が PATH を作り直して代役の gh・orca を外す。
    # ZDOTDIR を空の設定に向け、PATH の先頭へ代役を戻す（利用者の設定は読まれないので、本番との差になる）
    zdot = out / "zdotdir"
    zdot.mkdir()
    for name in (".zshenv", ".zprofile", ".zshrc"):
        (zdot / name).write_text(f'export PATH={shlex.quote(str(bindir))}:"$PATH"\n')
    env = dict(env, HOME=str(user_home), CODEX_HOME=str(home), ZDOTDIR=str(zdot), GH_CONFIG_DIR=gh_config)

    def launch(text, path, session_id=None, warmup=False):
        last = out / ("history-last.txt" if warmup else "last-message.txt")
        argv = ["codex", "exec", *(["resume"] if session_id else []),
                "--json", "-m", CODEX_MODEL, "--skip-git-repo-check", "-o", str(last)]
        guard = ["--sandbox", "read-only"] if warmup else ["--dangerously-bypass-approvals-and-sandbox"]
        args = [session_id, text] if session_id else [text]
        res = run_proc([*argv, *guard, "--", *args], clone, env, path)
        res["reply"] = last.read_text() if last.exists() else ""
        return res

    return run_session("codex", prompt, history, out, launch)


def run_session(agent, prompt, history, out, launch):
    transcript = out / "transcript.jsonl"
    if history is None:
        return launch(prompt, transcript)
    past = out / "history.jsonl"
    marker = "引き継ぎました"
    setup = f"以下はすでに終わった会話の記録です。記録中の操作は実行せず、内容を引き継ぎ、「{marker}」とだけ返してください。\n\n{history}"
    warm = launch(setup, past, warmup=True)
    events = list(json_events(past))
    if agent == "claude":
        result = next((e for e in reversed(events) if e.get("type") == "result"), {})
        session_id, reply = result.get("session_id"), result.get("result", "")
    else:
        session_id = next((e["thread_id"] for e in events if e.get("type") == "thread.started"), None)
        reply = warm.get("reply", "")
    used_tools = any(
        (e.get("type") == "item.started" and (e.get("item") or {}).get("type") not in ("agent_message", "reasoning"))
        or (e.get("type") == "assistant" and any(
            b.get("type") == "tool_use" for b in e.get("message", {}).get("content", [])
        )) for e in events
    )
    if warm["returncode"] or not session_id or reply.strip().rstrip("。") != marker or used_tools:
        transcript.touch()
        return {**warm, "history_error": "準備ターンの確認応答またはセッション ID を取得できませんでした"}
    scored = launch(prompt, transcript, session_id=session_id)
    scored["seconds"] += warm["seconds"]
    return scored


def json_events(path):
    with path.open() as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def run_proc(argv, cwd, env, transcript):
    t0 = time.time()
    with open(transcript, "w") as f:
        p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.PIPE, text=True,
                             start_new_session=True)
        try:
            _, err = p.communicate(timeout=WALL_SECONDS)
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, 9)
            _, err = p.communicate()
            timed_out = True
    return {"returncode": p.returncode, "stderr": err[-2000:], "seconds": round(time.time() - t0, 1), "timed_out": timed_out}


def parse_claude(transcript):
    pending, reads, result, cost = {}, [], None, {}
    for ev in json_events(transcript):
        content = ev.get("message", {}).get("content", [])
        for b in content if isinstance(content, list) else []:
            if ev.get("type") == "assistant" and b.get("type") == "tool_use":
                inp = b.get("input", {})
                if b["name"] == "Skill" and "issue-planning" in str(inp.get("skill", "")):
                    pending[b["id"]] = "Skill"
                if b["name"] == "Read" and "issue-planning" in str(inp.get("file_path", "")):
                    pending[b["id"]] = inp["file_path"]
            if ev.get("type") == "user" and b.get("type") == "tool_result" and b.get("tool_use_id") in pending and not b.get("is_error"):
                reads.append(pending.pop(b["tool_use_id"]))  # 読み込みは、成功した結果が返ったものだけ数える
        if ev.get("type") == "result":
            result = ev
            cost = {"usd": ev.get("total_cost_usd"), "turns": ev.get("num_turns"), "usage": ev.get("usage")}
    return {"reply": (result or {}).get("result", ""), "result_event": result, "skill_reads": reads, "cost": cost}


def parse_codex(transcript):
    reads, usage = [], None
    for ev in json_events(transcript):
        item = ev.get("item") or {}
        if ev.get("type") == "item.completed" and item.get("type") == "command_execution" and item.get("exit_code") == 0 \
                and "issue-planning" in item.get("command", "") and "SKILL.md" in item.get("command", "") \
                and re.search(r"(^|[\s'\"])(cat|sed|head|tail|less|more|bat|nl|awk)\s", item.get("command", "")):  # ls・find は読み込みではない
            reads.append(item["command"])
        if ev.get("type") == "turn.completed":
            usage = ev.get("usage")
    return {"skill_reads": reads, "cost": {"usd": None, "usage": usage}}


def load_cases(names, holdout_repo):
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in names):
        raise ValueError("ケース名には英数字・ハイフン・アンダースコアだけを使ってください")
    if holdout_repo:
        return load_holdout(holdout_repo, names)
    return [json.loads((HERE / "cases" / f"{name}.json").read_text()) for name in names]


def prepare(case, repo, cond, agent, out):
    if case.get("split") == "test":
        reset_repo(repo)
        nums = seed_repo(repo, case)  # test の種を共有の repo-state.json に記録しない。
    else:
        nums, _ = ensure_seed(repo, case)
    clone, bindir, state = make_workdir(repo, case, nums, cond, agent, out)
    log = out / "calls.jsonl"
    log.write_text("")
    before = snapshot(repo)
    return nums, clone, bindir, state, log, before


def _trial(case, repo, cond, agent, out, use_judge=True):
    out.mkdir(parents=True, exist_ok=True)
    try:
        nums, clone, bindir, state, log, before = prepare(case, repo, cond, agent, out)
        env = agent_env(bindir, state, log, repo)
        prompt = subst(text_for(case["prompt"], cond), nums)
        history = subst(text_for(case["history"], cond), nums) if "history" in case else None
        run_agent = run_claude if agent == "claude" else run_codex
        res = run_agent(prompt, clone, env, cond, out, history=history)
    except RuntimeError as e:  # 種や起動の失敗はエージェントの失敗に数えない。
        rec = {"case": case["id"], "cond": cond, "agent": agent, "repo": repo, "infra_failure": True, "run": {"seconds": 0}, "error": str(e)}
        (out / "trial.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        return rec
    parsed = (parse_claude if agent == "claude" else parse_codex)(out / "transcript.jsonl")
    if history is not None:
        if res.get("history_error"):
            parsed["cost"] = (parse_claude if agent == "claude" else parse_codex)(out / "history.jsonl")["cost"]
        elif agent == "codex":
            warm_usage = parse_codex(out / "history.jsonl")["cost"]["usage"]
            trial_usage = parsed["cost"]["usage"]
            if warm_usage and trial_usage:
                parsed["cost"]["usage"] = {k: warm_usage.get(k, 0) + v for k, v in trial_usage.items()}
    res.update({k: v for k, v in parsed.items() if k != "reply" or agent == "claude"})
    try:
        after = snapshot(repo)
    except RuntimeError as e:  # 終状態を読めなかった試行は、被験の失敗に数えず、やり直す
        rec = {"case": case["id"], "cond": cond, "agent": agent, "repo": repo, "infra_failure": True, "run": {"seconds": res["seconds"]}, "error": str(e)}
        (out / "trial.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        return rec
    ctx = {"calls": read_calls(log), "state": json.loads(state.read_text()), "nums": nums, "before": before, "after": after}
    infra = bool(res.get("history_error")) or (res["returncode"] != 0 and not res["timed_out"] and not (res.get("result_event") or {}).get("subtype", "").startswith("error_max"))
    if agent == "claude" and (res.get("result_event") or {}).get("is_error") and not str((res["result_event"] or {}).get("subtype", "")).startswith("error_max"):
        infra = True
    rec = {"case": case["id"], "cond": cond, "agent": agent, "repo": repo, "infra_failure": infra, "run": {k: res[k] for k in ("returncode", "seconds", "timed_out", "skill_reads", "cost") if k in res},
           "reply": res.get("reply", "")}
    if res.get("history_error"):
        rec["error"] = res["history_error"]
    if not infra:
        try:
            rec["grade"] = grade(case, ctx, res.get("reply", ""), agent, out, use_judge)
            rec["loaded_skill"] = bool(res.get("skill_reads"))
        except RuntimeError as e:  # 判定器の失敗は、被験の失敗に数えず、やり直す
            rec["infra_failure"], rec["error"] = True, str(e)
    (out / "trial.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    (out / "after.json").write_text(json.dumps(after, ensure_ascii=False, indent=2, default=str))
    return rec


def trial(case, repo, cond, agent, out, use_judge=True):
    rec = None
    try:
        rec = _trial(case, repo, cond, agent, out, use_judge)
    finally:
        try:
            clean_trial(case, repo)
        except RuntimeError as exc:
            if rec is None:
                raise
            rec.update(infra_failure=True, error=f"試行後の種を削除できませんでした: {exc}")
            (out / "trial.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    return rec


def clean_trial(case, repo):
    if case.get("split") == "test":
        reset_repo(repo)
    else:
        restore(repo)


def cmd_check(args):
    """配線の確認: 採点器が null・oracle・bad に正しく答えるか（#88 7.3 の 4）。"""
    case, = load_cases([args.case], args.holdout_repo)
    rows = []
    for kind in ("null", "oracle", "bad"):
        steps = {"null": [], "oracle": case.get("oracle", []), "bad": case.get("bad")}[kind]
        if steps is None:
            continue
        out = Path(tempfile.mkdtemp(prefix=f"ipe-check-{kind}-"))
        try:
            nums, clone, bindir, state, log, before = prepare(case, args.repo, "with", "claude", out)
            env = agent_env(bindir, state, log, args.repo)
            for step in steps:
                argv = [subst(a, nums) for a in step]
                subprocess.run(argv, env=env, cwd=clone, capture_output=True, text=True)
            ctx = {"calls": read_calls(log), "state": json.loads(state.read_text()), "nums": nums, "before": before, "after": snapshot(args.repo)}
            g = grade(case, ctx, "", "claude", out, use_judge=False)
        finally:
            clean_trial(case, args.repo)
            shutil.rmtree(out, ignore_errors=True)
        rows.append({"kind": kind, "pass_code": g["pass_code"], "checks": g["checks"], "fail_on_any": g["fail_on_any"]})
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_trial(args):
    out = Path(args.out or tempfile.mkdtemp(prefix="ipe-trial-")).resolve()
    case, = load_cases([args.case], args.holdout_repo)
    rec = trial(case, args.repo, args.cond, args.agent, out)
    print(json.dumps({"out": str(out), **{k: rec[k] for k in ("case", "cond", "infra_failure")}, "grade": rec.get("grade"), "run": rec["run"]}, ensure_ascii=False, indent=2))


def cmd_batch(args):
    cases = load_cases(args.cases.split(","), args.holdout_repo)
    conds = args.cond.split(",")
    repos = args.repos.split(",")
    out_root = Path(args.out or Path.home() / ".cache/issue-planning-eval" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")).resolve()
    jobs = [(c, cond, i) for c in cases for cond in conds for i in range(args.n)]
    random.Random(args.seed).shuffle(jobs)  # 有と無を混ぜて流す（#88 6）
    # リポジトリはケースごとに割り当てる（種が立ったままのリポジトリを使い回し、立て直しを減らす）。足りなければ全ケースで共有する
    shared = list(repos)
    pools = {c["id"]: (repos[i::len(cases)] if len(repos) >= len(cases) else shared) for i, c in enumerate(cases)}
    lock, cv = threading.Lock(), threading.Condition()

    def work(job):
        case, cond, i = job
        pool = pools[case["id"]]
        with cv:
            cv.wait_for(lambda: pool)
            repo = pool.pop()
        try:
            for attempt in range(3):  # 原因がエージェントの外の失敗だけ、やり直す
                d = out_root / f"{case['id']}-{cond}-{args.agent}-{i}" / f"try{attempt}"
                rec = trial(case, repo, cond, args.agent, d)
                if not rec["infra_failure"]:
                    break
            with lock:
                print(json.dumps({"case": case["id"], "cond": cond, "i": i, "infra": rec["infra_failure"], "pass_code": (rec.get("grade") or {}).get("pass_code"), "usd": rec["run"].get("cost", {}).get("usd")}, ensure_ascii=False), flush=True)
            return rec
        finally:
            with cv:
                pool.append(repo)
                cv.notify()

    with concurrent.futures.ThreadPoolExecutor(len(repos)) as ex:
        list(ex.map(work, jobs))
    print(f"out: {out_root}")


def cmd_report(args):
    rows = {}
    paths = [p for d in args.dir for p in sorted([*Path(d).glob("*/try*/trial.json"), *Path(d).glob("trial.json")])]  # batch の形と、trial --out の形
    for p in paths:
        r = json.loads(p.read_text())
        key = (r["case"], r["cond"], r["agent"])
        g = rows.setdefault(key, {"n": 0, "pass_code": 0, "pass_all": 0, "fail_on_any": 0, "infra": 0, "usd": 0.0, "sec": 0.0, "loaded": 0, "judge_no": 0})
        if r["infra_failure"]:
            g["infra"] += 1
            g["usd"] += r["run"].get("cost", {}).get("usd") or 0  # 失敗した試行の費用も合計に入れる（件数には入れない）
            continue
        gr = r["grade"]
        g["n"] += 1
        g["pass_code"] += gr["pass_code"]
        g["pass_all"] += gr["pass_all"]
        g["fail_on_any"] += bool(gr["fail_on_any"])
        g["loaded"] += r.get("loaded_skill", False)
        g["judge_no"] += sum(v is not True for v in gr["judge"].values())
        usd = r["run"].get("cost", {}).get("usd")
        g["usd_unknown"] = g.get("usd_unknown", 0) + (usd is None)  # Codex は費用を返さない。0 とは数えない
        g["usd"] += usd or 0
        g["sec"] += r["run"]["seconds"]
    print("case / cond / agent: n pass_code pass_all fail_on_any loaded infra  usd/試行 sec/試行")
    for (case, cond, agent), g in sorted(rows.items()):
        n = max(g["n"], 1)
        usd = "$n/a" if g.get("usd_unknown") else f"${g['usd'] / n:.2f}"
        print(f"{case} / {cond} / {agent}: n={g['n']} code={g['pass_code']} all={g['pass_all']} fail_on_any={g['fail_on_any']} loaded={g['loaded']} infra={g['infra']}  {usd}  {g['sec'] / n:.0f}s")
    partial = "（費用を返さない試行を含まない一部の合計）" if any(g.get("usd_unknown") for g in rows.values()) else ""
    print(f"合計 usd: ${sum(g['usd'] for g in rows.values()):.2f}{partial}")
    leaks = [str(p.parent) for d in args.dir for p in [*Path(d).glob("*/try*/transcript.jsonl"), *Path(d).glob("transcript.jsonl")] if LEAK.search(p.read_text())]
    print(f"本番の環境の漏れ（Phase 0 の 1・3）: {len(leaks)} 件", *leaks, sep="\n  ")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check"); p.add_argument("case"); p.add_argument("--repo", default="ipe-1"); p.set_defaults(f=cmd_check)
    p.add_argument("--holdout-repo", help="test ケースを取得する非公開の owner/repo（標準入力にトークンが必要）")
    p = sub.add_parser("trial"); p.add_argument("case"); p.add_argument("--cond", required=True, choices=["with", "without"]); p.add_argument("--agent", default="claude", choices=["claude", "codex"]); p.add_argument("--repo", default="ipe-1"); p.add_argument("--out"); p.set_defaults(f=cmd_trial)
    p.add_argument("--holdout-repo", help="test ケースを取得する非公開の owner/repo（標準入力にトークンが必要）")
    p = sub.add_parser("batch"); p.add_argument("cases"); p.add_argument("--n", type=int, default=3); p.add_argument("--cond", default="with,without"); p.add_argument("--agent", default="claude", choices=["claude", "codex"]); p.add_argument("--repos", default="ipe-1,ipe-2,ipe-3,ipe-4"); p.add_argument("--out"); p.add_argument("--seed", type=int, default=91); p.set_defaults(f=cmd_batch)
    p.add_argument("--holdout-repo", help="test ケースを取得する非公開の owner/repo（標準入力にトークンが必要）")
    p = sub.add_parser("labels"); p.add_argument("dir", nargs="+"); p.add_argument("--out", required=True); p.add_argument("--seed", type=int, default=91); p.set_defaults(f=cmd_labels)
    p = sub.add_parser("agreement"); p.add_argument("human"); p.add_argument("answers"); p.set_defaults(f=cmd_agreement)
    p = sub.add_parser("report"); p.add_argument("dir", nargs="+"); p.set_defaults(f=cmd_report)
    args = ap.parse_args()
    if args.cmd in ("trial", "batch") and args.holdout_repo and not args.out:
        ap.error("holdout の試行ログは --out で非共有ディレクトリを指定してください")
    args.f(args)


if __name__ == "__main__":
    main()
