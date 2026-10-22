#!/usr/bin/env python3
"""이해 확인 퀴즈용 로컬 웹 화면 (서술형).

사용자는 질문에 한두 문장으로 답하고 확신도를 고른다. 제출하면 채점 대기 상태가 되고, 채점 결과 파일이 채워지면
정답 기준과 채점 근거를 보여 준다. 사용자는 채점에 동의하는지, 문항이 공정했는지 표시할 수 있다.
객관식 이유 보기는 쓰지 않는다. 보기가 정답을 흘리는 것을 확인했기 때문이다(references/validation-notes.md).

127.0.0.1에서만 열린다. 정답 기준은 제출하고 채점이 끝난 뒤에만 내보낸다.

  python3 quiz_server.py --items quiz.json --answers answers.json --grades grades.json [--port 8778]

quiz.json:    [{"item_id", "question", "key_points": [...], "full_credit", "partial_credit", "evidence": [...],
               "project", "date"}]
answers.json: {"submitted": bool, "items": {item_id: {"mode": "답"|"모르겠음"|"맡김", "text", "confidence",
               "agree", "fair", "comment"}}}
grades.json:  {item_id: {"grade": "맞음"|"부분"|"틀림", "why": "..."}}  (채점기가 쓴다)
"""
import argparse
import datetime
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

LOCK = threading.Lock()
MODES = ("답", "모르겠음", "맡김")
CONFIDENCE = ("확실", "대략", "찍음")
GRADES = ("맞음", "부분", "틀림")
AGREE = ("", "동의", "이의")
FAIR = ("", "공정", "불공정", "애매")
PUBLIC = ("item_id", "question", "project", "date")


def classify(ans, grade):
    """문항 하나의 결과. 점수가 아니라 상태다."""
    mode = ans.get("mode")
    if mode == "맡김":
        return "맡김"
    if mode != "답":
        return "모름"
    g = (grade or {}).get("grade")
    if g == "맞음":
        return "이해"
    if g == "부분":
        return "부분 이해"
    if g == "틀림":
        return "확신 오답" if ans.get("confidence") == "확실" else "틀림"
    return "채점 전"


def complete(ans):
    mode = ans.get("mode")
    if mode in ("모르겠음", "맡김"):
        return True
    return mode == "답" and bool((ans.get("text") or "").strip()) and ans.get("confidence") in CONFIDENCE


def needs_grade(ans):
    return ans.get("mode") == "답"


PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>이해 확인</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1f2328;--mute:#69707a;--line:#e3e0d9;--accent:#2f5d50;--ok:#2f7a4f;--bad:#a4442f;--warn:#9a5b00}
@media (prefers-color-scheme:dark){:root{--bg:#16181a;--card:#1f2326;--ink:#e8e6e1;--mute:#9aa1a9;--line:#32383d;--accent:#7fc4ad;--ok:#7fd19b;--bad:#f09a86;--warn:#e0a458}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:720px;margin:0 auto;padding:16px 16px 96px}
header{position:sticky;top:0;background:var(--bg);padding:12px 0 10px;border-bottom:1px solid var(--line);z-index:5}
h1{font-size:18px;margin:0 0 4px}.sub{color:var(--mute);font-size:14px;margin:0}
.bar{height:6px;background:var(--line);border-radius:3px;margin:10px 0 6px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent);width:0;transition:width .2s}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:14px 0}
.meta{font-size:13px;color:var(--mute)}
.qs{font-size:17px;font-weight:600;margin:6px 0 10px;white-space:pre-wrap;word-break:break-word}
.q{font-weight:600;font-size:14px;margin:12px 0 6px}
.opts{display:flex;gap:8px;flex-wrap:wrap}
.opts label{flex:1 1 80px;border:1px solid var(--line);border-radius:10px;padding:10px;cursor:pointer;min-height:44px;text-align:center}
.opts input{position:absolute;opacity:0}.opts label:has(input:checked){background:var(--accent);color:var(--bg);border-color:var(--accent);font-weight:700}
.opts label:has(input:focus-visible){outline:2px solid var(--accent);outline-offset:2px}
textarea{width:100%;font:inherit;font-size:15px;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);min-height:72px;resize:vertical}
textarea:disabled{opacity:.8}
.hide{display:none}
button.go{width:100%;padding:14px;font:inherit;font-weight:700;border:0;border-radius:10px;background:var(--accent);color:var(--bg);cursor:pointer;margin-top:12px}
button.go:disabled{opacity:.4;cursor:not-allowed}
.res{border-top:1px dashed var(--line);margin-top:12px;padding-top:10px;font-size:14px}
.tag{display:inline-block;border-radius:999px;padding:1px 10px;font-weight:700;font-size:13px;border:1px solid currentColor;margin-bottom:6px}
.t-이해{color:var(--ok)}.t-확신{color:var(--bad)}.t-틀림,.t-부분{color:var(--warn)}.t-모름,.t-맡김,.t-채점{color:var(--mute)}
ul{margin:4px 0 6px 18px;padding:0}
blockquote{margin:6px 0;padding:4px 10px;border-left:3px solid var(--line);color:var(--mute);white-space:pre-wrap}
.sum,.wait{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-top:14px}
.saved{font-size:12px;color:var(--accent);height:16px;margin-top:4px}
</style></head><body><main>
<header><h1>이해 확인</h1><p class="sub">최근 작업에서 정한 것들에 대한 질문이에요. 기록을 찾아보지 말고 지금 아는 대로 한두 문장으로 답해 주세요. 맞춤법이나 표현은 상관없어요.</p>
<div class="bar"><i id="bar"></i></div><div class="meta" id="count"></div></header>
<div id="list"></div><div id="after"></div></main>
<script>
const $=(s,r=document)=>r.querySelector(s);
function el(t,c,txt){const e=document.createElement(t);if(c)e.className=c;if(txt!=null)e.textContent=txt;return e}
let items=[],ans={},submitted=false,timer={};
function done(a){if(!a)return false;if(a.mode==='모르겠음'||a.mode==='맡김')return true;return a.mode==='답'&&!!(a.text||'').trim()&&!!a.confidence}
function update(){const n=items.filter(i=>done(ans[i.item_id])).length;$('#count').textContent=`${items.length}문항 중 ${n}개 답함`;
 $('#bar').style.width=(items.length?100*n/items.length:0)+'%';const b=$('#submit');if(b)b.disabled=n<items.length||submitted}
