#!/usr/bin/env python3
"""재검토를 통과한 어긋남과 에피소드 표로 "가장 비싼 습관"을 계산해 한 장짜리 HTML로 만든다.

  python3 report.py --breaks kept.jsonl --episodes episodes.jsonl --out report.html

breaks:   재검토에서 원인이 사용자로 확인된 어긋남. 한 줄에 하나:
          {session_idx, user_turn, habit, quote, what_happened, resolved_turn}
episodes: episodes.py 출력(같은 sessions.jsonl로 만든 것).

비용: 어긋난 요청부터 제자리로 돌아온 요청 바로 앞까지 버려진 AI 작업 시간과, 사람이 그 결과를 읽고 바로잡은 시간.
제자리로 돌아온 요청(resolved_turn)을 모르면 어긋난 요청 하나만 센다. 요청 100개당으로 바꾸고,
세션을 다시 뽑아 계산한 80% 구간을 붙인다. 어긋남이 2개 미만인 습관은 가장 비싼 습관으로 고르지 않는다.
"""
import argparse
import html
import json
import os
import random
import sys

HABITS = {
    "이해": "큰 결정을 승인하기 전에 \"그럼 결과적으로 ~가 되는 거지?\"를 한 문장으로 되말하기",
    "읽기": "긴 답변을 받으면 마지막 질문과 경고부터 찾아 읽기",
    "목표 명확성": "요청 첫 줄에 \"이걸로 ~가 되면 성공\"을 쓰기",
    "원하는 것의 분명함": "맡기기 전에 좋은 결과의 조건 두 가지를 적기",
    "표현 정확성": "보내기 전에 \"처음 보는 사람이 이걸 읽으면 무엇을 만들까\"를 떠올리고, 빠져야 할 것도 적기",
    "검증": "\"됐어요\"를 받으면 무엇으로 확인했는지(실행 결과, 화면) 하나를 붙여 달라고 하기",
}
MAX_SPAN = 6
BOOT = 2000


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def cost_of(b, eps):
    """어긋남 하나의 (버려진 에피소드 수, 분)."""
    s, t, r = b["session_idx"], b["user_turn"], b.get("resolved_turn")
    end = min(r, t + MAX_SPAN) if isinstance(r, int) and r > t else t + 1
    turns = [x for x in range(t, end) if (s, x) in eps]
    secs = sum(eps[(s, x)].get("work_s") or 0 for x in turns)
    secs += sum(eps[(s, x)].get("wait_before_s") or 0 for x in range(t + 1, end + 1) if (s, x) in eps)
    return len(turns), secs / 60


def totals(breaks, sessions, requests):
    out = {h: [0, 0.0, 0] for h in HABITS}
    by_s = {}
    for b in breaks:
        by_s.setdefault(b["session_idx"], []).append(b)
    for s in sessions:
        for b in by_s.get(s, []):
            o = out[b["habit"]]
            o[0] += b["_cost"][0]
            o[1] += b["_cost"][1]
            o[2] += 1
    k = 100 / requests if requests else 0
    return {h: {"rework_per100": v[0] * k, "minutes_per100": v[1] * k, "breaks": v[2]} for h, v in out.items()}


def compute(breaks, episode_rows, seed=0, boot=BOOT):
    eps, req = {}, {}
    for r in episode_rows:
        if r.get("missing"):
            continue
        req[r["session_idx"]] = len(r["episodes"])
        for ep in r["episodes"]:
            eps[(r["session_idx"], ep["user_turn"])] = ep
    breaks = [dict(b, _cost=cost_of(b, eps)) for b in breaks if b.get("habit") in HABITS and b["session_idx"] in req]
    sessions = sorted(req)
    base = totals(breaks, sessions, sum(req.values()))
    rng = random.Random(seed)
    draws = {h: [] for h in HABITS}
    for _ in range(boot if sessions else 0):
        pick = [rng.choice(sessions) for _ in sessions]
        t = totals(breaks, pick, sum(req[s] for s in pick))
        for h in HABITS:
            draws[h].append(t[h]["minutes_per100"])
    for h, v in base.items():
        d = sorted(draws[h])
        v["low"] = d[int(0.1 * (len(d) - 1))] if d else None
        v["high"] = d[int(0.9 * (len(d) - 1))] if d else None
    cand = [h for h, v in base.items() if v["breaks"] >= 2 and v["minutes_per100"] > 0]
    top = max(cand, key=lambda h: base[h]["minutes_per100"]) if cand else None
    starts = sorted(ep.get("start") for ep in eps.values() if ep.get("start"))
    return {"sessions": len(sessions), "requests": sum(req.values()), "habits": base, "costliest": top,
            "period": (starts[0][:10], starts[-1][:10]) if starts else None,
            "examples": {h: [b for b in breaks if b["habit"] == h] for h in HABITS}}


