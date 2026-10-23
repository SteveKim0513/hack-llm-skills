#!/usr/bin/env python3
"""능력 측정 최종 결과를 한 장짜리 HTML로 만든다. 외부 파일이나 네트워크 없이 열린다.

순서: 한 줄 결론 → 가장 비싼 습관(estimate.py 결과가 있을 때) → 먼저 보완할 것 → 능력 지도 → 능력별 근거와 연습법
→ 생각과 실제가 다른 곳 → 신뢰도와 한계.
능력별 판정은 references/abilities.md의 종합 규칙대로 여기서 계산한다(한 사람 안의 상대 비교).

  python3 build_final.py --input final.json --out final.html

final.json 형식은 references/sample-final.json(지어낸 샘플)을 본다.
"""
import argparse
import html
import json
import math
import os
import sys

ABILITIES = ["이해", "읽기", "목표 명확성", "원하는 것의 분명함", "표현 정확성", "검증"]
MIN_LOG = 5
MIN_TASK = 3
# 문턱은 한 사람의 여섯 능력을 한꺼번에 볼 때 기준이다. 능력 하나 기준 1.64를 쓰면 차이가 없는 사람도
# 16~21%가 거짓 "먼저 보완"을 하나 이상 받았다. 2.33이면 4.7% 이하(simulate.py, validation-notes.md 14번).
GATE = 2.33          # 합친 z가 이 값을 넘어야 먼저 보완이나 강점
GATE_MIX = 2.81      # 두 증거의 차이가 이 값을 넘어야 "엇갈림"
PRIOR_WEIGHT = 2.0   # 그 사람의 통합 비율 쪽으로 당기는 가상 관측 수. 조정할 값이며 근거 있는 값이 아니다
# "시험해 볼 가설"로 고른 능력이 진짜 약한 능력이었던 비율. 능력당 평균 증거 수(이상)별, simulate.py 기준 대략값.
HYPO_HIT = [(25, 85), (10, 65), (0, 50)]
STATUS_CLASS = {"먼저 보완": "bad", "강점": "ok", "증거가 엇갈림": "mid", "아직 가릴 수 없음": "mute", "증거 부족": "mute"}

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
    r = rates_of(ab)["log"]
    return r[0] / r[1] if r else None


def task_score(ab):
    t = ab.get("task") or {}
    if (t.get("total") or 0) < MIN_TASK:
        return None
    return t.get("got", 0) / t["total"]


def rates_of(ab):
    """증거마다 (좋은 쪽 수, 전체 수). 과제는 얻은 점수.
    로그는 기회 기록이 있으면 (기회 − 끊김, 기회), 옛 형식이면 (보임, 보임 + 끊김)."""
    lg, t = ab.get("log") or {}, ab.get("task") or {}
    shown, broken = lg.get("shown", 0), lg.get("broken", 0)
    opp = lg.get("opportunities")
    if opp:
        log = (opp - broken, opp) if opp >= MIN_LOG else None
    else:
        log = (shown, shown + broken) if shown + broken >= MIN_LOG else None
    task = (t.get("got", 0), t.get("total", 0)) if (t.get("total") or 0) >= MIN_TASK else None
    return {"log": log, "task": task}


def source_z(k, n, others_k, others_n, pooled):
    """한 증거에서 이 능력이 그 사람의 다른 능력 평균보다 얼마나 벗어났나(z).
    비율은 Jeffreys 사전분포에 그 사람의 통합 비율 쪽으로 가상 관측 PRIOR_WEIGHT개만큼 당겨서 구한다.
    증거가 적을수록 평균 쪽으로 당겨져서 작은 표본의 우연한 차이가 약점으로 보이지 않는다."""
    a = k + 0.5 + PRIOR_WEIGHT * pooled
    b = (n - k) + 0.5 + PRIOR_WEIGHT * (1 - pooled)
    ao, bo = others_k + 0.5, (others_n - others_k) + 0.5
    # 비율을 아크사인 제곱근으로 바꿔 비교한다. 0.9 같은 끝쪽 비율은 분포가 한쪽으로 기울어서 그냥 빼면
    # 거짓 강점이나 거짓 약점 한쪽이 많아진다. 이 변환은 흔들림이 비율과 상관없이 1/(4n)이 된다(simulate.py로 확인).
    t = math.asin(math.sqrt(a / (a + b)))
    to = math.asin(math.sqrt(ao / (ao + bo)))
    sd = math.sqrt(1 / (4 * (a + b)) + 1 / (4 * (ao + bo)))
    return (t - to) / sd if sd > 0 else 0.0


