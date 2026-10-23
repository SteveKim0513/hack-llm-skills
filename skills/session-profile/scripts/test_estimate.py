"""estimate 테스트. 지어낸 기회 기록과 에피소드만 쓴다.
실행: cd skills/session-profile/scripts && python3 -m unittest -v test_estimate
"""
import json
import tempfile
import unittest
from pathlib import Path

import estimate as es


def ep(t, work=60, wait=60, **kw):
    return dict({"user_turn": t, "work_s": work, "wait_before_s": wait, "reedited_files": [], "interrupted": False,
                 "next_correction_cue": False, "next_repeat": False}, **kw)


def op(s, t, ab, pole, resolved=None):
    d = {"session_idx": s, "user_turn": t, "ability": ab, "pole": pole}
    if resolved is not None:
        d["resolved_turn"] = resolved
    return d


EPISODES = [
    {"session_idx": 0, "episodes": [ep(t) for t in range(10)]},
    {"session_idx": 1, "episodes": [ep(t, reedited_files=["a.py"] if t in (6, 7) else []) for t in range(10)]},
]


class EstimateTest(unittest.TestCase):
    def test_break_cost_uses_resolved_turn(self):
        events = [op(0, 2, "표현 정확성", "끊김", resolved=4), op(1, 3, "표현 정확성", "끊김")]
        events += [op(0, t, "표현 정확성", "없음") for t in (5, 6, 7)]
        d = es.estimate(events, None, EPISODES, boot=50)
        c = d["abilities"]["표현 정확성"]["cost"]
        # 첫 끊김: 요청 2, 3이 버려짐(AI 작업 1분씩) + 3, 4 앞 읽는 시간 1분씩 = 2개 4분.
        # 둘째: resolved 없음 → 요청 3 하나(최소 추정): 작업 1분 + 요청 4 앞 읽는 시간 1분 = 1개 2분
        self.assertEqual(d["requests"], 20)
        self.assertAlmostEqual(c["rework_per100"], 100 * 3 / 20)
        self.assertAlmostEqual(c["minutes_per100"], 100 * 6 / 20)
        self.assertEqual(c["minimum_estimate"], 1)
        self.assertEqual(d["costliest"]["ability"], "표현 정확성")
        self.assertEqual(d["abilities"]["표현 정확성"]["score"]["point"], 60)

    def test_critic_removes_cost_and_keeps_opportunity(self):
        events = [op(0, 2, "읽기", "끊김", resolved=4), op(0, 5, "읽기", "끊김", resolved=6)]
        critic = [{"session_idx": 0, "user_turn": 2, "ability": "읽기", "cause": "AI"},
                  {"session_idx": 0, "user_turn": 5, "ability": "읽기", "cause": "사용자"}]
        v = es.estimate(events, critic, EPISODES, boot=20)["abilities"]["읽기"]
        self.assertEqual((v["opportunities"], v["broken"]), (2, 1))
        self.assertAlmostEqual(v["cost"]["minutes_per100"], 100 * 2 / 20)  # 요청 5 작업 1분 + 요청 6 앞 읽는 시간 1분

    def test_no_costliest_with_fewer_than_two_breaks(self):
        d = es.estimate([op(0, 2, "이해", "끊김", resolved=3)], None, EPISODES, boot=20)
        self.assertIsNone(d["costliest"])

    def test_score_interval_and_more_needed(self):
        d = es.estimate([op(0, t, "검증", "없음") for t in range(5)] + [op(0, 5, "검증", "끊김")], None, EPISODES, boot=10)
        sc = d["abilities"]["검증"]["score"]
        self.assertLessEqual(sc["low"], sc["point"])
        self.assertGreaterEqual(sc["high"], sc["point"])
        self.assertIsNotNone(sc["more_needed"])  # 기회 6개로는 구간이 넓다
        self.assertIsNone(d["abilities"]["이해"]["score"])  # 기회 없음

    def test_effect_of_shown(self):
        events = [op(1, t, "목표 명확성", "보임") for t in range(0, 5)]   # 다음 3개 안에 다시 고침(6, 7)이 있는 건 4, 5뿐
        events += [op(1, t, "목표 명확성", "없음") for t in range(5, 10)]  # 5, 6, 7은 걸림
        eff = es.estimate(events, None, EPISODES, boot=30)["abilities"]["목표 명확성"]["effect_of_shown"]
        self.assertEqual((eff["after_shown"], eff["after_none"]), (20, 60))
        self.assertEqual(eff["diff"], -40)

    def test_input_is_not_modified_and_cli(self):
        events = [op(0, 2, "읽기", "끊김", resolved=3)]
        es.estimate(events, None, EPISODES, boot=5)
        self.assertNotIn("_rework", events[0])
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "e.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8")
            (d / "p.jsonl").write_text("\n".join(json.dumps(r) for r in EPISODES), encoding="utf-8")
            out = d / "o.json"
            self.assertEqual(es.main(["--events", str(d / "e.jsonl"), "--episodes", str(d / "p.jsonl"), "--out", str(out)]), 0)
            self.assertIn("abilities", json.loads(out.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
