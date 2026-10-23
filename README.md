# hack-users-for-llms

Claude Code와 Codex에서 함께 쓰는 스킬 모음. 스킬은 `skills/<이름>/SKILL.md` 한 폴더 단위다. `.claude-plugin/`이 있어 Claude 플러그인으로도 설치된다. 스킬을 추가하면 `plugin.json`의 `version`을 올려야 설치된 쪽이 갱신을 받는다.

## 설치

### Claude Code (플러그인)
```
/plugin marketplace add SteveKim0513/hack-users-for-llms
/plugin install hack-users-for-llms@hack-users-for-llms
```

### Codex
```bash
# 스킬 CLI. 현재 프로젝트에 설치, 전체 사용자용은 -g
npx skills add SteveKim0513/hack-users-for-llms -a codex

# 수동: 저장소를 받아 사용자 스킬 폴더에 링크 (Codex는 ~/.agents/skills를 읽는다)
git clone https://github.com/SteveKim0513/hack-users-for-llms.git ~/hack-users-for-llms
mkdir -p ~/.agents/skills
ln -s ~/hack-users-for-llms/skills/criteria ~/.agents/skills/criteria
ln -s ~/hack-users-for-llms/skills/criteria-gap ~/.agents/skills/criteria-gap
ln -s ~/hack-users-for-llms/skills/session-profile ~/.agents/skills/session-profile
```
설치 후 스킬이 안 보이면 Codex를 재시작한다.

### Claude Code (수동)
```bash
ln -s ~/hack-users-for-llms/skills/<스킬이름> ~/.claude/skills/<스킬이름>
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
| `criteria` | 합의한 판단 기준을 기록·조회·변경하는 기준 기록소. |
| `criteria-init` | 위임 전 기준 점검 훅을 켜고 끄는 스위치 (Claude Code 플러그인 전용) |
| `criteria-gap` | 대화에서 기준 공백을 찾아 대화로 묻고, AI의 암묵 기준과 비교해 재요청 (`criteria` 필요) |
| `session-profile` | AI와 일하는 사람의 여섯 능력(이해, 읽기, 목표 명확성, 원하는 것의 분명함, 표현 정확성, 검증)을 재고 무엇을 먼저 보완할지 알려 준다. 로컬 세션 기록(Claude Code·Codex)에서 능력이 드러나거나 어긋난 장면을 찾고, 그 사람의 분야로 만든 15~20분짜리 과제를 풀게 한 뒤, 한 장짜리 결과(먼저 보완할 능력, 능력 지도, 근거, 연습법)를 평가받는 본인에게만 준다. 사용자는 과제만 풀고 분류·채점은 AI가 한다. 다른 사람과 비교하는 점수는 없음. 판정 문턱은 시뮬레이션으로 정했고 실제 사람으로는 검증하지 못함. 결과는 저장소 밖에 저장. Python 3과 서브에이전트 필요. 새 과제는 실제 사용자로 아직 시험하지 못함. Codex에서의 실행은 확인하지 못함 |

## 위임 전 점검 훅 (Claude Code 전용, 기본 꺼짐)

플러그인에 `hooks/`가 들어 있지만, 켜기 전에는 아무것도 하지 않는다. 켜려면 Claude Code에서 `criteria-init`을 실행한다(범위와 강도를 묻는다).
켜면 일을 맡기는 요청이 감지될 때만 기록소를 조회해, 확정 기준은 Claude에게 알려 주고 없으면 작업 전에 묻게 한다. 세션당 횟수 제한과 쿨다운이 있다. 끄려면 `criteria-init`으로 끄거나 `.criteria/config.json`의 `enabled`를 `false`로 바꾼다.

## 개발

```bash
cd hooks && python3 -m unittest -v test_criteria_hook
cd skills/session-profile/scripts && python3 -m unittest -v test_extract_sessions test_episodes test_pick_points test_quiz_check test_log_signals test_task_server test_build_final
```
