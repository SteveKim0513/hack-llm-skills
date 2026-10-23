"""episodes 테스트. 지어낸 Claude, Codex 기록으로 확인한다.
실행: cd skills/session-profile/scripts && python3 -m unittest -v test_episodes
"""
import json
import os
import tempfile
import unittest

import episodes as ep


def write(lines):
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    for o in lines:
        f.write(json.dumps(o, ensure_ascii=False) + "\n")
    f.close()
    return f.name


def cu(text, ts, **kw):
    return dict({"type": "user", "timestamp": ts, "sessionId": "s1", "cwd": "/x/proj",
                 "message": {"role": "user", "content": text}}, **kw)


def ca(blocks, ts):
    return {"type": "assistant", "timestamp": ts, "sessionId": "s1", "cwd": "/x/proj",
            "message": {"role": "assistant", "content": blocks}}


def tool(i, name, **inp):
    return {"type": "tool_use", "id": i, "name": name, "input": inp}


def result(i, err=False):
    return {"type": "user", "timestamp": "2026-10-01T00:00:30Z", "sessionId": "s1",
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": i, "is_error": err, "content": "x"}]}}


class ClaudeTest(unittest.TestCase):
    def setUp(self):
        self.path = write([
            cu("로그인 화면 고쳐줘", "2026-10-01T00:00:00Z"),
            ca([tool("t1", "Edit", file_path="/x/proj/a.py")], "2026-10-01T00:00:10Z"),
            result("t1", err=True),
            ca([tool("t2", "Edit", file_path="/x/proj/a.py"), {"type": "text", "text": "고쳤어요"}], "2026-10-01T00:01:00Z"),
            cu("아니 그게 아니라 버튼 색이야", "2026-10-01T00:03:00Z"),
            cu("<system-reminder>무시</system-reminder>", "2026-10-01T00:03:01Z", isMeta=True),
            ca([tool("t3", "Write", file_path="/x/proj/a.py")], "2026-10-01T00:03:20Z"),
            {"type": "user", "timestamp": "2026-10-01T00:03:30Z", "sessionId": "s1",
             "message": {"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user]"}]}},
            cu("그만하고 멈춰", "2026-10-01T00:04:00Z"),
            ca([{"type": "text", "text": "멈췄어요"}], "2026-10-01T00:04:05Z"),
            cu("고마워", "2026-10-01T02:00:00Z"),
            ca([{"type": "text", "text": "네"}], "2026-10-01T02:00:02Z"),
        ])

    def tearDown(self):
        os.unlink(self.path)

    def test_episodes_and_metrics(self):
        s = ep.claude_events(self.path, ep.Counter())
        self.assertEqual(s["project"], "proj")
        eps = ep.build_episodes(s["events"])
        # 둘째 요청 뒤에 AI 글이 없이 중단되고 셋째 요청이 왔으므로 둘째와 셋째는 한 턴으로 합쳐진다(추출기와 같은 경계)
        self.assertEqual(len(eps), 3)
        a, b, c = eps
        self.assertEqual((a["tools"], a["tool_errors"]), (2, 1))
        self.assertEqual(a["edited_files"], ["a.py"])
        self.assertTrue(a["next_correction_cue"])
        self.assertEqual(a["work_s"], 60.0)
        self.assertEqual(b["reedited_files"], ["a.py"])
        self.assertTrue(b["interrupted"])
        self.assertEqual(b["wait_before_s"], 120.0)
        self.assertIsNone(c["wait_before_s"])  # 30분 넘는 공백은 읽는 시간으로 보지 않는다
        self.assertNotIn("text", json.dumps(eps))  # 원문은 남기지 않는다
        self.assertNotIn("로그인", json.dumps(eps, ensure_ascii=False))

    def test_summary(self):
        eps = ep.build_episodes(ep.claude_events(self.path, ep.Counter())["events"])
        sm = ep.summarize(eps)
        self.assertEqual(sm["episodes"], 3)
        self.assertEqual(sm["interrupted"], 1)
        self.assertEqual(sm["reedit_episodes"], 1)
        self.assertEqual(sm["tool_error_rate"], round(1 / 3, 3))


class CodexTest(unittest.TestCase):
    def test_codex_items(self):
        path = write([
            {"type": "session_meta", "timestamp": "2026-10-01T00:00:00Z", "payload": {"id": "c1", "cwd": "/y/web"}},
            {"type": "event_msg", "timestamp": "2026-10-01T00:00:01Z", "payload": {"type": "user_message", "message": "테스트 돌려줘"}},
            {"type": "response_item", "timestamp": "2026-10-01T00:00:02Z", "payload": {"type": "custom_tool_call", "name": "exec"}},
            {"type": "event_msg", "timestamp": "2026-10-01T00:00:05Z", "payload": {"type": "item_completed", "item": {"type": "CommandExecution", "exit_code": "1"}}},
            {"type": "event_msg", "timestamp": "2026-10-01T00:00:06Z", "payload": {"type": "item_completed", "item": {"type": "FileChange", "status": "completed", "changes": {"/y/web/t.js": {}}}}},
            {"type": "response_item", "timestamp": "2026-10-01T00:00:09Z", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "실패했어요"}]}},
            {"type": "event_msg", "timestamp": "2026-10-01T00:01:00Z", "payload": {"type": "user_message", "message": "다시 해"}},
            {"type": "event_msg", "timestamp": "2026-10-01T00:01:02Z", "payload": {"type": "turn_aborted"}},
        ])
        try:
            s = ep.codex_events(path, ep.Counter())
        finally:
            os.unlink(path)
        self.assertEqual((s["tool"], s["id"], s["project"]), ("codex", "c1", "web"))
        eps = ep.build_episodes(s["events"])
        self.assertEqual(len(eps), 2)
        self.assertEqual((eps[0]["tools"], eps[0]["tool_errors"]), (2, 1))  # 모델 쪽 호출은 실행 기록이 있으면 세지 않는다
        self.assertEqual(eps[0]["edited_files"], ["t.js"])
        self.assertTrue(eps[0]["next_correction_cue"])
        self.assertTrue(eps[1]["interrupted"])


class CueTest(unittest.TestCase):
    def test_cue_is_narrow(self):
        hit = lambda t: bool(ep.CUE_START.search(t) or ep.CUE_ANY.search(t))
        self.assertTrue(hit("다시 정리해봐"))
        self.assertTrue(hit("내 말은 그게 아니고"))
        self.assertFalse(hit("다시 보내기 버튼도 넣어"))
        self.assertFalse(hit("좋아 진행해"))

    def test_repeat(self):
        self.assertGreaterEqual(ep.similarity("로그인 버튼 색 바꿔줘", "로그인 버튼 색 바꿔줘 제발"), ep.REPEAT_SIM)
        self.assertLess(ep.similarity("로그인 버튼 색 바꿔줘", "배포해"), ep.REPEAT_SIM)


if __name__ == "__main__":
    unittest.main()
