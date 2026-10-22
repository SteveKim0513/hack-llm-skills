"""extract_sessions 테스트. 가짜 기록만 쓴다.
실행: cd skills/criteria-gap-audit/scripts && python3 -m unittest -v test_extract_sessions
"""
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import extract_sessions as ex


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def c_user(text, **kw):
    row = {"type": "user", "sessionId": "s1", "cwd": "/home/a/proj", "timestamp": "2026-10-01T00:00:00Z",
           "message": {"role": "user", "content": text}}
    row.update(kw)
    return row


def c_asst(text):
    return {"type": "assistant", "sessionId": "s1", "cwd": "/home/a/proj", "timestamp": "2026-10-01T00:00:01Z",
            "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "비공개"},
                                                         {"type": "text", "text": text}]}}


class CleanTextTest(unittest.TestCase):
    def test_injected_tags_dropped(self):
        for t in ("<task-notification>x</task-notification>", "<command-name>/foo</command-name>",
                  "<local-command-stdout>ok</local-command-stdout>", "[Request interrupted by user]"):
            self.assertEqual(ex.clean_user_text(t), "", t)

    def test_context_blocks_stripped_but_typed_text_kept(self):
        t = "<ide_selection>선택 코드</ide_selection>\n이거 정리해줘"
        self.assertEqual(ex.clean_user_text(t), "이거 정리해줘")

    def test_pasted_content_shortened_with_or_without_close_tag(self):
        long = "가" * 1000
        out = ex.clean_user_text('<pasted_content id="ab">\n%s\n</pasted_content id="ab">\n\n요약해줘' % long)
        self.assertIn("요약해줘", out)
        self.assertIn("[붙여넣은 내용]", out)
        self.assertLess(len(out), 450)
        self.assertEqual(ex.clean_user_text('<pasted_content id="ab">\n짧은 글'), "[붙여넣은 내용] 짧은 글")

    def test_project_label_uses_folder_name_only(self):
        self.assertEqual(ex.project_label("/Users/x/Projects/app"), "app")
        self.assertEqual(ex.project_label("/Users/x/Projects/app/.claude/worktrees/feat-1"), "app")
        self.assertEqual(ex.project_label(None), "(unknown)")


class ClaudeTest(unittest.TestCase):
    def test_only_human_turns_and_text_blocks_survive(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj" / "s1.jsonl"
            write_jsonl(p, [
                c_user("자료 좀 걸러줘"),
                c_asst("이렇게 걸렀어요"),
                c_user("<system-reminder>x</system-reminder>", isMeta=True),
                c_user("작업 끝남", origin={"kind": "task-notification"}),
                c_user("서브에이전트 말", isSidechain=True),
                {"type": "user", "sessionId": "s1", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "t", "content": "결과"}]}},
                c_user("좋아, 다음"),
            ])
            s = ex.parse_claude(str(p), 1500, Counter())
        self.assertEqual([(t["role"], t["text"]) for t in s["turns"]],
                         [("user", "자료 좀 걸러줘"), ("assistant", "이렇게 걸렀어요"), ("user", "좋아, 다음")])
        self.assertEqual(s["project"], "proj")
        self.assertNotIn("비공개", json.dumps(s, ensure_ascii=False))

    def test_subagent_folder_is_not_listed(self):
        with tempfile.TemporaryDirectory() as d:
            write_jsonl(Path(d) / "proj" / "s1.jsonl", [c_user("hi")])
            write_jsonl(Path(d) / "proj" / "s1" / "subagents" / "agent-1.jsonl", [c_user("hi")])
            files = ex.claude_files(d)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith("s1.jsonl"))


def cx_meta(sid, **kw):
    p = {"id": sid, "cwd": "/home/a/proj", "timestamp": "2026-10-02T00:00:00Z", "source": "vscode"}
    p.update(kw)
    return {"type": "session_meta", "timestamp": p["timestamp"], "payload": p}


def cx_event_user(text):
    return {"type": "event_msg", "timestamp": "t", "payload": {"type": "user_message", "message": text}}


def cx_item_user(text):
    return {"type": "event_msg", "timestamp": "t", "payload": {"type": "item_completed", "item": {
        "type": "UserMessage", "content": [{"type": "text", "text": text}]}}}


def cx_model_user(text):
    return {"type": "response_item", "timestamp": "t", "payload": {"type": "message", "role": "user",
            "content": [{"type": "input_text", "text": text}]}}


def cx_asst(text):
    return {"type": "response_item", "timestamp": "t", "payload": {"type": "message", "role": "assistant",
            "content": [{"type": "output_text", "text": text}]}}


