"""build_final 테스트. 저장소에 든 지어낸 샘플(references/sample-final.json)을 쓴다.
실행: cd skills/session-profile/scripts && python3 -m unittest -v test_build_final
"""
import copy
import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

import build_final as bf

SAMPLE = json.loads((Path(__file__).resolve().parent.parent / "references" / "sample-final.json").read_text(encoding="utf-8"))


class Balance(HTMLParser):
    VOID = {"meta", "br", "hr", "img", "input", "link"}

    def __init__(self):
        super().__init__()
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(tag)
        else:
            self.stack.pop()


class FinalTest(unittest.TestCase):
    def test_sections_in_order(self):
        out = bf.render(SAMPLE)
        ids = [out.index('id="%s"' % k) for k in ("mm", "quiz", "profile", "links", "rel")]
        self.assertEqual(ids, sorted(ids))
        self.assertIn(SAMPLE["headline"], out)

    def test_tags_balance_and_no_external_resources(self):
        out = bf.render(SAMPLE)
        p = Balance()
        p.feed(out)
        self.assertEqual((p.errors, p.stack), ([], []))
        self.assertIsNone(re.search(r'(src|href)="https?://', out))

    def test_text_is_escaped(self):
        d = copy.deepcopy(SAMPLE)
        d["headline"] = "<script>alert(1)</script>"
        d["quiz"]["items"][0]["your_answer"] = "<img src=x onerror=1>"
        out = bf.render(d)
        self.assertNotIn("<script>alert", out)
        self.assertNotIn("<img src=x", out)

    def test_empty_parts_still_render(self):
        out = bf.render({"headline": "h"})
        self.assertIn("이번에는 찾지 못했어요", out)
        self.assertIn("두 번째 분류자와의 일치도가 없어요", out)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")
            out = Path(d) / "sub" / "final.html"
            self.assertEqual(bf.main(["--input", str(src), "--out", str(out)]), 0)
            self.assertTrue(out.read_text(encoding="utf-8").startswith("<!doctype html>"))


if __name__ == "__main__":
    unittest.main()
