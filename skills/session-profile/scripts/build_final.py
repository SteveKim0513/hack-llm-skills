#!/usr/bin/env python3
"""최종 결과를 한 장짜리 HTML로 만든다. 외부 파일이나 네트워크 없이 열린다.

사용자에게 건네는 유일한 결과물이다. 순서: 한 줄 결론 → 생각과 실제가 다른 곳 → 이해 확인 퀴즈 → 행동 프로필 →
둘을 함께 본 것 → 신뢰도와 한계. 점수나 등급은 만들지 않는다.

  python3 build_final.py --input final.json --out final.html

final.json 형식은 references/sample-final.json을 본다. profile에는 build_report.py --json-out 출력을 그대로 넣는다.
"""
import argparse
import html
import json
import os
import sys

AXES = ["검증", "구조", "방향 주도", "메타인지"]
AXIS_NOTE = {
    "검증": "AI의 오류를 짚고, 근거를 묻고, 확인을 시킨 장면",
    "구조": "목표·조건·산출물·순서를 나눠 준 장면",
    "방향 주도": "방향을 정하거나 바꾸고, 제안을 고친 장면",
    "메타인지": "모르는 것을 알아차리고 탐색하거나, 자기 결정을 다시 본 장면",
}
STATUS_CLASS = {"이해": "ok", "부분 이해": "mid", "확신 오답": "bad", "틀림": "mid", "모름": "mute", "맡김": "mute"}
STATUS_ORDER = ["이해", "부분 이해", "확신 오답", "틀림", "모름", "맡김"]
SATURATED = 0.85

CSS = """
:root{--bg:#f7f6f3;--card:#fff;--ink:#1d2125;--mute:#69707a;--line:#e4e1da;--accent:#2f5d50;--accent-soft:#e7f0ec;
--ok:#2f7a4f;--mid:#9a5b00;--bad:#a4442f;--bad-soft:#f8ebe7;--bar:#cfe0d8}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#15171a;--card:#1e2225;--ink:#e8e6e1;--mute:#9aa1a9;
--line:#30363b;--accent:#7fc4ad;--accent-soft:#1f2e29;--ok:#7fd19b;--mid:#e0a458;--bad:#f09a86;--bad-soft:#33221e;--bar:#2c4a40}}
:root[data-theme="dark"]{--bg:#15171a;--card:#1e2225;--ink:#e8e6e1;--mute:#9aa1a9;--line:#30363b;--accent:#7fc4ad;
--accent-soft:#1f2e29;--ok:#7fd19b;--mid:#e0a458;--bad:#f09a86;--bad-soft:#33221e;--bar:#2c4a40}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:760px;margin:0 auto;padding:24px 16px 80px}
h1{font-size:22px;margin:0 0 4px;letter-spacing:-.01em}h2{font-size:18px;margin:40px 0 4px}h3{font-size:15px;margin:18px 0 6px}
.meta{color:var(--mute);font-size:13px}
.lead{font-size:19px;font-weight:650;line-height:1.5;margin:18px 0 6px}
.sub{color:var(--mute);font-size:14px;margin:0 0 12px}
nav{display:flex;gap:6px;flex-wrap:wrap;margin:14px 0 0}
nav a{font-size:13px;color:var(--accent);text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:3px 10px;background:var(--card)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0}
.mm{border-color:var(--bad);background:var(--bad-soft)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:8px 0}
@media (max-width:560px){.cols{grid-template-columns:1fr}}
.col{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
.lbl{font-size:12px;color:var(--mute);font-weight:600;margin-bottom:2px}
.tag{display:inline-block;border-radius:999px;padding:0 10px;font-weight:700;font-size:13px;border:1px solid currentColor;white-space:nowrap}
.ok{color:var(--ok)}.mid{color:var(--mid)}.bad{color:var(--bad)}.mute{color:var(--mute)}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 4px}
.chip{font-size:13px;border:1px solid var(--line);border-radius:999px;padding:2px 10px;background:var(--card)}
.q{font-weight:650;margin:2px 0 8px}
.row{display:flex;justify-content:space-between;gap:10px;align-items:baseline;flex-wrap:wrap}
ul{margin:4px 0 4px 18px;padding:0}li{margin:2px 0}
.tl{border-left:2px solid var(--line);margin:6px 0 6px 4px;padding-left:12px;font-size:14px}
.tl div{margin:3px 0}.tl b{font-variant-numeric:tabular-nums}
.src{font-size:12px;color:var(--mute);word-break:break-all}
.axis{display:grid;grid-template-columns:92px 1fr;gap:4px 12px;align-items:center;margin:12px 0}
.axis .name{font-weight:650}.axis .note{grid-column:2;font-size:13px;color:var(--mute)}
.track{background:var(--line);border-radius:6px;height:12px;overflow:hidden}.fill{background:var(--accent);height:100%}
.nums{grid-column:2;font-size:13px;font-variant-numeric:tabular-nums}
.warn{font-size:13px;color:var(--mid);grid-column:2}
details{margin:6px 0}summary{cursor:pointer;color:var(--accent);font-size:14px}
blockquote{margin:6px 0;padding:6px 10px;border-left:3px solid var(--bar);background:var(--accent-soft);border-radius:0 8px 8px 0;font-size:14px;white-space:pre-wrap}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid var(--line);padding:6px 4px;text-align:right}th:first-child,td:first-child{text-align:left}
th{color:var(--mute);font-weight:600}
.scroll{overflow-x:auto}
footer{margin-top:40px;color:var(--mute);font-size:13px}
"""