function post(url,body){return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
function save(id){const a=ans[id]||{};const st=document.querySelector(`[data-id="${id}"] .saved`);
 post('/api/answer',{item_id:id,mode:a.mode,text:a.text||'',confidence:a.confidence||''}).then(r=>{if(st)st.textContent=r.ok?'저장됨':'저장 실패'}).catch(()=>{if(st)st.textContent='저장 실패'})}
function radios(name,vals,cur,on){const o=el('div','opts');vals.forEach(v=>{const lb=el('label');const r=document.createElement('input');r.type='radio';r.name=name;
 const val=typeof v==='object'?v.value:v;r.checked=cur===val;r.disabled=submitted;r.onchange=()=>on(val);lb.appendChild(r);lb.appendChild(document.createTextNode(typeof v==='object'?v.label:v));o.appendChild(lb)});return o}
function card(it,n){const c=el('section','card');c.dataset.id=it.item_id;const a=ans[it.item_id]=ans[it.item_id]||{};
 c.appendChild(el('div','meta',`${n}번 · ${it.project||''} · ${it.date||''}`));c.appendChild(el('div','qs',it.question));
 const box=el('div');
 c.appendChild(radios('m'+it.item_id,[{value:'답',label:'답할게요'},{value:'모르겠음',label:'모르겠음'},{value:'맡김',label:'맡긴 부분이라 몰라도 됨'}],a.mode,v=>{a.mode=v;box.classList.toggle('hide',v!=='답');save(it.item_id);update()}));
 const ta=document.createElement('textarea');ta.placeholder='한두 문장으로';ta.value=a.text||'';ta.disabled=submitted;
 ta.oninput=()=>{a.text=ta.value;update();clearTimeout(timer[it.item_id]);timer[it.item_id]=setTimeout(()=>save(it.item_id),500)};
 box.appendChild(el('div','q','답'));box.appendChild(ta);box.appendChild(el('div','q','얼마나 확신하나요?'));
 box.appendChild(radios('c'+it.item_id,['확실','대략','찍음'],a.confidence,v=>{a.confidence=v;save(it.item_id);update()}));
 box.classList.toggle('hide',a.mode!=='답');c.appendChild(box);c.appendChild(el('div','saved',''));return c}
function render(){const list=$('#list');list.textContent='';items.forEach((it,i)=>list.appendChild(card(it,i+1)));
 const after=$('#after');after.textContent='';
 if(!submitted){const b=el('button','go','제출하기');b.id='submit';b.onclick=submit;after.appendChild(b)}update()}
async function submit(){if(!confirm('제출하면 답을 바꿀 수 없어요. 제출할까요?'))return;const r=await post('/api/submit',{});
 if(!r.ok){alert('모든 문항에 답하거나 모르겠음/맡김을 골라야 제출할 수 있어요');return}submitted=true;render();reveal()}
async function reveal(){const r=await fetch('/api/reveal');const after=$('#after');
 if(r.status===202){after.textContent='';const w=el('div','wait');w.appendChild(el('b',null,'제출했어요. 채점을 기다리는 중이에요.'));
  w.appendChild(el('div','meta','채점이 끝나면 이 페이지를 새로고침하세요.'));after.appendChild(w);return}
 if(!r.ok)return;const d=await r.json();const cnt={};
 d.results.forEach(x=>{cnt[x.status]=(cnt[x.status]||0)+1;const c=document.querySelector(`[data-id="${x.item_id}"]`);if(!c)return;
  const box=el('div','res');box.appendChild(el('span','tag t-'+x.status.split(' ')[0],x.status));
  if(x.why)box.appendChild(el('div',null,'채점 근거: '+x.why));
  box.appendChild(el('div','q','정답 기준'));const ul=el('ul');(x.key_points||[]).forEach(k=>ul.appendChild(el('li',null,k)));box.appendChild(ul);
  (x.evidence||[]).forEach(q=>box.appendChild(el('blockquote',null,q)));
  const a=ans[x.item_id]||{};const fb=()=>post('/api/feedback',{item_id:x.item_id,agree:a.agree||'',fair:a.fair||'',comment:a.comment||''});
  if(a.mode==='답'){box.appendChild(el('div','q','채점에 동의하나요?'));box.appendChild(radios('a'+x.item_id,['동의','이의'],a.agree,v=>{a.agree=v;fb()}))}
  box.appendChild(el('div','q','이 문항은 공정했나요?'));box.appendChild(radios('f'+x.item_id,['공정','불공정','애매'],a.fair,v=>{a.fair=v;fb()}));
  const t=document.createElement('textarea');t.placeholder='한 줄 의견 (선택)';t.value=a.comment||'';
  t.oninput=()=>{a.comment=t.value;clearTimeout(timer['f'+x.item_id]);timer['f'+x.item_id]=setTimeout(fb,500)};box.appendChild(t);c.appendChild(box)});
 // 공개 화면에서는 피드백 컨트롤만 다시 켠다
 document.querySelectorAll('.res input').forEach(i=>i.disabled=false);
 const s=el('div','sum');s.appendChild(el('b',null,'결과 요약 (점수가 아니에요)'));
 ['이해','부분 이해','확신 오답','틀림','모름','맡김'].forEach(k=>{if(cnt[k])s.appendChild(el('div',null,`${k}: ${cnt[k]}문항`))});
 s.appendChild(el('div','meta','문항 수가 적어서 "수준"이 아니라 이 결정들을 지금 알고 있는지에 대한 진단이에요. 채점이 이상하면 "이의"를 골라 주세요.'));after.textContent='';after.appendChild(s)}
fetch('/api/items').then(r=>r.json()).then(d=>{items=d.items;ans=d.answers||{};submitted=d.submitted;render();if(submitted)reveal()});
</script></body></html>
"""


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def make_handler(items_path, answers_path, grades_path, port):
    allowed = {"127.0.0.1:%d" % port, "localhost:%d" % port}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            raw = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _ok_host(self):
            return self.headers.get("Host", "") in allowed

        def _state(self):
            items = read_json(items_path, [])
            st = read_json(answers_path, {})
            st.setdefault("items", {})
            st.setdefault("submitted", False)
            return items, st

        def do_GET(self):
            if not self._ok_host():
                return self._send(403, "{}")
            if self.path in ("/", "/index.html"):
                return self._send(200, PAGE, "text/html; charset=utf-8")
            with LOCK:
                items, st = self._state()
                grades = read_json(grades_path, {})
            if self.path == "/api/items":
                return self._send(200, json.dumps({"items": [{k: i[k] for k in PUBLIC if k in i} for i in items],
                                                   "answers": st["items"], "submitted": st["submitted"]},
                                                  ensure_ascii=False))
            if self.path == "/api/reveal":
                if not st["submitted"]:
                    return self._send(403, "{}")
                pending = [i["item_id"] for i in items
                           if needs_grade(st["items"].get(i["item_id"], {})) and i["item_id"] not in grades]
                if pending:
                    return self._send(202, json.dumps({"pending": len(pending)}))
                res = []
                for i in items:
                    a = st["items"].get(i["item_id"], {})
                    g = grades.get(i["item_id"], {})
                    res.append({"item_id": i["item_id"], "status": classify(a, g), "why": g.get("why", ""),
                                "key_points": i.get("key_points", []), "evidence": i.get("evidence", [])})
                return self._send(200, json.dumps({"results": res}, ensure_ascii=False))
            self._send(404, "{}")

        def do_POST(self):
            if not self._ok_host():
                return self._send(403, "{}")
            if "application/json" not in self.headers.get("Content-Type", ""):
                return self._send(415, "{}")
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(min(n, 100000)) or b"{}")
            except ValueError:
                return self._send(400, "{}")
            with LOCK:
                items, st = self._state()
                ids = {i["item_id"] for i in items}
                iid = body.get("item_id")
                if self.path == "/api/answer":
                    if st["submitted"]:
                        return self._send(409, "{}")
                    if iid not in ids or body.get("mode") not in MODES + (None,):
                        return self._send(400, "{}")
                    conf = body.get("confidence")
                    st["items"][iid] = {
                        "mode": body.get("mode"),
                        "text": str(body.get("text") or "")[:2000],
                        "confidence": conf if conf in CONFIDENCE else None,
                        "answered_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    }
                elif self.path == "/api/submit":
                    if not all(complete(st["items"].get(i, {})) for i in ids):
                        return self._send(400, "{}")
                    st["submitted"] = True
                    st["submitted_at"] = datetime.datetime.now().isoformat(timespec="seconds")
                elif self.path == "/api/feedback":
                    if (not st["submitted"] or iid not in ids or body.get("agree", "") not in AGREE
                            or body.get("fair", "") not in FAIR):
                        return self._send(400, "{}")
                    st["items"].setdefault(iid, {}).update({"agree": body.get("agree", ""), "fair": body.get("fair", ""),
                                                            "comment": str(body.get("comment", ""))[:1000]})
                else:
                    return self._send(404, "{}")
                write_json_atomic(answers_path, st)
            self._send(200, "{}")

    return H


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--items", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--grades", required=True)
    ap.add_argument("--port", type=int, default=8778)
    args = ap.parse_args(argv)
    items = os.path.expanduser(args.items)
    if not os.path.exists(items):
        print("문항 파일이 없다: %s" % items, file=sys.stderr)
        return 2
    srv = HTTPServer(("127.0.0.1", args.port), make_handler(items, os.path.expanduser(args.answers),
                                                            os.path.expanduser(args.grades), args.port))
    print("http://127.0.0.1:%d  (끄려면 Ctrl+C)" % args.port, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
