#!/usr/bin/env python3
"""능력 측정 과제를 푸는 로컬 웹 화면.

사용자가 하는 일은 여기서 과제에 답하는 것뿐이다. 제출하면 끝이고, 채점은 에이전트가 한 뒤 최종 결과 화면
(build_final.py)으로 건넨다. 정답 기준이나 채점 기준은 이 화면에 내보내지 않는다. 127.0.0.1에서만 열린다.

과제 종류(type)
  open        이해 퀴즈. 질문에 서술형으로 답한다. "맡긴 부분이라 몰라도 됨"을 고를 수 있다.
  reading     지문을 읽고 "다 읽었어요"를 누르면 지문이 사라지고 질문들(fields)이 나온다.
  goal        상황 카드(question)를 보고 fields(목표, 완료 조건)를 쓴다.
  criteria    요청(question)과 결과물 두 개(options)를 보고 고른 것과 기준을 쓴다.
  expression  목표 명세(target)를 보고 AI에게 보낼 요청을 쓴다. 명세는 복사하지 않도록 안내한다.
  review      AI가 작업을 끝내고 보낸 보고(passage)를 보고 fields에 답한다. 보고는 계속 보인다.

  python3 task_server.py --items tasks.json --answers answers.json [--port 8778]

tasks.json:   [{"item_id", "ability", "type", "title", "question", "passage", "options": [{"label", "text"}],
               "target": [...], "fields": [{"label", "placeholder"}], "project", "date", ...채점용 필드는 내보내지 않는다}]
answers.json: {"submitted": bool, "items": {item_id: {"mode": "답"|"모르겠음"|"맡김", "texts": [...], "confidence",
               "read_done"}}}
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
TYPES = ("open", "reading", "goal", "criteria", "expression", "review")
# 능력 이름과 채점 기준은 내보내지 않는다. 무엇을 재는지 알면 그에 맞춘 "모범 답안"을 쓸 수 있다.
PUBLIC = ("item_id", "type", "title", "question", "passage", "options", "target", "fields", "project", "date")


def fields_of(item):
    return item.get("fields") or [{"label": "답"}]


def public(item):
    out = {k: item[k] for k in PUBLIC if k in item}
    out["fields"] = fields_of(item)
    out["allow_delegate"] = item.get("type", "open") == "open"
    return out


def complete(item, ans):
    mode = ans.get("mode")
    if mode == "모르겠음":
        return True
    if mode == "맡김":
        return item.get("type", "open") == "open"
    texts = ans.get("texts") or []
    n = len(fields_of(item))
    return (mode == "답" and len(texts) == n and all((t or "").strip() for t in texts)
            and ans.get("confidence") in CONFIDENCE)


PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>능력 확인 과제</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1f2328;--mute:#69707a;--line:#e3e0d9;--accent:#2f5d50;--soft:#eef3f0}
@media (prefers-color-scheme:dark){:root{--bg:#16181a;--card:#1f2326;--ink:#e8e6e1;--mute:#9aa1a9;--line:#32383d;--accent:#7fc4ad;--soft:#22302b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:720px;margin:0 auto;padding:16px 16px 96px}
header{position:sticky;top:0;background:var(--bg);padding:12px 0 10px;border-bottom:1px solid var(--line);z-index:5}
h1{font-size:18px;margin:0 0 4px}.sub{color:var(--mute);font-size:14px;margin:0}
.bar{height:6px;background:var(--line);border-radius:3px;margin:10px 0 6px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent);width:0;transition:width .2s}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:14px 0}
.meta{font-size:13px;color:var(--mute)}.ab{font-weight:700;color:var(--accent)}
.title{font-size:16px;font-weight:700;margin:4px 0 6px}
.qs{font-size:16px;margin:6px 0 10px;white-space:pre-wrap;word-break:break-word}
.passage{background:var(--soft);border-radius:10px;padding:12px;white-space:pre-wrap;font-size:15px}
.opt{border:1px solid var(--line);border-radius:10px;padding:10px;margin:8px 0;white-space:pre-wrap;font-size:15px}
.opt b{display:block;margin-bottom:4px}
.target{background:var(--soft);border-radius:10px;padding:10px 12px;user-select:none;-webkit-user-select:none}
.target ul{margin:4px 0 0 18px;padding:0}
.q{font-weight:600;font-size:14px;margin:12px 0 6px}
.opts{display:flex;gap:8px;flex-wrap:wrap}
.opts label{flex:1 1 80px;border:1px solid var(--line);border-radius:10px;padding:10px;cursor:pointer;min-height:44px;text-align:center}
.opts input{position:absolute;opacity:0}.opts label:has(input:checked){background:var(--accent);color:var(--bg);border-color:var(--accent);font-weight:700}
.opts label:has(input:focus-visible){outline:2px solid var(--accent);outline-offset:2px}
textarea{width:100%;font:inherit;font-size:15px;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);min-height:72px;resize:vertical}
.hide{display:none}
button.go,button.read{width:100%;padding:12px;font:inherit;font-weight:700;border:0;border-radius:10px;background:var(--accent);color:var(--bg);cursor:pointer;margin-top:10px}
button.go:disabled{opacity:.4;cursor:not-allowed}
.done{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-top:14px}
.saved{font-size:12px;color:var(--accent);height:16px;margin-top:4px}
</style></head><body><main>
<header><h1>능력 확인 과제</h1><p class="sub">기록을 찾아보지 말고 지금 생각대로 답해 주세요. 맞춤법은 상관없어요. 모르면 "모르겠음"도 정당한 답이에요. 채점은 AI가 하고, 결과는 제출 뒤에 한 장으로 드려요.</p>
<div class="bar"><i id="bar"></i></div><div class="meta" id="count"></div></header>
<div id="list"></div><div id="after"></div></main>
<script>
const $=(s,r=document)=>r.querySelector(s);
function el(t,c,txt){const e=document.createElement(t);if(c)e.className=c;if(txt!=null)e.textContent=txt;return e}
let items=[],ans={},submitted=false,timer={};
function done(it,a){if(!a)return false;if(a.mode==='모르겠음')return true;if(a.mode==='맡김')return it.allow_delegate;
 const t=a.texts||[];return a.mode==='답'&&t.length===it.fields.length&&t.every(x=>(x||'').trim())&&!!a.confidence}
function update(){const n=items.filter(i=>done(i,ans[i.item_id])).length;$('#count').textContent=`${items.length}개 중 ${n}개 답함`;
 $('#bar').style.width=(items.length?100*n/items.length:0)+'%';const b=$('#submit');if(b)b.disabled=n<items.length||submitted}
function post(url,body){return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
function save(id){const a=ans[id]||{};const st=document.querySelector(`[data-id="${id}"] .saved`);
 post('/api/answer',{item_id:id,mode:a.mode,texts:a.texts||[],confidence:a.confidence||'',read_done:!!a.read_done}).then(r=>{if(st)st.textContent=r.ok?'저장됨':'저장 실패'}).catch(()=>{if(st)st.textContent='저장 실패'})}
function radios(name,vals,cur,on){const o=el('div','opts');vals.forEach(v=>{const lb=el('label');const r=document.createElement('input');r.type='radio';r.name=name;
 r.checked=cur===v.value;r.disabled=submitted;r.onchange=()=>on(v.value);lb.appendChild(r);lb.appendChild(document.createTextNode(v.label));o.appendChild(lb)});return o}
function card(it,n){const c=el('section','card');c.dataset.id=it.item_id;const a=ans[it.item_id]=ans[it.item_id]||{};a.texts=a.texts||[];
 c.appendChild(el('div','meta',`${n}번${it.project?' · '+it.project:''}${it.date?' · '+it.date:''}`));
 if(it.title)c.appendChild(el('div','title',it.title));
 if(it.question)c.appendChild(el('div','qs',it.question));
 if(it.type!=='reading'&&it.passage)c.appendChild(el('div','passage',it.passage));
 (it.options||[]).forEach(o=>{const d=el('div','opt');d.appendChild(el('b',null,o.label));d.appendChild(document.createTextNode(o.text));c.appendChild(d)});
 if(it.target&&it.target.length){const t=el('div','target');t.appendChild(el('b',null,'만들고 싶은 것 (그대로 옮기지 말고 자기 말로 써 주세요)'));const ul=el('ul');it.target.forEach(x=>ul.appendChild(el('li',null,x)));t.appendChild(ul);c.appendChild(t)}
 const body=el('div');
 let gate=null;
 if(it.type==='reading'){if(!(a.read_done||submitted))c.appendChild(el('div','meta','다 읽고 "다 읽었어요"를 누르면 지문이 사라지고 질문이 나와요. 지문은 다시 볼 수 없어요.'));const p=el('div','passage',it.passage||'');const btn=el('button','read','다 읽었어요');
  btn.onclick=()=>{a.read_done=true;p.classList.add('hide');btn.classList.add('hide');body.classList.remove('hide');save(it.item_id)};
  if(a.read_done||submitted){p.classList.add('hide');btn.classList.add('hide')}else body.classList.add('hide');
  c.appendChild(p);c.appendChild(btn)}
 const modes=[{value:'답',label:'답할게요'},{value:'모르겠음',label:'모르겠음'}];if(it.allow_delegate)modes.push({value:'맡김',label:'맡긴 부분이라 몰라도 됨'});
 const box=el('div');
 body.appendChild(radios('m'+it.item_id,modes,a.mode,v=>{a.mode=v;box.classList.toggle('hide',v!=='답');save(it.item_id);update()}));
 it.fields.forEach((f,i)=>{box.appendChild(el('div','q',f.label));const ta=document.createElement('textarea');ta.placeholder=f.placeholder||'';ta.value=a.texts[i]||'';ta.disabled=submitted;
  ta.oninput=()=>{a.texts[i]=ta.value;update();clearTimeout(timer[it.item_id]);timer[it.item_id]=setTimeout(()=>save(it.item_id),500)};box.appendChild(ta)});
 box.appendChild(el('div','q','얼마나 확신하나요?'));
 box.appendChild(radios('c'+it.item_id,[{value:'확실',label:'확실'},{value:'대략',label:'대략'},{value:'찍음',label:'찍음'}],a.confidence,v=>{a.confidence=v;save(it.item_id);update()}));
 box.classList.toggle('hide',a.mode!=='답');body.appendChild(box);c.appendChild(body);c.appendChild(el('div','saved',''));return c}
function render(){const list=$('#list');list.textContent='';items.forEach((it,i)=>list.appendChild(card(it,i+1)));
 const after=$('#after');after.textContent='';
 if(submitted){const d=el('div','done');d.appendChild(el('b',null,'제출했어요. 이 창은 닫아도 돼요.'));
  d.appendChild(el('div','meta','채점이 끝나면 최종 결과 화면을 따로 드려요.'));after.appendChild(d)}
 else{const b=el('button','go','제출하기');b.id='submit';b.onclick=submit;after.appendChild(b)}update()}
async function submit(){if(!confirm('제출하면 답을 바꿀 수 없어요. 제출할까요?'))return;const r=await post('/api/submit',{});
 if(!r.ok){alert('모든 과제에 답하거나 모르겠음을 골라야 제출할 수 있어요');return}submitted=true;render()}
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
                return self._send(200, json.dumps({"items": [public(i) for i in items], "answers": st["items"],
                                                   "submitted": st["submitted"]}, ensure_ascii=False))
            self._send(404, "{}")

        def do_POST(self):
            if not self._ok_host():
                return self._send(403, "{}")
            if "application/json" not in self.headers.get("Content-Type", ""):
                return self._send(415, "{}")
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(min(n, 200000)) or b"{}")
            except ValueError:
                return self._send(400, "{}")
            with LOCK:
                items, st = self._state()
                by_id = {i["item_id"]: i for i in items}
                if self.path == "/api/answer":
                    iid = body.get("item_id")
                    if st["submitted"]:
                        return self._send(409, "{}")
                    if iid not in by_id or body.get("mode") not in MODES + (None,):
                        return self._send(400, "{}")
                    texts = body.get("texts") or []
                    if not isinstance(texts, list):
                        return self._send(400, "{}")
                    conf = body.get("confidence")
                    st["items"][iid] = {
                        "mode": body.get("mode"),
                        "texts": [str(t or "")[:4000] for t in texts[:len(fields_of(by_id[iid]))]],
                        "confidence": conf if conf in CONFIDENCE else None,
                        "read_done": bool(body.get("read_done")),
                        "answered_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    }
                elif self.path == "/api/submit":
                    if not all(complete(i, st["items"].get(i["item_id"], {})) for i in items):
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
        print("과제 파일이 없다: %s" % items, file=sys.stderr)
        return 2
    bad = [i.get("item_id") for i in read_json(items, []) if i.get("type", "open") not in TYPES]
    if bad:
        print("알 수 없는 과제 종류: %s" % bad, file=sys.stderr)
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
