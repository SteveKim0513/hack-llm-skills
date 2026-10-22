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


def ab(name, shown, broken, got, total):
    return {"name": name, "log": {"shown": shown, "broken": broken}, "task": {"got": got, "total": total}}


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


class JudgeTest(unittest.TestCase):
    def test_both_sources_bottom_top_and_split(self):
        abilities = [ab("이해", 9, 1, 9, 10), ab("읽기", 2, 8, 1, 10), ab("목표 명확성", 8, 2, 8, 10),
                     ab("원하는 것의 분명함", 3, 7, 9.5, 10), ab("표현 정확성", 6, 4, 2, 10)]
        v = bf.judge(abilities)
        self.assertEqual(v["읽기"], ("먼저 보완", False))
        self.assertEqual(v["이해"], ("강점", False))
        self.assertEqual(v["원하는 것의 분명함"], ("증거가 엇갈림", False))
        self.assertEqual(v["표현 정확성"][0], "보통")

    def test_single_source_and_too_little_evidence(self):
        abilities = [ab("이해", 1, 0, 9, 10), ab("읽기", 0, 0, 1, 10), ab("목표 명확성", 0, 0, 5, 10),
                     ab("원하는 것의 분명함", 0, 0, 1, 2), ab("표현 정확성", 0, 0, 0, 0)]
        v = bf.judge(abilities)
        self.assertEqual(v["이해"], ("강점", True))
        self.assertEqual(v["원하는 것의 분명함"], ("증거 부족", False))


class RenderTest(unittest.TestCase):
    def test_sample_order_and_focus(self):
        out = bf.render(SAMPLE)
        ids = [out.index('id="%s"' % k) for k in ("focus", "map", "detail", "mm", "rel")]
        self.assertEqual(ids, sorted(ids))
        focus = out[out.index('id="focus"'):out.index('id="map"')]
        self.assertIn("읽기", focus)

    def test_tags_balance_and_no_external_resources(self):
        out = bf.render(SAMPLE)
        p = Balance()
        p.feed(out)
        self.assertEqual((p.errors, p.stack), ([], []))
        self.assertIsNone(re.search(r'(src|href)="https?://', out))

    def test_text_is_escaped(self):
        d = copy.deepcopy(SAMPLE)
        d["headline"] = "<script>alert(1)</script>"
        d["abilities"][0]["log"]["examples_shown"][0]["quote"] = "<img src=x onerror=1>"
        out = bf.render(d)
        self.assertNotIn("<script>alert", out)
        self.assertNotIn("<img src=x", out)

    def test_empty_input_renders(self):
        out = bf.render({"headline": "h"})
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
