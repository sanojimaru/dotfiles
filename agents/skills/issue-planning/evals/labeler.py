"""判定器の較正のラベルを、利用者の代わりに付けるラベラー（dotfiles#193）。

labels.md の問いと証拠だけを読み、別の会社の 2 モデルに yes・no・unsure と理由を答えさせる。
2 つが同じ yes か no なら採用し、unsure か食い違いなら保留（null）にする。1 つのモデルだと、
test のどちらかの組で判定器と同じモデルになり、被験と同じ系統のモデルだけでラベルが決まるため。
answers.json（判定器の答え）と human.json（利用者のラベル）は開かない。
"""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from common import CLAUDE_MODEL, CODEX_MODEL, STRIP_ENV, sh

MODELS = {"claude": CLAUDE_MODEL, "codex": CODEX_MODEL}
PROMPT = """あなたは、AI エージェントの評価で、人の代わりに yes/no のラベルを付けます。
下の証拠は、評価の試行でエージェントが残したもの（{source}）です。問いに、証拠だけから答えてください。ファイルを読んだりコマンドを実行したりしないでください。

- 問いが求めることを、証拠の記述で確かめられるときだけ yes にします。
- 証拠に問いが求めることが無いか、反する記述があれば no にします。
- 証拠を読んでも yes とも no とも決められないときは unsure にします。推測で yes や no を選ばないでください。

---
{evidence}
---
問い: {question}

次の JSON だけを 1 行で答えてください。reason は日本語で 1〜2 文にし、根拠にした証拠の箇所を書きます。
{{"answer": "yes" | "no" | "unsure", "reason": "..."}}"""
SOURCES = {"reply": "利用者への返事", "first_reply": "最初の返事", "issues": "Issue の本文やコメントの JSON", "orca": "orca コマンドの呼び出し", "combined": "返事と記録を合わせたもの"}


def parse_labels(text):
    """labels.md から [(key, qid, source, question, evidence)] を取り出す（calibrate.py の cmd_labels が書く形）。"""
    items, cur = [], None
    for line in text.split("\n"):
        if m := re.fullmatch(r"### ([A-Za-z]+\d+)/(\S+)", line):
            cur = {"key": m[1], "qid": m[2], "q": None, "source": "reply", "evidence": []}
            items.append(cur)
        elif line.startswith("#"):
            cur = None
        elif cur is None:
            continue
        elif m := re.fullmatch(r"問い: (.*)（yes / no）", line):
            cur["q"] = m[1]
        elif m := re.fullmatch(r"判定器に渡した証拠（(\w+)）:", line):
            cur["source"] = m[1]
        elif line.startswith(">"):
            cur["evidence"].append(line[2:] if line.startswith("> ") else line[1:])
    for it in items:
        if it["q"] is None:
            raise SystemExit(f"{it['key']}/{it['qid']} の問いを labels.md から読めなかった")
        it["evidence"] = "\n".join(it["evidence"])
    return items


def codex_args(home, deny):
    """Codex に、問いと証拠のほかを読ませずに答えさせる起動のしかた。
    CODEX_HOME には auth.json だけを置き、~/.codex/AGENTS.md（評価しているワークフローの規則）と config.toml の MCP を読ませない。
    codex exec は read-only でも作業ディレクトリの外を読めるので、shell の道具を切り、sandbox-exec で deny のパスの読み取りを止める。
    Codex の道具は自分の sandbox-exec を入れ子にできず失敗するので、道具が動く前に止まる。Claude 側は --tools "" で道具が無い。"""
    rules = "".join(f'(deny file-read* (subpath "{d.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"))' for d in deny)
    return ["sandbox-exec", "-p", f"(version 1)(allow default){rules}", "codex", "exec", "-m", MODELS["codex"], "-s", "read-only",
            "--skip-git-repo-check", "--ephemeral", "--json", "--disable", "shell_tool", "--disable", "unified_exec"]


