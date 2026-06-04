"""Performance helpers for the headless hypothesis chat flow."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable, Optional, TypeVar

_logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_CONTEXT_MAX_CHARS = 4500


def env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes")


def fast_submit_enabled() -> bool:
    """One combined LLM call for socratic pass + TOT after clarify (saves ~2 calls)."""
    return env_flag("HYPOTHESIS_FAST_MODE", "1")


def skip_socratic_answers() -> bool:
    return env_flag("HYPOTHESIS_SKIP_SOCRATIC_ANSWERS", "0")


def skip_readiness_check() -> bool:
    """Skip extra LLM call before each hypothesis-stage option pick."""
    return env_flag("HYPOTHESIS_SKIP_READINESS_CHECK", "1")


def skip_analysis_on_generate() -> bool:
    """Return hypothesis only; skip analysis rubric LLM call (saves ~1 call)."""
    return env_flag("HYPOTHESIS_SKIP_ANALYSIS_ON_GENERATE", "0")


def context_max_chars() -> int:
    try:
        return max(500, int(os.getenv("HYPOTHESIS_CONTEXT_MAX_CHARS", str(DEFAULT_CONTEXT_MAX_CHARS))))
    except ValueError:
        return DEFAULT_CONTEXT_MAX_CHARS


def trim_context(context: str, max_chars: Optional[int] = None) -> str:
    """Keep the tail of long context so prompts stay smaller and faster."""
    limit = max_chars if max_chars is not None else context_max_chars()
    text = (context or "").strip()
    if len(text) <= limit:
        return text
    trimmed = text[-limit:]
    return f"[... earlier context truncated ...]\n\n{trimmed}"


def run_in_background(fn: Callable[[], Any], label: str = "hypothesis-bg") -> None:
    """Fire-and-forget for non-critical work (e.g. orchestrator sync)."""

    def _wrapper() -> None:
        try:
            fn()
        except Exception as exc:
            _logger.debug("%s failed: %s", label, exc)

    threading.Thread(target=_wrapper, daemon=True, name=label).start()
