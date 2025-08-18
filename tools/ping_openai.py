#!/usr/bin/env python3
from __future__ import annotations

import sys

from pathlib import Path

# Ensure repository root is on sys.path when running directly
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import time
from datetime import datetime
from scripts.query_llm import query, query_raw  # noqa: E402


PROMPT = "Respond with exactly: ok\nDo not add punctuation, explanation, or quotes. Answer with a single token: ok"

# Toggle to simulate failure (should be False for real test)
FORCE_FAILURE = False

# ANSI colors and symbols
GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
RESET = "\033[0m"
CHECK = "✔"
CROSS = "✗"


def main() -> int:
    try:
        t0 = time.perf_counter()
        full = query_raw(PROMPT)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        response = (full.get("choices") or [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        print(f"Error: {e}")
        return 2

    normalized = (response or "").strip().lower()
    model = full.get("model") or ""
    usage = full.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if normalized == "ok" and not FORCE_FAILURE:
        print(f"{GREEN}{CHECK} Ping OK{RESET}")
        print(f"  Model: {model}")
        print(f"  Latency: {dt_ms:.0f} ms")
        print(f"  Tokens: prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")
        print(f"  Time: {ts}")
        return 0

    # Failure path (forced or actual mismatch)
    reason = "forced failure for testing" if FORCE_FAILURE and normalized == "ok" else f"unexpected content: {response!r}"
    print(f"{RED}{CROSS} Ping FAILED{RESET}")
    print(f"  Reason: {reason}")
    print(f"  Model: {model}")
    print(f"  Latency: {dt_ms:.0f} ms")
    print(f"  Tokens: prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")
    print(f"  Time: {ts}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


