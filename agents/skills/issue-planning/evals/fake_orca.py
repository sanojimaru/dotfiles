#!/usr/bin/env python3
"""評価用の `orca` の代役。PATH の先頭に `orca` として置く。

呼ばれたコマンドを ORCA_FAKE_LOG に記録し、ORCA_FAKE_STATE（試行の種）の状態を本物の出力の形で返す。
`skills` とヘルプは本物へ渡す（orchestration の SKILL.md が `orca skills get` で本文を取るため。ヘルプは状態を変えず、
代役の作ったヘルプでは本物に無いコマンドも成功して見え、被験がそれを使ってしまうため。dotfiles#171）。
"""
import json
import os
import subprocess
import sys
import time


ORCA_REAL = "@@ORCA_REAL@@"  # 試行ごとにコピーするとき、本物の orca のパスを埋める
# `orca orchestration --help` が挙げるサブコマンド（Orca 1.4 系）
ORCHESTRATION_COMMANDS = {
    "run-create", "run-use", "run-current", "run-list", "run-show", "send", "check", "reply", "inbox",
    "task-create", "task-list", "task-update", "worker-start", "worker-show", "worker-read", "worker-stop", "deny",
    "worker-abandon", "worker-release", "worker-keep-open", "worker-list", "dispatch", "request-show",
    "dispatch-show", "ask", "coordinator-start", "coordinator-stop", "gate-create", "gate-resolve", "gate-list", "reset",
}


def log(argv, started, rc):
    path = opt(argv, "--spec-file") if argv[:2] in (["orchestration", "task-create"], ["orchestration", "worker-start"]) else None
    details = {}
    if argv[:2] == ["orchestration", "worker-start"]:
        details["cwd"] = os.path.realpath(os.getcwd())
    if path and os.path.isfile(path):
        with open(path) as f:
            details["spec"] = f.read()
    with open(os.environ["ORCA_FAKE_LOG"], "a") as f:
        f.write(json.dumps({"ts": started, "tool": "orca", "argv": argv, "rc": rc, **details}, ensure_ascii=False) + "\n")


def ok(result=None):
    print(json.dumps({"ok": True, "result": result if result is not None else {}}, ensure_ascii=False, indent=2))


def fail(code, message):
    print(json.dumps({"ok": False, "error": {"code": code, "message": message}}, ensure_ascii=False))
    sys.exit(1)


def opt(argv, name):
    for i, value in enumerate(argv):
        if value == name and i + 1 < len(argv):
            return argv[i + 1]
        if value.startswith(name + "="):
            return value.split("=", 1)[1]
    return None


def save(path, state):
    with open(path, "w") as f:
        json.dump(state, f)


def selector_hits(sel, w):
    kind, _, val = sel.partition(":")
    return {"issue": str(w.get("issue")), "path": w["path"], "identity": w["identity"], "name": w["name"],
            "branch": w["name"]}.get(kind) == (val.removeprefix("refs/heads/") if kind == "branch" else val)


def current_worktree(state):
    cwd = os.path.realpath(os.getcwd())
    return next((w for w in state["worktrees"] if os.path.commonpath([cwd, os.path.realpath(w["path"])]) ==
                 os.path.realpath(w["path"])), state["worktrees"][0])


def worktrees(state):
    return [
        {
            "id": f"{state['repo_id']}::{w['path']}",
            "identity": {"key": w["identity"], "executionHostId": "local"},
            "repoId": state["repo_id"],
            "path": w["path"],
            "branch": f"refs/heads/{w['name']}",
            "displayName": w["name"],
            "linkedIssue": w.get("issue"),
            "isMainWorktree": w is state["worktrees"][0],
        }
        for w in state["worktrees"]
    ]


def workers(state):
    by_issue = {w["issue"]: w for w in state["worktrees"] if w.get("issue")}
    out = []
    for i, w in enumerate(state["workers"]):
        wt = w.get("worktree") or by_issue.get(w["issue"], {})
        row = {
            "dispatchId": w.get("dispatch_id", f"ctx_fake{i:04d}"),
            "taskId": w.get("task_id", f"task_fake{i:04d}"),
            "state": w["state"],
            "liveness": w["liveness"],
            "agent": w.get("agent", "claude/claude-opus-5-5"),
            "workspace": f"{state['repo_id']}::{wt.get('path', '')}",
            "host": "local",
        }
        if w["liveness"] == "live":
            outcome = w["state"] if w["state"] in ("succeeded", "failed") else "in_progress"
            row.update({"outcome": outcome, "terminalState": "retained"})
        else:
            row.update({"terminalState": "released"})
        out.append(row)
    return out


