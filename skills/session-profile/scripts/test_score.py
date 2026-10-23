"""quiz, score 테스트. 지어낸 세션만 쓴다.
실행: cd skills/session-profile/scripts && python3 -m unittest -v test_score
"""
import json
import tempfile
import unittest
from pathlib import Path

import quiz
import score

LONG = "결정 내용 " * 60


def session(n, project="p"):
    turns = []
    for i in range(n):
        turns.append({"role": "user", "text": "요청%d 내용" % i})
        turns.append({"role": "assistant", "text": LONG if i % 2 == 0 else "짧음"})
    return {"project": project, "turns": turns}


SESSIONS = [session(6, "a"), session(6, "b")]


def t(s, u, typ, **sc):
    return {"session_idx": s, "user_turn": u, "type": typ, "scores": sc, "quote": "요청%d" % u, "reason": "r%d" % u}


class QuizTest(unittest.TestCase):
    def test_pick_needs_long_ai_reply_before(self):
        turns = [t(0, 1, "진행"), t(0, 2, "진행"), t(1, 3, "진행"), t(1, 4, "지시")]
        d = quiz.pick(SESSIONS, turns, n=10)
        # 요청 u의 바로 앞 AI 답변은 u-1번째 답변. 짝수 번째 답변이 길다 → u=1, 3만 고른다
        self.assertEqual(sorted((e["session_idx"], e["user_turn"]) for e in d["events"]), [(0, 1), (1, 3)])
        self.assertEqual(len(d["recheck_sessions"]), 2)

    def test_server_hides_keys_and_locks_after_submit(self):
        import http.client, threading, os
        from http.server import HTTPServer
        q = [{"id": "q1", "kind": "동작", "question": "지금 X는?", "answer_key": "SECRET-a"},
             {"id": "r1", "kind": "읽기", "question": "상황", "passage": "지문", "fields": ["답장", "전달"], "keys": {"detail": "SECRET-b"}}]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "a.json")
            srv = HTTPServer(("127.0.0.1", 0), None)
            port = srv.server_address[1]
            srv.RequestHandlerClass = quiz.handler(q, path, port)
            threading.Thread(target=srv.serve_forever, daemon=True).start()

            def call(method, url, body=None, host=None):
                c = http.client.HTTPConnection("127.0.0.1", port)
                h = {"Host": host or "127.0.0.1:%d" % port, "Content-Type": "application/json"}
                c.request(method, url, json.dumps(body) if body is not None else None, h)
                r = c.getresponse()
                return r.status, r.read().decode("utf-8")

            code, text = call("GET", "/api/items")
            self.assertEqual(code, 200)
            self.assertNotIn("SECRET", text)
            self.assertNotIn("동작", text)  # 무엇을 재는지 내보내지 않는다
            self.assertEqual(json.loads(text)["items"][1]["reading"], True)
            self.assertEqual(call("GET", "/api/items", host="evil.example")[0], 403)
            call("POST", "/api/answer", {"id": "q1", "mode": "맡김"})
            call("POST", "/api/answer", {"id": "r1", "mode": "맡김"})
            self.assertEqual(call("POST", "/api/submit", {})[0], 400)   # 읽기 과제는 맡김을 고를 수 없다
            call("POST", "/api/answer", {"id": "r1", "mode": "답", "texts": ["a", "b", "넘침"], "read": True})
            self.assertEqual(call("POST", "/api/submit", {})[0], 200)
            saved = json.load(open(path, encoding="utf-8"))
            self.assertEqual(saved["items"]["r1"]["texts"], ["a", "b"])
            self.assertEqual(call("POST", "/api/answer", {"id": "q1", "mode": "모르겠음"})[0], 409)
            srv.shutdown()

    def test_page_script_parses(self):
        import re, shutil, subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("node 없음")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "page.js"
            p.write_text(re.search(r"<script>(.*)</script>", quiz.PAGE, re.S).group(1), encoding="utf-8")
            self.assertEqual(subprocess.run([node, "--check", str(p)], capture_output=True).returncode, 0)


