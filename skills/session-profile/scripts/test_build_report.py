"""build_report 테스트. 가짜 세션과 장면만 쓴다.
실행: cd skills/session-profile/scripts && python3 -m unittest -v test_build_report
"""
import json
import tempfile
import unittest
from pathlib import Path

import build_report as br


def sess(project, n_user, task=""):
    s = {"project": project, "user_turns": n_user}
    if task:
        s["task_type"] = task
    return s


def ev(i, axis, pole="능동", eid=None, position=None):
    e = {"session_idx": i, "axis": axis, "pole": pole, "eid": eid if eid is not None else i * 100 + len(axis)}
    if position:
        e["position"] = position
    return e


SESSIONS = [sess("a", 5, "코딩"), sess("a", 12, "코딩"), sess("b", 40, "기획"), sess("b", 4)]


class AnalyzeTest(unittest.TestCase):
    def test_presence_counts_sessions_not_events(self):
        events = [ev(0, "검증"), ev(0, "검증"), ev(0, "검증"), ev(1, "검증"), ev(2, "구조")]
        d = br.analyze(SESSIONS, events)
        self.assertEqual(d["presence"]["검증"], 2)
        self.assertEqual(d["events_by_axis"]["검증"], 4)
        self.assertEqual(d["presence"]["구조"], 1)
        self.assertEqual(d["presence"]["메타인지"], 0)

    def test_old_acceptance_events_are_excluded_not_counted(self):
        d = br.analyze(SESSIONS, [ev(0, "방향 주도", pole="수용"), ev(0, "검증")])
        self.assertEqual(d["excluded"], 1)
        self.assertEqual(d["presence"]["방향 주도"], 0)

    def test_length_bins_and_groups(self):
        d = br.analyze(SESSIONS, [ev(2, "구조")])
        by_len = {label: n for label, _, n in d["by_length"]}
        self.assertEqual(by_len, {"10 미만": 2, "10~29": 1, "30 이상": 1})
        self.assertEqual({t for t, _, _ in d["by_task"]}, {"코딩", "기획"})
        self.assertEqual(sum(n for _, _, n in d["by_project"]), 4)

    def test_cap_marks_sessions(self):
        events = [ev(0, "검증", eid=k) for k in range(3)]
        d = br.analyze(SESSIONS, events, cap=3)
        self.assertEqual(d["capped"], 1)

    def test_agreement_with_second_classifier(self):
        events = [ev(0, "검증"), ev(1, "검증"), ev(2, "구조")]
        second = {"sessions": [0, 1, 2, 3], "events": [ev(0, "검증"), ev(2, "검증")]}
        ag = br.analyze(SESSIONS, events, second)["agreement"]
        self.assertEqual(ag["sessions"], 4)
        self.assertAlmostEqual(ag["by_axis"]["검증"]["agree"], 0.5)   # 0 같음, 1 다름, 2 다름, 3 같음
        self.assertAlmostEqual(ag["by_axis"]["구조"]["agree"], 0.75)
        self.assertIsNone(ag["by_axis"]["메타인지"]["kappa"])          # 둘 다 전부 없음: 기대 일치 1
        self.assertIsNone(br.analyze(SESSIONS, events)["agreement"])

    def test_kappa_perfect_and_chance(self):
        self.assertEqual(br.kappa([(True, True), (False, False)]), (1.0, 1.0))
        po, k = br.kappa([(True, False), (False, True)])
        self.assertEqual(po, 0.0)
        self.assertLess(k, 0)


class RateTest(unittest.TestCase):
    def test_rates_pool_sessions_and_skip_capped_ones(self):
        # 세션 0(발화 5)은 상한에 걸려 빠지고, 1(12)·2(40)·3(4) = 발화 56개
        events = [ev(0, "검증", eid=k) for k in range(3)] + [ev(1, "검증", eid=10), ev(2, "검증", eid=11)]
        r = br.analyze(SESSIONS, events, cap=3)["rates"]
        self.assertEqual((r["sessions"], r["turns"]), (3, 56))
        self.assertAlmostEqual(r["all"]["검증"], 10 * 2 / 56)

    def test_response_only_rate_and_front_share(self):
        events = [ev(1, "구조", eid=1, position="시작"), ev(1, "구조", eid=2, position="응답"),
                  ev(2, "구조", eid=3, position="새 방향")]
        r = br.analyze(SESSIONS, events)["rates"]
        self.assertAlmostEqual(r["front_share"]["구조"], 2 / 3)
        self.assertAlmostEqual(r["response"]["구조"], 10 * 1 / 61)
        text = br.render(br.analyze(SESSIONS, events))
        self.assertIn("**구조**: 장면의 67%가 대화 시작이나 새 방향에서", text)

    def test_per_session_distribution_needs_enough_long_sessions(self):
        r = br.analyze(SESSIONS, [ev(2, "검증")])["rates"]
        self.assertEqual(r["per_session_n"], 2)  # 발화 10개 이상은 12, 40뿐
        text = br.render(br.analyze(SESSIONS, [ev(2, "검증")]))
        self.assertIn("세션 부족", text)

    def test_no_positions_means_no_position_columns(self):
        r = br.analyze(SESSIONS, [ev(1, "검증")])["rates"]
        self.assertIsNone(r["response"])
        self.assertIsNone(r["front_share"])


class RenderTest(unittest.TestCase):
    def test_report_has_caveats_and_no_score(self):
        text = br.render(br.analyze(SESSIONS, [ev(0, "검증")]))
        self.assertIn("참고용", text)
        self.assertIn("수준이 낮다는 뜻이 아닙니다", text)
        self.assertNotIn("점수:", text)
        self.assertIn("1/4 (25%)", text)

    def test_saturated_axes_get_a_warning(self):
        events = [ev(i, "검증") for i in range(4)]
        text = br.render(br.analyze(SESSIONS, events))
        self.assertIn("검증: 세션 85% 이상에서 나와", text)
        self.assertNotIn("구조: 세션 85%", text)

    def test_cli_reads_json_and_jsonl_and_skips_skipped_lines(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "s.jsonl").write_text("\n".join(json.dumps(s) for s in SESSIONS), encoding="utf-8")
            (d / "e.jsonl").write_text(json.dumps(ev(0, "검증")) + "\n" + json.dumps({"session_idx": 0, "skipped": 3}) + "\n",
                                       encoding="utf-8")
            out = d / "r.md"
            jo = d / "p.json"
            self.assertEqual(br.main(["--sessions", str(d / "s.jsonl"), "--events", str(d / "e.jsonl"), "--out", str(out),
                                      "--json-out", str(jo)]), 0)
            self.assertIn("분석한 세션 4개", out.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(jo.read_text(encoding="utf-8"))["sessions"], 4)


if __name__ == "__main__":
    unittest.main()
