"""report 테스트. 지어낸 에피소드와 어긋남만 쓴다.
실행: cd skills/session-profile/scripts && python3 -m unittest -v test_report
"""
import json
import tempfile
import unittest
from pathlib import Path

import report as rp

EPISODES = [{"session_idx": s, "episodes": [{"user_turn": t, "work_s": 60, "wait_before_s": 60, "start": "2026-10-0%dT00:00:00" % (s + 1)}
                                            for t in range(10)]} for s in (0, 1)]


def br(s, t, habit, resolved=None):
    return {"session_idx": s, "user_turn": t, "habit": habit, "quote": "q%d" % t, "what_happened": "w", "resolved_turn": resolved}


class ReportTest(unittest.TestCase):
    def test_cost_and_costliest(self):
        breaks = [br(0, 2, "읽기", 4), br(1, 3, "읽기"), br(0, 7, "검증", 8)]
        d = rp.compute(breaks, EPISODES, boot=50)
        # 읽기: 요청 2, 3 버려짐(작업 1분씩) + 3, 4 앞 읽는 시간 = 2개 4분, 둘째는 최소 추정 1개 2분 → 요청 20개
        self.assertAlmostEqual(d["habits"]["읽기"]["rework_per100"], 100 * 3 / 20)
        self.assertAlmostEqual(d["habits"]["읽기"]["minutes_per100"], 100 * 6 / 20)
        self.assertEqual(d["costliest"], "읽기")   # 검증은 어긋남 1개라 고르지 않는다
        self.assertEqual(d["period"], ("2026-10-01", "2026-10-02"))

    def test_no_costliest_and_unknown_habit(self):
        d = rp.compute([br(0, 2, "읽기"), br(0, 3, "창의성"), br(5, 1, "읽기")], EPISODES, boot=10)
        self.assertIsNone(d["costliest"])
        self.assertEqual(d["habits"]["읽기"]["breaks"], 1)  # 모르는 습관과 없는 세션은 뺀다
        self.assertIn("아직 없어요", rp.render(d))

    def test_render_escapes_and_has_practice(self):
        d = rp.compute([br(0, 2, "읽기"), dict(br(1, 2, "읽기"), quote="<script>x</script>")], EPISODES, boot=10)
        out = rp.render(d)
        self.assertNotIn("<script>x", out)
        self.assertIn(rp.HABITS["읽기"], out.replace("&quot;", '"'))
        self.assertIn("가장 비싼 습관은 <b>읽기</b>", out)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "b.jsonl").write_text(json.dumps(br(0, 2, "읽기"), ensure_ascii=False), encoding="utf-8")
            (d / "e.jsonl").write_text("\n".join(json.dumps(r) for r in EPISODES), encoding="utf-8")
            self.assertEqual(rp.main(["--breaks", str(d / "b.jsonl"), "--episodes", str(d / "e.jsonl"), "--out", str(d / "o.html")]), 0)
            self.assertTrue((d / "o.html").read_text(encoding="utf-8").startswith("<!doctype html>"))


if __name__ == "__main__":
    unittest.main()
