import json
import os
import re
from typing import Any
import urllib.request


def _load_env_if_needed() -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k:
                    os.environ[k] = v


_load_env_if_needed()


def _clean_response_text(text: str) -> str:
    # إزالة وسوم التفكير الداخلية لنماذج Qwen3 إن ظهرت
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(line for line in lines if not line.strip().startswith("```")).strip()
    return cleaned


def _call_groq(prompt: str, json_mode: bool = True, temperature: float = 0.1) -> str:
    _load_env_if_needed()
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY غير مضبوط في متغيرات البيئة")

    model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b").strip()
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return _clean_response_text(data["choices"][0]["message"]["content"])


def _call_ollama(prompt: str, json_mode: bool = True, temperature: float = 0.1) -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b").strip()

    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": 4096},
    }
    if json_mode:
        payload["format"] = "json"

    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return _clean_response_text(data.get("message", {}).get("content", ""))


def generate_text(prompt: str, json_mode: bool = True, temperature: float = 0.1) -> str:
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    order = ["groq", "ollama"] if provider != "ollama" else ["ollama", "groq"]

    last_err: Exception | None = None
    for p in order:
        try:
            if p == "groq" and os.getenv("GROQ_API_KEY", "").strip():
                return _call_groq(prompt, json_mode=json_mode, temperature=temperature)
            if p == "ollama":
                return _call_ollama(prompt, json_mode=json_mode, temperature=temperature)
        except Exception as exc:
            last_err = exc
            continue

    raise RuntimeError(f"تعذر توليد الاستجابة عبر Groq أو Ollama: {last_err}")


def generate_json(prompt: str, temperature: float = 0.1) -> dict[str, Any]:
    raw = generate_text(prompt, json_mode=True, temperature=temperature)
    return json.loads(raw)