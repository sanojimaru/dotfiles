"""判定器の較正: 返事を人が yes/no を付けられる形に出し、人のラベルと判定器の一致率を出す（#88 の 3.1。90% 以上で使う）。"""
import json
import random
from pathlib import Path

from common import HERE


def load_case(name):
    return json.loads((HERE / "cases" / f"{name}.json").read_text())


def cmd_labels(args):
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    paths = [p for d in args.dir for p in sorted([*Path(d).glob("*/try*/trial.json"), *Path(d).glob("trial.json")])]  # batch の形と、trial --out の形
    trials = [(p.parent, json.loads(p.read_text())) for p in paths]
    trials = [(d, r) for d, r in trials if not r["infra_failure"]]
    random.Random(args.seed).shuffle(trials)  # 条件（有・無）が並びから分からないように混ぜる
    lines, answers = ["# 判定器の較正: 返事に yes/no を付ける", "",
                      "返事ごとに、問いに yes か no で答えてください。判定器の答えは別のファイル（answers.json）にあり、ここには出していません。", ""], {}
    for i, (d, r) in enumerate(trials, 1):
        case = load_case(r["case"])
        key = f"L{i:02d}"
        lines += [f"## {key}", "", "> " + r["reply"].replace("\n", "\n> "), ""]
        for j in case["expect"].get("judge", []):
            lines.append(f"- [ ] {key}/{j['id']}: {j['q']}（yes / no）")
        lines.append("")
        answers[key] = {"trial": str(d), "case": r["case"], "cond": r["cond"], "judge": r["grade"]["judge"]}
    (out / "labels.md").write_text("\n".join(lines))
    (out / "answers.json").write_text(json.dumps(answers, ensure_ascii=False, indent=2))
    (out / "human.json").write_text(json.dumps({k: {j: None for j in v["judge"]} for k, v in answers.items()}, ensure_ascii=False, indent=2))
    print(f"{len(trials)} 件の返事を {out} に出した")


def cmd_agreement(args):
    human, answers = json.loads(Path(args.human).read_text()), json.loads(Path(args.answers).read_text())
    pairs = [(human[k][j], v["judge"][j]) for k, v in answers.items() for j in v["judge"] if human.get(k, {}).get(j) is not None]
    agree = sum(h == m for h, m in pairs)
    print(f"一致 {agree}/{len(pairs)} = {agree / max(len(pairs), 1):.0%}（90% 以上で判定器を使う）")