def e(x):
    return html.escape("" if x is None else str(x))


def pct(k, n):
    return round(100 * k / n) if n else 0


def section_mismatch(items):
    if not items:
        return ('<h2 id="mm">생각과 실제가 다른 곳</h2><p class="sub">이번에는 찾지 못했어요. 퀴즈에서 답한 내용이 지금 시스템과 맞았어요.</p>')
    out = ['<h2 id="mm">생각과 실제가 다른 곳 <span class="tag bad">%d</span></h2>' % len(items),
           '<p class="sub">알고 있는 것과 지금 시스템의 동작이 다른 곳이에요. 코드를 고칠지, 알고 있던 것을 고칠지는 직접 정하세요.</p>']
    for m in items:
        opts = "".join("<li>%s</li>" % e(o) for o in m.get("options", []))
        out.append(
            '<div class="card mm"><div class="row"><b>%s</b><span class="meta">%s</span></div>'
            '<div class="cols"><div class="col"><div class="lbl">알고 있던 것</div>%s</div>'
            '<div class="col"><div class="lbl">지금 실제 동작</div>%s</div></div>'
            '%s<div class="src">근거: %s</div>%s</div>' % (
                e(m.get("topic")), e(m.get("project")), e(m.get("you_thought")), e(m.get("actually")),
                ('<div class="meta">%s</div>' % e(m["note"])) if m.get("note") else "",
                e(" · ".join(m.get("sources", []))),
                ('<h3>할 수 있는 것</h3><ul>%s</ul>' % opts) if opts else ""))
    return "".join(out)


