#!/usr/bin/env python3
"""issue-planning の評価の実行器（#88 の基準。dotfiles#91）。

  run_eval.py check  <case> [--repo ipe-1]            種を立て、何もしない手本（null）・正解の手本（oracle）・誤った手本（bad）を採点する
  run_eval.py trial  <case> --cond with|without --agent claude|codex [--repo ipe-1]
  run_eval.py batch  <case,case,...> --n 3 [--cond with,without] [--agent claude] [--repos ipe-1,ipe-2] [--out DIR]
  run_eval.py report <DIR...>
  run_eval.py labels <DIR...> --out DIR [--count 20]    判定器の較正のために、判定器の証拠を人が yes/no を付けられる形（labels.md）に出す
  run_eval.py agreement <human.json> <answers.json>     人のラベルと判定器の一致率（90% 以上で使う）

固定の評価用リポジトリ（非公開の `ipe-N`）を使い回す。種が立っていれば使い回し、試行の後は、エージェントが変えたものだけを戻す
（戻せないときだけ、Issue を全部削除して種を立て直す）。
`gh` は見張り（gh_guard.py）、`orca` は代役（fake_orca.py）を PATH の先頭に置く。
既定（`--gh fake`）では、種を GitHub でなく手元の状態に立て、`gh` の Issue・ラベル・api も代役（fake_gh.py）が返す。
GitHub の API の上限は利用者の全リポジトリ・全エージェントで共有しているため（dotfiles#138）。`--gh real` は、代役と本物のずれを確かめるときだけ使う。
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
                    STRIP_ENV, WALL_SECONDS, gh, sh)
from calibrate import cmd_agreement, cmd_labels
from grading import grade, read_calls
from holdout import audit_transcript, hide_holdout
import fake_gh
from seed import ensure_seed, orca_state, pr_state, reset_repo, restore, seed_local, seed_repo, snapshot, subst


def make_workdir(repo, case, nums, cond, agent, root, fake):
    repo_clone = root / "clone"
    if fake:  # 評価用リポジトリと同じ中身を手元に作る（clone も GitHub の API を呼ぶ）
        repo_clone.mkdir()
        seed_git(repo_clone, "init", "--quiet", "-b", "main")
        seed_commit(repo_clone, {"README.md": f"# {repo}\n"}, "neutral readme")
        seed_git(repo_clone, "remote", "add", "origin", f"https://github.com/{OWNER}/{repo}.git")
        seed_git(repo_clone, "update-ref", "refs/remotes/origin/main", "HEAD")
    else:
        gh("repo", "clone", f"{OWNER}/{repo}", str(repo_clone), "--", "--quiet")
    files = case["seed"].get("files", {})
    if files:
        seed_commit(repo_clone, files, "Prepare repository files")
        seed_git(repo_clone, "update-ref", "refs/remotes/origin/main", "HEAD")
    orca = orca_state(case, nums, repo_clone, repo)
    clone = repo_clone
    for spec, wt in zip(case["orca"]["worktrees"], orca["worktrees"][1:]):
        if not spec.get("checkout"):
            continue
        checkout = root / wt["name"]
        seed_git(repo_clone, "worktree", "add", "--quiet", "-b", wt["name"], str(checkout))
        if committed := spec.get("committed"):
            seed_commit(checkout, committed, "Update documentation")
        seed_git(checkout, "update-ref", f"refs/remotes/origin/{wt['name']}", "HEAD")
        seed_git(checkout, "branch", f"--set-upstream-to=origin/{wt['name']}")
        wt["path"] = str(checkout)
        wt["checkout"] = True
        write_files(checkout, spec.get("changes", {}))
        if spec.get("current"):
            clone = checkout
    if clone != repo_clone:
        with (repo_clone / ".git/info/exclude").open("a") as exclude:
            exclude.write("\n/.claude/skills/\n/.agents/skills/\n")
    prs = pr_state(case, nums, repo)
    local_branches = {wt["name"] for wt in orca["worktrees"] if wt.get("checkout")}
    local_prs = [pr for pr in prs if (case["split"] == "dev" or fake) and pr["headRefName"] in local_branches]
    for pr in local_prs:
        pr["headRefOid"] = seed_git(repo_clone, "rev-parse", f"refs/heads/{pr['headRefName']}").strip()
        if pr["state"] == "MERGED":
            seed_git(repo_clone, "-c", "user.name=Repository Maintainer", "-c", "user.email=maintainer@example.invalid",
                     "merge", "--no-edit", "--no-gpg-sign", pr["headRefOid"])
            pr["mergeCommit"] = {"oid": seed_git(repo_clone, "rev-parse", "HEAD").strip()}
    if case["split"] == "holdout" or local_prs or fake:
        remote = root / "push.git"
        seed_git(repo_clone, "init", "--bare", "--quiet", "-b", "main", str(remote))
        # dev で PR とローカルのブランチを照合するケースと代役では、fetch でも種の状態が残るようにする。
        push_only = ["--push"] if not (local_prs or fake) else []
        seed_git(repo_clone, "remote", "set-url", *push_only, "origin", str(remote))
        seed_git(repo_clone, "push", "--all", "origin")
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
    state.write_text(json.dumps(orca, ensure_ascii=False))
    shutil.copy(HERE / "pr_replay.py", bindir)
    shutil.copy(HERE / "fake_gh.py", bindir)
    for pr in prs:
        if "replay_checks" in pr:
            pr["headRefOid"] = seed_git(repo_clone, "rev-parse", f"refs/heads/{pr['headRefName']}").strip()
    (root / "pr-state.json").write_text(json.dumps(prs, ensure_ascii=False))
    return clone, bindir, state


def write_files(directory, files):
    for name, text in files.items():
        path = directory / name
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)


def seed_git(directory, *args):
    result = sh(["git", *args], cwd=directory)
    if result.returncode:
        raise RuntimeError(f"Git の種を作れません: {result.stderr.strip()}")
    return result.stdout


def seed_commit(directory, files, title):
    write_files(directory, files)
    seed_git(directory, "add", "-A")
    seed_git(directory, "-c", "user.name=Repository Maintainer", "-c", "user.email=maintainer@example.invalid",
             "commit", "--no-gpg-sign", "--allow-empty", "-m", title)


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
    if (gh_state := state.with_name("gh-state.json")).exists():
        env["IPE_GH_STATE"] = str(gh_state)
    env.update(extra or {})
    return env


def isolated_zdotdir(out):
    # zsh の起動ファイルを分け、利用者の PATH 設定に代役を上書きさせない。
    zdot = out / "zdotdir"
    zdot.mkdir()
    for name in (".zshenv", ".zprofile", ".zshrc"):
        (zdot / name).write_text(f'export PATH={shlex.quote(str(out / "bin"))}:"$PATH"\n')
    return str(zdot)


def trial_tmp(out):
    """被験の一時ディレクトリを試行ごとに分ける。`$TMPDIR/x.md` のような固定名のファイルを、並行する試行と共有しないため
    （dotfiles#173）。macOS の mktemp は TMPDIR でなく利用者ごとの一時ディレクトリに乱数の名前で作るので、衝突しない。
    zsh はヒアドキュメントの一時ファイルを $TMPPREFIX（既定 /tmp/zsh）に作るので、隔離した /tmp の外に向ける。"""
    (out / "tmp").mkdir()
    (out / "zsh-tmp").mkdir()
    return {"TMPDIR": f"{out / 'tmp'}/", "TMPPREFIX": str(out / "zsh-tmp" / "zsh")}


def sb_string(path):
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def tmp_sandbox(out):
    """並行する試行や前のセッションと `/tmp` の固定名のファイルを共有しないよう、被験から `/private/tmp` を読み書きさせない。
    Claude Code 自身が使う `/private/tmp/claude-<uid>` だけは許す。被験が書いた `/tmp/x.md` が、別の試行の同名の
    ファイルの中身のまま Issue と `ask` に送られた（dotfiles#171）。Codex は採点の起動で自分の sandbox を使わないので包める。
    準備ターン（`--sandbox read-only`）は Codex が sandbox-exec を使い、入れ子にできないので包まない。"""
    profile = out / "tmp-sandbox.sb"
    profile.write_text(
        "(version 1)\n(allow default)\n"
        '(deny file-read* file-write* (subpath "/private/tmp"))\n'
        f'(allow file-read* file-write* (literal "/private/tmp") (subpath "/private/tmp/claude-{os.getuid()}"))\n'
        # Claude Code の Bash ツールは、コマンドごとの作業ディレクトリを乱数の名前の /tmp/claude-<hex>-cwd に書く
        '(allow file-read* file-write* (regex #"^/private/tmp/claude-[0-9a-f]+-cwd$"))\n'
        # 出力先が /tmp の下でも、被験は自分の試行のファイル（指示書の下書き・clone・代役）を読み書きする
        f'(allow file-read* file-write* (subpath {sb_string(out.resolve())}))\n'
        # Codex は CODEX_HOME を正規化するので、出力先の祖先の stat を許す
        + "".join(f"(allow file-read-metadata (literal {sb_string(p)}))\n" for p in out.resolve().parents)
    )
    return ["sandbox-exec", "-f", str(profile)]


def run_claude(prompt, clone, env, cond, out, history=None, followup=None):
    draft = out / "agents-md.md"
    draft.write_text(draft_for(cond))
    env = dict(env, CLAUDE_CODE_DISABLE_CLAUDE_MDS="1", CLAUDE_CODE_DISABLE_AUTO_MEMORY="1",
               CLAUDE_CODE_SHELL="/bin/zsh", ZDOTDIR=isolated_zdotdir(out), **trial_tmp(out))
    argv = [*tmp_sandbox(out), "claude", "-p", "--output-format", "stream-json", "--verbose", "--model", CLAUDE_MODEL,
            "--setting-sources", "project,local", "--strict-mcp-config", "--permission-mode", "bypassPermissions",
            "--append-system-prompt-file", str(draft), "--max-budget-usd", str(BUDGET_USD)]

    def launch(text, path, session_id=None, warmup=False, timeout=WALL_SECONDS):
        resume = ["--resume", session_id] if session_id else []
        return run_proc([*argv, *resume, "--tools", "" if warmup else CLAUDE_TOOLS, "--", text], clone, env, path, timeout)

    return run_session("claude", prompt, history, out, launch, followup)


def run_codex(prompt, clone, env, cond, out, history=None, followup=None):
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
    env = dict(env, HOME=str(user_home), CODEX_HOME=str(home), ZDOTDIR=isolated_zdotdir(out), GH_CONFIG_DIR=gh_config,
               **trial_tmp(out))
    sandbox = tmp_sandbox(out)

    def launch(text, path, session_id=None, warmup=False, timeout=WALL_SECONDS):
        last = out / ("last-message.txt" if path.name == "transcript.jsonl" else f"{path.stem}-last.txt")
        argv = ["codex", "exec", *(["resume"] if session_id else []),
                "--json", "-m", CODEX_MODEL, "--skip-git-repo-check", "-o", str(last)]
        guard = ["--sandbox", "read-only"] if warmup else ["--dangerously-bypass-approvals-and-sandbox"]
        args = [session_id, text] if session_id else [text]
        res = run_proc([*([] if warmup else sandbox), *argv, *guard, "--", *args], clone, env, path, timeout)
        res["reply"] = last.read_text() if last.exists() else ""
        return res

    return run_session("codex", prompt, history, out, launch, followup)


def session_reply(agent, path, result):
    events = list(json_events(path))
    if agent == "claude":
        final = next((e for e in reversed(events) if e.get("type") == "result"), {})
        return final.get("session_id"), final.get("result", ""), events
    session_id = next((e["thread_id"] for e in events if e.get("type") == "thread.started"), None)
    return session_id, result.get("reply", ""), events


def run_session(agent, prompt, history, out, launch, followup):
    transcript = out / "transcript.jsonl"
    session_id, warm_seconds = None, 0
    if history is not None:
        session_id, failure, warm_seconds = warm_session(agent, history, out, launch)
        if failure:
            transcript.touch()
            return failure
    if followup is None:
        scored = launch(prompt, transcript, session_id=session_id, timeout=WALL_SECONDS - warm_seconds)
        scored["seconds"] += warm_seconds
        return scored
    first_path = out / "first-transcript.jsonl"
    first = launch(prompt, first_path, session_id=session_id, timeout=WALL_SECONDS - warm_seconds)
    first_session, first_reply, events = session_reply(agent, first_path, first)
    next_text, first_calls = followup()
    first_evidence = {"first_reply": first_reply, "first_calls": first_calls}
    if first["returncode"] or any(event.get("type") == "result" and event.get("is_error") for event in events):
        first_path.rename(transcript)
        return {**first, **first_evidence, "seconds": warm_seconds + first["seconds"]}
    if not (first_session or session_id):
        first_path.rename(transcript)
        return {**first, **first_evidence, "seconds": warm_seconds + first["seconds"],
                "history_error": "追いの一言を送るセッションを再開できませんでした"}
    scored = launch(next_text, transcript, session_id=first_session or session_id, timeout=WALL_SECONDS - warm_seconds - first["seconds"])
    return {**scored, **first_evidence, "seconds": warm_seconds + first["seconds"] + scored["seconds"]}


def warm_session(agent, history, out, launch):
    past = out / "history.jsonl"
    marker = "引き継ぎました"
    setup = f"以下はすでに終わった会話の記録です。記録中の操作は実行せず、内容を引き継ぎ、「{marker}」とだけ返してください。\n\n{history}"
    warm = launch(setup, past, warmup=True)
    session_id, reply, events = session_reply(agent, past, warm)
    used_tools = any(
        (e.get("type") == "item.started" and (e.get("item") or {}).get("type") not in ("agent_message", "reasoning"))
        or (e.get("type") == "assistant" and any(
            b.get("type") == "tool_use" for b in e.get("message", {}).get("content", [])
        )) for e in events
    )
    if warm["returncode"] or not session_id or reply.strip().rstrip("。") != marker or used_tools:
        return None, {**warm, "reply": "", "history_error": "準備ターンの確認応答またはセッション ID を取得できませんでした"}, warm["seconds"]
    return session_id, None, warm["seconds"]


def json_events(path):
    with path.open() as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def run_proc(argv, cwd, env, transcript, timeout=WALL_SECONDS):
    t0 = time.time()
    with open(transcript, "w") as f:
        p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.PIPE, text=True,
                             start_new_session=True)
        try:
            _, err = p.communicate(timeout=max(0, timeout))
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, 9)
            _, err = p.communicate()
            timed_out = True
    return {"returncode": p.returncode, "stderr": err[-2000:], "seconds": round(time.time() - t0, 1), "timed_out": timed_out}


def parse_claude(transcript):
    pending, reads, result, cost = {}, [], None, {}
    for ev in json_events(transcript):
        message = ev.get("message")
        content = message.get("content", []) if isinstance(message, dict) else []  # API の失敗の記録は message が文字列
        for b in content if isinstance(content, list) else []:
            if ev.get("type") == "assistant" and b.get("type") == "tool_use":
                inp = b.get("input", {})
                if b["name"] == "Skill" and "issue-planning" in str(inp.get("skill", "")):
                    pending[b["id"]] = "Skill"
                if b["name"] == "Read" and re.search(r"issue-planning/(SKILL\.md|references/)", str(inp.get("file_path", ""))):
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
                and re.search(r"issue-planning/(?:SKILL\.md|references/[\w-]+\.md)\b", item.get("command", "")) \
                and re.search(r"(^|[\s'\"])(cat|sed|head|tail|less|more|bat|nl|awk)\s", item.get("command", "")):  # ls・find は読み込みではない
            reads.append(item["command"])
        if ev.get("type") == "turn.completed":
            usage = ev.get("usage")
    return {"skill_reads": reads, "cost": {"usd": None, "usage": usage}}


def load_cases(names, split):
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in names):
        raise ValueError("ケース名には英数字・ハイフン・アンダースコアだけを使ってください")
    directory = HERE / {"dev": "cases", "holdout": "holdout"}[split]
    cases = []
    for name in names:
        case = json.loads((directory / f"{name}.json").read_text())
        if case.get("id") != name or case.get("split") != split:
            raise ValueError(f"{name} の id または split が正しくありません")
        cases.append(case)
    return cases


def prepare(case, repo, cond, agent, out, fake):
    if fake:
        nums, gh_state = seed_local(case, repo)
        (out / "gh-state.json").write_text(json.dumps(gh_state, ensure_ascii=False))
    elif case.get("split") == "holdout":
        reset_repo(repo)
        nums = seed_repo(repo, case)  # 評価データセットの種を共有の repo-state.json に記録しない。
    else:
        nums, _ = ensure_seed(repo, case)
    clone, bindir, state = make_workdir(repo, case, nums, cond, agent, out, fake)
    log = out / "calls.jsonl"
    log.write_text("")
    before = read_snapshot(repo, out, fake)
    return nums, clone, bindir, state, log, before


def read_snapshot(repo, out, fake):
    if fake:
        return fake_gh.snapshot(json.loads((out / "gh-state.json").read_text()))
    return snapshot(repo)


def spec_prompt(case, nums, repo, clone):
    """ワーカーのケースは、`references/spec.md` の型に番号とパスを入れて渡す。型を直すと、次の試行から変わった型で走る。"""
    block = re.search(r"```text\n(.*?)```", (SKILL_DIR / "references/spec.md").read_text(), re.S)[1]
    spec = case["spec"]
    text = (block.replace("<owner>/<repo>#<作業 Issue の番号>", f"{OWNER}/{repo}#{nums[spec['issue']]}")
            .replace("（Epic #<番号> の親、または単独タスクを担当する窓口）", f"（Epic #{nums[spec['epic']]} の親）")
            .replace("<この Issue の作業時間の目安>", spec["hours"])
            .replace("path:<worktree の絶対パス>", f"path:{clone}"))
    if leftover := re.findall(r"<(?:owner|番号|作業 Issue の番号|この Issue の作業時間の目安|worktree の絶対パス)[^<>\n]*>", text):
        raise RuntimeError(f"spec の型に埋めていない箇所があります: {leftover}")
    return text


def _trial(case, repo, cond, agent, out, use_judge=True, fake=True):
    out.mkdir(parents=True, exist_ok=True)
    try:
        nums, clone, bindir, state, log, before = prepare(case, repo, cond, agent, out, fake)
        env = agent_env(bindir, state, log, repo)
        prompt = spec_prompt(case, nums, repo, clone) if "spec" in case else subst(text_for(case["prompt"], cond), nums)
        history = subst(text_for(case["history"], cond), nums) if "history" in case else None
        run_agent = run_claude if agent == "claude" else run_codex
        followup = None
        if "followup" in case:
            followup = lambda: (subst(case["followup"], nums), read_calls(log))
        res = run_agent(prompt, clone, env, cond, out, history=history, followup=followup)
    except RuntimeError as e:  # 種や起動の失敗はエージェントの失敗に数えない。
        rec = {"case": case["id"], "cond": cond, "agent": agent, "repo": repo, "infra_failure": True, "run": {"seconds": 0}, "error": str(e)}
        (out / "trial.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        return rec
    parsed = (parse_claude if agent == "claude" else parse_codex)(out / "transcript.jsonl")
    if (out / "first-transcript.jsonl").exists():
        parse = parse_claude if agent == "claude" else parse_codex
        first = parse(out / "first-transcript.jsonl")
        parsed["skill_reads"] = first["skill_reads"] + parsed["skill_reads"]
        if agent == "claude":
            for key in ("usd", "turns"):
                amounts = [cost.get(key) for cost in (first["cost"], parsed["cost"])]
                if any(value is not None for value in amounts):
                    parsed["cost"][key] = sum(value or 0 for value in amounts)
        elif first["cost"]["usage"] and parsed["cost"]["usage"]:
            usage = parsed["cost"]["usage"]
            for key, value in first["cost"]["usage"].items():
                usage[key] = usage.get(key, 0) + value
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
        after = read_snapshot(repo, out, fake)
    except RuntimeError as e:  # 終状態を読めなかった試行は、被験の失敗に数えず、やり直す
        rec = {"case": case["id"], "cond": cond, "agent": agent, "repo": repo, "infra_failure": True, "run": {"seconds": res["seconds"]}, "error": str(e)}
        (out / "trial.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        return rec
    ctx = {"calls": read_calls(log), "state": json.loads(state.read_text()), "nums": nums, "before": before, "after": after,
           "clone": clone, "first_reply": res.get("first_reply", ""), "first_calls": res.get("first_calls", [])}
    infra = bool(res.get("history_error")) or (res["returncode"] != 0 and not res["timed_out"] and not (res.get("result_event") or {}).get("subtype", "").startswith("error_max"))
    if agent == "claude" and (res.get("result_event") or {}).get("is_error") and not str((res["result_event"] or {}).get("subtype", "")).startswith("error_max"):
        infra = True
    rec = {"case": case["id"], "cond": cond, "agent": agent, "repo": repo, "infra_failure": infra, "run": {k: res[k] for k in ("returncode", "seconds", "timed_out", "skill_reads", "cost") if k in res},
           "reply": res.get("reply", "")}
    if "first_reply" in res:
        rec["first_reply"] = res["first_reply"]
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


def trial(case, repo, cond, agent, out, use_judge=True, fake=True):
    rec = None
    try:
        rec = _trial(case, repo, cond, agent, out, use_judge, fake)
    finally:
        try:
            if not fake:
                clean_trial(case, repo)
        except RuntimeError as exc:
            if rec is None:
                raise
            rec.update(infra_failure=True, error=f"試行後の種を削除できませんでした: {exc}")
            (out / "trial.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    return rec


def clean_trial(case, repo):
    if case.get("split") == "holdout":
        reset_repo(repo)
    else:
        restore(repo)


def cmd_check(args):
    """配線の確認: 採点器が null・oracle・bad に正しく答えるか（#88 7.3 の 4）。"""
    case, = load_cases([args.case], args.split)
    if args.split == "holdout" and case.get("bad") is None:
        raise ValueError(f"{args.case} の評価ケースに誤った手本 (bad) がありません")
    rows = []
    for kind in ("null", "oracle", "bad"):
        sample = {"null": [], "oracle": case.get("oracle", []), "bad": case.get("bad")}[kind]
        if sample is None:
            continue
        if isinstance(sample, list):
            sample = {"commands": sample}
        out = Path(tempfile.mkdtemp(prefix=f"ipe-check-{kind}-")).resolve()
        try:
            nums, clone, bindir, state, log, before = prepare(case, args.repo, "with", "claude", out, args.gh == "fake")
            env = agent_env(bindir, state, log, args.repo)
            first = sample.get("first", {})
            strict = args.split == "holdout" and kind == "oracle"
            replay_steps(first.get("commands", []), nums, clone, env, require_success=strict)
            first_calls = read_calls(log)
            replay_steps(sample.get("commands", []), nums, clone, env, require_success=strict)
            ctx = {"calls": read_calls(log), "state": json.loads(state.read_text()), "nums": nums, "before": before,
                   "after": read_snapshot(args.repo, out, args.gh == "fake"), "clone": clone, "first_reply": subst(first.get("reply", ""), nums),
                   "first_calls": first_calls}
            reply = subst(sample.get("reply", ""), nums)
            check_code = grade(case, ctx, reply, "claude", out, use_judge=False)
            needs_judge = check_code["pass_code"] or any(j.get("fail_on_any") for j in case["expect"].get("judge", []))
            g = grade(case, ctx, reply, "claude", out) if args.split == "holdout" and needs_judge else check_code
        finally:
            if args.gh == "real":
                clean_trial(case, args.repo)
            shutil.rmtree(out, ignore_errors=True)
        row = {"kind": kind, **{key: g[key] for key in ("pass_code", "checks", "fail_on_any")}}
        if args.split == "holdout":
            row.update(pass_all=g["pass_all"], judge=g["judge"])
        rows.append(row)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    if args.split == "holdout":
        expected = {"null": False, "oracle": True, "bad": False}
        fatal = any(c.get("fail_on_any") for key in ("checks", "judge") for c in case["expect"].get(key, []))
        observed = {row["kind"]: row["pass_all"] for row in rows}
        return int(observed != expected or (fatal and not any(row["fail_on_any"] for row in rows if row["kind"] == "bad")))


