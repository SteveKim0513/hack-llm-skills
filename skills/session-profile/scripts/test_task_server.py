"""task_server 테스트. 임시 폴더와 가짜 과제만 쓴다.
실행: cd skills/session-profile/scripts && python3 -m unittest -v test_task_server
"""
import json
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import task_server as ts

ITEMS = [
    {"item_id": "c1", "ability": "이해", "type": "open", "question": "q", "key_points": ["SECRET-key"]},
    {"item_id": "r1", "ability": "읽기", "type": "reading", "passage": "지문", "fields": [{"label": "질문1"}, {"label": "질문2"}],
     "keys": [["SECRET-r1"], ["SECRET-r2"]]},
    {"item_id": "e1", "ability": "표현 정확성", "type": "expression", "question": "상황", "target": ["속성1", "속성2"],
     "fields": [{"label": "AI에게 보낼 요청"}]},
]


class CompleteTest(unittest.TestCase):
    def test_rules(self):
        c1, r1, e1 = ITEMS
        self.assertTrue(ts.complete(c1, {"mode": "맡김"}))
        self.assertFalse(ts.complete(r1, {"mode": "맡김"}))          # 맡김은 이해 퀴즈에서만
        self.assertTrue(ts.complete(r1, {"mode": "모르겠음"}))
        self.assertFalse(ts.complete(r1, {"mode": "답", "texts": ["a"], "confidence": "확실"}))
        self.assertTrue(ts.complete(r1, {"mode": "답", "texts": ["a", "b"], "confidence": "확실"}))
        self.assertFalse(ts.complete(e1, {"mode": "답", "texts": [" "], "confidence": "대략"}))

    def test_public_hides_keys_and_adds_defaults(self):
        p = ts.public(ITEMS[0])
        self.assertNotIn("key_points", p)
        self.assertEqual(p["fields"], [{"label": "답"}])
        self.assertTrue(p["allow_delegate"])
        self.assertFalse(ts.public(ITEMS[1])["allow_delegate"])


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.items, self.answers = str(d / "t.json"), str(d / "a.json")
        Path(self.items).write_text(json.dumps(ITEMS, ensure_ascii=False), encoding="utf-8")
        self.srv = HTTPServer(("127.0.0.1", 0), ts.make_handler(self.items, self.answers, 0))
        self.port = self.srv.server_address[1]
        self.srv.RequestHandlerClass = ts.make_handler(self.items, self.answers, self.port)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def call(self, path, body=None, host=None):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path),
                                     data=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
                                     method="GET" if body is None else "POST")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read()
                return r.status, json.loads(raw) if "json" in r.headers.get("Content-Type", "") else raw
        except urllib.error.HTTPError as e:
            return e.code, None

    def test_items_never_carry_keys(self):
        code, d = self.call("/api/items")
        self.assertEqual(code, 200)
        self.assertNotIn("SECRET", json.dumps(d, ensure_ascii=False))
        self.assertEqual([i["type"] for i in d["items"]], ["open", "reading", "expression"])

    def test_answer_submit_lock(self):
        self.call("/api/answer", {"item_id": "c1", "mode": "맡김"})
        self.call("/api/answer", {"item_id": "r1", "mode": "답", "texts": ["x"], "confidence": "확실", "read_done": True})
        self.call("/api/answer", {"item_id": "e1", "mode": "답", "texts": ["요청"], "confidence": "대략"})
        self.assertEqual(self.call("/api/submit", {})[0], 400)       # r1 칸이 하나 비어 있다
        self.call("/api/answer", {"item_id": "r1", "mode": "답", "texts": ["x", "y", "넘침"], "confidence": "확실", "read_done": True})
        self.assertEqual(self.call("/api/submit", {})[0], 200)
        saved = json.loads(Path(self.answers).read_text(encoding="utf-8"))
        self.assertEqual(saved["items"]["r1"]["texts"], ["x", "y"])  # 칸 수만큼만 저장
        self.assertTrue(saved["items"]["r1"]["read_done"])
        self.assertEqual(self.call("/api/answer", {"item_id": "c1", "mode": "모르겠음"})[0], 409)

    def test_rejects_bad_requests(self):
        self.assertEqual(self.call("/api/answer", {"item_id": "zz", "mode": "답"})[0], 400)
        self.assertEqual(self.call("/api/answer", {"item_id": "c1", "mode": "답", "texts": "문자열"})[0], 400)
        self.assertEqual(self.call("/api/items", host="evil.example")[0], 403)

    def test_page_script_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node 없음")
        js = re.search(r"<script>(.*)</script>", ts.PAGE, re.S).group(1)
        p = Path(self.tmp.name) / "page.js"
        p.write_text(js, encoding="utf-8")
        self.assertEqual(subprocess.run([node, "--check", str(p)], capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
