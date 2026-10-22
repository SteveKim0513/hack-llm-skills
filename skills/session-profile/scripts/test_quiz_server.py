"""quiz_server 테스트. 임시 폴더와 가짜 문항만 쓴다.
실행: cd skills/session-profile/scripts && python3 -m unittest -v test_quiz_server
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

import quiz_server as qs

ITEMS = [
    {"item_id": "a", "question": "q1", "key_points": ["k1"], "full_credit": "f", "evidence": ["e1"], "project": "x", "date": "d"},
    {"item_id": "b", "question": "q2", "key_points": ["k2"], "full_credit": "f", "evidence": [], "project": "x", "date": "d"},
]


class CompleteTest(unittest.TestCase):
    def test_complete_needs_text_and_confidence(self):
        self.assertFalse(qs.complete({"mode": "답", "text": "  ", "confidence": "확실"}))
        self.assertFalse(qs.complete({"mode": "답", "text": "t"}))
        self.assertTrue(qs.complete({"mode": "답", "text": "t", "confidence": "대략"}))
        self.assertTrue(qs.complete({"mode": "맡김"}))
        self.assertTrue(qs.complete({"mode": "모르겠음"}))


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.items, self.answers = str(d / "q.json"), str(d / "a.json")
        Path(self.items).write_text(json.dumps(ITEMS, ensure_ascii=False), encoding="utf-8")
        self.srv = HTTPServer(("127.0.0.1", 0), qs.make_handler(self.items, self.answers, 0))
        self.port = self.srv.server_address[1]
        self.srv.RequestHandlerClass = qs.make_handler(self.items, self.answers, self.port)
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

    def test_key_never_leaves_the_server(self):
        code, d = self.call("/api/items")
        self.assertEqual(code, 200)
        for item in d["items"]:
            self.assertEqual(set(item), {"item_id", "question", "project", "date"})
        self.assertNotIn("k1", json.dumps(d, ensure_ascii=False))
        self.assertEqual(self.call("/api/reveal")[0], 404)

    def test_submit_needs_every_item_then_locks(self):
        self.call("/api/answer", {"item_id": "a", "mode": "답", "text": "내 답", "confidence": "확실"})
        self.assertEqual(self.call("/api/submit", {})[0], 400)
        self.call("/api/answer", {"item_id": "b", "mode": "맡김"})
        self.assertEqual(self.call("/api/submit", {})[0], 200)
        self.assertEqual(self.call("/api/answer", {"item_id": "b", "mode": "답", "text": "x", "confidence": "확실"})[0], 409)
        saved = json.loads(Path(self.answers).read_text(encoding="utf-8"))
        self.assertTrue(saved["submitted"])
        self.assertEqual(saved["items"]["a"]["text"], "내 답")

    def test_rejects_bad_requests(self):
        self.assertEqual(self.call("/api/answer", {"item_id": "zz", "mode": "답"})[0], 400)
        self.assertEqual(self.call("/api/answer", {"item_id": "a", "mode": "x"})[0], 400)
        self.assertEqual(self.call("/api/items", host="evil.example")[0], 403)

    def test_page_script_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node 없음")
        js = re.search(r"<script>(.*)</script>", qs.PAGE, re.S).group(1)
        p = Path(self.tmp.name) / "page.js"
        p.write_text(js, encoding="utf-8")
        self.assertEqual(subprocess.run([node, "--check", str(p)], capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
