#!/usr/bin/env python3
"""분류·채점 결과와 확인 질문 점수로 최종 점수를 계산해 한 장짜리 HTML로 만든다. 계산은 모두 여기서 한다.

  python3 score.py --sessions sessions.jsonl --turns turns.jsonl [--turns-b recheck.jsonl] [--graded graded.json] \
      --out report.html [--json result.json]

점수(0~100)
  기준 점수   기록(요청 채점)과 직접 확인(확인 질문 답, 읽기 과제)을 따로 낸다. 섞으면 수백 개의 무난한 요청이
             몇 개의 어려운 확인 결과를 덮는다. 대표 점수는 직접 확인이 2개 이상이면 그것, 아니면 기록이다.
  구간       세션 단위로 복원 추출해 다시 계산한 80% 구간. 같은 세션의 요청끼리는 닮아서 요청을 하나씩 따로 보면 구간이 지나치게 좁다.
  종류별 품질 지시, 질문은 요청마다 매긴 기준들의 평균. 진행은 확인 질문 답의 평균(진행 요청 전체를 이걸로 어림한다).
  종합       종류별 품질을 그 종류가 대화에서 차지한 비율로 가중 평균한다.
"""
import argparse
import html
import json
import os
import random
import sys

TYPES = ["지시", "질문", "진행"]
CRITERIA = ["논리력", "이해력", "표현", "문해력"]
QUIZ_KIND = {"동작": "이해력", "공백": "논리력", "읽기": "문해력"}
PRACTICE = {
    "논리력": "AI 제안을 받아들이기 전에 \"이게 안 되는 경우는 언제야?\"를 하나 묻고, 답을 듣고 나서 진행한다",
    "이해력": "AI 제안을 받아들이기 전에 \"그럼 지금부터 X하면 Y가 되는 거지?\"를 한 문장으로 되묻는다",
    "표현": "보내기 전에 대상, 범위, 끝났다고 볼 조건, 빠질 것을 한 줄씩 적는다",
    "문해력": "긴 답변을 받으면 마지막 질문과 경고부터 찾고, 답장에서 그것부터 답한다",
}
MIN_N = 5      # 기록 증거가 이보다 적으면 대표 점수로 쓰지 않는다
MIN_TEST = 2   # 직접 확인이 이만큼 있으면 기록 대신 대표 점수로 쓴다
AGREE_TYPE = 0.7   # 두 채점자의 종류 일치가 이보다 낮으면 결과에 경고
AGREE_DIFF = 1.0   # 같은 기준 점수 차이의 평균이 이보다 크면 경고


def read_jsonl(path):
    with open(os.path.expanduser(path), encoding="utf-8") as f:
        text = f.read().strip()
    if text.startswith("["):
        return json.loads(text)
    return [json.loads(l) for l in text.splitlines() if l.strip()]


def user_texts(session):
    return [t["text"] for t in session["turns"] if t["role"] == "user"]


def clean(turns, sessions):
    """인용이 원문에 없는 기록과 중복을 뺀다."""
    texts = [user_texts(s) for s in sessions]
    seen, out, bad = set(), [], 0
    for t in turns:
        s, u = t.get("session_idx"), t.get("user_turn")
        if t.get("type") not in TYPES + ["기타"] or s is None or s >= len(texts) or u is None or u >= len(texts[s]):
            bad += 1
            continue
        q = (t.get("quote") or "").strip()
        if q and q not in texts[s][u]:
            bad += 1
            continue
        if (s, u) in seen:
            continue
        seen.add((s, u))
        out.append(t)
    return out, bad


BOOT = 1000