def section_quiz(quiz):
    items = quiz.get("items", [])
    counts = {}
    for it in items:
        counts[it.get("status")] = counts.get(it.get("status"), 0) + 1
    chips = "".join('<span class="chip"><span class="%s">%s</span> %d</span>' % (STATUS_CLASS.get(s, "mute"), e(s), counts[s])
                    for s in STATUS_ORDER if counts.get(s))
    out = ['<h2 id="quiz">이해 확인 퀴즈</h2>',
           '<p class="sub">AI의 제안을 짧게 승인하고 넘어간 지점에서, 그 결정으로 생긴 지금의 환경을 물었어요. 정답은 이후 세션과 저장소로 확인한 지금 기준이에요. %d문항으로는 수준을 매기지 않아요.</p>' % len(items),
           '<div class="chips">%s</div>' % chips]
    for n, it in enumerate(items, 1):
        st = it.get("status", "")
        tl = "".join('<div><b>%s</b> %s</div>' % (e(c.get("date")), e(c.get("what"))) for c in it.get("later_changes", []))
        answer = it.get("your_answer") or ""
        ans_html = ('%s <span class="meta">(%s)</span>' % (e(answer), e(it.get("confidence")))) if answer else '<span class="meta">%s</span>' % e(st)
        out.append(
            '<div class="card"><div class="row"><span class="meta">%d · %s · %s</span><span class="tag %s">%s</span></div>'
            '<div class="q">%s</div>'
            '<div class="cols"><div class="col"><div class="lbl">내 답</div>%s</div>'
            '<div class="col"><div class="lbl">지금 기준</div>%s</div></div>'
            '%s%s<div class="src">근거: %s</div></div>' % (
                n, e(it.get("project")), e(it.get("date")), STATUS_CLASS.get(st, "mute"), e(st), e(it.get("question")),
                ans_html, e(it.get("now_answer")),
                ('<div class="meta">%s</div>' % e(it["why"])) if it.get("why") else "",
                ('<div class="lbl" style="margin-top:8px">그 뒤에 바뀐 것</div><div class="tl">%s</div>' % tl) if tl else "",
                e(" · ".join(it.get("sources", [])))))
    v = quiz.get("validation")
    if v:
        out.append('<p class="meta">문항 검증: 후보 지점 %s개 → 문항 %s개 → 대화를 읽은 답만 맞고 대화를 안 읽은 답은 틀린 문항 %s개를 냈어요.</p>' % (
            e(v.get("points")), e(v.get("written")), e(v.get("passed"))))
    return "".join(out)


def section_profile(p, examples):
    n = p.get("sessions", 0)
    r = p.get("rates") or {}
    out = ['<h2 id="profile">행동 프로필</h2>',
           '<p class="sub">세션 %d개, 사용자 발화 %d개에서 실제로 보인 행동만 셌어요. 안 보였다고 하지 않았다는 뜻은 아니에요. 채팅 밖에서 한 일은 기록에 없어요.</p>' % (
               n, p.get("user_turns", 0))]
    for a in AXES:
        k = p.get("presence", {}).get(a, 0)
        share = pct(k, n)
        rate = (r.get("all") or {}).get(a)
        resp = (r.get("response") or {}).get(a) if r.get("response") else None
        fs = (r.get("front_share") or {}).get(a) if r.get("front_share") else None
        nums = "세션 %d/%d (%d%%)" % (k, n, share)
        if rate is not None:
            nums += " · 10발화당 %.1f건" % rate
        if resp is not None:
            nums += " · 응답 중 %.1f건" % resp
        warn = []
        if n and k / n >= SATURATED:
            warn.append("거의 모든 세션에 있어서 세션 비율로는 차이가 잘 안 보여요. 10발화당 수치를 보세요.")
        if fs is not None and fs >= 0.4:
            warn.append("%d%%가 요청을 처음 꺼낼 때 나와요. 긴 대화일수록 발화당 수치가 낮게 나와요." % round(100 * fs))
        ex = examples.get(a, [])
        ex_html = ""
        if ex:
            ex_html = '<details><summary>대표 장면 %d개</summary>%s</details>' % (len(ex), "".join(
                '<blockquote>%s</blockquote><div class="src">%s%s</div>' % (
                    e(x.get("quote")), e(x.get("project")), (" · 직전 AI: " + e(x.get("ai_context"))) if x.get("ai_context") else "")
                for x in ex))
        out.append('<div class="axis"><div class="name">%s</div><div class="track" role="img" aria-label="%s 세션 비율 %d%%">'
                   '<div class="fill" style="width:%d%%"></div></div><div class="note">%s</div><div class="nums">%s</div>%s'
                   '<div style="grid-column:2">%s</div></div>' % (
                       e(a), e(a), share, share, e(AXIS_NOTE[a]), e(nums),
                       "".join('<div class="warn">%s</div>' % e(w) for w in warn), ex_html))
    if r.get("by_length"):
        rows = "".join("<tr><td>%s</td><td>%d</td>%s</tr>" % (e(lbl), ns, "".join("<td>%.1f</td>" % rr[a] for a in AXES))
                       for lbl, rr, ns, _turns in r["by_length"])
        out.append('<h3>대화 길이별 10발화당 장면 수</h3><div class="scroll"><table><tr><th>사용자 발화</th><th>세션</th>%s</tr>%s</table></div>' % (
            "".join("<th>%s</th>" % e(a) for a in AXES), rows))
    if p.get("by_project"):
        rows = "".join("<tr><td>%s%s</td><td>%d</td>%s</tr>" % (
            e(name), ' <span class="meta">(참고용)</span>' if ns < 3 else "", ns,
            "".join("<td>%d%%</td>" % pct(pres[a], ns) for a in AXES)) for name, pres, ns in p["by_project"])
        out.append('<h3>프로젝트별 세션 비율</h3><div class="scroll"><table><tr><th>프로젝트</th><th>세션</th>%s</tr>%s</table></div>' % (
            "".join("<th>%s</th>" % e(a) for a in AXES), rows))
    return "".join(out)


