#!/usr/bin/env python3
"""criteria 기록소 로컬 웹. 표준 라이브러리만 쓰고 127.0.0.1에만 연다.

저장 형식은 ../references/format.md 를 따른다.
종료 코드: 0 저장/닫힘, 2 시간 초과, 3 "일단 진행" 선택.
"""
import argparse
import datetime
import json
import os
import re
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
FIELDS = ["id", "area", "decision", "status", "source", "confirmed_at",
          "review_after", "supersedes", "evidence"]
REVIEW_DAYS = 90
MAX_BODY = 64 * 1024
WEB_DIR = Path(__file__).resolve().parent / "web"
EXIT_CODES = {"saved": 0, "closed": 0, "proceed": 3, "timeout": 2}


# ---------- 파일 형식 ----------

def parse_file(text):
    meta, body = {}, text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                value = value.strip()
                if value.startswith('"'):
                    try:
                        value = json.loads(value)
                    except ValueError:
                        pass
                else:
                    value = re.split(r"\s+#", value)[0].strip()
                meta[key.strip()] = value
            body = text[end + 4:].lstrip("\n")
    return meta, body.rstrip("\n")


def dump_file(meta, body):
    lines = ["---"]
    for key in FIELDS:
        value = meta.get(key, "") or ""
        if key == "evidence" and value:
            value = json.dumps(value, ensure_ascii=False)
        lines.append(f"{key}: {value}".rstrip())
    lines += ["---", "", body.strip(), ""]
    return "\n".join(lines)


def atomic_write(path, text):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def today():
    return datetime.date.today()


def parse_date(value):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def is_stale(meta):
    if meta.get("status") != "confirmed":
        return False
    due = parse_date(meta.get("review_after"))
    if due is None:
        confirmed = parse_date(meta.get("confirmed_at"))
        if confirmed is None:
            return True
        due = confirmed + datetime.timedelta(days=REVIEW_DAYS)
    return due < today()


def slug(text, fallback):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or fallback


def clean_line(text):
    return " ".join(str(text).split())[:80]


# ---------- 기록소 ----------