def stat(pairs, seed=0):
    """pairs: (세션, 0~3점). 점수는 평균 ÷ 3 × 100, 구간은 세션 단위 복원 추출의 80%."""
    pairs = [(g, x) for g, x in pairs if x is not None]
    if not pairs:
        return None
    pct = lambda v: round(100 * v / 3)
    groups = {}
    for g, x in pairs:
        groups.setdefault(g, []).append(x)
    keys = list(groups)
    low = high = None
    if len(keys) > 1:
        rng = random.Random(seed)
        means = []
        for _ in range(BOOT):
            xs = [x for k in (rng.choice(keys) for _ in keys) for x in groups[k]]
            means.append(sum(xs) / len(xs))
        means.sort()
        low, high = pct(means[int(0.1 * (BOOT - 1))]), pct(means[int(0.9 * (BOOT - 1))])
    return {"score": pct(sum(x for _, x in pairs) / len(pairs)), "low": low, "high": high, "n": len(pairs), "sessions": len(keys)}


def agreement(a, b):
    if not b:
        return None
    ka = {(t["session_idx"], t["user_turn"]): t for t in a}
    pairs = [(ka[(t["session_idx"], t["user_turn"])], t) for t in b if (t["session_idx"], t["user_turn"]) in ka]
    if not pairs:
        return None
    same = sum(1 for x, y in pairs if x["type"] == y["type"]) / len(pairs)
    diffs = [abs(x["scores"][c] - y["scores"][c]) for x, y in pairs for c in CRITERIA
             if (x.get("scores") or {}).get(c) is not None and (y.get("scores") or {}).get(c) is not None]
    md = sum(diffs) / len(diffs) if diffs else None
    return {"turns": len(pairs), "type_agree": round(same, 2), "score_diff": round(md, 2) if md is not None else None,
            "warn": same < AGREE_TYPE or (md is not None and md > AGREE_DIFF)}


def compute(sessions, turns, turns_b=None, graded=None):
    turns, bad = clean(turns, sessions)
    turns_b = clean(turns_b, sessions)[0] if turns_b else None
    graded = [g for g in (graded or []) if g.get("score") is not None]
    counted = [t for t in turns if t["type"] in TYPES]
    n = {k: sum(1 for t in counted if t["type"] == k) for k in TYPES}
    total = sum(n.values())
    share = {k: (n[k] / total if total else 0) for k in TYPES}

    ev = {c: [] for c in CRITERIA}      # 기록
    ev_test = {c: [] for c in CRITERIA}  # 직접 확인
    quality = {"지시": [], "질문": [], "진행": []}
    examples = {c: [] for c in CRITERIA}
    for t in counted:
        sc = {c: v for c, v in (t.get("scores") or {}).items() if c in CRITERIA and isinstance(v, (int, float))}
        for c, v in sc.items():
            ev[c].append((t["session_idx"], v))
            examples[c].append((v, t.get("quote"), t.get("reason")))
        if t["type"] in ("지시", "질문") and sc:
            quality[t["type"]].append((t["session_idx"], sum(sc.values()) / len(sc)))
    for g in graded:
        c = QUIZ_KIND.get(g.get("kind"))
        grp = g.get("session_idx", "q:%s" % g.get("id"))  # 읽기 과제는 세션이 없으니 문항마다 따로 센다
        if c:
            ev_test[c].append((grp, g["score"]))
        if g.get("kind") in ("동작", "공백"):
            quality["진행"].append((grp, g["score"]))  # 읽기 과제는 진행 요청의 어림에 넣지 않는다

    crit = {}
    for c in CRITERIA:
        lg, ts = stat(ev[c]), stat(ev_test[c])
        main = ts if ts and ts["n"] >= MIN_TEST else lg if lg and lg["n"] >= MIN_N else None
        crit[c] = {"log": lg, "test": ts, "main": main, "from": None if not main else ("test" if main is ts else "log")}
    qual = {k: stat(quality[k]) for k in TYPES}
    have = [k for k in TYPES if qual[k] and share[k] > 0]
    w = sum(share[k] for k in have)
    overall = round(sum(share[k] * qual[k]["score"] for k in have) / w) if w else None
    ranked = sorted([c for c in CRITERIA if crit[c]["main"]], key=lambda c: crit[c]["main"]["score"])
    weakest = ranked[0] if ranked else None
    clear = False
    if weakest and len(ranked) > 1 and crit[weakest]["main"]["high"] is not None:
        rest = sum(crit[c]["main"]["score"] for c in ranked[1:]) / (len(ranked) - 1)
        clear = crit[weakest]["main"]["high"] < rest
    low_examples = sorted([x for x in examples.get(weakest, []) if x[0] <= 1], key=lambda x: x[0])[:3] if weakest else []
    return {"sessions": len(sessions), "turns": total, "dropped": bad, "counts": n,
            "share": {k: round(v, 2) for k, v in share.items()}, "quality": qual, "criteria": crit,
            "overall": overall, "overall_missing": [k for k in TYPES if k not in have and share[k] > 0],
            "weakest": weakest, "weakest_clear": clear, "examples": low_examples,
            "quiz": {"answered": sum(1 for g in graded if g.get("kind") in ("동작", "공백")), "reading": sum(1 for g in graded if g.get("kind") == "읽기")}, "agreement": agreement(turns, turns_b)}


