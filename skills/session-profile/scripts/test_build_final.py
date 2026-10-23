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
    NAMES = bf.ABILITIES

    def same(self, shown=14, broken=6, got=6, total=10):
        return [ab(n, shown, broken, got, total) for n in self.NAMES]

    def test_no_difference_gives_no_verdicts_and_no_name_bias(self):
        v = bf.judge(self.same())
        self.assertEqual({x["status"] for x in v.values()}, {"아직 가릴 수 없음"})
        self.assertEqual(len({round(x["z"], 6) for x in v.values()}), 1)  # 같은 데이터면 이름과 상관없이 같은 값

    def test_clear_weakness_and_strength(self):
        abilities = self.same(14, 6, 6, 10)
        abilities[1] = ab("읽기", 4, 16, 1, 10)
        abilities[2] = ab("목표 명확성", 20, 0, 10, 10)
        v = bf.judge(abilities)
        self.assertEqual(v["읽기"]["status"], "먼저 보완")
        self.assertEqual(v["목표 명확성"]["status"], "강점")
        self.assertEqual(v["이해"]["status"], "아직 가릴 수 없음")

    def test_mixed_evidence_when_sources_disagree_strongly(self):
        abilities = self.same(14, 6, 6, 10)
        abilities[3] = ab("원하는 것의 분명함", 20, 0, 0, 10)
        self.assertEqual(bf.judge(abilities)["원하는 것의 분명함"]["status"], "증거가 엇갈림")

    def test_small_samples_are_pulled_to_the_middle(self):
        abilities = self.same(4, 1, 2, 3)
        abilities[1] = ab("읽기", 3, 2, 1, 3)   # 비율은 낮지만 증거가 적다
        self.assertEqual(bf.judge(abilities)["읽기"]["status"], "아직 가릴 수 없음")
        abilities[1] = ab("읽기", 1, 4, 0, 3)   # 두 증거 모두 극단적으로 낮으면 적은 증거로도 잡는다
        self.assertEqual(bf.judge(abilities)["읽기"]["status"], "먼저 보완")

    def test_single_source_and_no_evidence(self):
        abilities = [ab(n, 0, 0, 6, 10) for n in self.NAMES]
        abilities[4] = ab("표현 정확성", 0, 0, 0, 0)
        v = bf.judge(abilities)
        self.assertTrue(v["이해"]["single"])
        self.assertEqual(v["표현 정확성"]["status"], "증거 부족")

    def test_precision_bands(self):
        v = bf.judge(self.same(14, 6, 6, 10))
        self.assertEqual(v["이해"]["precision"], "높음")
        self.assertEqual(bf.judge(self.same(4, 1, 2, 3))["이해"]["precision"], "낮음")


class RenderTest(unittest.TestCase):
    def test_sample_order_and_focus(self):
        out = bf.render(SAMPLE)
        ids = [out.index('id="%s"' % k) for k in ("focus", "map", "detail", "mm", "rel")]
        self.assertEqual(ids, sorted(ids))
        focus = out[out.index('id="focus"'):out.index('id="map"')]
        self.assertIn("읽기", focus)
        self.assertIn("시험해 볼 가설", focus)   # 샘플에는 분명한 약점이 없다
        self.assertIn("아무 능력이나 고르면 17%", focus)  # 가설이 맞을 비율을 함께 보여 준다
        self.assertIn("전체 수준", out)

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
