# 기준 기록소 저장 형식

## 폴더
```
.criteria/
  INDEX.md
  <id>.md
```

`config.json`은 훅 설정이며 기준 파일이 아니다(`criteria-init` 참고). 조회 대상에서 제외한다.

## 기준 파일 `<id>.md`
`id`는 `영역-결정종류-번호` 형태의 영문 소문자·하이픈. 예: `magazine-source-filter-1`

```markdown
---
id: magazine-source-filter-1
area: magazine            # 무엇에 대한 일인지
decision: source-filter   # 어떤 결정에 쓰는 기준인지
status: confirmed         # confirmed | draft | superseded | retired
source: user              # user | co-created | ai-inferred
confirmed_at: 2026-10-20  # confirmed일 때만
review_after: 2027-01-20  # 선택. 없으면 확정 후 90일
supersedes:               # 이전 버전 id, 없으면 비움
evidence: "세션 인용 한 줄"  # 선택. 어떤 대화에서 나온 기준인지
---

기준 본문. 사용자의 말 그대로.
```

## `INDEX.md`
한 줄에 기준 하나. 질문 전에 이 파일만 읽어 조회한다.

```markdown
- [magazine-source-filter-1](magazine-source-filter-1.md) · magazine/source-filter · confirmed · 2025년 이후 1차 자료만
```

## 조회 규칙
1. `area`와 `decision`이 같은 `confirmed` 기준을 찾는다. 프로젝트 → 전역 순.
2. 애매하면 `INDEX.md` 요약을 보고 가장 가까운 것을 고르되, 확신이 없으면 후보를 보여주고 묻는다.
3. 아래 중 하나면 "확정"으로 취급하지 않는다: `draft`, `ai-inferred`, `review_after` 경과(없으면 확정 후 90일), 영역이 달라짐.
4. `superseded`, `retired`는 조회 대상이 아니다.
