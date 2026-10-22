"""build_report 테스트. 가짜 세션과 장면만 쓴다.
실행: cd skills/criteria-gap-audit/scripts && python3 -m unittest -v test_build_report
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


def ev(i, axis, pole="능동", eid=None):
    return {"session_idx": i, "axis": axis, "pole": pole, "eid": eid if eid is not None else i * 100 + len(axis)}


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

    def test_label_accuracy_by_axis_and_pole(self):
        events = [ev(0, "검증", eid=1), ev(1, "구조", "수용", eid=2)]
        labels = [{"eid": 1, "ai_label": "검증/능동", "verdict": "맞음"},
                  {"eid": 2, "ai_label": "구조/수용", "verdict": "아님"},
                  {"eid": 3, "ai_label": "검증/능동", "verdict": ""}]
        d = br.analyze(SESSIONS, events, labels)
        self.assertEqual(d["labels"][("검증", "능동")], {"맞음": 1})
        self.assertEqual(d["labels"][("구조", "수용")], {"아님": 1})
        self.assertEqual(len(d["labels"]), 2)


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
            self.assertEqual(br.main(["--sessions", str(d / "s.jsonl"), "--events", str(d / "e.jsonl"), "--out", str(out)]), 0)
            self.assertIn("분석한 세션 4개", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
