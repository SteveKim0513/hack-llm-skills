#!/usr/bin/env python3
"""능력마다 점수와 "그 습관의 비용"을 계산한다. 같은 단위(다시 작업, 분)라서 능력끼리 바로 견줄 수 있다.

능력의 비율은 능력마다 원래 흔한 정도가 달라서(예: 근거를 요청하는 행동은 누구에게나 드물다) 바로 견주기 어렵다.
그래서 "무엇을 먼저 고칠까"는 사용자 원인의 끊김이 실제로 만든 다시 작업으로 정한다.

  python3 estimate.py --events events.jsonl --critic critic.jsonl --episodes episodes.jsonl --out estimate.json

events:   log_signals.py와 같은 기회 기록. 끊김에는 resolved_turn(다시 제자리로 돌아온 사용자 턴)을 적는다.
critic:   끊김 재검토. 주면 원인이 사용자로 확인된 끊김만 비용에 넣는다.
episodes: episodes.py 출력(같은 sessions.jsonl로 만든 것). 다시 작업의 시간을 여기서 읽는다.

계산
  점수        100 × (1 − 끊김 ÷ 기회). 제프리스 80% 구간. 구간 폭이 TARGET_WIDTH보다 넓으면 기회가 몇 개 더 필요한지 어림한다.
  비용        끊김이 난 요청 t부터 제자리로 돌아온 요청(resolved_turn) 바로 앞까지의 에피소드 수와 시간
              (AI 작업 + 사람이 그 결과를 읽고 바로잡은 시간). resolved_turn이 없으면 요청 t 하나만 센다(최소 추정).
              요청 100개당으로 바꾼다. 버려진 에피소드 안에 쓸모 있던 작업이 섞였을 수 있어 많게 잡힐 수 있다.
  구간        세션을 복원 추출해 BOOT번 다시 계산한 80% 구간. "가장 비쌌던 비율"도 여기서 센다.
  보임의 효과  기회에서 보임이었던 요청과 없음이었던 요청의 다음 3개 에피소드 안 다시 작업 비율의 차이.
              결과 화면에는 내지 않는다. 시험 실행에서 검증이 드러난 요청 뒤에 다시 작업이 더 많았다(확인해서 문제를
              찾으면 고칠 일이 생긴다). 짝지어 비교하기 전까지는 참고용이다.
"""
import argparse
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import log_signals as ls  # noqa: E402

ABILITIES = ls.ABILITIES
TARGET_WIDTH = 20.0  # 점수 80% 구간이 이보다 넓으면 "아직"
MAX_REWORK = 6       # 끊김 하나가 만든 다시 작업으로 셀 최대 에피소드 수
WINDOW = 3           # 보임의 효과를 볼 에피소드 수
BOOT = 2000
MIN_GROUP = 5


def quantiles(xs, lo=0.1, hi=0.9):
    s = sorted(xs)
    if not s:
        return None, None
    return s[int(lo * (len(s) - 1))], s[int(hi * (len(s) - 1))]


def score(opp, broken, rng, draws=4000):
    if opp < ls.MIN_EVIDENCE:
        return None
    xs = [100 * (1 - rng.betavariate(broken + 0.5, opp - broken + 0.5)) for _ in range(draws)]
    lo, hi = quantiles(xs)
    point = 100 * (1 - broken / opp)
    width = hi - lo
    more = None
    if width > TARGET_WIDTH:
        more = max(1, math.ceil(opp * (width / TARGET_WIDTH) ** 2) - opp)
    return {"point": round(point), "low": round(lo), "high": round(hi), "more_needed": more}


def rework_of(e, eps):
    """끊김 하나가 만든 다시 작업. 요청 t가 어긋났으면 그 요청의 AI 작업부터 버려진다.
    버려진 에피소드: t부터 제자리로 돌아온 요청 r의 바로 앞까지(t..r-1).
    버려진 시간: 그 에피소드들의 AI 작업 시간 + 사람이 그 결과를 읽고 바로잡느라 쓴 시간(t+1..r의 읽는 시간)."""
    t = e.get("user_turn")
    if t is None:
        return None
    s = e["session_idx"]
    r = e.get("resolved_turn")
    minimum = not (isinstance(r, int) and r > t)
    end = t + 1 if minimum else min(r, t + MAX_REWORK)
    turns = [x for x in range(t, end) if (s, x) in eps]
    secs = sum(eps[(s, x)].get("work_s") or 0 for x in turns)
    secs += sum((eps[(s, x)].get("wait_before_s") or 0) for x in range(t + 1, end + 1) if (s, x) in eps)
    return {"episodes": len(turns), "minutes": secs / 60, "minimum": minimum}


def troubled(eps, s, t):
    """요청 t부터 WINDOW개 에피소드 안에 다시 작업의 흔적이 있었나."""
    for x in range(t, t + WINDOW):
        ep = eps.get((s, x))
        if ep and (ep.get("reedited_files") or ep.get("interrupted") or ep.get("next_correction_cue") or ep.get("next_repeat")):
            return True
    return False


