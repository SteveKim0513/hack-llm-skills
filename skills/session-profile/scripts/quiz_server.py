#!/usr/bin/env python3
"""이해 확인 퀴즈용 로컬 웹 화면 (서술형).

사용자가 하는 일은 여기서 답하는 것뿐이다. 질문에 한두 문장으로 답하고 확신도를 고르거나, "모르겠음",
"맡긴 부분이라 몰라도 됨"을 고른다. 제출하면 끝이고, 채점과 사실 확인은 에이전트가 한 뒤 최종 결과
화면(build_final.py)으로 건넨다. 정답 기준은 이 화면에 나오지 않는다.
객관식 보기는 쓰지 않는다. 보기가 정답을 흘리는 것을 확인했기 때문이다(references/validation-notes.md).

127.0.0.1에서만 열린다.

  python3 quiz_server.py --items quiz.json --answers answers.json [--port 8778]

quiz.json:    [{"item_id", "question", "project", "date", ...정답 기준 필드는 내보내지 않는다}]
answers.json: {"submitted": bool, "items": {item_id: {"mode": "답"|"모르겠음"|"맡김", "text", "confidence"}}}
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
PUBLIC = ("item_id", "question", "project", "date")


def complete(ans):
    mode = ans.get("mode")
    if mode in ("모르겠음", "맡김"):
        return True
    return mode == "답" and bool((ans.get("text") or "").strip()) and ans.get("confidence") in CONFIDENCE


PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>이해 확인</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1f2328;--mute:#69707a;--line:#e3e0d9;--accent:#2f5d50}
@media (prefers-color-scheme:dark){:root{--bg:#16181a;--card:#1f2326;--ink:#e8e6e1;--mute:#9aa1a9;--line:#32383d;--accent:#7fc4ad}}
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
.hide{display:none}
button.go{width:100%;padding:14px;font:inherit;font-weight:700;border:0;border-radius:10px;background:var(--accent);color:var(--bg);cursor:pointer;margin-top:12px}
button.go:disabled{opacity:.4;cursor:not-allowed}
.done{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-top:14px}
.saved{font-size:12px;color:var(--accent);height:16px;margin-top:4px}
</style></head><body><main>
<header><h1>이해 확인</h1><p class="sub">최근 작업에서 정한 것들에 대한 질문이에요. 기록을 찾아보지 말고 지금 아는 대로 한두 문장으로 답해 주세요. 맞춤법이나 표현은 상관없어요. 모르면 "모르겠음"도 정당한 답이에요.</p>
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
 if(submitted){const d=el('div','done');d.appendChild(el('b',null,'제출했어요. 이 창은 닫아도 돼요.'));
  d.appendChild(el('div','meta','채점과 사실 확인이 끝나면 최종 결과 화면을 따로 드려요.'));after.appendChild(d)}
 else{const b=el('button','go','제출하기');b.id='submit';b.onclick=submit;after.appendChild(b)}update()}
async function submit(){if(!confirm('제출하면 답을 바꿀 수 없어요. 제출할까요?'))return;const r=await post('/api/submit',{});
 if(!r.ok){alert('모든 문항에 답하거나 모르겠음/맡김을 골라야 제출할 수 있어요');return}submitted=true;render()}
fetch('/api/items').then(r=>r.json()).then(d=>{items=d.items;ans=d.answers||{};submitted=d.submitted;render()});
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


def make_handler(items_path, answers_path, port):
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
            if self.path == "/api/items":
                with LOCK:
                    items, st = self._state()
                return self._send(200, json.dumps({"items": [{k: i[k] for k in PUBLIC if k in i} for i in items],
                                                   "answers": st["items"], "submitted": st["submitted"]},
                                                  ensure_ascii=False))
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
                if self.path == "/api/answer":
                    iid = body.get("item_id")
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
                else:
                    return self._send(404, "{}")
                write_json_atomic(answers_path, st)
            self._send(200, "{}")

    return H


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--items", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--port", type=int, default=8778)
    args = ap.parse_args(argv)
    items = os.path.expanduser(args.items)
    if not os.path.exists(items):
        print("문항 파일이 없다: %s" % items, file=sys.stderr)
        return 2
    srv = HTTPServer(("127.0.0.1", args.port), make_handler(items, os.path.expanduser(args.answers), args.port))
    print("http://127.0.0.1:%d  (끄려면 Ctrl+C)" % args.port, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
