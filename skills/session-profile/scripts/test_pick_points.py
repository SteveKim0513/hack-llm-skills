"""pick_points 테스트. 가짜 세션만 쓴다.
실행: cd skills/session-profile/scripts && python3 -m unittest -v test_pick_points
"""
import unittest

import pick_points as pp

LONG = "추천 방식은 A예요. 대신 B도 있어요. 어느 쪽으로 할까요?\n1) A\n2) B\n" + "설명 " * 300


def sess(sid, project, turns):
    return {"id": sid, "project": project, "started_at": "2026-10-10T00:00:00Z",
            "turns": [{"role": r, "text": t} for r, t in turns]}


def good(sid, project):
    return sess(sid, project, [("user", "기획해줘"), ("assistant", LONG), ("user", "진행해"),
                               ("assistant", "했어요"), ("user", "좋아"), ("assistant", "끝")])


class CandidateTest(unittest.TestCase):
    def test_short_approval_after_long_decision_reply(self):
        c = pp.candidates([good("s1", "p")])
        self.assertEqual([(x["si"], x["ti"]) for x in c], [(0, 2)])

    def test_questions_long_replies_and_pastes_are_not_approvals(self):
        for reply in ("진행해?", "이건 그냥 승인이 아니라 길게 이유를 설명하는 답장입니다 정말로", "[붙여넣은 내용] x"):
            s = sess("s", "p", [("user", "a"), ("assistant", LONG), ("user", reply), ("assistant", "x"), ("user", "y"), ("assistant", "z")])
            self.assertEqual(pp.candidates([s]), [], reply)

    def test_short_or_cueless_ai_reply_and_no_aftermath_are_skipped(self):
        short = sess("s", "p", [("user", "a"), ("assistant", "추천 대신"), ("user", "네"), ("assistant", "x"), ("user", "y"), ("assistant", "z")])
        cueless = sess("s", "p", [("user", "a"), ("assistant", "설명 " * 400), ("user", "네"), ("assistant", "x"), ("user", "y"), ("assistant", "z")])
        no_after = sess("s", "p", [("user", "a"), ("assistant", LONG), ("user", "네")])
        for s in (short, cueless, no_after):
            self.assertEqual(pp.candidates([s]), [])


class PickTest(unittest.TestCase):
    def test_round_robin_one_per_session_and_cap(self):
        sessions = [good("a%d" % i, "big") for i in range(10)] + [good("b", "small")]
        c = pp.candidates(sessions)
        picked = pp.pick(c, total=4, per_project=2)
        projects = [sessions[x["si"]]["project"] for x in picked]
        self.assertEqual(sorted(projects), ["big", "big", "small"])
        self.assertEqual(len({x["si"] for x in picked}), len(picked))

    def test_packet_shape(self):
        s = good("s1", "p")
        pk = pp.packet(0, s, 2)
        self.assertEqual(pk["approval"], "진행해")
        self.assertEqual(pk["before"][-1]["role"], "assistant")
        self.assertEqual(pk["session_id"], "s1")
        self.assertEqual(pk["date"], "2026-10-10")


if __name__ == "__main__":
    unittest.main()
