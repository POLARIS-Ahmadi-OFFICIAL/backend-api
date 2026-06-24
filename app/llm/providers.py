from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.tools.memory import MemoryManager

# Configure retry exception types for Gemini transient errors
try:
    from google.api_core.exceptions import GoogleAPICallError
    _GEMINI_RETRY_TYPES = (GoogleAPICallError,)
except ImportError:
    from langchain_core.exceptions import LangChainException
    _GEMINI_RETRY_TYPES = (LangChainException,)


def get_llm(memory: "MemoryManager") -> BaseChatModel:
    """
    Build a LangChain chat model configured from MemoryManager settings.
    Falls back to env vars when memory values are absent.
    """
    provider = (memory.get_var("llm_provider") or os.getenv("LLM_PROVIDER") or "qwen").lower().strip()
    api_key = memory.get_var("api_key") or os.getenv("LLM_API_KEY") or ""
    model = memory.get_var("llm_model") or os.getenv("LLM_MODEL") or ""

    if provider == "gemini":
        if not api_key:
            _logger.warning(
                "No LLM API key configured (provider=%s); using placeholder — real inference will fail with auth error",
                "gemini",
            )
        llm = ChatGoogleGenerativeAI(
            model=model or "gemini-2.0-flash",
            google_api_key=api_key,
        )
        return llm.with_retry(
            retry_if_exception_type=_GEMINI_RETRY_TYPES,
            wait_exponential_jitter=True,
            stop_after_attempt=3,
        )

    base_url = (
        memory.get_var("qwen_base_url")
        or os.getenv("QWEN_BASE_URL")
        or "https://router.huggingface.co/v1"
    )
    # Use a placeholder key when none is configured so the client object can be
    # constructed without raising at import time; real calls will still fail
    # if the key is genuinely absent.
    effective_key = api_key or "placeholder-not-set"
    if not api_key:
        _logger.warning(
            "No LLM API key configured (provider=%s); using placeholder — real inference will fail with auth error",
            "qwen",
        )
    return ChatOpenAI(
        model=model or "Qwen/Qwen2.5-72B-Instruct",
        api_key=effective_key,
        base_url=base_url,
    )
