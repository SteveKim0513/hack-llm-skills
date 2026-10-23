#!/usr/bin/env python3
"""원본 세션 기록에서 에피소드(사람 요청 하나 + 다음 사람 요청 전까지 AI가 한 일)와 결과 지표를 만든다.

대화 원문은 남기지 않는다. 남는 것은 숫자, 도구 이름, 파일 이름(경로 없이)뿐이다.
그래도 프로젝트 이름과 파일 이름이 들어가므로 공개 저장소 밖에 저장한다.

에피소드 경계는 extract_sessions.py의 사용자 턴과 같다. 사람 발화 사이에 AI 글이 없으면 한 턴으로 합친다.
그래서 에피소드 번호(user_turn)로 sessions.jsonl의 사용자 턴을 찾을 수 있다.

결과 지표는 "그 요청 뒤에 일이 어떻게 흘렀나"다. 원인이 사용자인지는 이 스크립트가 가리지 않는다.
정정 신호(correction_cue)와 반복(repeat)은 낱말과 글자 겹침으로 찾은 후보일 뿐이다.

  python3 episodes.py --sessions sessions.jsonl --out episodes.jsonl
  python3 episodes.py --out episodes.jsonl --since 2026-08-01     # sessions.jsonl 없이 전부
"""
import argparse
import datetime
import json
import os
import re
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_sessions as ex  # noqa: E402

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
BREAK_S = 30 * 60  # 사람 쪽 공백이 이보다 길면 읽는 시간이 아니라 자리를 비운 것으로 본다
# 다음 요청 첫머리에 이런 말이 오면 앞 결과를 정정한 후보로 본다. 후보일 뿐 판정이 아니다.
CUE_START = re.compile(r"^\s*(아니|아뇨|그게 아니|그거 말고|그건 아니|말고|다시(?:\s*(?:해|하|정리|봐|생각|확인)|[.!,]|$)|왜 |내 말은|잘못|틀렸|no[,.! ]|nope|wrong|not that|that's not)", re.I)
CUE_ANY = re.compile(r"(그게 아니라|그런 뜻이 아니|내 말은|다시 해|원래대로|되돌려|취소해|i meant|not what i|instead of|revert|undo)", re.I)
REPEAT_SIM = 0.6


def ts_of(value):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return float(value)
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def base(path):
    return os.path.basename(str(path).rstrip("/")) if path else None


# ---------- 원본을 공통 사건 목록으로 ----------
# 사건: (kind, ts, data). kind는 human, ai, tool, interrupt.

def claude_events(path, stats):
    meta, events = {}, []
    for o in ex.read_jsonl(path, stats):
        typ = o.get("type")
        if typ not in ("user", "assistant") or o.get("isSidechain"):
            continue
        meta.setdefault("cwd", o.get("cwd"))
        meta.setdefault("id", o.get("sessionId"))
        ts = ts_of(o.get("timestamp"))
        content = (o.get("message") or {}).get("content")
        if typ == "assistant":
            for b in content or []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and (b.get("text") or "").strip():
                    events.append(("ai", ts, {"chars": len(b["text"].strip())}))
                elif b.get("type") == "tool_use":
                    inp = b.get("input") or {}
                    f = inp.get("file_path") or inp.get("notebook_path")
                    events.append(("tool", ts, {"id": b.get("id"), "name": b.get("name"),
                                                "file": base(f) if b.get("name") in EDIT_TOOLS else None}))
            continue
        blocks = [content] if isinstance(content, str) else (content or [])
        texts = []
        for b in blocks:
            if isinstance(b, str):
                texts.append(b)
            elif isinstance(b, dict) and b.get("type") == "tool_result":
                events.append(("result", ts, {"id": b.get("tool_use_id"), "error": bool(b.get("is_error"))}))
            elif isinstance(b, dict) and b.get("type") == "text":
                texts.append(b.get("text") or "")
        if any(t.strip().startswith("[Request interrupted") for t in texts):
            events.append(("interrupt", ts, {}))
            continue
        if o.get("isMeta") or o.get("isCompactSummary"):
            continue
        origin = o.get("origin")
        if isinstance(origin, dict) and origin.get("kind") not in (None, "human"):
            continue
        text = "\n".join(p for p in (ex.clean_user_text(t) for t in texts) if p)
        if text:
            events.append(("human", ts, {"text": text}))
    return {"tool": "claude", "id": meta.get("id") or os.path.splitext(os.path.basename(path))[0],
            "project": ex.project_label(meta.get("cwd")), "events": resolve_results(events)}


