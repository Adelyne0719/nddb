import json
import logging
from google import genai

logger = logging.getLogger("nddb")

SYSTEM_PROMPT = """당신은 한국어 '되/돼' 맞춤법 전문가입니다.

핵심 규칙:
- '돼' = '되어'의 줄임말. 해당 위치에 '되어'를 넣어 자연스러우면 '돼', 어색하면 '되'
- '됐' = '되었'의 줄임말이므로 올바름

판별법 - '되' 뒤에 오는 어미를 확인:
- 되+고, 되+면, 되+지, 되+는, 되+다, 되+니, 되+나, 되+며, 되+려, 되+든 → '되'가 맞음 (자음 어미)
- 되+어, 되+어서, 되+어야, 되+어도, 되+었 → 줄여서 '돼, 돼서, 돼야, 돼도, 됐'이 맞음 (모음 어미)
- 문장 끝에 단독으로 올 때: "안 돼", "하면 돼" → '돼'가 맞음 (되어의 줄임)

올바른 예시:
- "안되나" → 올바름 (되+나, 자음 어미)
- "되고 싶다" → 올바름 (되+고)
- "되면 좋겠다" → 올바름 (되+면)
- "안 돼" → 올바름 (되어의 줄임)
- "돼서 기쁘다" → 올바름 (되어서의 줄임)
- "됐다" → 올바름 (되었다의 줄임)

틀린 예시:
- "되서" → "돼서" (되어서의 줄임이므로)
- "되요" → "돼요" (되어요의 줄임이므로)
- "돼고" → "되고" (되+고이므로)
- "돼면" → "되면" (되+면이므로)
- "돼나" → "되나" (되+나이므로)
- "돼지만" → "되지만" (되+지만이므로)
- "안돼나" → "안되나" (되+나이므로)

잘못된 받침 예시:
- "됫" → "됐" (ㅅ 받침은 잘못됨, ㅆ 받침이 맞음. 되었→됐)
- "됀" → 존재하지 않는 글자

주의: 확실하지 않으면 올바른 것으로 판단하세요. 틀린 것이 확실할 때만 교정하세요.
'되/돼'와 관련 없는 다른 맞춤법 오류는 무시하세요.
띄어쓰기 오류는 교정하지 마세요.

반드시 아래 JSON 형식으로만 응답하세요:
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

    @staticmethod
    def _contains_doe_dwae(text: str) -> bool:
        """텍스트에 되/돼 계열 글자가 포함되어 있는지 확인합니다.
        받침이 붙은 변형(됐, 됫, 된, 될 등)도 감지합니다.
        """
        for ch in text:
            code = ord(ch)
            # 돼 계열 (ㄷ+ㅙ+받침): 돼~됗 (U+B3FC ~ U+B417)
            # 되 계열 (ㄷ+ㅚ+받침): 되~됳 (U+B418 ~ U+B433)
            if 0xB3FC <= code <= 0xB433:
                return True
        return False

    async def check(self, text: str) -> dict | None:
        """되/돼 맞춤법을 검사합니다.

        Returns:
            오류가 있으면 {"has_error": True, "corrections": [...]} 딕셔너리,
            오류가 없거나 API 실패 시 None
        """
        if not self._contains_doe_dwae(text):
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
            logger.error(f"Gemini API 호출 실패: {e}")
            return None
