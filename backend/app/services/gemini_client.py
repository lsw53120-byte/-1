import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_MODEL = "gemini-3.5-flash-lite"


class GeminiAPIError(RuntimeError):
    pass


def selected_model() -> str:
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip()
    if not model or not all(character.isalnum() or character in "-_." for character in model):
        raise ValueError("GEMINI_MODEL contains invalid characters")
    return model


def generate_json(prompt: str, *, model: str | None = None) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiAPIError("GEMINI_API_KEY 환경 변수가 없습니다.")
    model = model or selected_model()
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            data = json.load(response)
    except HTTPError as exc:
        if exc.code == 401:
            raise GeminiAPIError("Gemini API 키가 거절됐습니다 (HTTP 401). 유효한 GEMINI_API_KEY를 설정해 주세요.") from exc
        raise GeminiAPIError(f"Gemini API 요청 실패 (HTTP {exc.code}). 모델 접근 권한이나 사용량을 확인해 주세요.") from exc
    except URLError as exc:
        raise GeminiAPIError("Gemini API에 연결하지 못했습니다.") from exc
    candidates = data.get("candidates") or []
    if not candidates:
        raise GeminiAPIError("Gemini가 분석 결과를 반환하지 않았습니다.")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts)
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeminiAPIError("Gemini 결과가 올바른 JSON이 아닙니다.") from exc
    if not isinstance(result, dict):
        raise GeminiAPIError("Gemini 결과가 객체 형식이 아닙니다.")
    return result
