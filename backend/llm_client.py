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
            if k and (force or k not in os.environ or not os.environ[k].strip()):
                os.environ[k] = v

    _ENV_LOADED = True


_load_env_if_needed(force=True)


def _clean_response_text(text: str) -> str:
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
    max_retries: int = 1,
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
            if http_err.code in {400, 401, 403, 404, 429}:
                raise
            if attempt < max_retries:
                time.sleep(0.4)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as net_err:
            last_exc = net_err
            if attempt < max_retries:
                time.sleep(0.4)
                continue
            raise

    raise RuntimeError(f"فشل الاتصال بالخدمة: {last_exc}")


def _call_groq(prompt: str, json_mode: bool = True, temperature: float = 0.1) -> str:
    _load_env_if_needed(force=True)
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY غير مضبوط في متغيرات البيئة")

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    timeout_sec = int(os.getenv("GROQ_TIMEOUT_SECONDS", "20"))
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
        timeout=timeout_sec,
        max_retries=1,
    )
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return _clean_response_text(content)


def _call_ollama(prompt: str, json_mode: bool = True, temperature: float = 0.1) -> str:
    _load_env_if_needed(force=True)
    endpoint, model = _resolve_ollama_endpoint_and_model()
    num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
    timeout_sec = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "15"))

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
        timeout=timeout_sec,
        max_retries=0,
    )
    content = data.get("message", {}).get("content", "")
    return _clean_response_text(content)


def generate_text(prompt: str, json_mode: bool = True, temperature: float = 0.1) -> str:
    _load_env_if_needed(force=True)
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()

    if provider == "none":
        raise RuntimeError("LLM_PROVIDER مضبوط على none (وضع الإجابة المباشرة بدون LLM)")

    if provider == "ollama":
        return _call_ollama(prompt, json_mode=json_mode, temperature=temperature)

    # الوضع الافتراضي: استخدام Groq مباشرة إذا وُجد المفتاح، وعدم الانتظار طويلاً على Ollama
    if groq_key:
        try:
            return _call_groq(prompt, json_mode=json_mode, temperature=temperature)
        except Exception as exc:
            allow_ollama_fallback = os.getenv("ALLOW_OLLAMA_FALLBACK", "false").strip().lower() in {"1", "true", "yes"}
            if allow_ollama_fallback:
                return _call_ollama(prompt, json_mode=json_mode, temperature=temperature)
            raise RuntimeError(f"فشل استدعاء Groq: {exc}") from exc

    return _call_ollama(prompt, json_mode=json_mode, temperature=temperature)


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    cleaned = _clean_response_text(raw_text)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

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