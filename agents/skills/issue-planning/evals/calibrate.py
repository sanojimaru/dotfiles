"""判定器の較正: 判定器に渡した証拠を人が yes/no を付けられる形に出し、人のラベルと判定器の一致率を出す（#88 の 3.1。90% 以上で使う）。"""
import json
import random
import re
from pathlib import Path

from common import HERE


def load_case(name):
    """dev のケースか評価データセットのケース。どちらの試行の判定器も較正するため。"""
    path = HERE / "cases" / f"{name}.json"
    return json.loads((path if path.exists() else HERE / "holdout" / f"{name}.json").read_text())


def same_question(template, asked):
    """ケースの問い（<<key>> は試行の番号に置き換わる）と、試行で判定器に渡した問いが同じか。"""
    return re.fullmatch(re.sub(r"<<[\w\\-]+>>", r"[\\d-]+", re.escape(template)), asked) is not None


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
    for d, r in trials:  # 問いを直す前の試行は、古い問いの答えを今の較正に混ぜてしまう
        current = {j["id"]: j["q"] for j in load_case(r["case"])["expect"].get("judge", [])}
        asked = {j: v["q"] for j, v in r["grade"]["judge_inputs"].items()}
        if stale := sorted(j for j in asked.keys() | current.keys() if j not in current or j not in asked or not same_question(current[j], asked[j])):
            raise SystemExit(f"{d} の判定の問い {stale} が今のケースと違う。問いを直した後の試行を使ってください")
    random.Random(args.seed).shuffle(trials)  # 条件（有・無）が並びから分からないように混ぜる
    if args.cover:
        trials = cover_questions(trials)
    elif len(trials) < args.count:
        raise SystemExit(f"判定器の問いがある試行が {len(trials)} 件しかありません（{args.count} 件が要る）。dev の試行を足してください")
    else:
        trials = trials[:args.count]
    lines, answers, human = ["# 判定器の較正: 判定器の証拠に yes/no を付ける", "",
                             "問いごとに、判定器に渡したものと同じ証拠を読み、yes か no を human.json に書いてください。判定器の答えは別のファイル（answers.json）にあり、ここには出していません。", ""], {}, {}
    if args.append:  # 判定器の違う組（被験が Claude と Codex）を、1 回のラベル付けにまとめる
        lines = (out / "labels.md").read_text().split("\n")
        answers, human = (json.loads((out / name).read_text()) for name in ("answers.json", "human.json"))
    if args.title:
        lines += [f"# {args.title}", ""]
    for i, (d, r) in enumerate(trials, 1):
        case = load_case(r["case"])
        key = f"{args.prefix}{i:02d}"
        if key in answers:
            raise SystemExit(f"{key} は {out} にもうあります。--prefix を変えてください")
        lines += [f"## {key}", ""]
        for j in case["expect"].get("judge", []):
            if j["id"] not in r["judged"]:
                continue
            item = r["grade"]["judge_inputs"][j["id"]]
            lines += [f"### {key}/{j['id']}", "", f"問い: {item['q']}（yes / no）", "",
                      f"判定器に渡した証拠（{j.get('source', 'reply')}）:", "", quote(item["evidence"]), ""]
        answers[key] = {"trial": str(d), "case": r["case"], "cond": r["cond"], "judge": r["judged"]}
        human[key] = {j: None for j in r["judged"]}
    (out / "labels.md").write_text("\n".join(lines))
    (out / "answers.json").write_text(json.dumps(answers, ensure_ascii=False, indent=2))
    (out / "human.json").write_text(json.dumps(human, ensure_ascii=False, indent=2))
    print(f"{len(trials)} 件の返事を {out} に出した")


def cover_questions(trials):
    """ケースの判定の問いがそれぞれ 1 回以上入るよう、混ぜた順に、まだ入っていない問いを持つ試行だけを選ぶ。
    新しく書いた問いを、人のラベルで 1 問も漏らさず較正するため（dotfiles#190）。"""
    wanted = {(r["case"], j["id"]) for _, r in trials for j in load_case(r["case"])["expect"].get("judge", [])}
    picked, covered = [], set()
    for d, r in trials:
        new = {(r["case"], j) for j in r["judged"]} - covered
        if new:
            picked.append((d, r))
            covered |= new
    if missing := sorted(wanted - covered):
        print("証拠が空でない試行が無く、入れられなかった問い:", *(f"{c}/{j}" for c, j in missing))
    return picked


def cmd_agreement(args):
    human, answers = json.loads(Path(args.human).read_text()), json.loads(Path(args.answers).read_text())
    groups = {}
    for k, v in answers.items():  # 組（キーの英字の部分）ごとに出す。組ごとに判定器が違うため
        for j in v["judge"]:
            if human.get(k, {}).get(j) is not None:
                groups.setdefault(re.match(r"[A-Za-z]*", k)[0], []).append((human[k][j], v["judge"][j]))
    for group, pairs in sorted(groups.items()):
        agree = sum(h == m for h, m in pairs)
        print(f"{group}: 一致 {agree}/{len(pairs)} = {agree / max(len(pairs), 1):.0%}（90% 以上で判定器を使う）")