def replay_steps(steps, nums, clone, env, require_success):
    for step in steps:
        argv = [subst(arg, nums) for arg in step]
        result = subprocess.run(argv, env=env, cwd=clone, capture_output=True, text=True, errors="replace")
        if require_success and result.returncode:
            raise RuntimeError(f"正解の手本の {' '.join(argv[:3])} が失敗しました: {result.stderr.strip()}")


def cmd_trial(args):
    out = Path(args.out or tempfile.mkdtemp(prefix="ipe-trial-")).resolve()
    case, = load_cases([args.case], args.split)
    rec = trial(case, args.repo, args.cond, args.agent, out, fake=args.gh == "fake")
    print(json.dumps({"out": str(out), **{k: rec[k] for k in ("case", "cond", "infra_failure")}, "grade": rec.get("grade"), "run": rec["run"]}, ensure_ascii=False, indent=2))


def cmd_batch(args):
    cases = load_cases(args.cases.split(","), args.split)
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
                rec = trial(case, repo, cond, args.agent, d, fake=args.gh == "fake")
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
        g = rows.setdefault(key, {"n": 0, "pass_code": 0, "pass_all": 0, "fail_on_any": 0, "infra": 0, "usd": 0.0, "sec": 0.0, "loaded": 0, "judge_no": 0, "gql": []})
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
        g["gql"].append(gr.get("graphql_points", 0))
        usd = r["run"].get("cost", {}).get("usd")
        g["usd_unknown"] = g.get("usd_unknown", 0) + (usd is None)  # Codex は費用を返さない。0 とは数えない
        g["usd"] += usd or 0
        g["sec"] += r["run"]["seconds"]
    print("case / cond / agent: n pass_code pass_all fail_on_any loaded infra  usd/試行 sec/試行 GraphQL の見積もり（最大）")
    for (case, cond, agent), g in sorted(rows.items()):
        n = max(g["n"], 1)
        usd = "$n/a" if g.get("usd_unknown") else f"${g['usd'] / n:.2f}"
        print(f"{case} / {cond} / {agent}: n={g['n']} code={g['pass_code']} all={g['pass_all']} fail_on_any={g['fail_on_any']} loaded={g['loaded']} infra={g['infra']}  {usd}  {g['sec'] / n:.0f}s  gql={max(g['gql'], default=0)}")
    partial = "（費用を返さない試行を含まない一部の合計）" if any(g.get("usd_unknown") for g in rows.values()) else ""
    print(f"合計 usd: ${sum(g['usd'] for g in rows.values()):.2f}{partial}")
    leak_logs = ("history.jsonl", "first-transcript.jsonl", "transcript.jsonl")
    logs = (log for d in map(Path, args.dir) for name in leak_logs for log in (d / name, *d.glob(f"*/try*/{name}")))
    leaks = sorted({str(log.parent) for log in logs if log.is_file() and LEAK.search(log.read_text())})
    print(f"本番の環境の漏れ（Phase 0 の 1・3）: {len(leaks)} 件", *leaks, sep="\n  ")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check"); p.add_argument("case"); p.add_argument("--repo", default="ipe-1"); p.set_defaults(f=cmd_check)
    p.add_argument("--split", choices=("dev", "holdout"), default="dev")
    p.add_argument("--gh", choices=("fake", "real"), default="fake", help="real は本物の GitHub に種を立てる（上限を食う）")
    p = sub.add_parser("trial"); p.add_argument("case"); p.add_argument("--cond", required=True, choices=["with", "without"]); p.add_argument("--agent", default="claude", choices=["claude", "codex"]); p.add_argument("--repo", default="ipe-1"); p.add_argument("--out"); p.set_defaults(f=cmd_trial)
    p.add_argument("--split", choices=("dev", "holdout"), default="dev")
    p.add_argument("--gh", choices=("fake", "real"), default="fake", help="real は本物の GitHub に種を立てる（上限を食う）")
    p = sub.add_parser("batch"); p.add_argument("cases"); p.add_argument("--n", type=int, default=3); p.add_argument("--cond", default="with,without"); p.add_argument("--agent", default="claude", choices=["claude", "codex"]); p.add_argument("--repos", default="ipe-1,ipe-2,ipe-3,ipe-4"); p.add_argument("--out"); p.add_argument("--seed", type=int, default=91); p.set_defaults(f=cmd_batch)
    p.add_argument("--split", choices=("dev", "holdout"), default="dev")
    p.add_argument("--gh", choices=("fake", "real"), default="fake", help="real は本物の GitHub に種を立てる（上限を食う）")
    p = sub.add_parser("hide-holdout", help="スキルを書く子の worktree から評価データセットを外す")
    p.add_argument("worktree", type=Path)
    p = sub.add_parser("audit-holdout", help="スキルを書いた子の JSONL 会話記録から評価データセットへのアクセスを探す")
    p.add_argument("transcript", type=Path, nargs="+")
    p = sub.add_parser("labels"); p.add_argument("dir", nargs="+"); p.add_argument("--out", required=True); p.add_argument("--seed", type=int, default=91); p.set_defaults(f=cmd_labels)
    p.add_argument("--count", type=int, default=20, help="判定器の問いがある試行から、混ぜて選ぶ件数")
    p = sub.add_parser("agreement"); p.add_argument("human"); p.add_argument("answers"); p.set_defaults(f=cmd_agreement)
    p = sub.add_parser("report"); p.add_argument("dir", nargs="+"); p.set_defaults(f=cmd_report)
    args = ap.parse_args()
    if args.cmd == "hide-holdout":
        hide_holdout(args.worktree)
        return 0
    if args.cmd == "audit-holdout":
        try:
            findings = [hit for path in args.transcript for hit in audit_transcript(path)]
        except (OSError, ValueError) as exc:
            ap.error(str(exc))
        print(json.dumps(findings, ensure_ascii=False, indent=2))
        return int(bool(findings))
    if args.cmd in ("trial", "batch") and args.split == "holdout" and not args.out:
        ap.error("評価データセットの試行ログの保存先を --out で指定してください")
    return args.f(args)


if __name__ == "__main__":
    sys.exit(main())
