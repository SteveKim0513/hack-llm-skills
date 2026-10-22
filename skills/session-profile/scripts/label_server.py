#!/usr/bin/env python3
"""사용자 판정용 로컬 웹 화면.

127.0.0.1에서만 열리고, 답은 바뀔 때마다 labels 파일에 바로 저장된다. 외부로 아무것도 보내지 않는다.
대화 원문이 화면에 나오므로 공개 저장소 밖의 파일만 쓴다.

  python3 label_server.py --queue queue.json --labels labels.json [--port 8765]

queue.json: [{"eid", "group", "axis", "pole", "strength", "position", "project", "quote",
              "context": [{"role", "text", "full"}]}]
labels.json: [{"eid", "ai_label", "verdict", "correct_label", "reason", "answered_at"}]
"""
import argparse
import datetime
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

LOCK = threading.Lock()

PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>분류 확인</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1f2328;--mute:#69707a;--line:#e3e0d9;--accent:#2f5d50;--user:#eef4f1;--ai:#f3f1ec;--warn:#9a5b00}
@media (prefers-color-scheme:dark){:root{--bg:#16181a;--card:#1f2326;--ink:#e8e6e1;--mute:#9aa1a9;--line:#32383d;--accent:#7fc4ad;--user:#22302b;--ai:#262a2d;--warn:#e0a458}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:760px;margin:0 auto;padding:16px 16px 96px}
header{position:sticky;top:0;background:var(--bg);padding:12px 0 10px;border-bottom:1px solid var(--line);z-index:5}
h1{font-size:18px;margin:0 0 4px}.sub{color:var(--mute);font-size:14px;margin:0}
.bar{height:6px;background:var(--line);border-radius:3px;margin:10px 0 6px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent);width:0;transition:width .2s}
.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:14px;color:var(--mute)}
h2{font-size:15px;margin:28px 0 4px}.gnote{color:var(--mute);font-size:14px;margin:0 0 10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:12px 0}
.card.done{border-color:var(--accent)}
.meta{font-size:13px;color:var(--mute);display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.turn{border-radius:10px;padding:8px 10px;margin:8px 0;font-size:14px;white-space:pre-wrap;word-break:break-word}
.turn.user{background:var(--user)}.turn.assistant{background:var(--ai)}
.turn b{display:block;font-size:12px;color:var(--mute);font-weight:600;margin-bottom:2px}
.more{background:none;border:0;color:var(--accent);padding:0;font:inherit;font-size:13px;cursor:pointer;text-decoration:underline}
.quote{border-left:4px solid var(--accent);padding:6px 12px;margin:10px 0;font-size:16px;font-weight:600;white-space:pre-wrap;word-break:break-word}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 10px}.chip{font-size:13px;border:1px solid var(--line);border-radius:999px;padding:1px 10px}
.chip.main{background:var(--accent);color:var(--bg);border-color:var(--accent)}
.q{font-weight:600;margin:10px 0 6px}
.opts{display:flex;gap:8px;flex-wrap:wrap}
.opts label{flex:1 1 90px;border:1px solid var(--line);border-radius:10px;padding:10px 8px;text-align:center;cursor:pointer;min-height:44px}
.opts input{position:absolute;opacity:0}.opts label:has(input:checked){background:var(--accent);color:var(--bg);border-color:var(--accent);font-weight:700}
.opts label:has(input:focus-visible){outline:2px solid var(--accent);outline-offset:2px}
.extra{margin-top:10px}select,textarea{width:100%;font:inherit;font-size:15px;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}
textarea{min-height:64px;resize:vertical;margin-top:6px}label.f{font-size:13px;color:var(--mute);display:block;margin-top:8px}
.saved{font-size:12px;color:var(--accent);height:16px;margin-top:4px}.err{color:var(--warn)}
.hide{display:none}.legend{font-size:13px;color:var(--mute);margin:12px 0}
</style></head><body><main>
<header><h1>분류 확인</h1><p class="sub">AI가 붙인 분류가 맞는지만 봐 주세요. 답은 바꿀 때마다 자동 저장돼요.</p>
<div class="bar"><i id="bar"></i></div>
<div class="row"><span id="count"></span><label><input type="checkbox" id="onlyTodo"> 답 안 한 것만 보기</label></div></header>
<p class="legend"><b>AI 확신도</b>: 강함은 다르게 읽을 여지가 거의 없는 장면, 보통은 그렇게 읽는 게 자연스럽지만 다른 해석도 가능, 약함은 다르게 읽힐 수 있는 장면. 사람의 수준을 뜻하지 않아요.</p>
<div id="list"></div></main>
<script>
const OPTIONS=["검증/능동","검증/수용","구조/능동","구조/수용","방향 주도/능동","방향 주도/수용","메타인지/능동"];
let items=[],labels={},timers={};
const $=(s,r=document)=>r.querySelector(s);
function el(t,c,txt){const e=document.createElement(t);if(c)e.className=c;if(txt!=null)e.textContent=txt;return e}
async function load(){const r=await fetch('/api/data');const d=await r.json();items=d.items;labels={};d.labels.forEach(l=>labels[l.eid]=l);render();}
function update(){const n=items.filter(i=>labels[i.eid]&&labels[i.eid].verdict).length;
 $('#count').textContent=`${items.length}건 중 ${n}건 답함`;$('#bar').style.width=(items.length?100*n/items.length:0)+'%';
 document.querySelectorAll('.card').forEach(c=>{const l=labels[c.dataset.eid];c.classList.toggle('done',!!(l&&l.verdict));
  c.classList.toggle('hide',$('#onlyTodo').checked&&!!(l&&l.verdict))});}