class ScoreTest(unittest.TestCase):
    def test_shares_criteria_and_overall(self):
        turns = [t(0, i, "지시", 논리력=3, 표현=2) for i in range(4)] + [t(1, 0, "질문", 이해력=3, 문해력=3),
                 t(1, 1, "진행"), t(1, 2, "진행"), t(1, 3, "기타")]
        graded = [{"id": "q1", "kind": "동작", "score": 0}, {"id": "q2", "kind": "공백", "score": 3},
                  {"id": "q3", "kind": "동작", "score": None}]
        d = score.compute(SESSIONS, turns, graded=graded)
        self.assertEqual(d["counts"], {"지시": 4, "질문": 1, "진행": 2})
        self.assertEqual(d["criteria"]["논리력"]["log"]["n"], 4)       # 기록과 직접 확인은 섞지 않는다
        self.assertEqual(d["criteria"]["논리력"]["test"]["n"], 1)
        self.assertIsNone(d["criteria"]["논리력"]["from"])  # 기록 4개(5개 미만), 직접 확인 1개(2개 미만): 대표 점수 없음
        self.assertEqual(d["criteria"]["이해력"]["test"]["score"], 0)  # 동작 질문 하나(0점)
        self.assertEqual(d["quality"]["진행"]["score"], 50)        # 맡김(None)은 뺀다
        # 종합 = (4/7 × 83 + 1/7 × 100 + 2/7 × 50)
        self.assertEqual(d["overall"], round((4 * 83 + 1 * 100 + 2 * 50) / 7))

    def test_reading_task_feeds_literacy_only(self):
        turns = [t(0, 0, "지시", 문해력=3), t(0, 1, "진행")]
        graded = [{"id": "r1", "kind": "읽기", "score": 1.5}, {"id": "q1", "kind": "동작", "score": 3}]
        d = score.compute(SESSIONS, turns, graded=graded)
        self.assertEqual((d["criteria"]["문해력"]["log"]["n"], d["criteria"]["문해력"]["test"]["n"]), (1, 1))
        self.assertEqual(d["quality"]["진행"]["n"], 1)
        self.assertEqual(d["quiz"], {"answered": 1, "reading": 1})

    def test_direct_check_is_not_drowned_by_many_easy_requests(self):
        # 기록 100개가 3점이어도 직접 확인 두 개가 0점이면 그 기준의 대표 점수는 0이고 가장 낮은 기준이 된다
        turns = [t(i % 2, i % 6, "지시", 논리력=3, 표현=3) for i in range(12)]
        turns = [dict(x, user_turn=j % 6, session_idx=j // 6) for j, x in enumerate(turns)]
        graded = [{"id": "q1", "kind": "공백", "score": 0, "session_idx": 0}, {"id": "q2", "kind": "공백", "score": 0, "session_idx": 1}]
        d = score.compute(SESSIONS, turns, graded=graded)
        self.assertEqual((d["criteria"]["논리력"]["from"], d["criteria"]["논리력"]["main"]["score"]), ("test", 0))
        self.assertEqual(d["weakest"], "논리력")
        self.assertIn("판단 없이 AI에 맡겼고", score.render(d))

    def test_interval_counts_sessions_not_requests(self):
        # 세션마다 점수가 몰려 있으면 요청이 많아도 구간이 넓어야 한다
        pairs = [(0, 3)] * 50 + [(1, 1)] * 50 + [(2, 2)] * 50
        st = score.stat(pairs)
        self.assertEqual((st["score"], st["sessions"], st["n"]), (67, 3, 150))
        self.assertGreaterEqual(st["high"] - st["low"], 30)
        self.assertIsNone(score.stat([(0, 3), (0, 2)])["low"])  # 세션 하나면 구간을 내지 않는다

    def test_bad_quotes_and_duplicates_dropped(self):
        turns = [t(0, 0, "지시", 표현=3), dict(t(0, 1, "지시", 표현=0), quote="없는 말"), t(0, 0, "지시", 표현=0), t(9, 0, "지시")]
        d = score.compute(SESSIONS, turns)
        self.assertEqual((d["dropped"], d["counts"]["지시"], d["criteria"]["표현"]["log"]["score"]), (2, 1, 100))
        self.assertEqual(d["overall_missing"], [])

    def test_weakest_needs_enough_evidence_and_is_flagged_when_unclear(self):
        turns = [t(0, i, "지시", 논리력=3, 표현=1 + (i % 2)) for i in range(6)] + [t(1, i, "지시", 논리력=2, 표현=1) for i in range(6)]
        d = score.compute(SESSIONS, turns)
        self.assertEqual(d["weakest"], "표현")
        self.assertTrue(d["weakest_clear"])
        self.assertIn(score.PRACTICE["표현"].replace('"', "&quot;"), score.render(d))

    def test_agreement(self):
        a = [t(0, i, "지시", 표현=3) for i in range(4)]
        b = [t(0, 0, "지시", 표현=1), t(0, 1, "질문"), t(0, 2, "지시", 표현=3), t(0, 3, "지시", 표현=3)]
        ag = score.compute(SESSIONS, a, b)["agreement"]
        self.assertEqual((ag["turns"], ag["type_agree"]), (4, 0.75))
        self.assertAlmostEqual(ag["score_diff"], 2 / 3, places=2)

    def test_render_escapes_and_cli(self):
        turns = [dict(t(0, i, "지시", 표현=0), reason="<script>x</script>") for i in range(5)]
        self.assertNotIn("<script>x", score.render(score.compute(SESSIONS, turns)))
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "s.jsonl").write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in SESSIONS), encoding="utf-8")
            (d / "t.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in turns), encoding="utf-8")
            self.assertEqual(score.main(["--sessions", str(d / "s.jsonl"), "--turns", str(d / "t.jsonl"), "--out", str(d / "o.html")]), 0)
            self.assertTrue((d / "o.html").read_text(encoding="utf-8").startswith("<!doctype html>"))


if __name__ == "__main__":
    unittest.main()
