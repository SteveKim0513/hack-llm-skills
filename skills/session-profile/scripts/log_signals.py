#!/usr/bin/env python3
"""로그에서 찾은 능력 기회를 능력별로 집계한다. 최종 결과 화면(build_final.py)과 비용 계산(estimate.py)의 재료를 JSON으로 낸다.

기회 기록 하나는 "이 요청(user_turn)에서 이 능력을 쓸 기회가 있었고, 결과는 보임/끊김/없음이었다"이다.
  보임  그 능력이 드러남
  끊김  그 능력이 부족해서 일이 어긋남. 원인이 사용자 쪽이라는 근거가 있을 때만
  없음  기회는 있었지만 어느 쪽도 아님
기회의 정의는 references/abilities.md. 이 스크립트는 세기만 한다.

  python3 log_signals.py --sessions sessions.jsonl --events events.jsonl [--critic critic.jsonl] \
      [--events-b second.json] --out signals.json

sessions: extract_sessions.py 출력 JSONL. 줄 번호(0부터)가 session_idx.
events:   JSON 목록 또는 JSONL. 항목은 session_idx, user_turn, ability, pole, quote, context, cause_quote, resolved_turn.
          {"skipped": N} 줄은 무시한다. "없음"이 하나도 없는 옛 형식이면 기회 = 보임 + 끊김이 된다.
critic:   끊김 재검토 결과. 항목은 session_idx, user_turn, ability, cause(사용자/AI/공동/판정 불가).
          주면 cause가 "사용자"가 아닌 끊김은 "없음"으로 바뀐다(기회는 남는다).
events-b: 독립된 두 번째 분류자가 일부 세션을 다시 본 결과 {"sessions": [...], "events": [...]}.
          sessions에는 기회가 없던 세션도 넣는다.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

ABILITIES = ["이해", "읽기", "목표 명확성", "원하는 것의 분명함", "표현 정확성", "검증"]
POLES = ["보임", "끊김", "없음"]
RANK = {"끊김": 0, "보임": 1, "없음": 2}  # 같은 요청·능력이 두 번 적히면 이 순서로 하나만 남긴다
MIN_EVIDENCE = 5  # 기회가 이보다 적으면 증거 부족


def read_any(path):
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        return []
    if text[0] in "[{":
        try:
            data = json.loads(text)
            return data if isinstance(data, list) else [data]
        except ValueError:
            pass
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def user_turns_of(session):
    if "user_turns" in session:
        return session["user_turns"]
    return sum(1 for t in session.get("turns", []) if t.get("role") == "user")


def valid(events):
    return [e for e in events if isinstance(e, dict) and "session_idx" in e
            and e.get("ability") in ABILITIES and e.get("pole") in POLES]


def key(e):
    return (e["session_idx"], e.get("user_turn"), e["ability"])


def dedupe(events):
    """같은 요청·능력의 기록은 하나만 남긴다. user_turn이 없는 옛 기록은 그대로 둔다."""
    best, loose = {}, []
    for e in events:
        if e.get("user_turn") is None:
            loose.append(e)
            continue
        k = key(e)
        if k not in best or RANK[e["pole"]] < RANK[best[k]["pole"]]:
            best[k] = e
    return list(best.values()) + loose


def apply_critic(events, critic):
    """재검토에서 원인이 사용자로 확인되지 않은 끊김은 없음으로 바꾼다. 확인 결과가 없는 끊김도 바꾼다."""
    if critic is None:
        return events, 0
    ok = {(c["session_idx"], c.get("user_turn"), c["ability"]) for c in critic
          if isinstance(c, dict) and c.get("cause") == "사용자" and "session_idx" in c and "ability" in c}
    out, dropped = [], 0
    for e in events:
        if e["pole"] == "끊김" and key(e) not in ok:
            e = dict(e, pole="없음", dropped_break=True)
            dropped += 1
        out.append(e)
    return out, dropped


def kappa(pairs):
    n = len(pairs)
    if not n:
        return None, None
    po = sum(1 for a, b in pairs if a == b) / n
    pa = sum(1 for a, _ in pairs if a) / n
    pb = sum(1 for _, b in pairs if b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return po, (None if pe >= 1 else (po - pe) / (1 - pe))


def ac1(pairs, cats):
    """그웻의 AC1. 한쪽 범주가 드물어도 카파처럼 정의되지 않거나 0으로 무너지지 않는다."""
    n = len(pairs)
    if not n or len(cats) < 2:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    pe = 0.0
    for c in cats:
        pi = (sum(1 for a, _ in pairs if a == c) + sum(1 for _, b in pairs if b == c)) / (2 * n)
        pe += pi * (1 - pi)
    pe /= len(cats) - 1
    return None if pe >= 1 else (po - pe) / (1 - pe)


def agreement(events_a, second):
    if not second:
        return None
    ids = list(dict.fromkeys(second.get("sessions", [])))
    idset = set(ids)
    va = dedupe([e for e in valid(events_a) if e["session_idx"] in idset])
    vb = dedupe(valid(second.get("events", [])))

    def present(evs):
        out = defaultdict(set)
        for e in evs:
            if e["pole"] != "없음":
                out[(e["ability"], e["pole"])].add(e["session_idx"])
        return out

    pa, pb = present(va), present(vb)
    res = {}
    for ab in ABILITIES:
        res[ab] = {}
        for pole in ("보임", "끊김"):
            pairs = [(i in pa[(ab, pole)], i in pb[(ab, pole)]) for i in ids]
            po, k = kappa(pairs)
            res[ab][pole] = {"agree": po, "kappa": k, "ac1": ac1(pairs, [True, False])}
        # 요청 단위: 두 분류자가 같은 요청을 기회로 봤는지(겹침 비율), 둘 다 본 기회에서 결과가 같은지(AC1)
        ka = {key(e): e["pole"] for e in va if e["ability"] == ab and e.get("user_turn") is not None}
        kb = {key(e): e["pole"] for e in vb if e["ability"] == ab and e.get("user_turn") is not None}
        both = set(ka) & set(kb)
        union = set(ka) | set(kb)
        res[ab]["opportunity_overlap"] = len(both) / len(union) if union else None
        res[ab]["outcome_ac1"] = ac1([(ka[k], kb[k]) for k in both], POLES) if len(both) >= 3 else None
        res[ab]["shared_opportunities"] = len(both)
    return {"sessions": len(ids), "by_ability": res}


def analyze(sessions, events, second=None, cap=15, critic=None):
    ev, dropped = apply_critic(dedupe(valid(events)), critic)
    has_none = any(e["pole"] == "없음" for e in ev)
    # 옛 형식(장면만 기록)에서는 긴 세션이 빈도를 끌어올려서 장면이 많은 세션을 빈도에서 뺐다.
    # 기회 기록에서는 분모가 기회 수라서 그럴 필요가 없다.
    total = Counter(e["session_idx"] for e in events if isinstance(e, dict) and "session_idx" in e)
    capped = set() if has_none else {i for i in range(len(sessions)) if total.get(i, 0) >= cap}
    turns_open = sum(user_turns_of(s) for i, s in enumerate(sessions) if i not in capped)
    out = {"sessions": len(sessions), "user_turns": sum(user_turns_of(s) for s in sessions),
           "capped": len(capped), "cap": cap, "turns_for_rates": turns_open,
           "opportunity_based": has_none, "critic_applied": critic is not None, "breaks_dropped_by_critic": dropped,
           "abilities": {}}
    for ab in ABILITIES:
        mine = [e for e in ev if e["ability"] == ab]
        row = {}
        for pole in POLES:
            pe = [e for e in mine if e["pole"] == pole]
            in_open = [e for e in pe if e["session_idx"] not in capped]
            row[pole] = {
                "count": len(pe),
                "sessions": len({e["session_idx"] for e in pe}),
                "per10": (10 * len(in_open) / turns_open) if turns_open else 0.0,
            }
        shown, broken = row["보임"]["count"], row["끊김"]["count"]
        opp = len(mine) if has_none else shown + broken
        row["opportunities"] = opp
        row["evidence"] = opp
        row["break_ratio"] = broken / opp if opp >= MIN_EVIDENCE else None
        row["shown_ratio"] = shown / opp if opp >= MIN_EVIDENCE else None
        projects = Counter(sessions[e["session_idx"]].get("project") or "(unknown)" for e in mine
                           if e["session_idx"] < len(sessions))
        row["projects"] = dict(projects.most_common())
        out["abilities"][ab] = row
    out["agreement"] = agreement(events, second)
    return out


def summary(d):
    lines = ["세션 %d개, 사용자 발화 %d개%s" % (
        d["sessions"], d["user_turns"],
        "" if d["opportunity_based"] else " (옛 형식: 기회 기록 없음, 상한에 걸린 세션 %d개는 빈도에서 뺌)" % d["capped"])]
    if d["critic_applied"]:
        lines.append("  재검토에서 사용자 원인으로 확인되지 않아 없음으로 바꾼 끊김 %d개" % d["breaks_dropped_by_critic"])
    for ab in ABILITIES:
        r = d["abilities"][ab]
        br = "증거 부족" if r["break_ratio"] is None else "끊김 %d%%" % round(100 * r["break_ratio"])
        lines.append("  %s: 기회 %d, 보임 %d, 끊김 %d, %s" % (ab, r["opportunities"], r["보임"]["count"], r["끊김"]["count"], br))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sessions", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--critic")
    ap.add_argument("--events-b")
    ap.add_argument("--cap", type=int, default=15)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    sessions = read_any(os.path.expanduser(a.sessions))
    events = read_any(os.path.expanduser(a.events))
    critic = read_any(os.path.expanduser(a.critic)) if a.critic else None
    second = None
    if a.events_b:
        with open(os.path.expanduser(a.events_b), encoding="utf-8") as f:
            second = json.load(f)
    d = analyze(sessions, events, second, a.cap, critic)
    out = os.path.expanduser(a.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    print(summary(d), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