CSS = """
:root{--bg:#f7f6f3;--card:#fff;--ink:#1d2125;--mute:#69707a;--line:#e4e1da;--accent:#2f5d50;--bad:#a4442f;--bad-soft:#f8ebe7;--soft:#eef3f0}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#15171a;--card:#1e2225;--ink:#e8e6e1;--mute:#9aa1a9;--line:#30363b;--accent:#7fc4ad;--bad:#f09a86;--bad-soft:#33221e;--soft:#1f2e29}}
:root[data-theme="dark"]{--bg:#15171a;--card:#1e2225;--ink:#e8e6e1;--mute:#9aa1a9;--line:#30363b;--accent:#7fc4ad;--bad:#f09a86;--bad-soft:#33221e;--soft:#1f2e29}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:720px;margin:0 auto;padding:24px 16px 64px}h1{font-size:21px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 8px}
.meta{color:var(--mute);font-size:13px}.lead{font-size:19px;font-weight:650;line-height:1.5;margin:16px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0}
.top{border-color:var(--bad);background:var(--bad-soft)}.big{font-size:17px;font-weight:700;margin:6px 0}
.row{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;border-top:1px solid var(--line);padding:6px 0}
blockquote{margin:8px 0 2px;padding:6px 10px;border-left:3px solid var(--bad);background:var(--soft);border-radius:0 8px 8px 0;white-space:pre-wrap;font-size:14px}
ul{margin:4px 0 0 18px;padding:0}
"""


def e(x):
    return html.escape("" if x is None else str(x))


def n(x):
    return "-" if x is None else ("%.1f" % x).rstrip("0").rstrip(".")


def render(d):
    h = d["costliest"]
    period = "기록 %s~%s · " % d["period"] if d["period"] else ""
    body = ['<h1>AI와 일하는 습관</h1><div class="meta">%s세션 %d개 · 요청 %d개</div>' % (e(period), d["sessions"], d["requests"])]
    if h:
        v = d["habits"][h]
        body.append('<p class="lead">가장 비싼 습관은 <b>%s</b>예요. 요청 100개당 약 %s분을 다시 작업에 썼어요.</p>' % (e(h), n(v["minutes_per100"])))
        scenes = "".join('<blockquote>%s</blockquote><div class="meta">%s</div>' % (e(b.get("quote")), e(b.get("what_happened")))
                         for b in d["examples"][h][:3])
        body.append('<div class="card top"><div class="big">요청 100개당 다시 작업 %s번, 약 %s분</div>'
                    '<div class="meta">80%% 구간 %s~%s분 · 어긋남 %d개</div>%s'
                    '<h2 style="margin-top:16px">이번 주에 해 볼 것</h2><b>%s</b></div>' % (
                        n(v["rework_per100"]), n(v["minutes_per100"]), n(v["low"]), n(v["high"]), v["breaks"], scenes, e(HABITS[h])))
    else:
        body.append('<p class="lead">원인이 내 쪽으로 확인된 어긋남이 2개 이상인 습관이 아직 없어요.</p>'
                    '<p>기록이 더 쌓인 뒤 다시 보면 가려져요.</p>')
    rows = "".join('<div class="row"><span>%s · 어긋남 %d</span><span class="meta">요청 100개당 %s분 (%s~%s)</span></div>' % (
        e(k), v["breaks"], n(v["minutes_per100"]), n(v["low"]), n(v["high"]))
        for k, v in sorted(d["habits"].items(), key=lambda kv: -kv[1]["minutes_per100"]))
    body.append('<h2>습관별 다시 작업</h2><div class="card">%s</div>' % rows)
    body.append('<h2>읽는 법</h2><div class="card"><ul>'
                '<li>어긋남은 AI가 찾고, 다른 AI가 원인이 정말 내 쪽인지 다시 따진 것만 셌어요. AI가 틀린 장면은 세지 않았어요.</li>'
                '<li>다시 작업은 어긋난 요청부터 제자리로 돌아오기까지 버려진 AI 작업과 그걸 읽고 바로잡은 시간이에요. 그 안에 쓸모 있던 작업이 섞였을 수 있어요.</li>'
                '<li>다른 사람과 비교한 점수가 아니에요. 이 기간, 이 사람의 기록만 봤어요.</li>'
                '<li>평가받은 본인에게만 드리는 결과예요. 대화 내용이 들어 있어요. 보여 줄지는 본인이 정해요.</li></ul></div>')
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>AI와 일하는 습관</title><style>%s</style></head><body><main>%s</main></body></html>' % (CSS, "".join(body)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--breaks", required=True)
    ap.add_argument("--episodes", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    d = compute(read_jsonl(os.path.expanduser(a.breaks)), read_jsonl(os.path.expanduser(a.episodes)))
    out = os.path.expanduser(a.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(d))
    top = d["costliest"]
    print("저장: %s | 가장 비싼 습관: %s" % (out, "%s, 요청 100개당 %s분" % (top, n(d["habits"][top]["minutes_per100"])) if top else "아직 없음"),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
