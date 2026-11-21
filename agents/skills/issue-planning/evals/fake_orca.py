#!/usr/bin/env python3
"""評価用の `orca` の代役。PATH の先頭に `orca` として置く。

呼ばれたコマンドを ORCA_FAKE_LOG に記録し、ORCA_FAKE_STATE（試行の種）の状態を本物の出力の形で返す。
`skills` だけは本物へ渡す（orchestration の SKILL.md が `orca skills get` で本文を取るため）。
"""
import json
import os
import sys
import time


ORCA_REAL = "@@ORCA_REAL@@"  # 試行ごとにコピーするとき、本物の orca のパスを埋める


def log(argv, started, rc):
    with open(os.environ["ORCA_FAKE_LOG"], "a") as f:
        f.write(json.dumps({"ts": started, "tool": "orca", "argv": argv, "rc": rc}, ensure_ascii=False) + "\n")


def ok(result=None):
    print(json.dumps({"ok": True, "result": result if result is not None else {}}, ensure_ascii=False, indent=2))


def fail(code, message):
    print(json.dumps({"ok": False, "error": {"code": code, "message": message}}, ensure_ascii=False))
    sys.exit(1)


def opt(argv, name):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def save(path, state):
    with open(path, "w") as f:
        json.dump(state, f)


def selector_hits(sel, w):
    kind, _, val = sel.partition(":")
    return {"issue": str(w.get("issue")), "path": w["path"], "identity": w["identity"], "name": w["name"]}.get(kind) == val


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
            "isMainWorktree": w.get("issue") is None,
        }
        for w in state["worktrees"]
    ]


def workers(state):
    by_issue = {w["issue"]: w for w in state["worktrees"] if w.get("issue")}
    out = []
    for i, w in enumerate(state["workers"]):
        wt = by_issue[w["issue"]]
        row = {
            "dispatchId": f"ctx_fake{i:04d}",
            "taskId": f"task_fake{i:04d}",
            "state": w["state"],
            "liveness": w["liveness"],
            "agent": w.get("agent", "claude/claude-opus-5-5"),
            "workspace": f"{state['repo_id']}::{wt['path']}",
            "host": "local",
        }
        if w["liveness"] == "live":
            row.update({"outcome": "in_progress", "terminalState": "retained"})
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
    if cmd == "send" and opt(argv, "--type") == "worker_done" and opt(argv, "--outcome") not in ("succeeded", "failed"):
        fail("invalid_args", "worker_done requires --outcome succeeded or failed")
    ok({"messageId": "msg_eval_sent"})


def dispatch(argv, started):
    if argv[:1] == ["skills"]:
        log(argv, started, None)
        if os.environ.get("ORCA_FAKE_ACTIVE"):
            sys.exit("fake_orca: 本物の orca のパスが代役自身を指している")
        os.environ["ORCA_FAKE_ACTIVE"] = "1"
        os.execv(ORCA_REAL, [ORCA_REAL] + argv)
    if "--help" in argv or "-h" in argv:  # ヘルプは何も変えない
        print("Usage: orca " + " ".join(a for a in argv if a not in ("--help", "-h")) + " [options]  (評価用の代役のヘルプ。本物のオプションは orca --help を見る)")
        return
    state_path = os.environ["ORCA_FAKE_STATE"]
    with open(state_path) as f:
        state = json.load(f)
    cmd = argv[1] if argv[:1] == ["orchestration"] and len(argv) > 1 else None
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
    elif cmd == "run-list":
        ok({"runs": [{"id": state["run_id"], "objective": state["run_objective"]}]})
    elif cmd in ("inbox", "check", "ask", "reply", "send"):
        mail(cmd, argv, state, state_path)
    elif cmd == "task-create":
        if "--spec" not in argv and "--spec-file" not in argv:
            fail("invalid_args", "task-create requires --spec or --spec-file")
        state["seq"] = state.get("seq", 0) + 1
        task = f"task_new{state['seq']:04d}"
        state.setdefault("tasks", []).append(task)
        save(state_path, state)
        ok({"taskId": task, "status": "ready"})
    elif cmd == "worker-start":
        if "--spec" in argv or "--spec-file" in argv:  # 本物は、--spec を渡すと Task を作って起動する
            state["seq"] = state.get("seq", 0) + 1
            state.setdefault("tasks", []).append(f"task_new{state['seq']:04d}")
            argv = argv + ["--task", state["tasks"][-1]]
        if opt(argv, "--task") not in state.get("tasks", []):
            fail("task_not_found", f"Task {opt(argv, '--task')} does not exist. Create it with task-create first.")
        sel = opt(argv, "--worktree")
        if sel and not any(selector_hits(sel, w) for w in state["worktrees"]):
            fail("worktree_not_found", f"No worktree matches {sel}")
        state["seq"] = state.get("seq", 0) + 1
        wt = next((w for w in state["worktrees"] if sel and selector_hits(sel, w)), None)
        if wt and wt.get("issue"):  # 起こした親は、以後の worker-list に live で出る
            state["workers"].append({"issue": wt["issue"], "liveness": "live", "state": "ready", "agent": opt(argv, "--agent")})
        save(state_path, state)
        ok({"dispatchId": f"ctx_new{state['seq']:04d}", "taskId": opt(argv, "--task"), "state": "ready", "liveness": "live"})
    elif argv[:2] == ["worktree", "create"]:
        ok({"worktree": {"path": "/tmp/fake-worktree", "displayName": opt(argv, "--name")}})
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
