import json
from google import genai

SYSTEM_PROMPT = """당신은 한국어 '되/돼' 맞춤법 전문가입니다.

규칙:
- '돼'는 '되어'의 줄임말입니다
- '되어'로 바꿔서 자연스러우면 '돼'가 맞습니다
- '되어'로 바꿔서 어색하면 '되'가 맞습니다
- '됐'은 '되었'의 줄임말이므로 올바릅니다
- '됀'은 '되ㄴ'이 아니라 잘못된 표기입니다

다음 문장에서 '되/돼' 사용이 올바른지 검사하세요.
'되/돼'와 관련 없는 다른 맞춤법 오류는 무시하세요.
틀린 부분이 없으면 has_error를 false로 하고 corrections를 빈 배열로 하세요.

반드시 아래 JSON 형식으로만 응답하세요. JSON 외의 텍스트는 포함하지 마세요:
{
  "has_error": true,
  "corrections": [
    {
      "original": "틀린 단어/표현",
      "corrected": "올바른 단어/표현",
      "explanation": "왜 틀렸는지 간단한 설명"
    }
  ]
}"""


class GrammarChecker:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-2.5-flash"

    async def check(self, text: str) -> dict | None:
        """되/돼 맞춤법을 검사합니다.

        Returns:
            오류가 있으면 {"has_error": True, "corrections": [...]} 딕셔너리,
            오류가 없거나 API 실패 시 None
        """
        # '되' 또는 '돼'가 포함되어 있지 않으면 검사 불필요
        if '되' not in text and '돼' not in text:
            return None

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=f"문장: {text}",
                config=genai.types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )

            result = json.loads(response.text)

            if result.get("has_error") and result.get("corrections"):
                return result

            return None

        except (json.JSONDecodeError, KeyError, Exception) as e:
            print(f"[오류] Gemini API 호출 실패: {e}")
            return None
