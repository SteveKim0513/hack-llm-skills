# hack-llm-skills

Claude Code와 Codex에서 함께 쓰는 스킬 모음. 스킬은 `skills/<이름>/SKILL.md` 한 폴더 단위다. `.claude-plugin/`이 있어 Claude 플러그인으로도 설치된다. 스킬을 추가하면 `plugin.json`의 `version`을 올려야 설치된 쪽이 갱신을 받는다.

## 설치

### Claude Code (플러그인)
```
/plugin marketplace add SteveKim0513/hack-llm-skills
/plugin install hack-llm-skills@hack-llm-skills
```

### Codex
```bash
# 스킬 CLI. 현재 프로젝트에 설치, 전체 사용자용은 -g
npx skills add SteveKim0513/hack-llm-skills -a codex

# 수동: 저장소를 받아 사용자 스킬 폴더에 링크 (Codex는 ~/.agents/skills를 읽는다)
git clone https://github.com/SteveKim0513/hack-llm-skills.git ~/hack-llm-skills
mkdir -p ~/.agents/skills
ln -s ~/hack-llm-skills/skills/criteria ~/.agents/skills/criteria
ln -s ~/hack-llm-skills/skills/criteria-gap ~/.agents/skills/criteria-gap
```
설치 후 스킬이 안 보이면 Codex를 재시작한다.

### Claude Code (수동)
```bash
ln -s ~/hack-llm-skills/skills/<스킬이름> ~/.claude/skills/<스킬이름>
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
| `criteria` | 합의한 판단 기준을 기록·조회·변경하는 기준 기록소. 로컬 웹 관리 화면 포함 (python3 3.8+ 필요) |
| `criteria-gap` | 대화에서 기준 공백을 찾아 웹에서 작성받고, AI의 암묵 기준과 비교해 재요청 (`criteria` 필요) |

## 개발

`criteria`의 로컬 웹 테스트:

```bash
cd skills/criteria/scripts && python3 -m unittest -v test_criteria_web
```
