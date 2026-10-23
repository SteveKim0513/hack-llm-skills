#!/usr/bin/env python3
"""로그에서 찾은 능력 장면을 능력별로 집계한다. 최종 결과 화면(build_final.py)의 재료를 JSON으로 낸다.

장면은 능력(ability)과 극(pole: "보임" 또는 "끊김")을 가진다. 끊김은 원인이 사용자 쪽이라는 근거가 있을 때만
기록된 것이어야 한다(references/abilities.md). 이 스크립트는 세기만 한다.

  python3 log_signals.py --sessions sessions.jsonl --events events.json [--events-b second.json] --out signals.json

sessions: extract_sessions.py 출력 JSONL. 줄 번호(0부터)가 events의 session_idx.
events:   JSON 목록 또는 JSONL. 항목은 session_idx, ability, pole, quote 등. {"skipped": N} 줄은 무시한다.
events-b: 독립된 두 번째 분류자가 일부 세션을 다시 본 결과 {"sessions": [...], "events": [...]}.
          sessions에는 장면이 없던 세션도 넣는다. 있으면 능력·극마다 "그 세션에 있었나"의 일치율과 코헨 카파를 낸다.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

ABILITIES = ["이해", "읽기", "목표 명확성", "원하는 것의 분명함", "표현 정확성", "검증"]
POLES = ["보임", "끊김"]
MIN_EVIDENCE = 5  # 보임+끊김이 이보다 적으면 증거 부족


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


def kappa(pairs):
    n = len(pairs)
    if not n:
        return None, None
    po = sum(1 for a, b in pairs if a == b) / n
    pa = sum(1 for a, _ in pairs if a) / n
    pb = sum(1 for _, b in pairs if b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return po, (None if pe >= 1 else (po - pe) / (1 - pe))


def agreement(events_a, second):
    if not second:
        return None
    ids = list(dict.fromkeys(second.get("sessions", [])))

    def present(evs):
        out = defaultdict(set)
        for e in valid(evs):
            out[(e["ability"], e["pole"])].add(e["session_idx"])
        return out

    pa, pb = present(events_a), present(second.get("events", []))
    res = {}
    for ab in ABILITIES:
        res[ab] = {}
        for pole in POLES:
            po, k = kappa([(i in pa[(ab, pole)], i in pb[(ab, pole)]) for i in ids])
            res[ab][pole] = {"agree": po, "kappa": k}
    return {"sessions": len(ids), "by_ability": res}


def analyze(sessions, events, second=None, cap=15):
    ev = valid(events)
    total = Counter(e["session_idx"] for e in events if isinstance(e, dict) and "session_idx" in e)
    capped = {i for i in range(len(sessions)) if total.get(i, 0) >= cap}
    turns_open = sum(user_turns_of(s) for i, s in enumerate(sessions) if i not in capped)
    out = {"sessions": len(sessions), "user_turns": sum(user_turns_of(s) for s in sessions),
           "capped": len(capped), "cap": cap, "turns_for_rates": turns_open, "abilities": {}}
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
        row["break_ratio"] = broken / (shown + broken) if shown + broken >= MIN_EVIDENCE else None
        row["evidence"] = shown + broken
        projects = Counter(sessions[e["session_idx"]].get("project") or "(unknown)" for e in mine
                           if e["session_idx"] < len(sessions))
        row["projects"] = dict(projects.most_common())
        out["abilities"][ab] = row
    out["agreement"] = agreement(events, second)
    return out


def summary(d):
    lines = ["세션 %d개, 사용자 발화 %d개 (상한에 걸린 세션 %d개는 비율 계산에서 뺌)" % (
        d["sessions"], d["user_turns"], d["capped"])]
    for ab in ABILITIES:
        r = d["abilities"][ab]
        br = "증거 부족" if r["break_ratio"] is None else "끊김 비율 %d%%" % round(100 * r["break_ratio"])
        lines.append("  %s: 보임 %d, 끊김 %d, %s" % (ab, r["보임"]["count"], r["끊김"]["count"], br))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sessions", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--events-b")
    ap.add_argument("--cap", type=int, default=15)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    sessions = read_any(os.path.expanduser(a.sessions))
    events = read_any(os.path.expanduser(a.events))
    second = None
    if a.events_b:
        with open(os.path.expanduser(a.events_b), encoding="utf-8") as f:
            second = json.load(f)
    d = analyze(sessions, events, second, a.cap)
    out = os.path.expanduser(a.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    print(summary(d), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
