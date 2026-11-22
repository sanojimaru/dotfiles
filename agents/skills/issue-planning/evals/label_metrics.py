"""ラベラーのラベル（A）を、利用者のラベル（U）と判定器の答え（J）に照らし、dotfiles#193 の「測り方（事前登録）」の指標を出す。

今の判定の問いは yes が「被験が正しく振る舞った」を表すので、yes/no をそのまま数える。
A のうち保留（null）した問いは U で埋めてから合格線 1〜3 を出す（運用で利用者が付けるのと同じ扱い）。
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

JUDGE_LINE, AGREE_LINE, ALPHA_LINE, HOLD_LINE = 0.90, 0.95, 0.800, 0.20


def alpha(pairs):
    """Krippendorff の α（名義尺度、2 人、欠損なし）。両方が 1 種類の値しか使っていなければ None（期待される不一致が 0）。
    同時生起の行列で、不一致の問いは (yes, no) と (no, yes) に 1 ずつ入るので、α = 1 - (n-1)・D / (n_yes・n_no) になる。"""
    n = 2 * len(pairs)
    n_yes = sum(a + b for a, b in pairs)
    d = sum(a != b for a, b in pairs)
    return None if n_yes in (0, n) else 1 - (n - 1) * d / (n_yes * (n - n_yes))


def rate(pairs):
    return sum(a == b for a, b in pairs) / len(pairs) if pairs else None


def bootstrap(pairs, times, seed):
    """問い単位で引き直した α の 2.5・97.5 パーセンタイル。引き直した組で α が出ない回は除く。"""
    rng = random.Random(seed)
    got = sorted(a for a in (alpha(rng.choices(pairs, k=len(pairs))) for _ in range(times)) if a is not None)
    return (got[round(0.025 * (len(got) - 1))], got[round(0.975 * (len(got) - 1))]) if got else None


def group_of(key):
    return re.match(r"[A-Za-z]*", key)[0]


def measure(rows, a_of, times, seed, groups, incomplete=False):
    """rows は (key, qid, U, J, A) の並び。a_of で A を取り出す（代役を同じ式で測るため）。"""
    filled = [(a_of(r) if a_of(r) is not None else r[2], r[2]) for r in rows]
    kept = [(a_of(r), r[2]) for r in rows if a_of(r) is not None]
    no_rows = [r for r in rows if r[2] is False]
    out = {"n": len(rows), "agree": rate(filled), "alpha": alpha(filled), "alpha_ci": bootstrap(filled, times, seed),
           "held": sum(a_of(r) is None for r in rows) / len(rows),
           "kept_agree": rate(kept), "kept_alpha": alpha(kept),
           "user_no": len(no_rows), "user_no_caught": sum(a_of(r) is False for r in no_rows), "user_no_held": sum(a_of(r) is None for r in no_rows),
           "groups": {}, "incomplete": incomplete}
    for g in groups:
        sub = [r for r in rows if group_of(r[0]) == g]
        if not sub:  # 利用者のラベルが無い組を黙って外すと、残りの組だけで合格と出てしまう
            out["groups"][g] = {"n": 0, "judge_user": None, "judge_agent": None, "same_side": None}
            continue
        ju = rate([(r[3], r[2]) for r in sub])
        ja = rate([(r[3], a_of(r) if a_of(r) is not None else r[2]) for r in sub])
        out["groups"][g] = {"n": len(sub), "judge_user": ju, "judge_agent": ja, "same_side": (ju >= JUDGE_LINE) == (ja >= JUDGE_LINE)}
    out["pass"] = {"1": None if any(v["same_side"] is None for v in out["groups"].values()) else all(v["same_side"] for v in out["groups"].values()), "2": out["agree"] >= AGREE_LINE,
                   "3": out["alpha"] is not None and out["alpha"] >= ALPHA_LINE, "4": out["held"] <= HOLD_LINE}
    return out


def pct(x):
    return "—" if x is None else f"{x:.1%}"


def num(x):
    return "算出不能" if x is None else f"{x:.3f}"


def show(name, m):
    print(f"## {name}（{m['n']} 問）")
    for g, v in m["groups"].items():
        if v["same_side"] is None:
            print(f"- 合格線 1（組 {g}）: 未採点（利用者のラベルが 0 件）")
            continue
        print(f"- 合格線 1（組 {g}、{v['n']} 問）: J と U {pct(v['judge_user'])}、J と A {pct(v['judge_agent'])} → 90% の線での合否が{'同じ' if v['same_side'] else '違う'}")
    ci = m["alpha_ci"]
    print(f"- 合格線 2: A と U の一致率 {pct(m['agree'])}（95% 以上）")
    print(f"- 合格線 3: A と U の α {num(m['alpha'])}（0.800 以上。問い単位の bootstrap の 95% 区間 {'算出不能' if ci is None else f'{ci[0]:.3f}〜{ci[1]:.3f}'}）")
    print(f"- 合格線 4: 保留 {pct(m['held'])}（20% 以下）")
    verdict = "未判定（利用者のラベルが無い問いがある）" if m.get("incomplete") else "未判定（未採点の組がある）" if None in m["pass"].values() else "合格" if all(m["pass"].values()) else "不合格"
    print(f"- 判定: {'、'.join(f'{k} {chr(9675) if v else chr(215) if v is False else chr(8212)}' for k, v in m['pass'].items())} → {verdict}")
    print(f"- 報告だけ: 保留しなかった問いでの一致率 {pct(m['kept_agree'])}・α {num(m['kept_alpha'])}、"
          f"U の no {m['user_no']} 問のうち A も no {m['user_no_caught']} 問（保留 {m['user_no_held']} 問）")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("human", type=Path)
    ap.add_argument("answers", type=Path)
    ap.add_argument("agent", type=Path, nargs="?", help="ラベラーの agent.json。省くと、すべて yes の代役と判定器だけを出す")
    ap.add_argument("--flipped", type=Path, help="向きを反転した問いに付けた agent.json（反転した向きのまま）。元の向きの答えと矛盾しない割合を出す")
    ap.add_argument("--reasons", type=Path, help="ラベラーの reasons.json。費用と時間を出す")
    ap.add_argument("--groups", help="測る組の英字をカンマで並べる（例: A,B）。answers.json に無い組があれば未判定にする")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=193)
    ap.add_argument("--json", type=Path, help="指標と食い違った問いを JSON で書く")
    args = ap.parse_args()
    human, answers = json.loads(args.human.read_text()), json.loads(args.answers.read_text())
    agent = json.loads(args.agent.read_text()) if args.agent else {}
    rows = [(k, j, human[k][j], judged, agent.get(k, {}).get(j)) for k, v in answers.items() for j, judged in v["judge"].items()
            if human.get(k, {}).get(j) is not None]
    if not rows:
        raise SystemExit("利用者のラベルが付いた問いがありません")
    if unlabeled := sum(len(v["judge"]) for v in answers.values()) - len(rows):
        print(f"利用者のラベルが無い問いが {unlabeled} 問あります。付いた問いだけで測るので、合否は未判定にします")
    groups = sorted({group_of(k) for k in answers} | set(args.groups.split(",") if args.groups else []))
    result = {"all_yes": measure(rows, lambda r: True, args.boot, args.seed, groups, bool(unlabeled)), "judge": measure(rows, lambda r: r[3], args.boot, args.seed, groups, bool(unlabeled))}
    if args.agent:
        if missing := [f"{r[0]}/{r[1]}" for r in rows if r[1] not in agent.get(r[0], {})]:
            raise SystemExit(f"ラベラーが付けていない問いがあります: {missing}")
        result["agent"] = measure(rows, lambda r: r[4], args.boot, args.seed, groups, bool(unlabeled))
        show("ラベラー（A）", result["agent"])
        result["disagree"] = [{"q": f"{r[0]}/{r[1]}", "user": r[2], "agent": r[4], "judge": r[3]} for r in rows if r[4] is not None and r[4] != r[2]]
        result["held"] = [{"q": f"{r[0]}/{r[1]}", "user": r[2], "judge": r[3]} for r in rows if r[4] is None]
        print("- 食い違った問い（U / A / J）:", *(f"{d['q']} {d['user']}/{d['agent']}/{d['judge']}" for d in result["disagree"]) or ["なし"])
        print("- 保留した問い（U / J）:", *(f"{d['q']} {d['user']}/{d['judge']}" for d in result["held"]) or ["なし"])
    if args.flipped:
        flipped = json.loads(args.flipped.read_text())
        both = [(agent.get(k, {}).get(j), flipped.get(k, {}).get(j)) for k, v in answers.items() for j in v["judge"]]  # 利用者のラベルが無い問いも数える
        both = [(a, f) for a, f in both if a is not None and f is not None]
        result["flip_consistent"] = {"n": len(both), "rate": rate([(a, not f) for a, f in both])}
        print(f"- 報告だけ: 反転した問いと矛盾しない割合 {pct(result['flip_consistent']['rate'])}（両方で保留しなかった {len(both)} 問）")
    if args.reasons:
        meta = json.loads(args.reasons.read_text())["meta"]
        result["cost"] = meta
        print(f"- 報告だけ: 1 回の時間 {meta['seconds']} 秒、Claude の費用 ${meta['cost_usd']['claude']}、Codex のトークン {meta['tokens']['codex']}、読めなかった答え {meta['parse_errors']}")
    show("比べる相手: すべて yes の代役", result["all_yes"])
    show("比べる相手: 判定器（J）", result["judge"])
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