def call(kind, prompt, home, deny):
    """{"answer", "reason", "usage", "seconds"} を返す。答えが読めないか、道具を使ったか、時間切れなら answer は None。"""
    env = {k: v for k, v in os.environ.items() if not STRIP_ENV.match(k)}
    start = time.monotonic()
    text, usage, err = "", None, ""
    with tempfile.TemporaryDirectory() as tmp:  # 被験の試行と同じく、空のディレクトリで動かして手元のファイルを読ませない
        try:
            if kind == "codex":
                env["CODEX_HOME"] = str(home)
                out = Path(tmp) / "answer.txt"
                r = sh([*codex_args(home, deny), "-o", str(out), prompt], env=env, cwd=tmp)
                text, err = out.read_text() if out.exists() and r.returncode == 0 else "", r.stderr or f"終了コード {r.returncode}"
                events = []
                for line in filter(str.strip, r.stdout.splitlines()):  # 読めない行があると、道具を使ったかを確かめられないので、その呼び出しの失敗として扱う
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        text, err = "", f"JSONL を読めなかった: {line[:100]}"
                usage = next((e.get("usage") for e in reversed(events) if e.get("type") == "turn.completed"), None)
                # 道具を使おうとした答えは、証拠のほかの何かに基づいた答えかもしれないので捨てる
                tools = sorted({f"{it['type']}: {str(it.get('command', ''))[:80]}" for e in events if (it := e.get("item")) and it.get("type") not in ("agent_message", "reasoning")})
                if tools:
                    return {"answer": None, "reason": "tool-use: " + " / ".join(tools), "usage": usage, "seconds": round(time.monotonic() - start, 1)}
            else:
                env.update(CLAUDE_CODE_DISABLE_CLAUDE_MDS="1", CLAUDE_CODE_DISABLE_AUTO_MEMORY="1")
                r = sh(["claude", "-p", prompt, "--model", MODELS[kind], "--output-format", "json", "--setting-sources", "project,local", "--strict-mcp-config", "--tools", ""], env=env, cwd=tmp)
                err = r.stderr or f"終了コード {r.returncode}"
                try:
                    res = json.loads(r.stdout)
                    u = res.get("usage") or {}
                    text, usage = "" if r.returncode or res.get("is_error") else res.get("result", ""), {"cost_usd": res.get("total_cost_usd"), **{f: u.get(f, 0) for f in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}}
                except json.JSONDecodeError:
                    pass
        except subprocess.TimeoutExpired as e:
            err = f"timeout: {e}"
    m = re.search(r"\{.*\}", text, re.S)
    try:
        ans = json.loads(m[0]) if m else {}
    except json.JSONDecodeError:
        ans = {}
    if not isinstance(ans, dict) or not isinstance(ans.get("reason"), str) or not ans["reason"].strip():  # 理由の無い答えは、読めない答えとして呼び直す
        ans = {}
    answer = ans.get("answer") if ans.get("answer") in ("yes", "no", "unsure") else None
    return {"answer": answer, "reason": ans.get("reason") or text.strip()[:300] or err.strip()[:300], "usage": usage, "seconds": round(time.monotonic() - start, 1)}


def ask(kind, item, home, deny):
    prompt = PROMPT.format(source=SOURCES.get(item["source"], item["source"]), evidence=item["evidence"], question=item["q"])
    res = call(kind, prompt, home, deny)
    if res["answer"] is None:  # 一時的な失敗か書式の崩れ。1 回だけ呼び直す。費用は両方の回を数える
        first = res
        res = call(kind, prompt, home, deny) | {"retried": first["reason"][:300]}
        res["usages"] = [first["usage"], res["usage"]]
    return res


def decide(answers):
    """2 モデルの答えから、True・False・None（保留）を決める。"""
    got = {a["answer"] for a in answers.values()}
    return {"yes": True, "no": False}.get(got.pop()) if len(got) == 1 else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("labels", type=Path, help="labels.md のパス（同じディレクトリの answers.json・human.json は読まない）")
    ap.add_argument("--out", type=Path, required=True, help="agent.json と reasons.json を書くディレクトリ")
    ap.add_argument("--jobs", type=int, default=4, help="モデルごとの並列数")
    ap.add_argument("--only", help="この正規表現に合う key/qid だけを付ける（動作の確認用）")
    args = ap.parse_args()
    items = parse_labels(args.labels.read_text())
    if args.only:
        items = [it for it in items if re.search(args.only, f"{it['key']}/{it['qid']}")]
    args.out.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    # ラベルの置き場（human.json・answers.json）と、試行の記録（判定器の答えが入った trial.json）の置き場を読ませない
    deny = sorted({str(args.labels.resolve().parent), str(Path.home() / ".cache/issue-planning-eval")})
    with tempfile.TemporaryDirectory(prefix="labeler-codex-home-") as home:
        src = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "auth.json"
        (Path(home) / "auth.json").symlink_to(src)
        pools = {kind: concurrent.futures.ThreadPoolExecutor(args.jobs) for kind in MODELS}
        futures = {(i, kind): pools[kind].submit(ask, kind, it, home, deny) for i, it in enumerate(items) for kind in MODELS}
        results = {k: f.result() for k, f in futures.items()}
        for pool in pools.values():
            pool.shutdown()

    def usages(kind):
        return [u or {} for i in range(len(items)) for u in results[(i, kind)].get("usages", [results[(i, kind)]["usage"]])]

    agent, reasons = {}, {}
    for i, it in enumerate(items):
        answers = {kind: results[(i, kind)] for kind in MODELS}
        agent.setdefault(it["key"], {})[it["qid"]] = decide(answers)
        reasons.setdefault(it["key"], {})[it["qid"]] = {"q": it["q"], **answers}
    meta = {"models": MODELS, "items": len(items), "seconds": round(time.monotonic() - start, 1),
            "cost_usd": {"claude": round(sum(u.get("cost_usd") or 0 for u in usages("claude")), 4)},
            "tokens": {"codex": {f: sum(u.get(f, 0) for u in usages("codex")) for f in ("input_tokens", "cached_input_tokens", "output_tokens")}},
            "parse_errors": sum(r["answer"] is None for r in results.values()),
            "tool_uses": sum(r["reason"].startswith("tool-use") or r.get("retried", "").startswith("tool-use") for r in results.values())}
    (args.out / "agent.json").write_text(json.dumps(agent, ensure_ascii=False, indent=2))
    (args.out / "reasons.json").write_text(json.dumps({"meta": meta, "items": reasons}, ensure_ascii=False, indent=2))
    held = sum(v is None for q in agent.values() for v in q.values())
    print(f"{len(items)} 問にラベルを付けた（保留 {held}、読めなかった答え {meta['parse_errors']}、道具を使った答え {meta['tool_uses']}、{meta['seconds']} 秒）: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
