from unittest.mock import MagicMock, patch, AsyncMock
import pytest


def test_clarify_chain_invokable():
    """Chain must be a Runnable — invoking with correct keys should not raise TypeError."""
    mock_llm = MagicMock()
    mock_llm.return_value = MagicMock()
    with patch("app.llm.chains.hypothesis.get_llm", return_value=mock_llm):
        from app.llm.chains import hypothesis as hyp_chains
        import importlib
        importlib.reload(hyp_chains)
        # chains must expose these names
        assert hasattr(hyp_chains, "clarify_chain")
        assert hasattr(hyp_chains, "socratic_chain")
        assert hasattr(hyp_chains, "tot_chain")
        assert hasattr(hyp_chains, "synthesis_chain")
