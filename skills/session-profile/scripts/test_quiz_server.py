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
    {"item_id": "a", "question": "q1", "key_points": ["k1"], "full_credit": "f", "partial_credit": "p",
     "evidence": ["e1"], "project": "x", "date": "d"},
    {"item_id": "b", "question": "q2", "key_points": ["k2"], "full_credit": "f", "partial_credit": "p",
     "evidence": [], "project": "x", "date": "d"},
]


class ClassifyTest(unittest.TestCase):
    def test_states(self):
        a = {"mode": "답", "text": "t", "confidence": "확실"}
        self.assertEqual(qs.classify(a, {"grade": "맞음"}), "이해")
        self.assertEqual(qs.classify(a, {"grade": "부분"}), "부분 이해")
        self.assertEqual(qs.classify(a, {"grade": "틀림"}), "확신 오답")
        self.assertEqual(qs.classify(dict(a, confidence="찍음"), {"grade": "틀림"}), "틀림")
        self.assertEqual(qs.classify(a, {}), "채점 전")
        self.assertEqual(qs.classify({"mode": "모르겠음"}, None), "모름")
        self.assertEqual(qs.classify({"mode": "맡김"}, None), "맡김")

    def test_complete_needs_text_and_confidence(self):
        self.assertFalse(qs.complete({"mode": "답", "text": "  ", "confidence": "확실"}))
        self.assertFalse(qs.complete({"mode": "답", "text": "t"}))
        self.assertTrue(qs.complete({"mode": "답", "text": "t", "confidence": "대략"}))
        self.assertTrue(qs.complete({"mode": "맡김"}))


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.items, self.answers, self.grades = str(d / "q.json"), str(d / "a.json"), str(d / "g.json")
        Path(self.items).write_text(json.dumps(ITEMS, ensure_ascii=False), encoding="utf-8")
        self.srv = HTTPServer(("127.0.0.1", 0), qs.make_handler(self.items, self.answers, self.grades, 0))
        self.port = self.srv.server_address[1]
        self.srv.RequestHandlerClass = qs.make_handler(self.items, self.answers, self.grades, self.port)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def call(self, path, body=None):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path),
                                     data=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
                                     method="GET" if body is None else "POST")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read()
                return r.status, json.loads(raw) if "json" in r.headers.get("Content-Type", "") else raw
        except urllib.error.HTTPError as e:
            return e.code, None

    def test_key_does_not_leak_before_submit(self):
        code, d = self.call("/api/items")
        self.assertEqual(code, 200)
        for item in d["items"]:
            self.assertEqual(set(item), {"item_id", "question", "project", "date"})
        self.assertNotIn("k1", json.dumps(d, ensure_ascii=False))
        self.assertEqual(self.call("/api/reveal")[0], 403)

    def test_submit_then_wait_for_grades_then_reveal(self):
        self.call("/api/answer", {"item_id": "a", "mode": "답", "text": "내 답", "confidence": "확실"})
        self.assertEqual(self.call("/api/submit", {})[0], 400)
        self.call("/api/answer", {"item_id": "b", "mode": "맡김"})
        self.assertEqual(self.call("/api/submit", {})[0], 200)
        self.assertEqual(self.call("/api/answer", {"item_id": "b", "mode": "답", "text": "x", "confidence": "확실"})[0], 409)
        self.assertEqual(self.call("/api/reveal")[0], 202)  # a는 채점이 필요하다
        Path(self.grades).write_text(json.dumps({"a": {"grade": "부분", "why": "w"}}, ensure_ascii=False), encoding="utf-8")
        code, d = self.call("/api/reveal")
        self.assertEqual(code, 200)
        self.assertEqual([r["status"] for r in d["results"]], ["부분 이해", "맡김"])
        self.assertEqual(d["results"][0]["key_points"], ["k1"])

    def test_feedback_only_after_submit_and_valid_values(self):
        self.assertEqual(self.call("/api/feedback", {"item_id": "a", "agree": "동의"})[0], 400)
        self.call("/api/answer", {"item_id": "a", "mode": "모르겠음"})
        self.call("/api/answer", {"item_id": "b", "mode": "모르겠음"})
        self.call("/api/submit", {})
        self.assertEqual(self.call("/api/feedback", {"item_id": "a", "agree": "x"})[0], 400)
        self.assertEqual(self.call("/api/feedback", {"item_id": "a", "agree": "이의", "fair": "공정", "comment": "c"})[0], 200)
        saved = json.loads(Path(self.answers).read_text(encoding="utf-8"))
        self.assertEqual(saved["items"]["a"]["agree"], "이의")
        self.assertEqual(saved["items"]["a"]["mode"], "모르겠음")

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
