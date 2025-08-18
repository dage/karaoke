from __future__ import annotations

import os
import json
from typing import Optional

import requests
from dotenv import load_dotenv, find_dotenv


# Load environment variables from project .env if present
load_dotenv(find_dotenv())

# Defaults are hard-coded here; can be overridden via environment variables
DEFAULT_API_ENDPOINT: str = os.environ.get("OPENAI_API_ENDPOINT", "https://openrouter.ai/api/v1")
DEFAULT_MODEL: str = os.environ.get("OPENAI_DEFAULT_MODEL", "openai/gpt-5-chat")
DEFAULT_TEMPERATURE: float = 0.0
DEFAULT_MAX_TOKENS: int = 16
DEFAULT_TIMEOUT_SECONDS: float = 60.0


def _headers() -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in environment (.env)")
    # Minimal attribution headers recommended by OpenRouter
    app_title = os.environ.get("APP_NAME", "karaoke-yt")
    referer_host = os.environ.get("APP_REFERER", "https://karaoke-yt.local")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Title": app_title,
        "HTTP-Referer": referer_host,
        "Referer": referer_host,
    }


def query_raw(prompt: str, *, model: Optional[str] = None) -> dict:
    """Send a single-turn chat completion and return the full JSON response."""
    endpoint = DEFAULT_API_ENDPOINT.rstrip("/") + "/chat/completions"
    chosen_model = model or DEFAULT_MODEL

    payload = {
        "model": chosen_model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": DEFAULT_TEMPERATURE,
        "max_tokens": DEFAULT_MAX_TOKENS,
    }

    resp = requests.post(
        endpoint,
        headers=_headers(),
        data=json.dumps(payload),
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    if resp.status_code >= 400:
        # Raise with server-provided body for easier debugging
        raise RuntimeError(f"{resp.status_code} Error from LLM API: {resp.text}")
    # For 2xx, parse JSON
    return resp.json()


def query(prompt: str, *, model: Optional[str] = None) -> str:
    """Send a single-turn chat completion and return the assistant text content.

    Defaults are hard-coded; environment variables can override endpoint/model.
    """
    data = query_raw(prompt, model=model)
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        content = ""
    if isinstance(content, str):
        return content
    return str(content or "")


if __name__ == "__main__":
    # Simple manual test: prints the response
    print(query("Reply with exactly: ok"))