class Store:
    def __init__(self, dirs):
        self.dirs = dirs  # {"project": Path, "global": Path}
        self.lock = threading.Lock()

    def path(self, scope, cid):
        if scope not in self.dirs or not ID_RE.match(cid or ""):
            raise ValueError("잘못된 id 또는 범위")
        return self.dirs[scope] / f"{cid}.md"

    def load_all(self):
        items = []
        for scope, folder in self.dirs.items():
            if not folder.is_dir():
                continue
            for f in sorted(folder.glob("*.md")):
                if f.name == "INDEX.md":
                    continue
                meta, body = parse_file(f.read_text(encoding="utf-8"))
                meta["id"] = f.stem
                meta["scope"] = scope
                meta["body"] = body
                meta["stale"] = is_stale(meta)
                items.append(meta)
        return items

    def write_index(self, scope):
        lines = []
        for c in self.load_all():
            if c["scope"] != scope:
                continue
            first = (c["body"].splitlines() or [""])[0][:60]
            lines.append(f"- [{c['id']}]({c['id']}.md) · {c.get('area', '')}/"
                         f"{c.get('decision', '')} · {c.get('status', '')} · {first}")
        atomic_write(self.dirs[scope] / "INDEX.md", "\n".join(lines) + "\n")

    def _dates(self):
        now = today()
        return iso(now), iso(now + datetime.timedelta(days=REVIEW_DAYS))

    def save(self, data):
        scope = data.get("scope")
        if scope not in self.dirs:
            raise ValueError("범위가 올바르지 않습니다")
        area = clean_line(data.get("area", ""))
        decision = clean_line(data.get("decision", ""))
        body = str(data.get("body", "")).strip()
        if not area or not decision:
            raise ValueError("영역과 결정 종류를 입력하세요")
        if not body:
            raise ValueError("기준 내용을 입력하세요")
        if len(body.encode("utf-8")) > MAX_BODY:
            raise ValueError("기준 내용이 너무 깁니다")
        source = data.get("source")
        if source not in ("user", "co-created"):
            source = "user"
        with self.lock:
            folder = self.dirs[scope]
            folder.mkdir(parents=True, exist_ok=True)
            old = None
            superseded = data.get("supersedes") or ""
            if superseded:
                old_path = self.path(scope, superseded)
                if not old_path.is_file():
                    raise ValueError("이전 버전을 찾을 수 없습니다")
                old_meta, old_body = parse_file(old_path.read_text(encoding="utf-8"))
                if old_meta.get("status") not in ("confirmed", "draft"):
                    raise ValueError("이미 대체되었거나 폐기된 기준입니다")
                old = (old_path, old_meta, old_body)
                prefix = re.sub(r"-\d+$", "", superseded)
            else:
                prefix = f"{slug(area, 'area')}-{slug(decision, 'decision')}"
            number = 1
            for f in folder.glob(f"{prefix}-*.md"):
                m = re.fullmatch(re.escape(prefix) + r"-(\d+)\.md", f.name)
                if m:
                    number = max(number, int(m.group(1)) + 1)
            cid = f"{prefix}-{number}"
            meta = {"id": cid, "area": area, "decision": decision,
                    "status": "draft", "source": source,
                    "supersedes": superseded,
                    "evidence": clean_line(data.get("evidence", ""))}
            if data.get("confirm"):
                meta["status"] = "confirmed"
                meta["confirmed_at"], meta["review_after"] = self._dates()
            atomic_write(folder / f"{cid}.md", dump_file(meta, body))
            if old:
                old[1]["status"] = "superseded"
                atomic_write(old[0], dump_file(old[1], old[2]))
            self.write_index(scope)
        return {"scope": scope, "id": cid, "status": meta["status"]}

    def set_status(self, scope, cid, action):
        with self.lock:
            path = self.path(scope, cid)
            if not path.is_file():
                raise ValueError("기준을 찾을 수 없습니다")
            meta, body = parse_file(path.read_text(encoding="utf-8"))
            status = meta.get("status")
            if action == "confirm":
                if status != "draft":
                    raise ValueError("초안만 확정할 수 있습니다")
            elif action == "reconfirm":
                if status != "confirmed":
                    raise ValueError("확정된 기준만 다시 확인할 수 있습니다")
            elif action == "retire":
                if status in ("superseded", "retired"):
                    raise ValueError("이미 사용하지 않는 기준입니다")
                meta["status"] = "retired"
            else:
                raise ValueError("알 수 없는 동작")
            if action in ("confirm", "reconfirm"):
                meta["status"] = "confirmed"
                meta["confirmed_at"], meta["review_after"] = self._dates()
            meta["id"] = cid
            atomic_write(path, dump_file(meta, body))
            self.write_index(scope)
        return {"scope": scope, "id": cid, "status": meta["status"]}


def iso(date):
    return date.isoformat()


# ---------- 서버 ----------