def compute(events, eps, sessions, requests):
    """sessions: 계산에 넣을 session_idx 목록(복원 추출이면 중복 가능). requests: 그 세션들의 요청 수 합."""
    by_s = {}
    for e in events:
        by_s.setdefault(e["session_idx"], []).append(e)
    out = {}
    for ab in ABILITIES:
        eps_n = mins = 0.0
        shown_t = shown_n = none_t = none_n = 0
        for s in sessions:
            for e in by_s.get(s, []):
                if e["ability"] != ab:
                    continue
                if e["pole"] == "끊김":
                    rw = e["_rework"]
                    if rw:
                        eps_n += rw["episodes"]
                        mins += rw["minutes"]
                elif e.get("user_turn") is not None and not e.get("dropped_break"):
                    bad = troubled(eps, s, e["user_turn"])
                    if e["pole"] == "보임":
                        shown_n += 1
                        shown_t += bad
                    else:
                        none_n += 1
                        none_t += bad
        out[ab] = {"rework_per100": 100 * eps_n / requests if requests else 0.0,
                   "minutes_per100": 100 * mins / requests if requests else 0.0,
                   "shown": (shown_t, shown_n), "none": (none_t, none_n)}
    return out


def estimate(events, critic, episodes_rows, seed=0, boot=BOOT):
    rng = random.Random(seed)
    ev, _ = ls.apply_critic(ls.dedupe(ls.valid(events)), critic)
    ev = [dict(e) for e in ev]  # 입력을 바꾸지 않는다
    eps = {}
    req_by_s = {}
    for r in episodes_rows:
        if r.get("missing"):
            continue
        req_by_s[r["session_idx"]] = len(r.get("episodes", []))
        for ep in r.get("episodes", []):
            eps[(r["session_idx"], ep["user_turn"])] = ep
    ev = [e for e in ev if e["session_idx"] in req_by_s]
    for e in ev:
        e["_rework"] = rework_of(e, eps) if e["pole"] == "끊김" else None
    sessions = sorted(req_by_s)
    requests = sum(req_by_s.values())
    base = compute(ev, eps, sessions, requests)

    samples = {ab: [] for ab in ABILITIES}
    effects = {ab: [] for ab in ABILITIES}
    top = {ab: 0 for ab in ABILITIES}
    for _ in range(boot if sessions else 0):
        pick = [rng.choice(sessions) for _ in sessions]
        c = compute(ev, eps, pick, sum(req_by_s[s] for s in pick))
        for ab in ABILITIES:
            samples[ab].append(c[ab]["minutes_per100"])
            (st, sn), (nt, nn) = c[ab]["shown"], c[ab]["none"]
            if sn and nn:
                effects[ab].append(100 * (st / sn - nt / nn))
        best = max(ABILITIES, key=lambda a: c[a]["minutes_per100"])
        if c[best]["minutes_per100"] > 0:
            top[best] += 1

    out = {"sessions": len(sessions), "requests": requests, "abilities": {}}
    for ab in ABILITIES:
        mine = [e for e in ev if e["ability"] == ab]
        opp = len(mine)
        broken = [e for e in mine if e["pole"] == "끊김"]
        b = base[ab]
        lo, hi = quantiles(samples[ab])
        (st, sn), (nt, nn) = b["shown"], b["none"]
        eff = None
        if sn >= MIN_GROUP and nn >= MIN_GROUP:
            elo, ehi = quantiles(effects[ab])
            eff = {"after_shown": round(100 * st / sn), "after_none": round(100 * nt / nn),
                   "diff": round(100 * (st / sn - nt / nn)), "low": round(elo) if elo is not None else None,
                   "high": round(ehi) if ehi is not None else None, "n_shown": sn, "n_none": nn}
        out["abilities"][ab] = {
            "opportunities": opp,
            "shown": sum(1 for e in mine if e["pole"] == "보임"),
            "broken": len(broken),
            "score": score(opp, len(broken), rng),
            "cost": {"rework_per100": round(b["rework_per100"], 1), "minutes_per100": round(b["minutes_per100"], 1),
                     "minutes_low": round(lo, 1) if lo is not None else None,
                     "minutes_high": round(hi, 1) if hi is not None else None,
                     "minimum_estimate": sum(1 for e in broken if e["_rework"] and e["_rework"]["minimum"]),
                     "top_share": round(top[ab] / boot, 2) if sessions and boot else None},
            "effect_of_shown": eff,
        }
    out["costliest"] = costliest(out["abilities"])
    return out


def costliest(abilities):
    """요청 100개당 다시 작업 시간이 가장 큰 능력. 끊김이 2개 미만이면 고르지 않는다."""
    cand = [(ab, v) for ab, v in abilities.items() if v["broken"] >= 2 and v["cost"]["minutes_per100"] > 0]
    if not cand:
        return None
    ab, v = max(cand, key=lambda x: x[1]["cost"]["minutes_per100"])
    return {"ability": ab, **v["cost"], "broken": v["broken"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--events", required=True)
    ap.add_argument("--critic")
    ap.add_argument("--episodes", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    events = ls.read_any(os.path.expanduser(a.events))
    critic = ls.read_any(os.path.expanduser(a.critic)) if a.critic else None
    rows = ls.read_any(os.path.expanduser(a.episodes))
    d = estimate(events, critic, rows, a.seed)
    out = os.path.expanduser(a.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    lines = ["세션 %d개, 요청 %d개" % (d["sessions"], d["requests"])]
    for ab, v in d["abilities"].items():
        sc = v["score"]
        lines.append("  %s: 기회 %d, 끊김 %d, 점수 %s, 요청 100개당 다시 작업 %.1f번 %.1f분 (가장 비쌌던 비율 %s)" % (
            ab, v["opportunities"], v["broken"], "부족" if not sc else "%d (%d~%d)" % (sc["point"], sc["low"], sc["high"]),
            v["cost"]["rework_per100"], v["cost"]["minutes_per100"], v["cost"]["top_share"]))
    c = d["costliest"]
    lines.append("가장 비싼 습관: %s" % (c["ability"] if c else "아직 없음 (끊김 2개 이상인 능력 없음)"))
    print("\n".join(lines), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
