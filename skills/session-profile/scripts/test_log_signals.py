"""log_signals 테스트. 가짜 세션과 장면만 쓴다.
실행: cd skills/session-profile/scripts && python3 -m unittest -v test_log_signals
"""
import json
import tempfile
import unittest
from pathlib import Path

import log_signals as ls

SESSIONS = [{"project": "a", "user_turns": 10}, {"project": "a", "user_turns": 20}, {"project": "b", "user_turns": 10}]


def ev(i, ab, pole):
    return {"session_idx": i, "ability": ab, "pole": pole, "quote": "q"}


class AnalyzeTest(unittest.TestCase):
    def test_counts_ratio_and_evidence_floor(self):
        events = [ev(0, "읽기", "보임")] * 3 + [ev(1, "읽기", "끊김")] * 2 + [ev(2, "이해", "보임")]
        d = ls.analyze(SESSIONS, events)
        r = d["abilities"]["읽기"]
        self.assertEqual((r["보임"]["count"], r["끊김"]["count"], r["evidence"]), (3, 2, 5))
        self.assertAlmostEqual(r["break_ratio"], 0.4)
        self.assertIsNone(d["abilities"]["이해"]["break_ratio"])  # 장면 1개: 증거 부족
        self.assertEqual(r["projects"], {"a": 5})

    def test_unknown_ability_or_pole_is_ignored(self):
        d = ls.analyze(SESSIONS, [ev(0, "검증", "보임"), ev(0, "읽기", "능동"), {"session_idx": 0, "skipped": 3}])
        self.assertTrue(all(r["evidence"] == 0 for r in d["abilities"].values()))

    def test_capped_sessions_are_left_out_of_rates(self):
        events = [ev(0, "읽기", "보임")] * 3 + [ev(1, "읽기", "보임")]
        d = ls.analyze(SESSIONS, events, cap=3)
        self.assertEqual(d["capped"], 1)
        self.assertEqual(d["turns_for_rates"], 30)
        self.assertAlmostEqual(d["abilities"]["읽기"]["보임"]["per10"], 10 * 1 / 30)

    def test_agreement_per_ability_and_pole(self):
        events = [ev(0, "읽기", "끊김"), ev(1, "읽기", "끊김")]
        second = {"sessions": [0, 1, 2], "events": [ev(0, "읽기", "끊김")]}
        ag = ls.analyze(SESSIONS, events, second)["agreement"]
        self.assertEqual(ag["sessions"], 3)
        self.assertAlmostEqual(ag["by_ability"]["읽기"]["끊김"]["agree"], 2 / 3)
        self.assertIsNone(ag["by_ability"]["이해"]["보임"]["kappa"])

    def test_cli_writes_json(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "s.jsonl").write_text("\n".join(json.dumps(s) for s in SESSIONS), encoding="utf-8")
            (d / "e.json").write_text(json.dumps([ev(0, "읽기", "보임")], ensure_ascii=False), encoding="utf-8")
            out = d / "o.json"
            self.assertEqual(ls.main(["--sessions", str(d / "s.jsonl"), "--events", str(d / "e.json"), "--out", str(out)]), 0)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["abilities"]["읽기"]["보임"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
