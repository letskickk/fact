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
주어진 발언의 사실 여부를 가장 적합한 **단일 소스**로 검증하세요.

## 소스 선택 규칙 (하나만 선택!)
1. **reference** → 참고 자료가 제공되었고, 그 안에 발언을 검증할 충분한 정보가 있을 때
2. **web_search** → 참고 자료가 없거나 관련 없을 때. 최신 뉴스/통계/공식 발표가 필요할 때
3. **llm** → 널리 알려진 상식이나 역사적 사실로 참고 자료/웹 검색 없이도 확실히 판단 가능할 때

⚠️ 주의: 두 소스를 조합(reference+web_search 등)하지 마세요. 가장 신뢰할 수 있는 소스 하나만 사용하세요.
⚠️ 참고 자료가 제공되더라도 발언과 무관하면 무시하고 web_search나 llm을 사용하세요.

## 판정 기준
- fact: 소스와 일치함
- partial: 부분적으로 맞지만 오류나 과장이 있음
- false: 소스와 다름
- unverifiable: 확인 불가

반드시 아래 JSON 형식으로만 응답하세요:
{
  "verdict": "fact" | "partial" | "false" | "unverifiable",
  "confidence": 0.0~1.0,
  "explanation": "판정 근거를 구체적으로",
  "source_type": "reference" | "web_search" | "llm",
  "sources": ["실제 참조한 출처 (URL, 문서명 등)"]
}"""

VERIFIER_USER = "발언: {statement}"

VERIFIER_USER_WITH_CONTEXT = """\
발언: {statement}

[참고 자료에서 검색된 관련 내용]
{context}"""
