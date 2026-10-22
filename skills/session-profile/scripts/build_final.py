#!/usr/bin/env python3
"""능력 측정 최종 결과를 한 장짜리 HTML로 만든다. 외부 파일이나 네트워크 없이 열린다.

순서: 한 줄 결론 → 먼저 보완할 것 → 능력 지도 → 능력별 근거와 연습법 → 생각과 실제가 다른 곳 → 신뢰도와 한계.
능력별 판정은 references/abilities.md의 종합 규칙대로 여기서 계산한다(한 사람 안의 상대 비교).

  python3 build_final.py --input final.json --out final.html

final.json 형식은 references/sample-final.json(지어낸 샘플)을 본다.
"""
import argparse
import html
import json
import os
import sys

ABILITIES = ["이해", "읽기", "목표 명확성", "원하는 것의 분명함", "표현 정확성"]
MIN_LOG = 5
MIN_TASK = 3
STATUS_CLASS = {"먼저 보완": "bad", "강점": "ok", "증거가 엇갈림": "mid", "보통": "mute", "증거 부족": "mute"}

CSS = """
:root{--bg:#f7f6f3;--card:#fff;--ink:#1d2125;--mute:#69707a;--line:#e4e1da;--accent:#2f5d50;--soft:#e7f0ec;
--ok:#2f7a4f;--mid:#9a5b00;--bad:#a4442f;--bad-soft:#f8ebe7;--bar:#cfe0d8}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#15171a;--card:#1e2225;--ink:#e8e6e1;--mute:#9aa1a9;
--line:#30363b;--accent:#7fc4ad;--soft:#1f2e29;--ok:#7fd19b;--mid:#e0a458;--bad:#f09a86;--bad-soft:#33221e;--bar:#2c4a40}}
:root[data-theme="dark"]{--bg:#15171a;--card:#1e2225;--ink:#e8e6e1;--mute:#9aa1a9;--line:#30363b;--accent:#7fc4ad;
--soft:#1f2e29;--ok:#7fd19b;--mid:#e0a458;--bad:#f09a86;--bad-soft:#33221e;--bar:#2c4a40}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:760px;margin:0 auto;padding:24px 16px 80px}
h1{font-size:22px;margin:0 0 4px;letter-spacing:-.01em}h2{font-size:18px;margin:40px 0 6px}h3{font-size:15px;margin:16px 0 6px}
.meta{color:var(--mute);font-size:13px}.sub{color:var(--mute);font-size:14px;margin:0 0 12px}
.lead{font-size:19px;font-weight:650;line-height:1.5;margin:18px 0 6px}
nav{display:flex;gap:6px;flex-wrap:wrap;margin:14px 0 0}
nav a{font-size:13px;color:var(--accent);text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:3px 10px;background:var(--card)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0}
.focus{border-color:var(--bad);background:var(--bad-soft)}
.tag{display:inline-block;border-radius:999px;padding:0 10px;font-weight:700;font-size:13px;border:1px solid currentColor;white-space:nowrap}
.ok{color:var(--ok)}.mid{color:var(--mid)}.bad{color:var(--bad)}.mute{color:var(--mute)}
.row{display:flex;justify-content:space-between;gap:10px;align-items:baseline;flex-wrap:wrap}
.map{display:grid;grid-template-columns:minmax(110px,1.1fr) 1fr 1fr;gap:6px 12px;align-items:center;font-size:14px}
.map .h{font-size:12px;color:var(--mute);font-weight:600}
@media (max-width:560px){.map{grid-template-columns:1fr 1fr}.map .name{grid-column:1/-1;margin-top:8px}.map .h.n{display:none}}
.meter{display:flex;align-items:center;gap:8px;font-variant-numeric:tabular-nums}
.track{flex:1;background:var(--line);border-radius:6px;height:10px;overflow:hidden;min-width:50px}.fill{background:var(--accent);height:100%}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:8px 0}
@media (max-width:560px){.cols{grid-template-columns:1fr}}
.col{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
.lbl{font-size:12px;color:var(--mute);font-weight:600;margin-bottom:2px}
blockquote{margin:6px 0;padding:6px 10px;border-left:3px solid var(--bar);background:var(--soft);border-radius:0 8px 8px 0;font-size:14px;white-space:pre-wrap}
blockquote.broken{border-left-color:var(--bad);background:var(--bad-soft)}
.src{font-size:12px;color:var(--mute);word-break:break-all}
ul{margin:4px 0 4px 18px;padding:0}li{margin:3px 0}
.practice li{font-weight:600}
details{border-top:1px solid var(--line);margin-top:10px;padding-top:6px}summary{cursor:pointer;color:var(--accent);font-size:14px}
.task{border:1px solid var(--line);border-radius:10px;padding:10px;margin:8px 0;font-size:14px}
footer{margin-top:40px;color:var(--mute);font-size:13px}
"""


