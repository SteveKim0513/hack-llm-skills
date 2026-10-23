---
name: session-profile
description: AI와 일한 로컬 세션 기록(Claude Code, Codex)에서 사용자 쪽 원인으로 일이 어긋난 장면을 찾아, 어떤 습관이 다시 작업 시간을 가장 많이 만들었는지(요청 100개당 분)와 이번 주에 해 볼 연습 하나를 한 장으로 알려 준다. 사용자는 아무것도 하지 않고 결과만 받는다. "내 AI 활용 습관 분석해줘", "내가 뭘 고쳐야 해", "AI 쓰면서 어디서 시간을 버려", "세션 기록으로 내 약점 찾아줘" 같은 요청에 사용. 작업 중 기준 공백을 묻는 건 criteria-gap, 기준 저장·조회는 criteria 스킬.
---

# session-profile: 가장 비싼 습관 찾기

AI와 일하다 내 쪽 원인으로 어긋난 장면을 찾고, 그 어긋남이 만든 다시 작업 시간을 습관별로 센다. 결과는 한 문장이다. **"가장 비싼 습관은 X예요. 요청 100개당 약 N분을 다시 작업에 썼어요."** 장면 몇 개와 연습 하나가 붙는다.

습관 여섯 가지와 일꾼 지시문은 `references/habits.md`, 이 모양이 된 이유는 `references/notes.md`, 기록 형식은 `references/claude.md`, `references/codex.md`.

## 원칙
- AI가 틀린 장면은 세지 않는다. 원인이 분명히 사용자 쪽인 것만 센다.
- 찾는 일꾼과 따지는 일꾼은 서로 다른 에이전트여야 한다. 그럴 수 없는 환경이면 결과에 "재검토 안 됨"을 붙인다.
- 결과는 평가받는 사람에게만 준다. 공유는 본인이 정한다. 다른 사람과 비교하는 점수가 아니고, 선발이나 인사 평가에 쓰지 않는다.
- 대화 원문이 든 파일은 공개 저장소 밖(`~/.criteria/audit/`)에 둔다. 비밀번호나 키는 어디에도 옮기지 않는다.

## 순서
1. **모으기.** 최근 30일 기록에서 세션 40개를 고른다(진행 중인 대화는 뺀다).
   ```bash
   python3 scripts/extract_sessions.py --since <날짜> --sample 40 --max-chars 3000 --out ~/.criteria/audit/sessions.jsonl
   python3 scripts/episodes.py --sessions ~/.criteria/audit/sessions.jsonl --out ~/.criteria/audit/episodes.jsonl
   ```
2. **찾기.** `habits.md`의 "찾는 일꾼"대로 어긋남 후보를 찾는다. 세션이 많으면 여러 일꾼에게 나눈다. 인용이 원문에 실제로 있는지 코드로 확인한다.
3. **따지기.** 다른 일꾼이 `habits.md`의 "재검토 일꾼"대로 원인이 사용자인 것만 `kept.jsonl`에 남긴다.
4. **결과.**
   ```bash
   python3 scripts/report.py --breaks ~/.criteria/audit/kept.jsonl --episodes ~/.criteria/audit/episodes.jsonl \
     --out ~/.criteria/audit/report-<날짜>.html
   ```
   파일을 열고, 대화에는 한 줄 결론과 파일 위치만 쓴다.
5. **정리.** 중간 파일을 지울지 묻는다.

## 한계
- 판단은 AI가 한다. 재검토로 과한 판정을 줄이지만 없애지는 못한다.
- 다시 작업 시간 안에 쓸모 있던 작업이 섞였을 수 있다. 상관이지 인과가 아니다.
- 기록 밖에서 한 일(머릿속 판단, 화면에서 직접 확인)은 보이지 않는다.
- 세션 8개로만 시험했다. 40개 규모와 다른 사람의 기록, Codex 기록으로 끝까지 돌린 것은 확인하지 못했다.
