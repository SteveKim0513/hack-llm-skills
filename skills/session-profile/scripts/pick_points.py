#!/usr/bin/env python3
"""이해 확인 퀴즈의 후보 지점을 고른다.

후보: AI가 결정이 걸린 긴 답변(제안, 선택지, "할까요?")을 냈는데 사용자가 짧게 승인하고 넘어간 곳.
프로젝트를 돌아가며 세션당 하나씩 고르고, 지점마다 앞뒤 대화를 묶은 패킷을 만든다.

  python3 pick_points.py --sessions recent.jsonl --out packets.json [--total 16] [--per-project 5]

sessions: extract_sessions.py 출력 JSONL. 출력 패킷: [{pid, session_id, project, date, before, approval, after}]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, OrderedDict

# 결정이 걸린 답변의 신호. 한국어와 영어. 하나만으로는 부족해서 --min-cues개 이상을 요구한다.
CUE = re.compile(
    r"할까요|할지|중 (?:하나|어느)|선택|추천|어느 쪽|대신|트레이드오프|장단점"
    r"|should I|shall I|which (?:one|option)|recommend|instead|trade-?off|pros and cons"
    r"|^\s*\d+[.)]\s",
    re.M | re.I,
)


def is_short_approval(text, max_chars):
    t = (text or "").strip()
    return 0 < len(t) <= max_chars and "?" not in t and "？" not in t and "[붙여넣은" not in t


def candidates(sessions, max_reply=25, min_ai=600, min_cues=2, min_after=2):
    out = []
    for si, s in enumerate(sessions):
        turns = s.get("turns", [])
        for i, t in enumerate(turns):
            if t.get("role") != "user" or i == 0 or not is_short_approval(t.get("text"), max_reply):
                continue
            prev = turns[i - 1]
            if prev.get("role") != "assistant" or len(prev.get("text", "")) < min_ai:
                continue
            cues = len(CUE.findall(prev["text"]))
            if cues < min_cues:
                continue
            if sum(1 for x in turns[i + 1:i + 13] if x.get("role") == "assistant") < min_after:
                continue  # 그 뒤에 무슨 일이 있었는지 알 수 없으면 정답 기준을 세울 수 없다
            out.append({"si": si, "ti": i, "project": s.get("project") or "(unknown)", "cues": cues,
                        "ai_len": len(prev["text"])})
    return out


def pick(cands, total=16, per_project=5):
    """프로젝트를 돌아가며 하나씩, 세션당 하나만. 결정 신호가 많고 답변이 긴 것부터."""
    by = OrderedDict()
    for c in sorted(cands, key=lambda c: (c["project"], -c["cues"], -c["ai_len"])):
        by.setdefault(c["project"], []).append(c)
    order = sorted(by, key=lambda p: -len(by[p]))
    picked, seen, cnt = [], set(), Counter()
    while len(picked) < total:
        added = False
        for p in order:
            if cnt[p] >= per_project:
                continue
            for c in by[p]:
                if c["si"] in seen:
                    continue
                picked.append(c)
                seen.add(c["si"])
                cnt[p] += 1
                added = True
                break
            if len(picked) >= total:
                break
        if not added:
            break
    return picked


def packet(pid, session, ti, before=4, after=14):
    turns = session["turns"]
    keep = lambda xs: [{"role": x["role"], "text": x["text"]} for x in xs]
    return {"pid": pid, "session_id": session.get("id"), "project": session.get("project"),
            "date": (session.get("started_at") or "")[:10], "approval_turn": ti,
            "before": keep(turns[max(0, ti - before):ti]), "approval": turns[ti]["text"],
            "after": keep(turns[ti + 1:ti + 1 + after])}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sessions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--total", type=int, default=16)
    ap.add_argument("--per-project", type=int, default=5)
    ap.add_argument("--max-reply-chars", type=int, default=25, help="이보다 긴 사용자 발화는 승인으로 보지 않는다")
    ap.add_argument("--min-ai-chars", type=int, default=600)
    ap.add_argument("--min-cues", type=int, default=2)
    ap.add_argument("--exclude-session", action="append", default=[], help="뺄 세션 id (지금 진행 중인 대화 등)")
    args = ap.parse_args(argv)
    with open(os.path.expanduser(args.sessions), encoding="utf-8") as f:
        sessions = [json.loads(l) for l in f if l.strip()]
    sessions = [s for s in sessions if s.get("id") not in set(args.exclude_session)]
    cands = candidates(sessions, args.max_reply_chars, args.min_ai_chars, args.min_cues)
    chosen = pick(cands, args.total, args.per_project)
    packets = [packet(k, sessions[c["si"]], c["ti"]) for k, c in enumerate(chosen)]
    out = os.path.expanduser(args.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(packets, f, ensure_ascii=False)
    print("후보 %d개 → %d개 선택 %s" % (len(cands), len(packets), dict(Counter(p["project"] for p in packets))),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
