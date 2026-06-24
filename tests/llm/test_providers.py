from unittest.mock import MagicMock, patch
from app.llm.providers import get_llm


def test_get_llm_returns_openai_for_qwen():
    memory = MagicMock()
    memory.get_var.side_effect = lambda k, default=None: {
        "llm_provider": "qwen",
        "api_key": "hf-test-key",
        "llm_model": "Qwen/Qwen2.5-72B-Instruct",
        "qwen_base_url": "https://router.huggingface.co/v1",
    }.get(k, default)
    with patch("app.llm.providers.ChatOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        llm = get_llm(memory)
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["api_key"] == "hf-test-key"
        assert call_kwargs["model"] == "Qwen/Qwen2.5-72B-Instruct"


def test_get_llm_returns_gemini_for_gemini_provider():
    memory = MagicMock()
    memory.get_var.side_effect = lambda k, default=None: {
        "llm_provider": "gemini",
        "api_key": "gm-test-key",
        "llm_model": "gemini-2.0-flash",
    }.get(k, default)
    with patch("app.llm.providers.ChatGoogleGenerativeAI") as mock_cls:
        mock_cls.return_value.with_retry.return_value = MagicMock()
        llm = get_llm(memory)
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["google_api_key"] == "gm-test-key"
        assert call_kwargs["model"] == "gemini-2.0-flash"