function save(eid,card){const v=(card.querySelector('input[type=radio]:checked')||{}).value||'';
 const rec={eid:+eid,verdict:v,correct_label:v==='아님'?card.querySelector('select').value:'',reason:card.querySelector('textarea').value};
 const st=card.querySelector('.saved');st.textContent='저장 중...';st.classList.remove('err');
 fetch('/api/label',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(rec)})
 .then(r=>r.ok?r.json():Promise.reject(r.status)).then(l=>{labels[eid]=l;st.textContent='저장됨 ✓';update()})
 .catch(()=>{st.textContent='저장 실패. 서버가 켜져 있는지 확인해 주세요';st.classList.add('err')});}
function turn(t){const d=el('div','turn '+t.role);d.appendChild(el('b',null,t.role==='user'?'사용자':'AI'));
 const body=el('span',null,t.text);d.appendChild(body);
 if(t.full&&t.full.length>t.text.length){const b=el('button','more','전체 보기');let open=false;
  b.onclick=()=>{open=!open;body.textContent=open?t.full:t.text;b.textContent=open?'접기':'전체 보기'};d.appendChild(document.createElement('br'));d.appendChild(b)}
 return d}
function card(it,n){const c=el('section','card');c.dataset.eid=it.eid;const l=labels[it.eid]||{};
 const m=el('div','meta');m.appendChild(el('span',null,`${n}번 · ${it.project}`));m.appendChild(el('span',null,'위치: '+it.position));c.appendChild(m);
 (it.context||[]).forEach(t=>c.appendChild(turn(t)));
 const lab=el('div','meta');lab.appendChild(el('span',null,'사용자 발화 전체'));c.appendChild(lab);
 c.appendChild(el('div','quote',it.quote));
 const ch=el('div','chips');ch.appendChild(el('span','chip main',`AI 분류: ${it.axis} / ${it.pole}`));ch.appendChild(el('span','chip','AI 확신도: '+it.strength));c.appendChild(ch);
 c.appendChild(el('div','q',`이 분류(${it.axis} / ${it.pole})가 맞나요?`));
 const o=el('div','opts');['맞음','아님','애매'].forEach(v=>{const lb=el('label');const r=document.createElement('input');r.type='radio';r.name='v'+it.eid;r.value=v;r.checked=l.verdict===v;
  r.onchange=()=>{sel.parentElement.classList.toggle('hide',v!=='아님');save(it.eid,c)};lb.appendChild(r);lb.appendChild(document.createTextNode(v));o.appendChild(lb)});c.appendChild(o);
 const ex=el('div','extra');
 const w=el('div');w.appendChild(el('label','f','어느 쪽이 맞나요? (아님일 때)'));const sel=document.createElement('select');
 [['','선택 안 함'],...OPTIONS.map(x=>[x,x]),['해당 없음','해당 없음 (분류할 행동이 아님)']].forEach(([v,t])=>{const op=el('option',null,t);op.value=v;if(l.correct_label===v)op.selected=true;sel.appendChild(op)});
 sel.onchange=()=>save(it.eid,c);w.appendChild(sel);w.classList.toggle('hide',l.verdict!=='아님');ex.appendChild(w);
 ex.appendChild(el('label','f','이유 한 줄 (선택). 애매할 때는 무엇이 더 있어야 판단되는지'));const ta=document.createElement('textarea');ta.value=l.reason||'';
 ta.oninput=()=>{clearTimeout(timers[it.eid]);timers[it.eid]=setTimeout(()=>save(it.eid,c),500)};ex.appendChild(ta);c.appendChild(ex);
 c.appendChild(el('div','saved',l.verdict?'저장됨 ✓':''));return c}