def resolve_results(events):
    """Claude는 도구 결과가 다음 사용자 줄에 따로 온다. 결과의 오류 여부를 호출 쪽에 붙이고 결과 사건은 지운다."""
    err = {d["id"]: d["error"] for k, _, d in events if k == "result" and d.get("id")}
    out = []
    for k, ts, d in events:
        if k == "result":
            continue
        if k == "tool":
            d = dict(d, error=err.get(d.get("id")))
        out.append((k, ts, d))
    return out


def codex_events(path, stats):
    meta, typed, fallback, other = None, [], [], []
    items_seen = False
    seq = 0
    for o in ex.read_jsonl(path, stats):
        seq += 1
        typ, p = o.get("type"), o.get("payload") or {}
        ts = ts_of(o.get("timestamp"))
        if typ == "session_meta" and meta is None:
            meta = p
        elif typ == "event_msg" and p.get("type") == "user_message":
            typed.append((seq, ts, p.get("message", "")))
        elif typ == "event_msg" and p.get("type") == "turn_aborted":
            other.append((seq, "interrupt", ts, {}))
        elif typ == "event_msg" and p.get("type") == "item_completed":
            it = p.get("item") or {}
            t = it.get("type")
            if t == "UserMessage":
                typed.append((seq, ts, "\n".join((b.get("text") or "") for b in it.get("content") or [] if isinstance(b, dict))))
            elif t == "CommandExecution":
                items_seen = True
                code = str(it.get("exit_code", "0"))
                other.append((seq, "tool", ts, {"name": "command", "file": None, "error": code not in ("0", "None", "")}))
            elif t == "FileChange":
                items_seen = True
                ch = it.get("changes") or {}
                files = list(ch.keys()) if isinstance(ch, dict) else []
                bad = it.get("status") not in (None, "completed")
                for f in files or [None]:
                    other.append((seq, "tool", ts, {"name": "file_change", "file": base(f), "error": bad}))
            elif t in ("McpToolCall", "Extension"):
                items_seen = True
                other.append((seq, "tool", ts, {"name": t, "file": None, "error": it.get("status") not in (None, "completed")}))
        elif typ == "response_item" and p.get("type") == "message":
            blocks = p.get("content") or []
            if p.get("role") == "user":
                txt = "\n".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "input_text")
                if txt.strip().startswith("<turn_aborted"):
                    other.append((seq, "interrupt", ts, {}))
                else:
                    fallback.append((seq, ts, txt))
            elif p.get("role") == "assistant":
                txt = "\n".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "output_text").strip()
                if txt:
                    other.append((seq, "ai", ts, {"chars": len(txt)}))
        elif typ == "response_item" and p.get("type") in ("function_call", "custom_tool_call"):
            other.append((seq, "raw_tool", ts, {"name": p.get("name"), "file": None, "error": None}))
    # 명령 실행 기록(item_completed)이 있으면 그쪽이 오류 여부까지 있으니 그것만 쓴다. 없을 때만 모델 쪽 호출을 센다.
    evs = []
    for s, k, ts, d in other:
        if k == "raw_tool":
            if items_seen:
                continue
            k = "tool"
        evs.append((s, k, ts, d))
    users = typed if typed else fallback
    evs += [(s, "human", ts, {"text": ex.clean_user_text(t)}) for s, ts, t in users]
    evs.sort(key=lambda e: e[0])
    meta = meta or {}
    return {"tool": "codex", "id": meta.get("id") or os.path.splitext(os.path.basename(path))[0],
            "project": ex.project_label(meta.get("cwd")),
            "_subagent": isinstance(meta.get("source"), dict) and "subagent" in meta.get("source"),
            "events": [(k, ts, d) for _, k, ts, d in evs if not (k == "human" and not d["text"])]}