CSS = """
:root{--bg:#f7f6f3;--card:#fff;--ink:#1d2125;--mute:#69707a;--line:#e4e1da;--accent:#2f5d50;--bad:#a4442f;--soft:#eef3f0}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#15171a;--card:#1e2225;--ink:#e8e6e1;--mute:#9aa1a9;--line:#30363b;--accent:#7fc4ad;--bad:#f09a86;--soft:#1f2e29}}
:root[data-theme="dark"]{--bg:#15171a;--card:#1e2225;--ink:#e8e6e1;--mute:#9aa1a9;--line:#30363b;--accent:#7fc4ad;--bad:#f09a86;--soft:#1f2e29}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:720px;margin:0 auto;padding:24px 16px 64px}h1{font-size:21px;margin:0 0 4px}h2{font-size:17px;margin:30px 0 8px}
.meta{color:var(--mute);font-size:13px}.lead{font-size:19px;font-weight:650;line-height:1.5;margin:16px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0}
.row{display:grid;grid-template-columns:7em 1fr auto;gap:10px;align-items:center;padding:6px 0;border-top:1px solid var(--line)}
.row:first-child{border-top:0}.track{background:var(--line);border-radius:6px;height:10px;overflow:hidden}.fill{background:var(--accent);height:100%}
blockquote{margin:8px 0 2px;padding:6px 10px;border-left:3px solid var(--bad);background:var(--soft);border-radius:0 8px 8px 0;white-space:pre-wrap;font-size:14px}
ul{margin:4px 0 0 18px;padding:0}.lbl{font-size:15px}
"""


def e(x):
    return html.escape("" if x is None else str(x))


def bar(name, st, note=""):
    if not st:
        return '<div class="row"><b>%s</b><span class="meta">증거 없음</span><span></span></div>' % e(name)
    rng = " (%s~%s)" % (st["low"], st["high"]) if st["low"] is not None else ""
    return ('<div class="row"><b>%s</b><div class="track"><div class="fill" style="width:%d%%"></div></div>'
            '<span><b>%d</b><span class="meta">%s · %d개%s</span></span></div>') % (e(name), st["score"], st["score"], e(rng), st["n"], e(note))


