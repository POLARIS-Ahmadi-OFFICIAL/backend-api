"""LLM provider metadata shared by API and services."""

from typing import Any, Dict, List

LLM_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "qwen": {
        "label": "Qwen (Hugging Face)",
        "api_key_label": "Hugging Face API Key",
        "api_key_help": "https://huggingface.co/settings/tokens",
        "env_vars": ["HUGGINGFACE_API_KEY", "HF_API_KEY", "LLM_API_KEY"],
        "models": [
            "Qwen/Qwen2.5-VL-72B-Instruct",
            "Qwen/Qwen2.5-72B-Instruct",
            "Qwen/Qwen2.5-32B-Instruct",
            "Qwen/Qwen2.5-14B-Instruct",
            "Qwen/Qwen2.5-7B-Instruct",
        ],
        "default_model": "Qwen/Qwen2.5-VL-72B-Instruct",
        "endpoints": [
            {"value": "https://router.huggingface.co/v1", "label": "HF Router (recommended)"},
            {"value": "https://api-inference.huggingface.co/v1", "label": "HF Inference API"},
        ],
    },
    "gemini": {
        "label": "Google Gemini",
        "api_key_label": "Google Gemini API Key",
        "api_key_help": "https://aistudio.google.com/apikey",
        "env_vars": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "LLM_API_KEY"],
        "models": [
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ],
        "default_model": "gemini-2.0-flash-lite",
        "endpoints": [],
    },
}


def list_providers() -> List[Dict[str, Any]]:
    return [{"id": k, **v} for k, v in LLM_PROVIDERS.items()]
