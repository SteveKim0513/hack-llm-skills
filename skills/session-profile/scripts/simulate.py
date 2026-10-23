#!/usr/bin/env python3
"""판정 규칙(build_final.judge)을 지어낸 사람들에게 돌려서 문턱이 얼마나 틀리는지 잰다.

진짜 능력을 아는 가상의 사람을 만들고, 그 능력에서 로그 장면과 과제 점수를 뽑은 뒤 판정을 붙인다.
  차이 없음: 모든 능력이 같은 사람. 여기서 붙은 "먼저 보완"은 전부 거짓 약점이다.
  약점 하나: 한 능력만 로짓으로 --effect만큼 낮은 사람. 그 능력을 잡는 비율과 엉뚱한 능력을 잡는 비율을 본다.

숫자는 이 가정 아래에서만 맞다. 실제 사람의 능력 차이가 어느 정도인지는 모른다(확인하지 못함).

  python3 simulate.py                          # 기본 시나리오와 문턱 후보
  python3 simulate.py --gates 1.64,2.0 --trials 4000 --json out.json
"""
import argparse
import json
import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_final as bf  # noqa: E402

# (이름, 능력마다 로그 장면 수 범위, 능력마다 과제 점수 범위). 범위면 능력마다 고르게 뽑는다.
SCENARIOS = [
    ("최소 증거", (5, 5), (3, 3)),
    ("보통", (10, 10), (6, 6)),
    ("많음", (25, 25), (10, 10)),
    ("고르지 않음 (실제 실행과 비슷)", (0, 40), (0, 8)),
]


def logit(p):
    return math.log(p / (1 - p))


def inv(x):
    return 1 / (1 + math.exp(-x))


def binom(rng, n, p):
    return sum(1 for _ in range(n) if rng.random() < p)


def person(rng, names, log_range, task_range, p_log, p_task, weak=None, effect=0.0):
    out = []
    for n in names:
        d = effect if n == weak else 0.0
        nl = rng.randint(*log_range)
        nt = rng.randint(*task_range)
        k = binom(rng, nl, inv(logit(p_log) - d))
        g = binom(rng, nt, inv(logit(p_task) - d))
        out.append({"name": n, "log": {"shown": k, "broken": nl - k}, "task": {"got": g, "total": nt}})
    return out


def run(gate, scenario, trials, seed, names, p_log, p_task, effect, mix=None):
    _, log_range, task_range = scenario
    rng = random.Random(seed)
    old, old_mix = bf.GATE, bf.GATE_MIX
    bf.GATE = gate
    bf.GATE_MIX = mix or bf.GATE_MIX
    try:
        null_any = null_strength = null_mixed = 0
        hit = wrong = hypo_hit = 0
        for _ in range(trials):
            v = bf.judge(person(rng, names, log_range, task_range, p_log, p_task))
            st = [x["status"] for x in v.values()]
            null_any += "먼저 보완" in st
            null_strength += "강점" in st
            null_mixed += "증거가 엇갈림" in st
        for _ in range(trials):
            weak = rng.choice(names)
            v = bf.judge(person(rng, names, log_range, task_range, p_log, p_task, weak, effect))
            focus = [n for n, x in v.items() if x["status"] == "먼저 보완"]
            hit += weak in focus
            wrong += any(n != weak for n in focus)
            if focus:
                top = min(focus, key=lambda n: v[n]["z"])
            else:
                cand = [n for n, x in v.items() if x.get("z") is not None]
                top = min(cand, key=lambda n: v[n]["z"]) if cand else None
            hypo_hit += top == weak
    finally:
        bf.GATE, bf.GATE_MIX = old, old_mix
    t = float(trials)
    return {"gate": gate, "scenario": scenario[0],
            "false_weakness_person": null_any / t, "false_strength_person": null_strength / t,
            "false_mixed_person": null_mixed / t,
            "power": hit / t, "wrong_target": wrong / t, "top_is_weak": hypo_hit / t}


def table(rows):
    head = "%-28s %5s | %8s %8s %8s | %6s %8s %8s" % ("시나리오", "문턱", "거짓약점", "거짓강점", "거짓엇갈", "잡음", "엉뚱함", "맨아래맞음")
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append("%-28s %5.2f | %7.1f%% %7.1f%% %7.1f%% | %5.1f%% %7.1f%% %7.1f%%" % (
            r["scenario"], r["gate"], 100 * r["false_weakness_person"], 100 * r["false_strength_person"],
            100 * r["false_mixed_person"], 100 * r["power"], 100 * r["wrong_target"], 100 * r["top_is_weak"]))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gates", default="1.64,1.96,2.13,2.39")
    ap.add_argument("--mix", type=float, help="엇갈림 문턱. 없으면 build_final의 값")
    ap.add_argument("--trials", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--p-log", type=float, default=0.9, help="로그 장면 중 어긋나지 않은 비율(차이 없을 때)")
    ap.add_argument("--p-task", type=float, default=0.6, help="과제 득점률(차이 없을 때)")
    ap.add_argument("--effect", type=float, default=1.0, help="약한 능력을 로짓으로 얼마나 낮출지. 1.0이면 0.9→0.77, 0.6→0.36")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    names = list(bf.ABILITIES)
    rows = [run(float(g), sc, a.trials, a.seed, names, a.p_log, a.p_task, a.effect, a.mix)
            for sc in SCENARIOS for g in a.gates.split(",")]
    print("능력 %d개 · 사람 %d명씩 · 차이 없을 때 로그 %.2f 과제 %.2f · 약점 크기 로짓 %.1f" % (
        len(names), a.trials, a.p_log, a.p_task, a.effect))
    print("거짓약점/거짓강점/거짓엇갈: 차이 없는 사람에게 하나라도 붙은 비율. 잡음: 약한 능력에 먼저 보완이 붙은 비율.")
    print("엉뚱함: 다른 능력에 먼저 보완이 붙은 비율. 맨아래맞음: 먼저 보완이나 시험해 볼 가설로 고른 능력이 진짜 약한 능력인 비율.\n")
    print(table(rows))
    if a.json:
        with open(os.path.expanduser(a.json), "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
