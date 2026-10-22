#!/usr/bin/env python3
"""이해 확인 퀴즈 문항 검증을 돕는다. 정답 기준을 가린 파일을 만들고, 출처를 섞어 채점시키고, 통과 문항을 고른다.

검증 규칙: 대화를 읽은 답안은 "맞음", 대화를 보지 않은 답안은 "틀림"인 문항만 남긴다.

  # 1. 답안 작성용 파일 (정답 기준 없음)
  python3 quiz_check.py prepare --items items.json --packets packets.json --out blind/
  # 2. 두 답안을 섞어 채점용 파일과 출처 지도 만들기 (지도는 채점기가 볼 수 없는 곳에 둔다)
  python3 quiz_check.py grading --items items.json --context blind/context-answers.json \
      --nocontext blind/nocontext-answers.json --out blind/grading.json --map map.json
  # 3. 채점 결과로 통과 문항 고르기
  python3 quiz_check.py select --items items.json --grades blind/grades.json --map map.json \
      --packets packets.json --out quiz.json

items:   [{"item_id", "pid", "question", "key_points", "full_credit", "partial_credit", "evidence", ...}]
answers: [{"item_id", "answer", ...}]
grades:  [{"item_id", "X": {"grade", "why"}, "Y": {"grade", "why"}}]
"""
import argparse
import json
import os
import random
import sys
from collections import Counter

def load(path):
    with open(os.path.expanduser(path), encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    path = os.path.expanduser(path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def real_items(items):
    return [i for i in items if "item_id" in i and "question" in i]


def prepare(items, packets):
    items = real_items(items)
    with_pid = [{"item_id": i["item_id"], "pid": i["pid"], "question": i["question"]} for i in items]
    no_ctx = [{"item_id": i["item_id"], "question": i["question"]} for i in items]
    return with_pid, no_ctx, packets


def grading(items, context, nocontext, seed=0):
    rng = random.Random(seed)
    ctx = {a["item_id"]: a["answer"] for a in context}
    noc = {a["item_id"]: a["answer"] for a in nocontext}
    out, mapping = [], {}
    for i in real_items(items):
        k = i["item_id"]
        pair = [("context", ctx.get(k, "")), ("nocontext", noc.get(k, ""))]
        rng.shuffle(pair)
        mapping[k] = {"X": pair[0][0], "Y": pair[1][0]}
        out.append({"item_id": k, "question": i["question"], "key_points": i.get("key_points", []),
                    "full_credit": i.get("full_credit", ""), "partial_credit": i.get("partial_credit", ""),
                    "answer_X": pair[0][1], "answer_Y": pair[1][1]})
    return out, mapping


def unblind(grades, mapping):
    res = {}
    for g in grades:
        m = mapping.get(g["item_id"])
        if not m:
            continue
        res[g["item_id"]] = {m["X"]: g["X"]["grade"], m["Y"]: g["Y"]["grade"]}
    return res


def select(items, grades, mapping, packets=None, seed=0):
    res = unblind(grades, mapping)
    by_pid = {p["pid"]: p for p in (packets or [])}
    keep, table = [], Counter()
    for i in real_items(items):
        r = res.get(i["item_id"])
        if not r:
            continue
        table[(r.get("context"), r.get("nocontext"))] += 1
        if r.get("context") == "맞음" and r.get("nocontext") == "틀림":
            q = {k: i[k] for k in ("item_id", "question", "key_points", "full_credit", "partial_credit", "evidence")
                 if k in i}
            p = by_pid.get(i.get("pid"), {})
            q["project"] = i.get("project") or p.get("project", "")
            q["date"] = i.get("date") or p.get("date", "")
            keep.append(q)
    random.Random(seed).shuffle(keep)
    return keep, table


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--items", required=True)
    p.add_argument("--packets", required=True)
    p.add_argument("--out", required=True)
    g = sub.add_parser("grading")
    g.add_argument("--items", required=True)
    g.add_argument("--context", required=True)
    g.add_argument("--nocontext", required=True)
    g.add_argument("--out", required=True)
    g.add_argument("--map", required=True)
    g.add_argument("--seed", type=int, default=0)
    s = sub.add_parser("select")
    s.add_argument("--items", required=True)
    s.add_argument("--grades", required=True)
    s.add_argument("--map", required=True)
    s.add_argument("--packets")
    s.add_argument("--out", required=True)
    s.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)

    if a.cmd == "prepare":
        with_pid, no_ctx, packets = prepare(load(a.items), load(a.packets))
        save(os.path.join(a.out, "questions.json"), with_pid)
        save(os.path.join(a.out, "questions-nocontext.json"), no_ctx)
        save(os.path.join(a.out, "packets.json"), packets)
        print("문항 %d개. 정답 기준이 없는 파일만 %s에 썼다" % (len(with_pid), a.out), file=sys.stderr)
    elif a.cmd == "grading":
        out, mapping = grading(load(a.items), load(a.context), load(a.nocontext), a.seed)
        if os.path.dirname(os.path.abspath(os.path.expanduser(a.map))) == os.path.dirname(os.path.abspath(os.path.expanduser(a.out))):
            print("출처 지도는 채점 파일과 다른 폴더에 둬야 한다", file=sys.stderr)
            return 2
        save(a.out, out)
        save(a.map, mapping)
        print("채점용 %d문항" % len(out), file=sys.stderr)
    else:
        packets = load(a.packets) if a.packets else None
        keep, table = select(load(a.items), load(a.grades), load(a.map), packets, a.seed)
        save(a.out, keep)
        print("(대화 읽음, 대화 안 읽음) 결과: %s" % dict(table), file=sys.stderr)
        print("통과 %d문항 → %s" % (len(keep), a.out), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
