"""
Test configuration for tests/llm/.

On Python 3.9, app.tools.paths uses `str | None` union syntax (Python 3.10+)
which crashes at module load. We pre-stub the memory service so chain modules
can be imported without hitting real I/O or requiring live credentials.

get_llm is patched during all tests in this directory so that:
- chain module reloads work without real LLM credentials
- test_providers.py still tests the real get_llm logic via its own patches
"""
import sys
from unittest.mock import MagicMock, patch

import pytest


def pytest_configure(config):
    """
    Install the memory service stub and pre-import chain modules before
    test collection begins.
    """
    # --- Stub memory service (prevents import of paths.py / database.py) ---
    mock_memory = MagicMock()
    mock_memory_service = MagicMock()
    mock_memory_service.get_memory_manager.return_value = mock_memory
    sys.modules.setdefault("app.services.memory_service", mock_memory_service)

    # --- Pre-import chain modules with a mock LLM so module-level calls succeed ---
    mock_llm = MagicMock()
    with patch("app.llm.providers.get_llm", return_value=mock_llm):
        import app.llm.chains.hypothesis  # noqa: F401
        import app.llm.chains.experiment  # noqa: F401
        import app.llm.chains.analysis    # noqa: F401
        import app.llm.chains.routing     # noqa: F401


@pytest.fixture(autouse=True)
def _patch_providers_get_llm(request):
    """
    Patch app.llm.providers.get_llm for all tests in this directory.

    This is needed because importlib.reload() inside test_chains_hypothesis.py
    re-executes 'from app.llm.providers import get_llm', which would overwrite
    any test-level patch on hypothesis.get_llm. By patching the source function
    at the providers level, reloads pick up the mock automatically.

    test_providers.py tests the real get_llm() logic and uses its own patches
    for ChatOpenAI / ChatGoogleGenerativeAI — those tests do NOT call get_llm
    at module level, so this autouse fixture does not interfere with them.
    """
    mock_llm = MagicMock()
    with patch("app.llm.providers.get_llm", return_value=mock_llm):
        yield