def mail(cmd, argv, state, state_path):
    messages = state["messages"]
    if cmd in ("inbox", "check"):
        inspect_only = cmd == "inbox" or "--all" in argv or "--peek" in argv
        visible = messages if cmd == "inbox" or "--all" in argv else [m for m in messages if not m["read"]]
        terminal, run_id = opt(argv, "--terminal"), opt(argv, "--run")
        visible = [m for m in visible if (not terminal or m["to_handle"] == terminal) and (not run_id or m["run_id"] == run_id)]
        kinds = opt(argv, "--types")
        if kinds and inspect_only:
            visible = [m for m in visible if m["type"] in kinds.split(",")]
        if cmd == "inbox":
            limit = int(opt(argv, "--limit") or "50")
            ok({"count": len(visible[-limit:]), "messages": visible[-limit:]})
        else:
            ok({"messages": visible})
            if not inspect_only:
                for message in visible:
                    message["read"] = 1
                save(state_path, state)
        return
    if cmd == "ask":
        if not opt(argv, "--question"):
            fail("invalid_args", "ask requires --question")
        sequence = len(messages) + 1
        thread_id = f"thread_eval_question_{sequence}"
        answer = state["ask_reply"]
        if answer:
            answer = {**answer, "id": f'{answer["id"]}_{sequence}', "thread_id": thread_id, "sequence": sequence}
            messages.append(answer)
            save(state_path, state)
        ok({"messageId": f"msg_eval_question_{sequence}", "threadId": thread_id})
        return
    if cmd == "reply" and not any(m["id"] == opt(argv, "--id") and m["type"] == "question" for m in messages):
        fail("message_not_found", "reply に対応する question がありません")
    if cmd == "send" and not opt(argv, "--subject"):  # 本物と同じく --subject を必須にする
        fail("invalid_argument", "Missing required --subject")
    if cmd == "send" and opt(argv, "--type") == "worker_done" and opt(argv, "--outcome") not in ("succeeded", "failed"):
        fail("invalid_args", "worker_done requires --outcome succeeded or failed")
    ok({"messageId": "msg_eval_sent"})


