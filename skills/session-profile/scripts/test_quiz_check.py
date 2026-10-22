"""quiz_check 테스트. 가짜 문항만 쓴다.
실행: cd skills/session-profile/scripts && python3 -m unittest -v test_quiz_check
"""
import json
import tempfile
import unittest
from pathlib import Path

import quiz_check as qc

ITEMS = [{"item_id": k, "pid": n, "question": "q" + k, "key_points": ["secret-" + k], "full_credit": "f",
          "partial_credit": "p", "evidence": ["e"]} for n, k in enumerate("abc")] + [{"pid": 9, "drop": "x"}]
PACKETS = [{"pid": 0, "project": "P0", "date": "2026-10-01"}, {"pid": 1, "project": "P1", "date": "2026-10-02"},
           {"pid": 2, "project": "P2", "date": "2026-10-03"}]


class CheckTest(unittest.TestCase):
    def test_prepare_hides_keys(self):
        with_pid, no_ctx, _ = qc.prepare(ITEMS, PACKETS)
        self.assertEqual(len(with_pid), 3)
        self.assertNotIn("secret", json.dumps([with_pid, no_ctx]))
        self.assertTrue(all(set(x) == {"item_id", "question"} for x in no_ctx))

    def test_grading_shuffles_and_map_unblinds(self):
        ctx = [{"item_id": k, "answer": "ctx-" + k} for k in "abc"]
        noc = [{"item_id": k, "answer": "noc-" + k} for k in "abc"]
        out, mapping = qc.grading(ITEMS, ctx, noc, seed=3)
        for row in out:
            m = mapping[row["item_id"]]
            self.assertEqual(row["answer_" + ("X" if m["X"] == "context" else "Y")], "ctx-" + row["item_id"])
        self.assertNotIn("context", json.dumps(out))

    def test_select_keeps_only_context_right_and_nocontext_wrong(self):
        mapping = {"a": {"X": "context", "Y": "nocontext"}, "b": {"X": "nocontext", "Y": "context"},
                   "c": {"X": "context", "Y": "nocontext"}}
        grades = [{"item_id": "a", "X": {"grade": "맞음"}, "Y": {"grade": "틀림"}},
                  {"item_id": "b", "X": {"grade": "부분"}, "Y": {"grade": "맞음"}},
                  {"item_id": "c", "X": {"grade": "맞음"}, "Y": {"grade": "맞음"}}]
        keep, table = qc.select(ITEMS, grades, mapping, PACKETS)
        self.assertEqual([k["item_id"] for k in keep], ["a"])
        self.assertEqual((keep[0]["project"], keep[0]["date"]), ("P0", "2026-10-01"))
        self.assertEqual(table[("맞음", "부분")], 1)

    def test_cli_refuses_map_next_to_grading_file(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name, data in (("i.json", ITEMS), ("c.json", []), ("n.json", [])):
                (d / name).write_text(json.dumps(data), encoding="utf-8")
            rc = qc.main(["grading", "--items", str(d / "i.json"), "--context", str(d / "c.json"),
                          "--nocontext", str(d / "n.json"), "--out", str(d / "g.json"), "--map", str(d / "m.json")])
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