# ---------- 사건을 에피소드로 ----------

def grams(text):
    t = re.sub(r"\s+", "", text.lower())
    return {t[i:i + 3] for i in range(max(0, len(t) - 2))}


def similarity(a, b):
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def build_episodes(events):
    eps, cur = [], None
    for kind, ts, d in events:
        if kind == "human":
            if cur is not None and not cur["_ai_seen"]:
                if d["text"] != cur["_text"]:
                    cur["_text"] += "\n\n" + d["text"]
                cur["_last"] = ts or cur["_last"]
                continue
            cur = {"_text": d["text"], "_ai_seen": False, "start": ts, "_last": ts, "ai_chars": 0, "last_ai_chars": 0,
                   "tools": 0, "tool_errors": 0, "_files": [], "interrupted": False}
            eps.append(cur)
            continue
        if cur is None:
            continue  # 첫 사람 발화 전의 사건(시작 안내 등)은 세지 않는다
        if ts:
            cur["_last"] = ts
        if kind == "ai":
            cur["_ai_seen"] = True
            cur["ai_chars"] += d["chars"]
            cur["last_ai_chars"] = d["chars"]
        elif kind == "tool":
            cur["tools"] += 1
            cur["tool_errors"] += 1 if d.get("error") else 0
            if d.get("file"):
                cur["_files"].append(d["file"])
        elif kind == "interrupt":
            cur["interrupted"] = True
    return finish(eps)


def finish(eps):
    seen_files = set()
    out = []
    for i, e in enumerate(eps):
        files = list(dict.fromkeys(e["_files"]))
        text = e["_text"]
        nxt = eps[i + 1]["_text"] if i + 1 < len(eps) else None
        wait = None
        if i > 0 and e["start"] and eps[i - 1]["_last"]:
            gap = e["start"] - eps[i - 1]["_last"]
            wait = round(gap, 1) if 0 <= gap <= BREAK_S else None
        out.append({
            "user_turn": i,
            "start": datetime.datetime.fromtimestamp(e["start"], datetime.timezone.utc).isoformat(timespec="seconds") if e["start"] else None,
            "user_chars": len(text),
            "pasted": "[붙여넣은 내용]" in text,
            "asks": "?" in text or "？" in text,
            "ai_chars": e["ai_chars"],
            "last_ai_chars": e["last_ai_chars"],
            "tools": e["tools"],
            "tool_errors": e["tool_errors"],
            "edited_files": files,
            "reedited_files": [f for f in files if f in seen_files],
            "interrupted": e["interrupted"],
            "work_s": round(e["_last"] - e["start"], 1) if e["start"] and e["_last"] else None,
            "wait_before_s": wait,
            "next_correction_cue": bool(nxt and (CUE_START.search(nxt) or CUE_ANY.search(nxt[:300]))),
            "next_repeat": bool(nxt and similarity(text, nxt) >= REPEAT_SIM),
        })
        seen_files.update(files)
    return out


def summarize(eps):
    n = len(eps)
    if not n:
        return {"episodes": 0}
    tools = sum(e["tools"] for e in eps)
    work = [e["work_s"] for e in eps if e["work_s"] is not None]
    wait = [e["wait_before_s"] for e in eps if e["wait_before_s"] is not None]
    return {
        "episodes": n,
        "tools": tools,
        "tool_error_rate": round(sum(e["tool_errors"] for e in eps) / tools, 3) if tools else None,
        "interrupted": sum(e["interrupted"] for e in eps),
        "reedit_episodes": sum(1 for e in eps if e["reedited_files"]),
        "correction_cue": sum(e["next_correction_cue"] for e in eps),
        "repeat": sum(e["next_repeat"] for e in eps),
        "median_work_s": round(statistics.median(work), 1) if work else None,
        "median_wait_s": round(statistics.median(wait), 1) if wait else None,
    }