def dispatch(argv, started):
    if argv[:1] == ["skills"] or "--help" in argv or "-h" in argv:
        log(argv, started, None)
        if os.environ.get("ORCA_FAKE_ACTIVE"):
            sys.exit("fake_orca: 本物の orca のパスが代役自身を指している")
        os.environ["ORCA_FAKE_ACTIVE"] = "1"
        if argv[:1] != ["skills"]:
            # 本物は `-h` をヘルプと読まないので、元の引数のまま渡すと状態を変えるコマンドが本物に届く。コマンドの語だけを渡す
            argv = next((argv[:i] for i, a in enumerate(argv) if a.startswith("-")), argv) + ["--help"]
        os.execv(ORCA_REAL, [ORCA_REAL] + argv)
    state_path = os.environ["ORCA_FAKE_STATE"]
    with open(state_path) as f:
        state = json.load(f)
    cmd = argv[1] if argv[:1] == ["orchestration"] and len(argv) > 1 else None
    if cmd is not None and cmd not in ORCHESTRATION_COMMANDS:
        # 本物と同じく、無いサブコマンドは失敗させる（成功で返すと、被験が誤ったコマンドのまま進む）
        words = " ".join(next((argv[:i] for i, a in enumerate(argv) if a.startswith("-")), argv))
        fail("invalid_argument", f"Unknown command: {words}")
    if argv[:2] == ["worktree", "list"]:
        ok({"worktrees": worktrees(state)})
    elif cmd == "worker-list":
        ok({"workers": workers(state), "nextCursor": None, "scope": {"source": "all"}, "warnings": []})
    elif cmd in ("run-use", "run-show"):
        rid = opt(argv, "--id")
        if rid != state["run_id"]:
            fail("run_not_found", f"Run {rid} does not exist")
        ok({"runId": rid, "objective": state["run_objective"]})
    elif cmd == "run-current":
        ok({"runId": state["run_id"], "objective": state["run_objective"]})
    elif cmd == "run-create":
        next_run_id = state.pop("next_run_id", None)
        if not next_run_id and (state["workers"] or state["messages"]):
            # 種の Run が使われている（worker か通知がある）なら、本物と同じく別の Run を作る。
            # 使われていない種の Run は、これから作る Run の id として返す（S2-A2・S3-B1 の種）。
            state["seq"] = state.get("seq", 0) + 1
            next_run_id = f"run_new{state['seq']:04d}"
        if next_run_id:
            state.setdefault("previous_runs", {})[state["run_id"]] = state["run_objective"]
            state["run_id"] = next_run_id
        state["run_objective"] = opt(argv, "--objective") or state["run_objective"]
        save(state_path, state)
        ok({"runId": state["run_id"], "objective": state["run_objective"]})
    elif cmd == "run-list":
        runs = {**state.get("previous_runs", {}), state["run_id"]: state["run_objective"]}
        ok({"runs": [{"id": run_id, "objective": objective} for run_id, objective in runs.items()]})
    elif cmd in ("inbox", "check", "ask", "reply", "send"):
        mail(cmd, argv, state, state_path)
    elif cmd == "task-create":
        if not (opt(argv, "--spec") or opt(argv, "--spec-file")):
            fail("invalid_args", "task-create requires --spec or --spec-file")
        state["seq"] = state.get("seq", 0) + 1
        task = f"task_new{state['seq']:04d}"
        state.setdefault("tasks", []).append(task)
        save(state_path, state)
        ok({"taskId": task, "status": "ready"})
    elif cmd == "worker-start":
        if opt(argv, "--spec") or opt(argv, "--spec-file"):  # 本物は、--spec を渡すと Task を作って起動する
            state["seq"] = state.get("seq", 0) + 1
            state.setdefault("tasks", []).append(f"task_new{state['seq']:04d}")
            argv = argv + ["--task", state["tasks"][-1]]
        if opt(argv, "--task") not in state.get("tasks", []):
            fail("task_not_found", f"Task {opt(argv, '--task')} does not exist. Create it with task-create first.")
        sel = opt(argv, "--worktree")
        state["seq"] = state.get("seq", 0) + 1
        if sel in ("new-child", "new-top-level"):
            # 本物は新しい worktree を作って起動する。worker-start には Issue を結び付ける指定が無いので、Issue に結び付けない（dotfiles#171）
            name = opt(argv, "--name") or f"workspace-{state['seq']:04d}"
            wt = {"name": name, "issue": None, "has_parent": sel == "new-child",
                  "path": f"/fake/worktrees/{name}", "identity": f"wt2:local:{name}"}
            state["worktrees"].append(wt)
        else:
            wt = current_worktree(state) if not sel or sel == "current" else next((w for w in state["worktrees"] if selector_hits(sel, w)), None)
        if wt is None:
            fail("worktree_not_found", f"No worktree matches {sel}")
        state["workers"].append({"issue": wt["issue"], "liveness": "live", "state": "ready",
                                 "agent": opt(argv, "--agent"), "worktree": wt,
                                 "dispatch_id": f"ctx_new{state['seq']:04d}", "task_id": opt(argv, "--task")})
        save(state_path, state)
        ok({"dispatchId": f"ctx_new{state['seq']:04d}", "taskId": opt(argv, "--task"), "state": "ready", "liveness": "live"})
    elif argv[:2] == ["worktree", "create"]:
        name, issue = opt(argv, "--name"), opt(argv, "--issue")
        if not name:
            fail("invalid_args", "worktree create requires --name")
        if issue not in (None, "null") and not issue.isdecimal():
            fail("invalid_args", "worktree create --issue requires a number or null")
        wt = {"name": name, "issue": int(issue) if issue and issue != "null" else None,
              "has_parent": not {"--no-parent", "--no-parent=true"}.intersection(argv),
              "path": f"/fake/worktrees/{name}", "identity": f"wt2:local:{name}"}
        state["worktrees"].append(wt)
        if opt(argv, "--agent") and opt(argv, "--prompt"):
            state["seq"] = state.get("seq", 0) + 1
            state["workers"].append({"issue": wt["issue"], "liveness": "live", "state": "ready",
                                     "worktree": wt, "dispatch_id": f"ctx_new{state['seq']:04d}"})
        save(state_path, state)
        ok({"worktree": worktrees(state)[-1]})
    elif argv[:2] == ["worktree", "rm"]:
        selector = opt(argv, "--worktree") or (argv[2] if len(argv) > 2 else "")
        wt = next((w for w in state["worktrees"] if selector_hits(selector, w)), None)
        if wt is None or wt is state["worktrees"][0]:
            fail("worktree_not_found", f"No removable worktree matches {selector}")
        if wt.get("checkout") and not {"--force", "--force=true"}.intersection(argv):
            status = subprocess.run(["git", "-C", wt["path"], "status", "--porcelain"], capture_output=True, text=True)
            if status.returncode or status.stdout:
                fail("worktree_dirty", "The worktree has uncommitted changes or could not be checked")
        state["worktrees"].remove(wt)
        save(state_path, state)
        ok({"removed": True})
    else:
        ok({})


def main():
    argv, started, rc = sys.argv[1:], time.time(), 0
    try:
        dispatch(argv, started)
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    log(argv, started, rc)
    sys.exit(rc)


if __name__ == "__main__":
    main()
