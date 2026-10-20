"""criteria_web 테스트. 실행: python3 -m unittest -v test_criteria_web (scripts 폴더에서)"""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

import criteria_web as cw


class WebTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.store = cw.Store({"project": root / "p", "global": root / "g"})
        self.server = cw.Server(self.store, {"port": 0, "wait": True, "context": "매거진 기획",
                                             "candidates": []})
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def call(self, method, path, body=None, token=True, host=None, origin=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Token"] = self.server.token
        if host:
            headers["Host"] = host
        if origin:
            headers["Origin"] = origin
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        resp = conn.getresponse()
        raw = resp.read().decode()
        conn.close()
        try:
            return resp.status, json.loads(raw)
        except ValueError:
            return resp.status, raw

    def save(self, **kw):
        data = {"scope": "project", "area": "매거진", "decision": "소스 선별",
                "body": "2025년 이후 1차 자료만", "confirm": True}
        data.update(kw)
        return self.call("POST", "/api/save", data)

    # --- 보안 ---
    def test_page_requires_token(self):
        self.assertEqual(self.call("GET", "/")[0], 403)
        status, page = self.call("GET", "/?t=" + self.server.token)
        self.assertEqual(status, 200)
        self.assertIn("기준 기록소", page)

    def test_api_requires_token(self):
        self.assertEqual(self.call("GET", "/api/state", token=False)[0], 403)
        self.assertEqual(self.call("POST", "/api/save", {}, token=False)[0], 403)

    def test_rejects_foreign_host_and_origin(self):
        self.assertEqual(self.call("GET", "/api/state", host="evil.com")[0], 403)
        self.assertEqual(self.call("POST", "/api/save", {}, origin="http://evil.com")[0], 403)

    def test_rejects_path_traversal(self):
        status, _ = self.call("POST", "/api/status",
                              {"scope": "project", "id": "../x", "action": "retire"})
        self.assertEqual(status, 400)

    # --- 저장 ---
    def test_save_confirmed_writes_file_and_index(self):
        status, out = self.save()
        self.assertEqual(status, 200)
        self.assertEqual(out["status"], "confirmed")
        folder = self.store.dirs["project"]
        text = (folder / f"{out['id']}.md").read_text(encoding="utf-8")
        self.assertIn("status: confirmed", text)
        self.assertIn("2025년 이후 1차 자료만", text)
        index = (folder / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn(out["id"], index)
        self.assertIn("매거진/소스 선별 · confirmed", index)

    def test_draft_has_no_confirmed_date(self):
        _, out = self.save(confirm=False)
        meta, _ = cw.parse_file((self.store.dirs["project"] / f"{out['id']}.md")
                                .read_text(encoding="utf-8"))
        self.assertEqual(meta["status"], "draft")
        self.assertEqual(meta.get("confirmed_at", ""), "")

    def test_edit_creates_new_version_and_supersedes_old(self):
        _, first = self.save()
        status, second = self.save(body="1차 자료 + 공식 통계", supersedes=first["id"])
        self.assertEqual(status, 200)
        self.assertNotEqual(first["id"], second["id"])
        self.assertTrue(second["id"].endswith("-2"))
        items = {c["id"]: c for c in self.store.load_all()}
        self.assertEqual(items[first["id"]]["status"], "superseded")
        self.assertEqual(items[second["id"]]["supersedes"], first["id"])
        self.assertIn("2025년 이후 1차 자료만", items[first["id"]]["body"])  # 덮어쓰지 않음

    def test_cannot_supersede_twice(self):
        _, first = self.save()
        self.save(body="v2", supersedes=first["id"])
        status, _ = self.save(body="v3", supersedes=first["id"])
        self.assertEqual(status, 400)

    def test_requires_fields(self):
        self.assertEqual(self.save(body="  ")[0], 400)
        self.assertEqual(self.save(area="")[0], 400)

    def test_source_from_ui_cannot_be_ai_inferred(self):
        _, out = self.save(source="ai-inferred")
        meta, _ = cw.parse_file((self.store.dirs["project"] / f"{out['id']}.md")
                                .read_text(encoding="utf-8"))
        self.assertEqual(meta["source"], "user")

    # --- 상태 ---
    def test_confirm_retire_and_rules(self):
        _, d = self.save(confirm=False)
        sid = {"scope": "project", "id": d["id"]}
        self.assertEqual(self.call("POST", "/api/status", {**sid, "action": "confirm"})[1]["status"],
                         "confirmed")
        self.assertEqual(self.call("POST", "/api/status", {**sid, "action": "confirm"})[0], 400)
        self.assertEqual(self.call("POST", "/api/status", {**sid, "action": "retire"})[1]["status"],
                         "retired")
        self.assertEqual(self.call("POST", "/api/status", {**sid, "action": "retire"})[0], 400)

    def test_stale_detection(self):
        _, out = self.save()
        path = self.store.dirs["project"] / f"{out['id']}.md"
        meta, body = cw.parse_file(path.read_text(encoding="utf-8"))
        meta["review_after"] = "2000-01-01"
        path.write_text(cw.dump_file(meta, body), encoding="utf-8")
        item = [c for c in self.call("GET", "/api/state")[1]["criteria"] if c["id"] == out["id"]][0]
        self.assertTrue(item["stale"])
        self.call("POST", "/api/status", {"scope": "project", "id": out["id"], "action": "reconfirm"})
        item = [c for c in self.call("GET", "/api/state")[1]["criteria"] if c["id"] == out["id"]][0]
        self.assertFalse(item["stale"])

    # --- 대기 모드 ---
    def test_proceed_and_done(self):
        self.assertEqual(self.call("POST", "/api/proceed", {})[0], 200)
        self.assertEqual(self.server.result, "proceed")

    def test_done_reports_saved(self):
        self.save()
        self.call("POST", "/api/done", {})
        self.assertEqual(self.server.result, "saved")
        self.assertEqual(len(self.server.saved), 1)

    def test_done_without_save_is_closed(self):
        self.call("POST", "/api/done", {})
        self.assertEqual(self.server.result, "closed")

    def test_state_includes_context(self):
        state = self.call("GET", "/api/state")[1]
        self.assertEqual(state["context"], "매거진 기획")
        self.assertTrue(state["wait"])


class FormatTest(unittest.TestCase):
    def test_roundtrip_with_quotes_and_korean(self):
        meta = {"id": "a-b-1", "area": "매거진", "decision": "선별", "status": "confirmed",
                "source": "user", "evidence": '말한 대로 "1차 자료만"'}
        text = cw.dump_file(meta, "본문\n둘째 줄")
        parsed, body = cw.parse_file(text)
        self.assertEqual(parsed["evidence"], meta["evidence"])
        self.assertEqual(parsed["area"], "매거진")
        self.assertEqual(body, "본문\n둘째 줄")

    def test_parses_inline_comment_in_unquoted_value(self):
        parsed, _ = cw.parse_file("---\narea: magazine   # 설명\n---\n\n본문\n")
        self.assertEqual(parsed["area"], "magazine")


if __name__ == "__main__":
    unittest.main()
