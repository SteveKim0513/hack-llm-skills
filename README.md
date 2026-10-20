# hack-llm-skills

Claude Code와 Codex에서 함께 쓰는 스킬 모음. 스킬은 `skills/<이름>/SKILL.md` 한 폴더 단위다. `.claude-plugin/`이 있어 Claude 플러그인으로도 설치된다. 스킬을 추가하면 `plugin.json`의 `version`을 올려야 설치된 쪽이 갱신을 받는다.

## 설치

```bash
# Claude Code 플러그인 (Claude Code 안에서 실행)
/plugin marketplace add SteveKim0513/hack-llm-skills
/plugin install hack-llm-skills@hack-llm-skills

# 스킬 CLI (Claude Code, Codex 등에 설치)
npx skills add SteveKim0513/hack-llm-skills

# 또는 수동 링크
ln -s "$PWD/skills/<스킬이름>" ~/.claude/skills/<스킬이름>   # Claude Code
ln -s "$PWD/skills/<스킬이름>" ~/.codex/skills/<스킬이름>    # Codex
```

## 새 스킬 만들기

1. `templates/skill`을 `skills/<스킬이름>`으로 복사
2. `SKILL.md`의 `name`(폴더명과 동일)과 `description` 수정
3. 본문에 절차 작성. 필요하면 `scripts/`, `references/` 추가

## 호환 규칙

- 헤더는 `name`, `description`만 쓴다
- 특정 도구 이름(Claude 전용 도구 등)을 본문에 박지 않는다
- 에이전트 전용 동작이 필요하면 `references/claude.md`, `references/codex.md`로 분리한다

## 스킬 목록

| 스킬 | 설명 |
|---|---|
| (아직 없음) | |
