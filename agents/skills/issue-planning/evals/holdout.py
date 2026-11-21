"""スキルの開発中に test ケースを参照しないためのフックと会話記録の検査。"""
import json
import os
import re
import subprocess
import sys

TEST_PATH = "agents/skills/issue-planning/evals/test"
ACCESS = re.compile(r"""(?<![\w.-])evals/test(?:/([\w-]+)\.json(?![\w.-])|(?=$|[/\s"'\\]))""")


def hide_test(worktree):
    subprocess.run(
        ["git", "-C", str(worktree), "sparse-checkout", "set", "--no-cone", "--stdin"],
        input=f"/*\n!/{TEST_PATH}/\n",
        text=True,
        check=True,
    )


def test_access(tool_input):
    return {m[1] or "*" for m in ACCESS.finditer(json.dumps(tool_input, ensure_ascii=False))}


def tool_inputs(event):
    kind = event.get("type")
    if kind == "assistant":
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "tool_use":
                yield block.get("input")
    elif kind == "response_item":
        payload = event.get("payload", {})
        if payload.get("type") in {"function_call", "custom_tool_call"}:
            yield payload.get("arguments", payload.get("input"))
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
            cases = {case for tool_input in tool_inputs(event) for case in test_access(tool_input)}
            if cases:
                yield {"transcript": str(path), "line": line_no, "cases": sorted(cases)}


def check_hook():
    if os.environ.get("ISSUE_PLANNING_EVAL_RUNNER") == "1":
        return 0
    if test_access(json.load(sys.stdin).get("tool_input")):
        print("issue-planning: スキルの開発中は evals/test/ を読みません。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(check_hook())