def e(x):
    return html.escape("" if x is None else str(x))


def log_score(ab):
    lg = ab.get("log") or {}
    shown, broken = lg.get("shown", 0), lg.get("broken", 0)
    if shown + broken < MIN_LOG:
        return None
    return 1 - broken / (shown + broken)


def task_score(ab):
    t = ab.get("task") or {}
    if (t.get("total") or 0) < MIN_TASK:
        return None
    return t.get("got", 0) / t["total"]


def positions(scores):
    """점수가 있는 능력만으로 순위를 매기고 위쪽 둘과 아래쪽 둘을 표시한다."""
    have = [(n, s) for n, s in scores.items() if s is not None]
    if len(have) < 3:
        return {n: None for n in scores}
    ordered = sorted(have, key=lambda x: (-x[1], x[0]))
    top = {n for n, _ in ordered[:2]}
    bottom = {n for n, _ in ordered[-2:]}
    out = {}
    for n in scores:
        out[n] = None if scores[n] is None else ("top" if n in top else "bottom" if n in bottom else "mid")
    return out


def judge(abilities):
    names = [a["name"] for a in abilities]
    lp = positions({a["name"]: log_score(a) for a in abilities})
    tp = positions({a["name"]: task_score(a) for a in abilities})
    res = {}
    for n in names:
        a_, b_ = lp.get(n), tp.get(n)
        if a_ and b_:
            if a_ == b_ == "bottom":
                s = "먼저 보완"
            elif a_ == b_ == "top":
                s = "강점"
            elif {a_, b_} == {"top", "bottom"}:
                s = "증거가 엇갈림"
            else:
                s = "보통"
            res[n] = (s, False)
        elif a_ or b_:
            p = a_ or b_
            res[n] = ({"bottom": "먼저 보완", "top": "강점"}.get(p, "보통"), True)
        else:
            res[n] = ("증거 부족", False)
    return res


def meter(score, label):
    if score is None:
        return '<div class="meter mute">%s</div>' % e(label)
    w = round(100 * score)
    return '<div class="meter"><div class="track" aria-hidden="true"><div class="fill" style="width:%d%%"></div></div><span>%s</span></div>' % (w, e(label))


def tag(status, single):
    return '<span class="tag %s">%s%s</span>' % (STATUS_CLASS[status], e(status), " · 한 가지 증거" if single else "")


def section_focus(abilities, verdict):
    focus = [a for a in abilities if verdict[a["name"]][0] == "먼저 보완"]
    out = ['<h2 id="focus">먼저 보완할 것</h2>']
    if not focus:
        out.append('<p class="sub">로그와 과제가 함께 가리키는 약점은 없었어요. 아래 능력 지도에서 "보통"과 "증거가 엇갈림"을 보세요.</p>')
        return "".join(out)
    out.append('<p class="sub">다섯 능력 중 로그와 과제가 함께 상대적으로 약하다고 가리킨 것이에요. 다른 사람과 비교한 점수가 아니에요.</p>')
    for a in focus:
        p = (a.get("practice") or [""])[0]
        out.append('<div class="card focus"><div class="row"><b>%s</b>%s</div><div>%s</div>%s</div>' % (
            e(a["name"]), tag(*verdict[a["name"]]), e(a.get("why", "")),
            ('<div class="lbl" style="margin-top:8px">이번 주에 해 볼 것</div><div><b>%s</b></div>' % e(p)) if p else ""))
    return "".join(out)


