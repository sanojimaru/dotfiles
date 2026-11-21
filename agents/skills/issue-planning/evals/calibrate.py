"""判定器の較正: 判定器に渡した証拠を人が yes/no を付けられる形に出し、人のラベルと判定器の一致率を出す（#88 の 3.1。90% 以上で使う）。"""
import json
import random
from pathlib import Path

from common import HERE


def load_case(name):
    return json.loads((HERE / "cases" / f"{name}.json").read_text())


def quote(text):
    return "> " + (text or "（空）").replace("\n", "\n> ")


def cmd_labels(args):
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    paths = [p for d in args.dir for p in sorted([*Path(d).glob("*/try*/trial.json"), *Path(d).glob("trial.json")])]  # batch の形と、trial --out の形
    trials = [(p.parent, json.loads(p.read_text())) for p in paths]
    for _, r in trials:  # 証拠が空の問いは判定器を呼ばず allow_empty で決まるので、較正に入れない
        inputs = (r.get("grade") or {}).get("judge_inputs", {})
        r["judged"] = {j: v for j, v in (r.get("grade") or {}).get("judge", {}).items() if inputs.get(j, {}).get("evidence", "").strip()}
    trials = [(d, r) for d, r in trials if not r["infra_failure"] and r["judged"]]
    for d, r in trials:  # 問いを直す前の試行は、今のケースに無い id の証拠を labels.md に出せない
        if stale := set(r["judged"]) - {j["id"] for j in load_case(r["case"])["expect"].get("judge", [])}:
            raise SystemExit(f"{d} は今のケースに無い判定の id {sorted(stale)} を持つ。問いを直した後の試行を使ってください")
    random.Random(args.seed).shuffle(trials)  # 条件（有・無）が並びから分からないように混ぜる
    if len(trials) < args.count:
        raise SystemExit(f"判定器の問いがある試行が {len(trials)} 件しかありません（{args.count} 件が要る）。dev の試行を足してください")
    trials = trials[:args.count]
    lines, answers = ["# 判定器の較正: 判定器の証拠に yes/no を付ける", "",
                      "問いごとに、判定器に渡したものと同じ証拠を読み、yes か no を human.json に書いてください。判定器の答えは別のファイル（answers.json）にあり、ここには出していません。", ""], {}
    for i, (d, r) in enumerate(trials, 1):
        case = load_case(r["case"])
        key = f"L{i:02d}"
        lines += [f"## {key}", ""]
        for j in case["expect"].get("judge", []):
            if j["id"] not in r["judged"]:
                continue
            item = r["grade"]["judge_inputs"][j["id"]]
            lines += [f"### {key}/{j['id']}", "", f"問い: {item['q']}（yes / no）", "",
                      f"判定器に渡した証拠（{j.get('source', 'reply')}）:", "", quote(item["evidence"]), ""]
        answers[key] = {"trial": str(d), "case": r["case"], "cond": r["cond"], "judge": r["judged"]}
    (out / "labels.md").write_text("\n".join(lines))
    (out / "answers.json").write_text(json.dumps(answers, ensure_ascii=False, indent=2))
    (out / "human.json").write_text(json.dumps({k: {j: None for j in v["judge"]} for k, v in answers.items()}, ensure_ascii=False, indent=2))
    print(f"{len(trials)} 件の返事を {out} に出した")


def cmd_agreement(args):
    human, answers = json.loads(Path(args.human).read_text()), json.loads(Path(args.answers).read_text())
    pairs = [(human[k][j], v["judge"][j]) for k, v in answers.items() for j in v["judge"] if human.get(k, {}).get(j) is not None]
    agree = sum(h == m for h, m in pairs)
    print(f"一致 {agree}/{len(pairs)} = {agree / max(len(pairs), 1):.0%}（90% 以上で判定器を使う）")
