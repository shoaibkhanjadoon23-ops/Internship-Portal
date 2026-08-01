import requests
from app.config import GEMINI_API_KEY, GROQ_API_KEY

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def call_gemini(prompt: str, json_mode: bool = False, timeout: int = 30) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")

    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if json_mode:
        body["generationConfig"] = {"response_mime_type": "application/json"}

    resp = requests.post(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        json=body,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def call_groq(prompt: str, model: str = "llama-3.3-70b-versatile", timeout: int = 30) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")

    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def generate_text(prompt: str, json_mode: bool = False) -> tuple[str, str]:
    """
    Tries Gemini first (better structured output), falls back to Groq
    if Gemini's free daily quota is exhausted or the call fails.
    Returns (text, provider_used).
    """
    try:
        return call_gemini(prompt, json_mode=json_mode), "gemini"
    except Exception:
        return call_groq(prompt), "groq"