def section_map(abilities, verdict):
    rows = ['<div class="h n">능력</div><div class="h">과제 결과</div><div class="h">실제 작업 (어긋나지 않은 비율)</div>']
    for a in abilities:
        t, lg = a.get("task") or {}, a.get("log") or {}
        ts, ls = task_score(a), log_score(a)
        tl = ("%s/%s점" % (fmt(t.get("got", 0)), fmt(t.get("total", 0)))) if ts is not None else "과제 부족"
        ll = ("보임 %d · 끊김 %d" % (lg.get("shown", 0), lg.get("broken", 0))) if ls is not None else (
            "장면 %d개, 부족" % (lg.get("shown", 0) + lg.get("broken", 0)))
        rows.append('<div class="name"><b>%s</b><br>%s</div>%s%s' % (
            e(a["name"]), tag(*verdict[a["name"]]), meter(ts, tl), meter(ls, ll)))
    return ('<h2 id="map">능력 지도</h2><p class="sub">과제는 지금 풀어 본 결과, 실제 작업은 기록에서 그 능력이 드러난 장면(보임)과 그 능력이 부족해서 일이 어긋난 장면(끊김)이에요.</p>'
            '<div class="card"><div class="map">%s</div></div>' % "".join(rows))


def fmt(x):
    return ("%g" % x) if isinstance(x, (int, float)) else e(x)


def section_details(abilities, verdict):
    out = ['<h2 id="detail">능력별 근거와 연습</h2>']
    for a in abilities:
        lg, t = a.get("log") or {}, a.get("task") or {}
        shown = "".join('<blockquote>%s</blockquote><div class="src">%s%s</div>' % (
            e(x.get("quote")), e(x.get("project")), (" · " + e(x.get("context"))) if x.get("context") else "")
            for x in lg.get("examples_shown", []))
        broken = "".join('<blockquote class="broken">%s</blockquote><div class="src">%s%s</div>' % (
            e(x.get("quote")), e(x.get("project")), (" · " + e(x.get("what_happened"))) if x.get("what_happened") else "")
            for x in lg.get("examples_broken", []))
        tasks = "".join('<div class="task"><div class="row"><b>%s</b><span class="meta">%s</span></div>%s'
                        '<div class="lbl" style="margin-top:6px">내 답</div><div>%s</div>%s</div>' % (
                            e(x.get("title")), e(x.get("result")),
                            ('<div class="meta">%s</div>' % e(x["prompt"])) if x.get("prompt") else "",
                            e(x.get("your_answer") or "(답하지 않음)"),
                            ('<div class="meta" style="margin-top:4px">%s</div>' % e(x["note"])) if x.get("note") else "")
                        for x in t.get("items", []))
        practice = "".join("<li>%s</li>" % e(p) for p in a.get("practice", []))
        out.append(
            '<div class="card" id="ab-%d"><div class="row"><h3 style="margin:0">%s</h3>%s</div>'
            '<div class="meta">%s</div><p>%s</p>'
            '%s%s'
            '<details%s><summary>근거 보기 (장면 %d개, 과제 %d개)</summary>%s%s%s</details></div>' % (
                ABILITIES.index(a["name"]) if a["name"] in ABILITIES else 9, e(a["name"]), tag(*verdict[a["name"]]),
                e(a.get("definition")), e(a.get("why", "")),
                ('<div class="lbl">연습할 것</div><ul class="practice">%s</ul>' % practice) if practice else "",
                "",
                " open" if verdict[a["name"]][0] == "먼저 보완" else "",
                len(lg.get("examples_shown", [])) + len(lg.get("examples_broken", [])), len(t.get("items", [])),
                ('<h3>잘 드러난 장면</h3>' + shown) if shown else "",
                ('<h3>어긋난 장면</h3>' + broken) if broken else "",
                ('<h3>과제</h3>' + tasks) if tasks else ""))
    return "".join(out)