class Handler(BaseHTTPRequestHandler):
    server_version = "criteria-web"

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'unsafe-inline'; "
            "style-src 'unsafe-inline'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _guard(self):
        srv = self.server
        srv.last = time.time()
        if self.headers.get("Host", "") not in srv.allowed_hosts:
            self._send(403, {"error": "허용되지 않은 호스트"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in srv.allowed_origins:
            self._send(403, {"error": "허용되지 않은 출처"})
            return False
        return True

    def _token_ok(self, token):
        return secrets.compare_digest(token or "", self.server.token)

    def do_GET(self):
        if not self._guard():
            return
        url = urlparse(self.path)
        if url.path == "/":
            token = parse_qs(url.query).get("t", [""])[0]
            if not self._token_ok(token):
                return self._send(403, {"error": "토큰이 필요합니다"})
            page = (WEB_DIR / "index.html").read_text(encoding="utf-8")
            return self._send(200, page, "text/html; charset=utf-8")
        if url.path == "/api/state":
            if not self._token_ok(self.headers.get("X-Token")):
                return self._send(403, {"error": "토큰이 필요합니다"})
            return self._send(200, self.server.state())
        self._send(404, {"error": "없는 경로"})

    def do_POST(self):
        if not self._guard():
            return
        if not self._token_ok(self.headers.get("X-Token")):
            return self._send(403, {"error": "토큰이 필요합니다"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY * 2:
            return self._send(413, {"error": "요청이 너무 큽니다"})
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("JSON 객체가 필요합니다")
            self._route(data)
        except ValueError as e:
            self._send(400, {"error": str(e)})
        except OSError as e:
            self._send(500, {"error": f"파일 처리 실패: {e}"})

    def _route(self, data):
        srv = self.server
        if self.path == "/api/save":
            out = srv.store.save(data)
            srv.saved.append({"scope": out["scope"], "id": out["id"], "status": out["status"]})
            return self._send(200, out)
        if self.path == "/api/status":
            out = srv.store.set_status(data.get("scope"), data.get("id"), data.get("action"))
            srv.saved.append({"scope": out["scope"], "id": out["id"], "status": out["status"]})
            return self._send(200, out)
        if self.path in ("/api/proceed", "/api/done"):
            if not srv.opts.get("wait"):
                raise ValueError("대기 모드가 아닙니다")
            if self.path == "/api/proceed":
                srv.finish("proceed")
            else:
                srv.finish("saved" if srv.saved else "closed")
            return self._send(200, {"ok": True})
        self._send(404, {"error": "없는 경로"})


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, store, opts):
        super().__init__(("127.0.0.1", opts.get("port", 0)), Handler)
        self.store = store
        self.opts = opts
        self.token = secrets.token_urlsafe(24)
        port = self.server_address[1]
        self.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.allowed_origins = {f"http://{h}" for h in self.allowed_hosts}
        self.saved = []
        self.finished = threading.Event()
        self.result = None
        self.last = time.time()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}/?t={self.token}"

    def finish(self, result):
        if not self.finished.is_set():
            self.result = result
            self.finished.set()

    def state(self):
        o = self.opts
        return {"context": o.get("context", ""), "area": o.get("area", ""),
                "decision": o.get("decision", ""), "wait": bool(o.get("wait")),
                "candidates": o.get("candidates", []),
                "dirs": {k: str(v) for k, v in self.store.dirs.items()},
                "criteria": self.store.load_all()}


def load_candidates(path):
    if not path:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and item.get("title") and item.get("body"):
            out.append({"title": str(item["title"])[:80], "body": str(item["body"])[:2000]})
    return out[:6]


def main(argv=None):
    ap = argparse.ArgumentParser(description="criteria 기록소 로컬 웹")
    ap.add_argument("--dir", default=".criteria", help="프로젝트 기준 폴더")
    ap.add_argument("--global-dir", default="~/.criteria", help="전역 기준 폴더")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--context", default="", help="지금 하던 일 (화면 상단에 고정)")
    ap.add_argument("--area", default="", help="새 기준 폼에 미리 채울 영역")
    ap.add_argument("--decision", default="", help="새 기준 폼에 미리 채울 결정 종류")
    ap.add_argument("--candidates", help="'모름'일 때 보여줄 후보 JSON 파일")
    ap.add_argument("--wait", action="store_true",
                    help="작성이 끝날 때까지 기다린다 (일단 진행/완료 버튼 표시)")
    ap.add_argument("--timeout", type=int, default=None,
                    help="대기 모드는 총 대기 초(기본 900), 관리 모드는 유휴 초(기본 3600)")
    ap.add_argument("--no-open", action="store_true", help="브라우저를 열지 않는다")
    args = ap.parse_args(argv)

    project_dir = Path(args.dir).expanduser().resolve()
    store = Store({"project": project_dir,
                   "global": Path(args.global_dir).expanduser().resolve()})
    opts = {"port": args.port, "context": clean_line(args.context) if args.context else "",
            "area": clean_line(args.area), "decision": clean_line(args.decision),
            "wait": args.wait, "candidates": load_candidates(args.candidates)}
    marker = project_dir / ".last-action.json"
    if args.wait and marker.exists():
        marker.unlink()

    server = Server(store, opts)
    print(json.dumps({"url": server.url, "pid": os.getpid(), "wait": args.wait}),
          flush=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if not args.no_open:
        webbrowser.open(server.url)

    timeout = args.timeout or (900 if args.wait else 3600)
    try:
        if args.wait:
            if not server.finished.wait(timeout):
                server.finish("timeout")
        else:
            while not server.finished.wait(5):
                if time.time() - server.last > timeout:
                    server.finish("closed")
    except KeyboardInterrupt:
        server.finish("closed")
    time.sleep(0.3)  # 마지막 응답이 브라우저에 도착할 시간
    server.shutdown()

    result = {"result": server.result, "saved": server.saved}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if args.wait:
        project_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(marker, json.dumps(result, ensure_ascii=False))
    return EXIT_CODES[server.result]


if __name__ == "__main__":
    sys.exit(main())