function render(){const list=$('#list');list.textContent='';let n=0,last=null;
 items.forEach(it=>{if(it.group!==last){last=it.group;const g=it.group.split('|');list.appendChild(el('h2',null,g[0]));if(g[1])list.appendChild(el('p','gnote',g[1]))}
  list.appendChild(card(it,++n))});update();}
$('#onlyTodo').onchange=update;load();
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


def make_handler(queue_path, labels_path, port):
    allowed_hosts = {"127.0.0.1:%d" % port, "localhost:%d" % port}

    class Handler(BaseHTTPRequestHandler):
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

        def _host_ok(self):
            return self.headers.get("Host", "") in allowed_hosts

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, "{}")
            if self.path in ("/", "/index.html"):
                return self._send(200, PAGE, "text/html; charset=utf-8")
            if self.path == "/api/data":
                with LOCK:
                    data = {"items": read_json(queue_path, []), "labels": read_json(labels_path, [])}
                return self._send(200, json.dumps(data, ensure_ascii=False))
            self._send(404, "{}")

        def do_POST(self):
            if not self._host_ok() or self.path != "/api/label":
                return self._send(403, "{}")
            if "application/json" not in self.headers.get("Content-Type", ""):
                return self._send(415, "{}")
            try:
                n = int(self.headers.get("Content-Length", "0"))
                rec = json.loads(self.rfile.read(min(n, 100000)))
                eid = int(rec["eid"])
            except (ValueError, KeyError, TypeError):
                return self._send(400, "{}")
            verdict = rec.get("verdict", "")
            if verdict not in ("", "맞음", "아님", "애매"):
                return self._send(400, "{}")
            with LOCK:
                items = {i["eid"]: i for i in read_json(queue_path, [])}
                if eid not in items:
                    return self._send(404, "{}")
                labels = read_json(labels_path, [])
                cur = next((l for l in labels if l.get("eid") == eid), None)
                if cur is None:
                    cur = {"eid": eid}
                    labels.append(cur)
                cur.update({
                    "ai_label": "%s/%s" % (items[eid]["axis"], items[eid]["pole"]),
                    "verdict": verdict,
                    "correct_label": str(rec.get("correct_label", ""))[:40],
                    "reason": str(rec.get("reason", ""))[:2000],
                    "answered_at": datetime.datetime.now().isoformat(timespec="seconds"),
                })
                write_json_atomic(labels_path, labels)
            self._send(200, json.dumps(cur, ensure_ascii=False))

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--queue", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)
    queue, labels = os.path.expanduser(args.queue), os.path.expanduser(args.labels)
    if not os.path.exists(queue):
        print("queue 파일이 없다: %s" % queue, file=sys.stderr)
        return 2
    srv = HTTPServer(("127.0.0.1", args.port), make_handler(queue, labels, args.port))
    print("http://127.0.0.1:%d  (끄려면 Ctrl+C)" % args.port, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