def section_mismatch(items):
    if not items:
        return ""
    out = ['<h2 id="mm">생각과 실제가 다른 곳</h2><p class="sub">이해 과제에서 확인됐어요. 코드를 고칠지, 알고 있던 것을 고칠지는 직접 정하세요.</p>']
    for m in items:
        opts = "".join("<li>%s</li>" % e(o) for o in m.get("options", []))
        out.append('<div class="card"><div class="row"><b>%s</b><span class="meta">%s</span></div>'
                   '<div class="cols"><div class="col"><div class="lbl">알고 있던 것</div>%s</div>'
                   '<div class="col"><div class="lbl">지금 실제 동작</div>%s</div></div>'
                   '<div class="src">근거: %s</div>%s</div>' % (
                       e(m.get("topic")), e(m.get("project")), e(m.get("you_thought")), e(m.get("actually")),
                       e(" · ".join(m.get("sources", []))), ('<ul>%s</ul>' % opts) if opts else ""))
    return "".join(out)


def section_reliability(signals, rel, limits):
    items = []
    ag = (signals or {}).get("agreement")
    if ag:
        parts = []
        for ab in ABILITIES:
            r = ag["by_ability"].get(ab, {}).get("끊김", {})
            parts.append("%s %s" % (ab, "계산 불가" if r.get("kappa") is None else "%.2f" % r["kappa"]))
        items.append("로그 장면은 서로 독립된 AI 분류자 둘이 찾았어요. 겹쳐 본 세션 %d개에서 '끊김' 판정의 카파: %s." % (
            ag["sessions"], ", ".join(parts)))
    else:
        items.append("로그 장면은 AI 분류자 하나만 찾았어요. 두 번째 분류자와의 일치도가 없어요.")
    items += list(rel or []) + list(limits or [])
    return '<h2 id="rel">신뢰도와 한계</h2><div class="card"><ul>%s</ul></div>' % "".join("<li>%s</li>" % e(x) for x in items)


def order_abilities(abilities):
    known = {a["name"]: a for a in abilities}
    return [known[n] for n in ABILITIES if n in known] + [a for a in abilities if a["name"] not in ABILITIES]


def render(d):
    m = d.get("meta", {})
    abilities = order_abilities(d.get("abilities", []))
    verdict = judge(abilities)
    nav = ['<a href="#focus">먼저 보완할 것</a>', '<a href="#map">능력 지도</a>', '<a href="#detail">근거와 연습</a>']
    if d.get("mismatches"):
        nav.append('<a href="#mm">생각과 실제</a>')
    nav.append('<a href="#rel">신뢰도</a>')
    head = "<header><h1>%s</h1><div class=\"meta\">%s</div><p class=\"lead\">%s</p><nav>%s</nav></header>" % (
        e(m.get("title", "AI 활용 능력 리포트")),
        e(" · ".join(x for x in [m.get("period") and "기록 " + m["period"], m.get("tools"),
                                 m.get("generated_at") and "만든 날 " + m["generated_at"]] if x)),
        e(d.get("headline", "")), "".join(nav))
    body = [head, section_focus(abilities, verdict), section_map(abilities, verdict), section_details(abilities, verdict),
            section_mismatch(d.get("mismatches", [])), section_reliability(d.get("signals"), d.get("reliability"), d.get("limits")),
            '<footer>점수나 등급이 아니라 한 사람 안에서 다섯 능력을 견준 결과예요. 이 파일에는 대화 내용이 들어 있으니 공유하지 마세요.</footer>']
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>%s</title><style>%s</style></head><body><main>%s</main></body></html>' % (
                e(m.get("title", "AI 활용 능력 리포트")), CSS, "".join(body)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    with open(os.path.expanduser(args.input), encoding="utf-8") as f:
        data = json.load(f)
    out = os.path.expanduser(args.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(data))
    v = judge(order_abilities(data.get("abilities", [])))
    print("저장: %s | %s" % (out, ", ".join("%s=%s" % (k, s) for k, (s, _) in v.items())), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
