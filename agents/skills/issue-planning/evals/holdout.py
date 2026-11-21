"""スキルの開発中に test ケースを参照しないためのフックと会話記録の検査。"""
import json
import os
import re
import subprocess
import sys

TEST_PATH = "agents/skills/issue-planning/evals/test"
TEST_EXCLUDE = f"!/{TEST_PATH}/"
ACCESS = re.compile(r"(?<![\w.-])evals/test(?:/([\w-]+)\.json(?![\w.-])|(?=$|[^\w.-]))")


def hide_test(worktree):
    subprocess.run(
        ["git", "-C", str(worktree), "sparse-checkout", "set", "--no-cone", "--stdin"],
        input=f"/*\n{TEST_EXCLUDE}\n",
        text=True,
        check=True,
    )


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def test_access(tool_input):
    return {m[1] or "*" for value in strings(tool_input) for m in ACCESS.finditer(value)}


def tool_inputs(event):
    kind = event.get("type")
    if kind == "assistant":
        for block in event.get("message", {}).get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block.get("input")
    elif kind == "response_item":
        payload = event.get("payload", {})
        if payload.get("type") in {"function_call", "custom_tool_call"}:
            arguments = payload.get("arguments", payload.get("input"))
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    pass  # custom_tool_call の入力はプレーンテキストの場合もある。
            yield arguments
        elif payload.get("type") == "local_shell_call":
            yield payload.get("action")
    elif kind in {"item.started", "item.completed"}:
        item = event.get("item", {})
        if item.get("type") == "command_execution":
            yield item.get("command")
        elif item.get("type") == "file_change":
            yield item.get("changes")
        elif item.get("type") == "mcp_tool_call":
            yield item.get("arguments")


def audit_transcript(path):
    with path.open() as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_no}: JSONL を読めません") from exc
            if not isinstance(event, dict):
                raise ValueError(f"{path}:{line_no}: JSONL のイベントがオブジェクトではありません")
            cases = {case for tool_input in tool_inputs(event) for case in test_access(tool_input)}
            if cases:
                yield {"transcript": str(path), "line": line_no, "cases": sorted(cases)}


def check_hook():
    if os.environ.get("ISSUE_PLANNING_EVAL_RUNNER") == "1":
        return 0
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(event, dict) or not test_access(event.get("tool_input")):
        return 0
    # sparse-checkout を設定した子だけを対象にし、通常の checkout で作業する TC を止めない。
    cwd = event.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    sparse = subprocess.run(["git", "sparse-checkout", "list"], cwd=cwd, capture_output=True, text=True)
    if TEST_EXCLUDE in sparse.stdout.splitlines():
        print("issue-planning: スキルの開発中は evals/test/ を読みません。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(check_hook())