# ---------- 모으기 ----------

def collect(args, stats):
    tools = set(args.tools.split(","))
    found = {}
    if "claude" in tools:
        for path in ex.claude_files(os.path.expanduser(args.claude_dir)):
            s = claude_events(path, stats)
            keep(found, s, stats)
    if "codex" in tools:
        root = os.path.expanduser(args.codex_dir)
        imported = ex.codex_imported_ids(root) if "claude" in tools else set()
        for path in ex.codex_files(root):
            s = codex_events(path, stats)
            if s.pop("_subagent") or s["id"] in imported:
                stats["제외: 서브에이전트나 가져온 사본"] += 1
                continue
            keep(found, s, stats)
    return found


def keep(found, s, stats):
    key = (s["tool"], s["id"])
    if key in found and len(found[key]["events"]) >= len(s["events"]):
        stats["제외: 같은 세션 id 중복"] += 1
        return
    found[key] = s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sessions", help="extract_sessions.py 출력. 주면 그 세션만, 그 순서(session_idx)대로 낸다")
    ap.add_argument("--claude-dir", default="~/.claude/projects")
    ap.add_argument("--codex-dir", default="~/.codex")
    ap.add_argument("--tools", default="claude,codex")
    ap.add_argument("--since", help="YYYY-MM-DD 이후 시작한 세션만 (--sessions가 없을 때)")
    ap.add_argument("--min-user-turns", type=int, default=3)
    ap.add_argument("--out", required=True, help="출력 JSONL. 공개 저장소 밖에 둔다")
    args = ap.parse_args(argv)

    stats = Counter()
    found = collect(args, stats)
    rows = []
    if args.sessions:
        with open(os.path.expanduser(args.sessions), encoding="utf-8") as f:
            wanted = [json.loads(l) for l in f if l.strip()]
        for i, w in enumerate(wanted):
            s = found.get((w["tool"], w["id"]))
            if not s:
                stats["원본을 찾지 못한 세션"] += 1
                rows.append({"session_idx": i, "tool": w["tool"], "id": w["id"], "project": w.get("project"), "missing": True})
                continue
            rows.append(row(i, s))
    else:
        since = ex.parse_date(args.since) if args.since else None
        for s in sorted(found.values(), key=lambda s: (s["tool"], s["id"])):
            r = row(len(rows), s)
            if r["summary"]["episodes"] < args.min_user_turns:
                continue
            if since and (ex.parse_date(r["episodes"][0]["start"]) or datetime.date.min) < since:
                continue
            rows.append(r)
    out = os.path.expanduser(args.out)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(report(rows, stats), file=sys.stderr)
    return 0


def row(i, s):
    eps = build_episodes(s["events"])
    return {"session_idx": i, "tool": s["tool"], "id": s["id"], "project": s["project"],
            "summary": summarize(eps), "episodes": eps}


def report(rows, stats):
    eps = [e for r in rows for e in r.get("episodes", [])]
    lines = ["[에피소드 요약] 세션 %d개, 에피소드 %d개" % (len(rows), len(eps))]
    lines += ["  %s: %d" % kv for kv in stats.items()]
    if eps:
        n = len(eps)
        tools = sum(e["tools"] for e in eps)
        lines.append("  도구 호출 %d, 오류 %d%% · 중단 %d · 같은 파일 다시 고친 에피소드 %d%% · 정정 신호 %d%% · 반복 %d%%" % (
            tools, round(100 * sum(e["tool_errors"] for e in eps) / tools) if tools else 0,
            sum(e["interrupted"] for e in eps), round(100 * sum(1 for e in eps if e["reedited_files"]) / n),
            round(100 * sum(e["next_correction_cue"] for e in eps) / n), round(100 * sum(e["next_repeat"] for e in eps) / n)))
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
