# 선행 연구와 지표 (2026-10-22 조사)

검색은 대표적인 것만 훑은 것이고 체계적 문헌 검토가 아니다. "원문 확인"은 페이지를 직접 읽었다는 뜻이고, "초록만 확인"은 초록만 읽었다는 뜻이다. 결론을 인용하기 전에 원문을 본다.

## 1. 로그 기반 선례: AI Fluency Index (원문 확인)
[Anthropic AI Fluency Index](https://academy.claude.com/tutorials/the-ai-fluency-index). 2026년 1월 일주일치 Claude.ai 대화 9,830건(여러 번 오간 대화만)에서 행동 11개의 유무를 분류했다.

- **단위:** 대화 하나에 행동마다 있음/없음. 한 대화에 여러 행동이 있을 수 있다.
- **방법:** 행동마다 이진 분류기 11개(LLM). 인사·한 단어·테스트 대화는 먼저 걸러냈다.
- **프레임워크:** 24개 행동(위임·설명·분별·성실, 4D). 채팅 안에서 보이는 건 11개이고 나머지 13개(AI 사용 공개 등)는 채팅 밖이라 못 쟀다.
- **행동과 출현율:** 반복하며 다듬음 85.7%, 목표를 먼저 밝힘 51.1%, 좋은 결과의 예를 줌 41.1%, 형식·구조를 지정 30%, 상호작용 방식을 설정 30%, 톤·문체를 전달 22.7%, AI가 맥락을 놓친 것을 짚음 20.3%, 독자를 정의 17.6%, AI 추론이 안 맞을 때 되물음 15.8%, 실행 전에 접근 방식을 AI와 상의 10.1%, 중요한 사실·주장을 확인 8.7%.
- **저자가 적은 한계:** 초기 사용자 집단, 일주일치, 이진 분류가 부분적 증거를 놓침, 머릿속이나 테스트로 한 평가는 채팅에 안 나옴, 상관일 뿐 인과가 아님.

### 이 스킬의 능력과의 대응 (이 스킬 작성자의 해석이며 공식 대응이 아님)
| 이 스킬 | 가장 가까운 Index 행동 |
|---|---|
| 이해 | 대응하는 행동이 없다. Index는 결과를 이해했는지 묻지 않는다 |
| 읽기 | 대응하는 행동이 없다 (가장 가까운 것은 AI 추론이 안 맞을 때 되묻기) |
| 목표 명확성 | 목표를 먼저 밝히기 |
| 원하는 것의 분명함 | 좋은 결과의 예 주기, 톤·문체 전달 |
| 표현 정확성 | 형식·구조 지정, 독자 정의, 상호작용 방식 설정 |
| 검증 | 중요한 사실·주장을 확인(8.7%), AI가 맥락을 놓친 것을 짚음. 자기 보고로는 재기 어렵다(3절 Huynh 등). 로그는 "검증 시작"만 보여 준다(4절) |

Index는 대화에 행동이 "있었나"만 세고, 그 행동이 잘 됐는지나 사람의 능력을 재지 않는다. 이 스킬은 끊김 장면과 과제를 더해 능력의 상대 비교를 시도한다.

## 2. 설문 기반 측정 도구 (초록만 확인)
- [Critical Thinking in AI Use Scale](https://consensus.app/papers/details/a5029af9485b579e9840dcebcee3ed34/?utm_source=claude_desktop) (Lau 등, 2025): 13문항, 검증·동기·성찰 세 요인, N=1,341. 점수가 높을수록 실제 사실 확인 과제에서 검증 전략이 더 다양하고 진위 판단이 더 정확했다.
- [Strategic Prompting Scale](https://consensus.app/papers/details/3f4fea6173155195a204ffa4128e74c8/?utm_source=claude_desktop) (Suriano 등, 2026): 15문항, 계획·적응·평가. 초기 심리측정 증거 단계.
- [AI 활용 유형](https://consensus.app/papers/details/a94c4ee740b95940a41d4e0b9307fd08/?utm_source=claude_desktop) (Hou 등, 2025): 성찰적·신중한·무심한·협력적 사용. 대학생 808명, 자가보고.
- [AI 리터러시 척도 리뷰](https://consensus.app/papers/details/a7d289563089588586e3a699c3880b8d/?utm_source=claude_desktop) (Lintner, 2024): 척도 16개 중 자가보고 13개, 수행평가 3개.
- [GLAT](https://consensus.app/papers/details/fb588952d0985bffb5e9224ae2471ef2/?utm_source=claude_desktop) (Jin 등, 2024): 20문항 수행형 검사. 자가보고 지표보다 AI 지원 과제 수행을 잘 예측했다.

## 3. 자가보고와 실제 행동은 어긋난다 (초록만 확인)
- [Huynh 등, 2026](https://consensus.app/papers/details/daf869f6a92153c0a0d48553e7341d18/?utm_source=claude_desktop): 평소 검증한다고 답한 학생들도 실제 상호작용에서 오류를 못 잡았다. 자기 경계심을 과대평가했다.
- [Fernandes 등, 2024](https://consensus.app/papers/details/faaee2a0e1fc542482a959289034ac26/?utm_source=claude_desktop): AI를 쓰면 성과는 오르지만 자기 수행을 과대평가한다. AI 지식이 많을수록 자기평가가 덜 정확했다.
- [Lee 등, CHI 2025](https://consensus.app/papers/details/c4e9dd153cff573990b70ac8a7640236/?utm_source=claude_desktop): GenAI에 대한 확신이 높을수록 비판적 사고가 줄고, 자기 확신이 높을수록 늘었다 (지식노동자 319명, 자가보고).

## 4. 검증은 층위가 다르다 (초록만 확인)
[Wei와 Shang, 2026](https://consensus.app/papers/details/f1562a99ed035bb4b0714b752933ee2a/?utm_source=claude_desktop): 측정 대상을 인식적 평가, 검증 시작, 과정의 질, 성공, 의존 결정, 즉시 성과, 독립 학습으로 나눈다. 검토한 14편 중 검증 성공과 이후 의존 보정을 함께 잰 연구는 없었다. 이 스킬의 로그는 "검증 시작"에 해당하는 증거만 준다.

## 5. 로그는 모니터링을 덜 잡는다 (초록만 확인)
[Li 등, 2026](https://consensus.app/papers/details/c5448648947754dcba1dce5932f18762/?utm_source=claude_desktop): 상호작용 로그와 말하며 생각하기(think-aloud)에 같은 틀을 적용했더니, 모니터링의 전략적·성찰적 증거는 말하기 쪽이 25.4%p 더 높았다. 학생 79명, 설명적 연구. 로그만 쓰면 머릿속 모니터링이 과소 집계된다.

## 6. 유형 분류 (초록만 확인)
[Si 등, 2026](https://consensus.app/papers/details/e283bfc407ba5438b747b228869b6d6f/?utm_source=claude_desktop): 설문 353명을 군집 분석해 네 유형을 얻었다. "단순 Q&A 사용자" 25.2%에서 "비판적 공동 사고자" 15.6%까지. 모두 자가보고다.

## 7. 비어 있는 곳
로그 기반이면서 외부 기준으로 검증된 "수준"이나 "유형" 분류는 이번 검색에서 찾지 못했다. Index도 유병률과 상관을 보고할 뿐 수준을 매기지 않는다.