class CodexTest(unittest.TestCase):
    def test_typed_events_win_over_model_input(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.jsonl"
            write_jsonl(p, [
                cx_meta("c1"),
                cx_model_user("# AGENTS.md instructions for /x"),
                cx_model_user("직접 쓴 요청"), cx_event_user("직접 쓴 요청"),
                cx_asst("답"),
                cx_model_user("<task-notification>끝</task-notification>"),
            ])
            s = ex.parse_codex(str(p), 1500, Counter())
        self.assertEqual([(t["role"], t["text"]) for t in s["turns"]], [("user", "직접 쓴 요청"), ("assistant", "답")])

    def test_item_completed_user_message_is_used(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.jsonl"
            write_jsonl(p, [cx_meta("c1"), cx_item_user("요청"), cx_model_user("요청"), cx_asst("답")])
            s = ex.parse_codex(str(p), 1500, Counter())
        self.assertEqual([t["role"] for t in s["turns"]], ["user", "assistant"])

    def test_old_format_falls_back_to_model_input(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.jsonl"
            write_jsonl(p, [cx_meta("c1"), cx_model_user("<environment_context>x</environment_context>"),
                            cx_model_user("옛 형식 요청"), cx_asst("답")])
            s = ex.parse_codex(str(p), 1500, Counter())
        self.assertEqual(s["turns"][0]["text"], "옛 형식 요청")

    def test_subagent_flag(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.jsonl"
            write_jsonl(p, [cx_meta("c1", source={"subagent": {"other": "guardian"}}), cx_event_user("x")])
            self.assertTrue(ex.parse_codex(str(p), 1500, Counter())["_subagent"])


class CollectTest(unittest.TestCase):
    def args(self, claude, codex, **kw):
        a = ex.argparse.Namespace(claude_dir=claude, codex_dir=codex, tools="claude,codex", since=None,
                                  min_user_turns=3, max_chars=1500)
        for k, v in kw.items():
            setattr(a, k, v)
        return a

    def test_imported_codex_copy_and_short_sessions_are_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            three = [c_user("하나"), c_asst("a"), c_user("둘"), c_asst("b"), c_user("셋")]
            write_jsonl(root / "claude" / "proj" / "s1.jsonl", three)
            write_jsonl(root / "claude" / "proj" / "short.jsonl", [c_user("하나")])
            msgs = [cx_event_user("a"), cx_asst("1"), cx_event_user("b"), cx_asst("2"), cx_event_user("c")]
            write_jsonl(root / "codex" / "sessions" / "2026" / "10" / "02" / "native.jsonl", [cx_meta("native")] + msgs)
            write_jsonl(root / "codex" / "sessions" / "2026" / "10" / "02" / "copy.jsonl", [cx_meta("copy")] + msgs)
            (root / "codex" / "external_agent_session_imports.json").write_text(
                json.dumps({"records": [{"imported_thread_id": "copy"}]}), encoding="utf-8")
            stats = Counter()
            kept = ex.collect(self.args(str(root / "claude"), str(root / "codex")), stats)
        self.assertEqual(sorted((s["tool"], s["id"]) for s in kept), [("claude", "s1"), ("codex", "native")])
        self.assertEqual(stats["제외: 다른 도구에서 가져온 사본"], 1)

    def test_codex_imports_kept_when_claude_not_scanned(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            msgs = [cx_event_user("a"), cx_asst("1"), cx_event_user("b"), cx_asst("2"), cx_event_user("c")]
            write_jsonl(root / "codex" / "sessions" / "x.jsonl", [cx_meta("copy")] + msgs)
            (root / "codex" / "external_agent_session_imports.json").write_text(
                json.dumps({"records": [{"imported_thread_id": "copy"}]}), encoding="utf-8")
            kept = ex.collect(self.args(str(root / "claude"), str(root / "codex"), tools="codex"), Counter())
        self.assertEqual(len(kept), 1)


class DedupeTest(unittest.TestCase):
    def test_same_session_id_in_two_files_keeps_the_longer(self):
        short = {"tool": "claude", "id": "x", "turns": [1, 2]}
        long = {"tool": "claude", "id": "x", "turns": [1, 2, 3]}
        other = {"tool": "codex", "id": "x", "turns": [1]}
        stats = Counter()
        out = ex.dedupe([short, long, other], stats)
        self.assertEqual(sorted(len(s["turns"]) for s in out), [1, 3])
        self.assertEqual(stats["제외: 같은 세션 id 중복"], 1)


class SampleTest(unittest.TestCase):
    def sessions(self):
        out = [{"tool": "claude", "project": "big", "id": "b%d" % i} for i in range(50)]
        out += [{"tool": "claude", "project": "small-%d" % i, "id": "s%d" % i} for i in range(4)]
        out += [{"tool": "codex", "project": "big", "id": "c0"}]
        return out

    def test_every_group_shows_up_before_a_big_group_gets_a_second_turn(self):
        picked = ex.sample(self.sessions(), 6, seed=1)
        groups = Counter((s["tool"], s["project"]) for s in picked)
        self.assertEqual(len(groups), 6)
        self.assertTrue(all(v == 1 for v in groups.values()))

    def test_same_seed_same_result_and_zero_means_all(self):
        a = [s["id"] for s in ex.sample(self.sessions(), 10, seed=3)]
        b = [s["id"] for s in ex.sample(self.sessions(), 10, seed=3)]
        self.assertEqual(a, b)
        self.assertEqual(len(ex.sample(self.sessions(), 0, seed=3)), 55)


if __name__ == "__main__":
    unittest.main()
