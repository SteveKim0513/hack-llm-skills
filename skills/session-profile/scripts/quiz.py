#!/usr/bin/env python3
"""확인 질문 후보를 고르고, 사용자가 답하는 로컬 화면을 연다.

  python3 quiz.py pick  --sessions sessions.jsonl --turns turns.jsonl --out picked.json
  python3 quiz.py serve --quiz quiz.json --answers answers.json [--port 8778]

pick:  "진행" 요청 중 바로 앞 AI 답변이 긴 것(결정이 담겼을 가능성이 큰 것)을 세션을 돌아가며 고른다.
       다시 채점(R)할 세션도 함께 고른다(20%, 최소 3개).
serve: 127.0.0.1에서만 열린다. 문항 종류는 둘이다.
         question  서술형 질문 하나에 답한다. "모르겠음", "맡김"을 고를 수 있다.
         reading   지문을 읽고 "다 읽었어요"를 누르면 지문이 사라지고 fields에 답한다. 지문은 다시 볼 수 없다.
       정답(answer_key, keys)은 화면으로 보내지 않는다. 제출하면 answers.json에 저장되고 잠긴다.

quiz.json: [{id, kind: "동작"|"공백"|"읽기", question, project, passage, fields: [label...], answer_key | keys}]
answers.json: {submitted, items: {id: {mode: "답"|"모르겠음"|"맡김", texts: [...]}}}
"""
import argparse
import json
import os
import random
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

PICK = 12           # 질문 만들기 일꾼에게 넘길 후보 수. 정답을 확정 못 한 것은 버려지므로 넉넉히
MIN_AI_CHARS = 300  # 앞 AI 답변이 이보다 짧으면 넘어간 내용이 거의 없다
PUBLIC = ("id", "question", "project", "passage", "fields")
LOCK = threading.Lock()