def judge(abilities):
    """references/abilities.md의 종합 규칙. 순위를 쓰지 않는다. 차이가 불확실성을 넘을 때만 판정한다."""
    rs = {a["name"]: rates_of(a) for a in abilities}
    zs = {a["name"]: {} for a in abilities}
    for src in ("log", "task"):
        have = {n: r[src] for n, r in rs.items() if r[src]}
        if len(have) < 3:
            continue  # 비교할 다른 능력이 너무 적으면 그 증거로는 판정하지 않는다
        tk, tn = sum(k for k, _ in have.values()), sum(n for _, n in have.values())
        pooled = tk / tn if tn else 0.5
        for n_, (k, n) in have.items():
            zs[n_][src] = source_z(k, n, tk - k, tn - n, pooled)
    out = {}
    for a in abilities:
        name = a["name"]
        z = zs[name]
        n_ev = sum(r[1] for r in rs[name].values() if r)
        info = {"z_log": z.get("log"), "z_task": z.get("task"), "evidence": n_ev,
                "precision": "높음" if n_ev >= 25 else "보통" if n_ev >= 10 else "낮음",
                "single": len(z) == 1, "more": None}
        if not z:
            info.update(status="증거 부족", z=None)
        else:
            comb = sum(z.values()) / math.sqrt(len(z))
            info["z"] = comb
            if len(z) == 2 and abs(z["log"] - z["task"]) / math.sqrt(2) >= GATE_MIX:
                info["status"] = "증거가 엇갈림"
            elif comb <= -GATE:
                info["status"] = "먼저 보완"
            elif comb >= GATE:
                info["status"] = "강점"
            else:
                info["status"] = "아직 가릴 수 없음"
                if abs(comb) >= 0.3:
                    # 같은 크기의 차이가 이어진다면 증거가 몇 개 더 있어야 문턱을 넘는지 어림한다.
                    # 지금 증거의 두 배를 넘게 필요하면 차이가 작다고만 말한다.
                    more = max(1, round(n_ev * ((GATE / abs(comb)) ** 2 - 1)))
                    info["more"] = more if more <= 2 * n_ev else None
        out[name] = info
    return out


def meter(score, label):
    if score is None:
        return '<div class="meter mute">%s</div>' % e(label)
    w = round(100 * score)
    return '<div class="meter"><div class="track" aria-hidden="true"><div class="fill" style="width:%d%%"></div></div><span>%s</span></div>' % (w, e(label))


def tag(v):
    return '<span class="tag %s">%s%s</span>' % (STATUS_CLASS[v["status"]], e(v["status"]), " · 한 가지 증거" if v.get("single") else "")


def precision_note(v):
    s = "확실도 %s · 증거 %d개" % (v["precision"], v["evidence"])
    if v.get("more"):
        s += " · 같은 차이가 이어진다면 약 %d개 더 있으면 가려져요" % v["more"]
    elif v["status"] == "아직 가릴 수 없음":
        s += " · 다른 능력과 차이가 거의 없어요"
    return s


def section_focus(abilities, verdict):
    focus = sorted([a for a in abilities if verdict[a["name"]]["status"] == "먼저 보완"], key=lambda a: verdict[a["name"]]["z"])
    out = ['<h2 id="focus">먼저 보완할 것</h2>']
    if focus:
        out.append('<p class="sub">로그와 과제를 합쳐 봤을 때 이 사람의 다른 능력보다 분명히 낮은 것이에요. 다른 사람과 비교한 점수가 아니에요.</p>')
        picks, hypo = focus, False
    else:
        cand = [a for a in abilities if verdict[a["name"]].get("z") is not None]
        if not cand:
            out.append('<p class="sub">아직 판정할 만큼 증거가 모이지 않았어요.</p>')
            return "".join(out)
        low = min(cand, key=lambda a: verdict[a["name"]]["z"])
        out.append('<p class="sub"><b>분명한 약점은 아직 없어요.</b> 능력 사이의 차이가 측정의 흔들림보다 작았어요. 대신 가장 낮게 나온 능력 하나를 '
                   '"시험해 볼 가설"로 드려요. 진단된 약점이 아니에요.</p>')
        picks, hypo = [low], True
        per = sum(verdict[a["name"]]["evidence"] for a in abilities) / max(1, len(abilities))
        hit = next(h for n, h in HYPO_HIT if per >= n)
        out.append('<p class="sub">증거가 이 정도일 때 이렇게 고른 능력이 진짜 가장 약한 능력이었던 비율은 지어낸 데이터에서 약 %d%%였어요. '
                   '아무 능력이나 고르면 %d%%예요.</p>' % (hit, round(100 / max(1, len(abilities)))))
    for a in picks:
        v = verdict[a["name"]]
        p = (a.get("practice") or [""])[0]
        out.append('<div class="card%s"><div class="row"><b>%s</b>%s</div><div>%s</div>%s<div class="meta" style="margin-top:6px">%s</div></div>' % (
            "" if hypo else " focus", e(a["name"]), ('<span class="tag mute">시험해 볼 가설</span>' if hypo else tag(v)), e(a.get("why", "")),
            ('<div class="lbl" style="margin-top:8px">이번 주에 해 볼 것</div><div><b>%s</b></div>' % e(p)) if p else "",
            e(precision_note(v))))
    return "".join(out)