def render(d):
    b = []
    b.append('<h1>AI와 일하는 실력</h1><div class="meta">세션 %d개 · 요청 %d개 · 확인 질문 %d개 · 읽기 과제 %d개</div>' % (
        d["sessions"], d["turns"], d["quiz"]["answered"], d["quiz"]["reading"]))
    w = d["weakest"]
    if d["overall"] is not None:
        lead = "종합 %d점이에요." % d["overall"]
        pq = d["quality"]["진행"]
        if pq:
            lead += " 요청의 %d%%를 자기 판단 없이 AI에 맡겼고, 그렇게 넘어간 내용을 직접 물어보니 %d점이었어요." % (
                round(100 * d["share"]["진행"]), pq["score"])
        if w:
            m = d["criteria"][w]["main"]
            lead += " 가장 낮은 기준은 <b>%s</b>(%s %d점)%s." % (
                e(w), "직접 확인" if d["criteria"][w]["from"] == "test" else "기록", m["score"],
                "예요" if d["weakest_clear"] else "이지만, 다른 기준과의 차이가 측정의 흔들림 안이에요")
        b.append('<p class="lead">%s</p>' % lead)
    if d["overall_missing"]:
        b.append('<p class="meta">%s 요청의 품질을 잴 증거가 없어 종합에서 뺐어요.</p>' % e(", ".join(d["overall_missing"])))
    sh = d["share"]
    b.append('<h2>대화의 구성</h2><div class="card">'
             + "".join(bar(k, d["quality"][k], " · 대화의 %d%%" % round(100 * sh[k])) for k in TYPES)
             + '<p class="meta" style="margin:8px 0 0">지시는 자기 판단을 더한 요청, 진행은 판단 없이 맡긴 요청이에요("네", "고쳐줘", "알아서 해" 포함). '
               '지시와 질문은 그 글을, 진행은 넘어간 내용을 지금 얼마나 아는지 직접 물어 매겼어요. 종합은 셋을 대화에서 차지한 비율로 가중 평균했어요.</p></div>')
    rows = []
    for c in CRITERIA:
        v = d["criteria"][c]
        rows.append('<div class="lbl" style="margin-top:8px"><b>%s</b></div>%s%s' % (
            e(c), bar("기록", v["log"]), bar("직접 확인", v["test"])))
    b.append('<h2>네 가지 기준</h2><div class="card">%s<p class="meta" style="margin:8px 0 0">기록은 평소 요청을 채점한 것, '
             '직접 확인은 넘어간 내용을 묻는 질문과 읽기 과제예요. 둘이 크게 다르면 평소 글은 괜찮아 보여도 실제로는 놓치고 있다는 뜻이에요.</p></div>' % "".join(rows))
    if w:
        ex = "".join('<blockquote>%s</blockquote><div class="meta">%s</div>' % (e(q), e(r)) for _, q, r in d["examples"])
        b.append('<h2>이번 주에 해 볼 것</h2><div class="card"><b>%s</b>%s</div>' % (e(PRACTICE[w]), ex))
    ag = d["agreement"]
    rel = []
    if ag:
        rel.append("다른 채점자가 요청 %d개를 따로 다시 매겼어요. 종류 일치 %d%%, 같은 기준 점수 차이 평균 %s점(0~3점 기준)%s." % (
            ag["turns"], round(100 * ag["type_agree"]), ag["score_diff"], " · 일치가 낮아 결과를 조심해서 보세요" if ag["warn"] else ""))
    else:
        rel.append("다른 채점자의 다시 채점이 없어요.")
    if d["dropped"]:
        rel.append("인용이 원문과 맞지 않은 기록 %d개는 뺐어요." % d["dropped"])
    rel += ["채점은 AI가 했어요. 점수는 이 사람의 이 기간 기록과 답만 본 것이고, 다른 사람과 비교한 점수가 아니에요.",
            "평가받은 본인에게만 드리는 결과예요. 대화 내용이 들어 있어요. 보여 줄지는 본인이 정해요."]
    b.append('<h2>읽는 법</h2><div class="card"><ul>%s</ul></div>' % "".join("<li>%s</li>" % e(x) for x in rel))
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>AI와 일하는 실력</title><style>%s</style></head><body><main>%s</main></body></html>' % (CSS, "".join(b)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sessions", required=True)
    ap.add_argument("--turns", required=True)
    ap.add_argument("--turns-b")
    ap.add_argument("--graded")
    ap.add_argument("--out", required=True)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    d = compute(read_jsonl(a.sessions), read_jsonl(a.turns),
                read_jsonl(a.turns_b) if a.turns_b else None, read_jsonl(a.graded) if a.graded else None)
    out = os.path.expanduser(a.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(d))
    if a.json:
        with open(os.path.expanduser(a.json), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    print("저장: %s | 종합 %s · %s" % (out, d["overall"], ", ".join(
        "%s %s" % (c, d["criteria"][c]["main"]["score"] if d["criteria"][c]["main"] else "-") for c in CRITERIA)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