def read_jsonl(path):
    with open(os.path.expanduser(path), encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def write_json(path, data):
    path = os.path.expanduser(path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def user_turn_context(session):
    """user_turn 번호마다 (사용자 글, 바로 앞 AI 글)."""
    out, prev_ai = [], ""
    for t in session["turns"]:
        if t["role"] == "assistant":
            prev_ai = t["text"]
        else:
            out.append((t["text"], prev_ai))
            prev_ai = ""
    return out


def pick(sessions, turns, n=PICK, seed=0, recheck=0.2):
    rng = random.Random(seed)
    ctx = [user_turn_context(s) for s in sessions]
    by_s = {}
    for t in turns:
        if t.get("type") != "진행":
            continue
        s, u = t["session_idx"], t["user_turn"]
        if s < len(ctx) and u < len(ctx[s]) and len(ctx[s][u][1]) >= MIN_AI_CHARS:
            by_s.setdefault(s, []).append((len(ctx[s][u][1]), u))
    keys = sorted(by_s)
    queues = [sorted(by_s[s], reverse=True) for s in keys]
    order = list(range(len(keys)))
    rng.shuffle(order)
    picked = []
    while len(picked) < n and any(queues):
        for i in order:
            if queues[i] and len(picked) < n:
                _, u = queues[i].pop(0)
                s = keys[i]
                picked.append({"session_idx": s, "user_turn": u, "project": sessions[s].get("project"),
                               "user_text": ctx[s][u][0][:300], "ai_before": ctx[s][u][1][:3000]})
    k = min(len(sessions), max(3, round(recheck * len(sessions))))
    return {"recheck_sessions": sorted(rng.sample(range(len(sessions)), k)), "events": picked}


def public(item):
    out = {k: item[k] for k in PUBLIC if k in item}
    out["reading"] = bool(item.get("passage"))
    out["fields"] = item.get("fields") or ["답"]
    return out


def complete(item, a):
    if a.get("mode") in ("모르겠음", "맡김"):
        return a["mode"] == "모르겠음" or not item.get("passage")
    texts = a.get("texts") or []
    return a.get("mode") == "답" and len(texts) == len(item.get("fields") or ["답"]) and all(t.strip() for t in texts)


PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>확인 질문</title><style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1f2328;--mute:#69707a;--line:#e3e0d9;--accent:#2f5d50;--soft:#eef3f0}
@media (prefers-color-scheme:dark){:root{--bg:#16181a;--card:#1f2326;--ink:#e8e6e1;--mute:#9aa1a9;--line:#32383d;--accent:#7fc4ad;--soft:#22302b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:720px;margin:0 auto;padding:16px 16px 80px}h1{font-size:18px;margin:8px 0 4px}.meta{font-size:13px;color:var(--mute)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:14px 0}
.q{white-space:pre-wrap;margin:6px 0 10px}.passage{background:var(--soft);border-radius:10px;padding:12px;white-space:pre-wrap}
.lbl{font-weight:600;font-size:14px;margin:10px 0 4px}textarea{width:100%;min-height:80px;font:inherit;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}
.modes{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}.modes label{border:1px solid var(--line);border-radius:999px;padding:4px 12px;cursor:pointer}
button{width:100%;padding:12px;font:inherit;font-weight:700;border:0;border-radius:10px;background:var(--accent);color:var(--bg);cursor:pointer;margin-top:10px}
button:disabled{opacity:.4}.hide{display:none}
</style></head><body><main>
<h1>확인 질문</h1><p class="meta">기록을 찾아보지 말고 지금 아는 대로 써 주세요. 맞춤법은 상관없어요. 모르면 "모르겠음"도 괜찮아요.</p>
<div id="list"></div><button id="go">제출하기</button><p class="meta" id="msg"></p></main><script>
const $=s=>document.querySelector(s);let items=[],ans={},done=false;
function el(t,c,x){const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function save(id){fetch('/api/answer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,...ans[id]})})}
function card(it,n){const a=ans[it.id]=ans[it.id]||{mode:'답',texts:[]};const c=el('section','card');
 c.appendChild(el('div','meta',n+'번'+(it.project?' · '+it.project:'')));if(it.question)c.appendChild(el('div','q',it.question));
 const body=el('div');
 if(it.reading){const p=el('div','passage',it.passage);const w=el('div','meta','다 읽고 버튼을 누르면 지문이 사라지고 질문이 나와요. 지문은 다시 볼 수 없어요.');const b=el('button',null,'다 읽었어요');
  const opened=a.read||done;if(opened){p.classList.add('hide');w.classList.add('hide');b.classList.add('hide')}else body.classList.add('hide');
  b.onclick=()=>{a.read=true;p.classList.add('hide');w.classList.add('hide');b.classList.add('hide');body.classList.remove('hide');save(it.id)};
  c.appendChild(w);c.appendChild(p);c.appendChild(b)}
 it.fields.forEach((f,i)=>{body.appendChild(el('div','lbl',f));const t=document.createElement('textarea');t.value=a.texts[i]||'';t.disabled=done;
  t.oninput=()=>{a.texts[i]=t.value;a.mode='답';save(it.id)};body.appendChild(t)});
 const m=el('div','modes');(it.reading?['모르겠음']:['모르겠음','맡김']).forEach(v=>{const l=el('label');const r=document.createElement('input');r.type='checkbox';
  r.checked=a.mode===v;r.disabled=done;r.onchange=()=>{a.mode=r.checked?v:'답';save(it.id);render()};l.appendChild(r);l.appendChild(document.createTextNode(' '+(v==='맡김'?'맡겨서 몰라도 됨':v)));m.appendChild(l)});
 body.appendChild(m);c.appendChild(body);return c}
function render(){const L=$('#list');L.textContent='';items.forEach((it,i)=>L.appendChild(card(it,i+1)));$('#go').disabled=done;if(done)$('#msg').textContent='제출했어요. 이 창은 닫아도 돼요.'}
$('#go').onclick=async()=>{if(!confirm('제출하면 답을 바꿀 수 없어요.'))return;const r=await fetch('/api/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
 if(r.ok){done=true;render()}else $('#msg').textContent='모든 질문에 답하거나 "모르겠음"을 골라 주세요.'};
fetch('/api/items').then(r=>r.json()).then(d=>{items=d.items;ans=d.answers;done=d.submitted;render()});
</script></body></html>"""


def handler(quiz, answers_path, port):
    allowed = {"127.0.0.1:%d" % port, "localhost:%d" % port}
    by_id = {q["id"]: q for q in quiz}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json; charset=utf-8"):
            raw = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def state(self):
            try:
                with open(answers_path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                return {"submitted": False, "items": {}}

        def do_GET(self):
            if self.headers.get("Host", "") not in allowed:
                return self.send(403, "{}")
            if self.path in ("/", "/index.html"):
                return self.send(200, PAGE, "text/html; charset=utf-8")
            if self.path == "/api/items":
                st = self.state()
                return self.send(200, json.dumps({"items": [public(q) for q in quiz], "answers": st["items"],
                                                  "submitted": st["submitted"]}, ensure_ascii=False))
            self.send(404, "{}")

        def do_POST(self):
            if self.headers.get("Host", "") not in allowed or "application/json" not in self.headers.get("Content-Type", ""):
                return self.send(403, "{}")
            try:
                body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 200000)) or b"{}")
            except ValueError:
                return self.send(400, "{}")
            with LOCK:
                st = self.state()
                if st["submitted"]:
                    return self.send(409, "{}")
                if self.path == "/api/answer":
                    q = by_id.get(body.get("id"))
                    if not q or body.get("mode") not in ("답", "모르겠음", "맡김") or not isinstance(body.get("texts", []), list):
                        return self.send(400, "{}")
                    st["items"][q["id"]] = {"mode": body["mode"], "texts": [str(t or "")[:4000] for t in body.get("texts", [])][:len(q.get("fields") or ["답"])],
                                            "read": bool(body.get("read"))}
                elif self.path == "/api/submit":
                    if not all(complete(q, st["items"].get(q["id"], {})) for q in quiz):
                        return self.send(400, "{}")
                    st["submitted"] = True
                else:
                    return self.send(404, "{}")
                write_json(answers_path, st)
            self.send(200, "{}")

    return H


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pick")
    p.add_argument("--sessions", required=True)
    p.add_argument("--turns", required=True)
    p.add_argument("--n", type=int, default=PICK)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--quiz", required=True)
    s.add_argument("--answers", required=True)
    s.add_argument("--port", type=int, default=8778)
    a = ap.parse_args(argv)
    if a.cmd == "pick":
        d = pick(read_jsonl(a.sessions), read_jsonl(a.turns), a.n, a.seed)
        write_json(a.out, d)
        print("질문 후보 %d개, 다시 채점할 세션 %s" % (len(d["events"]), d["recheck_sessions"]), file=sys.stderr)
        return 0
    with open(os.path.expanduser(a.quiz), encoding="utf-8") as f:
        quiz = json.load(f)
    srv = HTTPServer(("127.0.0.1", a.port), handler(quiz, os.path.expanduser(a.answers), a.port))
    print("http://127.0.0.1:%d  (끄려면 Ctrl+C)" % a.port, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
