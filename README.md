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
| `session-profile` | 로컬 세션 기록(Claude Code·Codex)으로 AI와 일하는 방식을 본다. 기본으로 A → B를 차례로 실행하고 마지막에 종합한다. 모드 A: 사용자가 한 행동(검증·구조·방향 주도·메타인지)이 나온 세션 비율과 10발화당 장면 수로 프로필 정리. 모드 B: AI 제안을 짧게 승인하고 넘어간 지점에서 그 결정으로 생긴 지금의 환경을 아는지 서술형 퀴즈로 확인하고, 생각과 실제가 다른 곳을 찾는다. 점수·수준 판정은 하지 않음. 결과는 저장소 밖에 저장. Python 3 필요, 모드 B는 서브에이전트 필요. Codex에서의 실행은 확인하지 못함 |

## 위임 전 점검 훅 (Claude Code 전용, 기본 꺼짐)

플러그인에 `hooks/`가 들어 있지만, 켜기 전에는 아무것도 하지 않는다. 켜려면 Claude Code에서 `criteria-init`을 실행한다(범위와 강도를 묻는다).
켜면 일을 맡기는 요청이 감지될 때만 기록소를 조회해, 확정 기준은 Claude에게 알려 주고 없으면 작업 전에 묻게 한다. 세션당 횟수 제한과 쿨다운이 있다. 끄려면 `criteria-init`으로 끄거나 `.criteria/config.json`의 `enabled`를 `false`로 바꾼다.

## 개발

```bash
cd hooks && python3 -m unittest -v test_criteria_hook
cd skills/session-profile/scripts && python3 -m unittest -v test_extract_sessions test_label_server test_build_report test_pick_points test_quiz_check test_quiz_server
```
