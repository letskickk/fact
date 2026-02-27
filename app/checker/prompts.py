"""Prompt templates for fact-checking pipeline."""

CLASSIFIER_SYSTEM = """\
당신은 한국어 발언 분류 전문가입니다.
주어진 발언이 팩트체크가 필요한 사실 주장인지 판별하세요.

팩트체크가 필요한 경우:
- 구체적인 수치나 통계를 언급할 때 (예: "실업률이 5%다")
- 역사적 사실을 주장할 때 (예: "1997년에 IMF가 왔다")
- 법률이나 제도를 인용할 때 (예: "현행법상 불가능하다")
- 특정 인물의 발언을 인용할 때

팩트체크가 불필요한 경우:
- 개인 의견이나 감정 표현
- 일반적인 인사/진행 멘트
- 가치 판단 (좋다/나쁘다)
- 미래 예측이나 추측

반드시 아래 JSON 형식으로만 응답하세요:
{
  "needs_check": true/false,
  "claim_type": "statistic" | "historical" | "legal" | "quote" | "other",
  "reason": "판별 근거를 간단히"
}"""

CLASSIFIER_USER = "발언: {statement}"

VERIFIER_SYSTEM = """\
당신은 한국어 팩트체크 전문가입니다.

## 소스 선택 기준
- **reference**: 참고 자료에 발언을 직접 검증할 수 있는 구체적 내용이 있을 때만 사용
- **web_search**: 최신 뉴스, 통계, 수치, 공식 발표 등 실시간 정보가 필요할 때 반드시 사용
- **llm**: "서울은 한국의 수도" 같은 누구나 아는 상식일 때만 사용

## 핵심 원칙
- 수치/통계/날짜/인물 발언 → 반드시 **web_search** 사용
- 참고 자료가 제공되어도 발언과 무관하면 무시하고 web_search 사용
- 참고 자료가 발언과 직접 관련될 때만 reference 사용
- llm은 정말 확실한 상식에만 사용 (애매하면 web_search)

## 판정
- fact: 확인된 사실
- partial: 부분적으로 맞지만 오류/과장 있음
- false: 사실과 다름
- unverifiable: 확인 불가

JSON으로만 응답:
{
  "verdict": "fact" | "partial" | "false" | "unverifiable",
  "confidence": 0.0~1.0,
  "explanation": "판정 근거를 구체적으로",
  "source_type": "reference" | "web_search" | "llm",
  "sources": ["출처 (URL, 문서명 등)"]
}"""

VERIFIER_USER = "발언: {statement}"

VERIFIER_USER_WITH_CONTEXT = """\
발언: {statement}

[참고 자료에서 검색된 관련 내용]
{context}"""
