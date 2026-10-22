"""label_server 테스트. 임시 폴더와 가짜 후보만 쓴다.
실행: cd skills/session-profile/scripts && python3 -m unittest -v test_label_server
"""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import label_server as ls

ITEMS = [{"eid": 7, "group": "g", "axis": "검증", "pole": "능동", "strength": "강함", "position": "응답",
          "project": "p", "quote": "q", "context": []}]


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.queue, self.labels = str(d / "q.json"), str(d / "l.json")
        Path(self.queue).write_text(json.dumps(ITEMS, ensure_ascii=False), encoding="utf-8")
        self.srv = HTTPServer(("127.0.0.1", 0), ls.make_handler(self.queue, self.labels, 0))
        self.port = self.srv.server_address[1]
        # 허용 Host는 실제 포트로 다시 만든다
        self.srv.RequestHandlerClass = ls.make_handler(self.queue, self.labels, self.port)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def call(self, path, body=None, ctype="application/json", host=None):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path),
                                     data=None if body is None else json.dumps(body).encode(),
                                     method="GET" if body is None else "POST")
        if body is not None:
            req.add_header("Content-Type", ctype)
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"{}") if "json" in r.headers.get("Content-Type", "") else r.read()
        except urllib.error.HTTPError as e:
            return e.code, None

    def test_page_and_data(self):
        self.assertEqual(self.call("/")[0], 200)
        code, data = self.call("/api/data")
        self.assertEqual((code, len(data["items"]), data["labels"]), (200, 1, []))

    def test_save_upserts_and_keeps_one_row_per_item(self):
        self.call("/api/label", {"eid": 7, "verdict": "아님", "correct_label": "구조/능동", "reason": "r"})
        self.call("/api/label", {"eid": 7, "verdict": "맞음", "correct_label": "", "reason": ""})
        rows = json.loads(Path(self.labels).read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["verdict"], rows[0]["ai_label"]), ("맞음", "검증/능동"))

    def test_rejects_bad_requests(self):
        self.assertEqual(self.call("/api/label", {"eid": 7, "verdict": "x"})[0], 400)
        self.assertEqual(self.call("/api/label", {"eid": 999, "verdict": "맞음"})[0], 404)
        self.assertEqual(self.call("/api/label", {"eid": 7, "verdict": "맞음"}, ctype="text/plain")[0], 415)
        self.assertEqual(self.call("/api/data", host="evil.example")[0], 403)
        self.assertFalse(Path(self.labels).exists())


if __name__ == "__main__":
    unittest.main()