def section_links(links):
    if not links:
        return ""
    return '<h2 id="links">둘을 함께 보면</h2><div class="card"><ul>%s</ul></div>' % "".join("<li>%s</li>" % e(x) for x in links)


def section_reliability(p, rel, limits):
    items = []
    ag = (p or {}).get("agreement")
    if ag:
        parts = []
        for a in AXES:
            r = ag["by_axis"][a]
            parts.append("%s %s" % (a, "카파 계산 불가" if r["kappa"] is None else "카파 %.2f" % r["kappa"]))
        items.append("행동 분류는 서로 독립된 AI 분류자 둘이 했어요. 겹쳐 본 세션 %d개에서 일치도: %s." % (ag["sessions"], ", ".join(parts)))
    else:
        items.append("행동 분류는 AI 분류자 하나만 했어요. 두 번째 분류자와의 일치도가 없어요.")
    if p:
        items.append("장면 상한에 걸려 뒤쪽이 덜 반영된 세션 %d개는 10발화당 계산에서 뺐어요." % p.get("capped", 0))
    for x in (rel or []):
        items.append(x)
    for x in (limits or []):
        items.append(x)
    return '<h2 id="rel">신뢰도와 한계</h2><div class="card"><ul>%s</ul></div>' % "".join("<li>%s</li>" % e(x) for x in items)


def render(d):
    m = d.get("meta", {})
    nav = ['<a href="#mm">생각과 실제</a>', '<a href="#quiz">퀴즈</a>', '<a href="#profile">행동 프로필</a>']
    if d.get("links"):
        nav.append('<a href="#links">함께 보기</a>')
    nav.append('<a href="#rel">신뢰도</a>')
    body = [
        "<header><h1>%s</h1><div class=\"meta\">%s</div>" % (e(m.get("title", "AI 활용 리포트")), e(" · ".join(
            x for x in [m.get("period_profile") and "프로필 " + m["period_profile"], m.get("period_quiz") and "퀴즈 " + m["period_quiz"],
                        m.get("tools"), m.get("generated_at") and "만든 날 " + m["generated_at"]] if x))),
        '<p class="lead">%s</p><nav>%s</nav></header>' % (e(d.get("headline", "")), "".join(nav)),
        section_mismatch(d.get("mismatches", [])),
        section_quiz(d.get("quiz", {})),
        section_profile(d.get("profile") or {}, d.get("examples") or {}),
        section_links(d.get("links", [])),
        section_reliability(d.get("profile"), d.get("reliability"), d.get("limits")),
        '<footer>점수나 등급이 아니에요. 같은 기준·같은 기간 길이의 이전 결과와만 비교하세요. 이 파일에는 대화 내용이 들어 있으니 공유하지 마세요.</footer>',
    ]
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>%s</title><style>%s</style></head><body><main>%s</main></body></html>' % (
                e(m.get("title", "AI 활용 리포트")), CSS, "".join(body)))


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
    print("저장: %s" % out, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
