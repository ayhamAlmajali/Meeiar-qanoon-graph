import json
import os
from pathlib import Path
import re
import time
from typing import Any
import urllib.error
import urllib.request

_ENV_LOADED = False


def _load_env_if_needed(force: bool = False) -> None:
    global _ENV_LOADED
    if _ENV_LOADED and not force:
        return

    backend_dir = Path(__file__).resolve().parent
    project_root = backend_dir.parent
    for env_path in (project_root / ".env", backend_dir / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v

    _ENV_LOADED = True


_load_env_if_needed()


def _clean_response_text(text: str) -> str:
    # إزالة وسوم التفكير الداخلية لنماذج التفكير (المغلقة أو غير المكتملة)
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    cleaned = re.sub(r"<think>.*$", "", cleaned, flags=re.DOTALL).strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(line for line in lines if not line.strip().startswith("```")).strip()
    return cleaned


def _resolve_ollama_endpoint_and_model() -> tuple[str, str]:
    raw_url = os.getenv("OLLAMA_URL", "").strip()
    if raw_url:
        endpoint = raw_url
    else:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        endpoint = f"{base_url}/api/chat"

    model = (
        os.getenv("OLLAMA_MODEL", "").strip()
        or os.getenv("OLLAMA_CHAT_MODEL", "").strip()
        or "qwen2.5:7b"
    )
    return endpoint, model


def _post_json_with_retry(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
    max_retries: int = 2,
) -> dict[str, Any]:
    encoded_body = json.dumps(payload).encode("utf-8")
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        req = urllib.request.Request(
            url,
            data=encoded_body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as http_err:
            last_exc = http_err
            # لا فائدة من إعادة المحاولة عند أخطاء المصادقة أو الطلب غير الصالح
            if http_err.code in {400, 401, 403, 404}:
                raise
            if attempt < max_retries:
                time.sleep(0.8 * (2 ** attempt))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as net_err:
            last_exc = net_err
            if attempt < max_retries:
                time.sleep(0.8 * (2 ** attempt))
                continue
            raise

    raise RuntimeError(f"فشل الاتصال بالخدمة: {last_exc}")


def _call_groq(prompt: str, json_mode: bool = True, temperature: float = 0.1) -> str:
    _load_env_if_needed()
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY غير مضبوط في متغيرات البيئة")

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    data = _post_json_with_retry(
        url="https://api.groq.com/openai/v1/chat/completions",
        payload=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0",
        },
        timeout=60,
        max_retries=2,
    )
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return _clean_response_text(content)


def _call_ollama(prompt: str, json_mode: bool = True, temperature: float = 0.1) -> str:
    _load_env_if_needed()
    endpoint, model = _resolve_ollama_endpoint_and_model()
    num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    if json_mode:
        payload["format"] = "json"

    data = _post_json_with_retry(
        url=endpoint,
        payload=payload,
        headers={"Content-Type": "application/json"},
        timeout=180,
        max_retries=1,
    )
    content = data.get("message", {}).get("content", "")
    return _clean_response_text(content)


def generate_text(prompt: str, json_mode: bool = True, temperature: float = 0.1) -> str:
    _load_env_if_needed()
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


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    cleaned = _clean_response_text(raw_text)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # محاولة استخراج أول كائن JSON متوازن في حال أضاف النموذج مقدمة أو خاتمة نصية
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start : end + 1]
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("استجابة النموذج لا تحتوي على كائن JSON صالح.")


def generate_json(prompt: str, temperature: float = 0.1) -> dict[str, Any]:
    raw = generate_text(prompt, json_mode=True, temperature=temperature)
    return _extract_json_object(raw)