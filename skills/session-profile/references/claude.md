# Claude Code 세션 기록

확인한 환경은 한 대(VS Code 확장, 2026-10). 버전이 다르면 형식이 다를 수 있다. 확인하지 못한 변형은 아래에 "확인하지 못함"으로 적었다.

## 위치
- `~/.claude/projects/<프로젝트 경로를 -로 바꾼 이름>/<세션id>.jsonl` — 세션 하나
- `~/.claude/projects/<프로젝트>/<세션id>/subagents/agent-*.jsonl` — 서브에이전트 기록. 사용자 대화가 아니므로 읽지 않는다.
- 작업 트리(worktree)에서 연 세션은 프로젝트 이름에 `--claude-worktrees-...`가 붙는다. 스크립트는 `cwd`에서 원래 저장소 이름으로 묶는다.

## 줄 형식
한 줄이 JSON 하나. `type`이 `user`, `assistant`인 줄만 대화다. 나머지(`system`, `attachment`, `queue-operation`, `ai-title` 등)는 메타데이터다.

사용자 줄에서 **사람이 직접 쓴 것만** 가려내는 신호:
- `isMeta: true`, `isCompactSummary: true` — 제외
- `origin.kind`가 `human`이 아니거나(`task-notification`, `peer`) — 제외. `origin`이 없는 줄은 옛 형식일 수 있어 본문으로 판단한다.
- `isSidechain: true` — 제외
- `message.content`가 `tool_result` 블록뿐이면 도구 결과이므로 제외
- 본문이 `<task-notification>`, `<command-name>`, `<local-command-stdout>`, `<system-reminder>` 등으로 시작하면 도구가 끼워 넣은 것
- `<ide_selection>`, `<ide_opened_file>` 블록은 사람 발화 안에 섞여 들어오므로 블록만 지운다
- `<pasted_content id="x">…</pasted_content id="x">`는 사용자가 붙여넣은 내용. 닫는 태그에도 id가 붙고, 닫는 태그가 없는 경우도 있었다.

AI 줄은 `message.content` 중 `type: "text"` 블록만 쓴다. `thinking`, `tool_use`는 쓰지 않는다.