def score_text(sc):
    if not sc:
        return "점수: 기회 부족"
    t = "점수 %d (80%% 구간 %d~%d)" % (sc["point"], sc["low"], sc["high"])
    if sc.get("more_needed"):
        t += " · 기회 약 %d개 더 있으면 구간이 좁아져요" % sc["more_needed"]
    return t


def section_cost(est, abilities):
    if not est:
        return ""
    ab = {a["name"]: a for a in abilities}
    rows = est.get("abilities", {})
    out = ['<h2 id="cost">가장 비싼 습관</h2><p class="sub">원인이 내 쪽이었던 어긋남이 실제로 만든 다시 작업이에요. '
           '기록 %d개 세션, 요청 %d개 기준이고, 같은 단위(요청 100개당 분)라서 능력끼리 바로 견줄 수 있어요.</p>' % (
               est.get("sessions", 0), est.get("requests", 0))]
    c = est.get("costliest")
    if c:
        name = c["ability"]
        p = ((ab.get(name) or {}).get("practice") or [""])[0]
        out.append(
            '<div class="card focus"><div class="row"><b>%s</b><span class="meta">끊김 %d개</span></div>'
            '<p class="lead" style="font-size:17px;margin:8px 0">요청 100개당 다시 작업 %s번, 약 %s분</p>'
            '<div class="meta">80%% 구간 %s~%s분 · 세션을 다시 뽑아 계산했을 때 이 습관이 가장 비쌌던 비율 %d%%</div>'
            '%s</div>' % (
                e(name), c["broken"], fmt(c["rework_per100"]), fmt(c["minutes_per100"]),
                fmt(c.get("minutes_low")), fmt(c.get("minutes_high")), round(100 * (c.get("top_share") or 0)),
                ('<div class="lbl" style="margin-top:8px">이번 주에 해 볼 것</div><div><b>%s</b></div>' % e(p)) if p else ""))
    else:
        out.append('<div class="card">원인이 내 쪽으로 확인된 어긋남이 2개 이상인 능력이 없어서 가장 비싼 습관을 고르지 않았어요.</div>')
    items = sorted(rows.items(), key=lambda kv: -kv[1]["cost"]["minutes_per100"])
    lines = "".join('<div class="row" style="border-top:1px solid var(--line);padding:6px 0"><span><b>%s</b> · 끊김 %d</span>'
                    '<span class="meta">요청 100개당 %s분 (%s~%s)</span></div>' % (
                        e(n), v["broken"], fmt(v["cost"]["minutes_per100"]), fmt(v["cost"].get("minutes_low")),
                        fmt(v["cost"].get("minutes_high"))) for n, v in items)
    mins = sum(v["cost"].get("minimum_estimate", 0) for v in rows.values())
    note = ('<div class="meta" style="margin-top:6px">끊김 %d개는 언제 제자리로 돌아왔는지 기록에서 가릴 수 없어 다음 요청 하나만 셌어요. '
            '실제 비용은 이보다 클 수 있어요.</div>' % mins) if mins else ""
    out.append('<div class="card"><div class="lbl">능력별 다시 작업</div>%s%s</div>' % (lines, note))
    return "".join(out)


def overall(abilities):
    tk = tn = lk = ln = 0
    for a in abilities:
        r = rates_of(a)
        if r["task"]:
            tk, tn = tk + r["task"][0], tn + r["task"][1]
        if r["log"]:
            lk, ln = lk + r["log"][0], ln + r["log"][1]
    parts = []
    if tn:
        parts.append("과제 전체 %d%% (%s/%s점)" % (round(100 * tk / tn), fmt(tk), fmt(tn)))
    if ln:
        parts.append("실제 작업 전체에서 어긋나지 않은 장면 %d%% (%d/%d)" % (round(100 * lk / ln), lk, ln))
    return " · ".join(parts)


