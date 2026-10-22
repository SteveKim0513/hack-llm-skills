#!/usr/bin/env python3
"""행동 장면 목록을 세션 단위 리포트(마크다운)로 만든다.

기본 지표는 "그 행동이 한 번이라도 나온 세션 수 / 분석한 세션 수"이다. 대화가 길수록 행동이 나올 기회가
늘어나므로 건수는 보조로만 쓰고, 길이 구간·프로젝트·과제 유형별로 나눠 보여 준다. 점수나 등급은 만들지 않는다.

  python3 build_report.py --sessions sample.jsonl --events events.json [--labels labels.json] [--out report.md]

sessions: 세션 JSONL (extract_sessions.py 출력). 줄 번호(0부터)가 events의 session_idx.
          선택 필드 task_type이 있으면 과제 유형별 표도 낸다.
events:   JSON 목록 또는 JSONL. 항목은 session_idx, axis, pole(능동|수용), eid 등. {"skipped": N} 줄은 무시한다.
labels:   사용자 확인 결과 [{"eid", "ai_label": "축/극", "verdict": 맞음|아님|애매}]. 있으면 분류 정확도를 낸다.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

AXES = ["검증", "구조", "방향 주도", "메타인지"]
BINS = [(0, 9, "10 미만"), (10, 29, "10~29"), (30, 10 ** 9, "30 이상")]
SMALL = 10  # 이보다 적으면 참고용이라고 표시한다
SATURATED = 0.85  # 세션 비율이 이 이상이면 구분력이 낮다고 알린다


def read_any(path):
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        return []
    if text[0] == "[":
        return json.loads(text)
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


def length_bin(n):
    for lo, hi, label in BINS:
        if lo <= n <= hi:
            return label
    return BINS[-1][2]


def analyze(sessions, events, labels=None, cap=15):
    ev = [e for e in events if isinstance(e, dict) and "session_idx" in e and "axis" in e]
    active = [e for e in ev if e.get("pole", "능동") == "능동" and e["axis"] in AXES]
    excluded = sum(1 for e in ev if e.get("pole") == "수용")

    per_session = defaultdict(Counter)
    for e in active:
        per_session[e["session_idx"]][e["axis"]] += 1
    total_events = Counter(e["session_idx"] for e in ev)

    info = []
    for i, s in enumerate(sessions):
        info.append({
            "idx": i,
            "project": s.get("project") or "(unknown)",
            "task_type": s.get("task_type") or "",
            "user_turns": user_turns_of(s),
            "axes": per_session.get(i, Counter()),
            "capped": total_events.get(i, 0) >= cap,
        })

    def group(key):
        g = defaultdict(list)
        for s in info:
            g[key(s)].append(s)
        return g

    def presence(rows):
        return {a: sum(1 for s in rows if s["axes"][a] > 0) for a in AXES}

    out = {
        "sessions": len(info),
        "user_turns": sum(s["user_turns"] for s in info),
        "presence": presence(info),
        "events_by_axis": {a: sum(s["axes"][a] for s in info) for a in AXES},
        "excluded": excluded,
        "capped": sum(1 for s in info if s["capped"]),
        "cap": cap,
        "by_length": [(label, presence(rows), len(rows)) for label, rows in
                      sorted(group(lambda s: length_bin(s["user_turns"])).items(),
                             key=lambda kv: [b[2] for b in BINS].index(kv[0]))],
        "by_project": sorted(((p, presence(rows), len(rows)) for p, rows in group(lambda s: s["project"]).items()),
                             key=lambda x: -x[2]),
        "by_task": sorted(((t, presence(rows), len(rows)) for t, rows in
                           group(lambda s: s["task_type"]).items() if t), key=lambda x: -x[2]),
        "labels": None,
    }
    if labels:
        by_eid = {e.get("eid"): e for e in ev}
        conf = defaultdict(Counter)
        for l in labels:
            if not l.get("verdict"):
                continue
            label = l.get("ai_label") or ""
            if "/" not in label and l.get("eid") in by_eid:
                e = by_eid[l["eid"]]
                label = "%s/%s" % (e["axis"], e.get("pole", "능동"))
            if "/" not in label:
                continue
            axis, pole = label.rsplit("/", 1)
            conf[(axis, pole)][l["verdict"]] += 1
        out["labels"] = {k: dict(v) for k, v in conf.items()}
    return out


def pct(k, n):
    return "%d/%d (%d%%)" % (k, n, round(100 * k / n)) if n else "0/0"


def table(rows, first):
    head = "| %s | 세션 | %s |" % (first, " | ".join(AXES))
    sep = "|---|---|" + "---|" * len(AXES)
    lines = [head, sep]
    for name, pres, n in rows:
        note = " (참고용)" if n < 3 else ""
        lines.append("| %s%s | %d | %s |" % (name, note, n, " | ".join(pct(pres[a], n) for a in AXES)))
    return "\n".join(lines)


def render(d, title="행동 프로필 리포트"):
    n = d["sessions"]
    L = ["# " + title, ""]
    L.append("분석한 세션 %d개, 사용자 발화 %d개." % (n, d["user_turns"]))
    if n < SMALL:
        L.append("**세션이 %d개 미만이라 참고용입니다.**" % SMALL)
    L += ["", "## 행동이 한 번이라도 나온 세션", "",
          "| 행동 | 세션 비율 | 관찰된 장면 수 |", "|---|---|---|"]
    for a in AXES:
        L.append("| %s | %s | %d |" % (a, pct(d["presence"][a], n), d["events_by_axis"][a]))
    L += ["", "세션 비율이 기본 지표입니다. 장면 수는 대화가 길수록 늘어나므로 세션 간 비교에 쓰지 않습니다."]
    sat = [a for a in AXES if n and d["presence"][a] / n >= SATURATED]
    if sat:
        L.append("**%s: 세션 %d%% 이상에서 나와 세션을 구분하는 힘이 낮습니다.** 길이별 표와 대표 장면을 함께 보십시오. "
                 "장면을 찾는 쪽에 \"모든 행동을 채우라\"는 지시가 들어갔다면 비율이 부풀려집니다." % (", ".join(sat), round(SATURATED * 100)))
    L += ["",
          "## 대화 길이(사용자 발화 수)별", "", table(d["by_length"], "발화 수")]
    if d["by_task"]:
        L += ["", "## 과제 유형별", "", table(d["by_task"], "과제 유형")]
    L += ["", "## 프로젝트별", "", table(d["by_project"], "프로젝트")]
    L += ["", "## 신뢰도와 한계", ""]
    L.append("- 장면 상한(%d건)에 걸려 뒤쪽이 덜 반영된 세션: %d개" % (d["cap"], d["capped"]))
    L.append("- 분류에서 제외된 장면(옛 수용 분류): %d건" % d["excluded"])
    if d["labels"] is None:
        L.append("- 사용자 확인: 없음. 모든 분류가 AI 분류입니다.")
    else:
        L.append("- 사용자 확인 결과(표본이 작으면 참고용):")
        for (axis, pole), c in sorted(d["labels"].items()):
            tot = sum(c.values())
            L.append("  - %s / %s: %d건 중 맞음 %d, 아님 %d, 애매 %d%s" % (
                axis, pole, tot, c.get("맞음", 0), c.get("아님", 0), c.get("애매", 0),
                " (참고용)" if tot < SMALL else ""))
    L += ["- 행동이 관찰되지 않았다고 해서 그 행동을 하지 않았거나 수준이 낮다는 뜻이 아닙니다. 채팅 밖에서 한 일은 로그에 없습니다.",
          "- 점수나 등급이 아닙니다. 같은 기준·같은 기간 길이의 이전 리포트와만 비교하십시오."]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sessions", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--labels")
    ap.add_argument("--cap", type=int, default=15, help="세션당 장면 상한. 이 수에 닿은 세션을 표시한다")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    sessions = read_any(os.path.expanduser(args.sessions))
    events = read_any(os.path.expanduser(args.events))
    labels = read_any(os.path.expanduser(args.labels)) if args.labels else None
    text = render(analyze(sessions, events, labels, args.cap))
    if args.out:
        out = os.path.expanduser(args.out)
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print("저장: %s" % out, file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