def section_map(abilities, verdict, est=None):
    rows = ['<div class="h n">능력</div><div class="h">과제 결과</div><div class="h">실제 작업 (어긋나지 않은 비율)</div>']
    for a in abilities:
        t, lg = a.get("task") or {}, a.get("log") or {}
        ts, ls = task_score(a), log_score(a)
        tl = ("%s/%s점" % (fmt(t.get("got", 0)), fmt(t.get("total", 0)))) if ts is not None else "과제 부족"
        if lg.get("opportunities"):
            ll = ("기회 %d · 끊김 %d" % (lg["opportunities"], lg.get("broken", 0))) if ls is not None else (
                "기회 %d개, 부족" % lg["opportunities"])
        else:
            ll = ("보임 %d · 끊김 %d" % (lg.get("shown", 0), lg.get("broken", 0))) if ls is not None else (
                "장면 %d개, 부족" % (lg.get("shown", 0) + lg.get("broken", 0)))
        sc = ((est or {}).get("abilities", {}).get(a["name"]) or {}).get("score") if est else None
        rows.append('<div class="name"><b>%s</b><br>%s<div class="meta">%s</div>%s</div>%s%s' % (
            e(a["name"]), tag(verdict[a["name"]]), e(precision_note(verdict[a["name"]])),
            ('<div class="meta">%s</div>' % e(score_text(sc))) if est else "", meter(ts, tl), meter(ls, ll)))
    return ('<h2 id="map">능력 지도</h2><p class="sub">과제는 지금 풀어 본 결과, 실제 작업은 기록에서 그 능력이 드러난 장면(보임)과 그 능력이 부족해서 일이 어긋난 장면(끊김)이에요. '
            '판정은 이 사람의 다른 능력 평균과 견줘 차이가 측정의 흔들림을 넘을 때만 붙어요.</p>'
            '<div class="card"><div class="meta" style="margin-bottom:8px">전체 수준: %s</div><div class="map">%s</div></div>' % (
                e(overall(abilities) or "증거 없음"), "".join(rows)))


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
                ABILITIES.index(a["name"]) if a["name"] in ABILITIES else 9, e(a["name"]), tag(verdict[a["name"]]),
                e(a.get("definition")), e(a.get("why", "")),
                ('<div class="lbl">연습할 것</div><ul class="practice">%s</ul>' % practice) if practice else "",
                "",
                " open" if verdict[a["name"]]["status"] == "먼저 보완" else "",
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
    est = d.get("estimate")
    nav = (['<a href="#cost">가장 비싼 습관</a>'] if est else []) + ['<a href="#focus">먼저 보완할 것</a>', '<a href="#map">능력 지도</a>', '<a href="#detail">근거와 연습</a>']
    if d.get("mismatches"):
        nav.append('<a href="#mm">생각과 실제</a>')
    nav.append('<a href="#rel">신뢰도</a>')
    head = "<header><h1>%s</h1><div class=\"meta\">%s</div><p class=\"lead\">%s</p><nav>%s</nav></header>" % (
        e(m.get("title", "AI 활용 능력 리포트")),
        e(" · ".join(x for x in [m.get("period") and "기록 " + m["period"], m.get("tools"),
                                 m.get("generated_at") and "만든 날 " + m["generated_at"]] if x)),
        e(d.get("headline", "")), "".join(nav))
    body = [head, section_cost(est, abilities), section_focus(abilities, verdict), section_map(abilities, verdict, est), section_details(abilities, verdict),
            section_mismatch(d.get("mismatches", [])), section_reliability(d.get("signals"), d.get("reliability"), d.get("limits")),
            '<footer>점수나 등급이 아니라 한 사람 안에서 능력끼리 견준 결과예요. 평가받은 본인에게만 드리는 결과이고, 대화 내용이 들어 있어요. 다른 사람에게 보여 줄지는 본인이 정해요.</footer>']
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>%s</title><style>%s</style></head><body><main>%s</main></body></html>' % (
                e(m.get("title", "AI 활용 능력 리포트")), CSS, "".join(body)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input", required=True)
    ap.add_argument("--estimate", help="estimate.py 출력. 주면 final.json의 estimate 자리에 넣는다")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    with open(os.path.expanduser(args.input), encoding="utf-8") as f:
        data = json.load(f)
    if args.estimate:
        with open(os.path.expanduser(args.estimate), encoding="utf-8") as f:
            data["estimate"] = json.load(f)
    out = os.path.expanduser(args.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(data))
    v = judge(order_abilities(data.get("abilities", [])))
    print("저장: %s | %s" % (out, ", ".join("%s=%s" % (k, x["status"]) for k, x in v.items())), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
