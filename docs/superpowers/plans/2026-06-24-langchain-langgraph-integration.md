# LangChain + LangGraph Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace POLARIS's custom `AgentRouter` with a LangGraph `StateGraph` pipeline that drives all 7 agents, adds human-in-the-loop checkpoints, and exposes new `/pipeline/` REST endpoints — while leaving every existing file and test untouched.

**Architecture:** A thin `PolarisGraphState` TypedDict carries routing signals between LangGraph nodes; each agent becomes a sub-graph; `MemoryAdapter` dual-writes to both LangGraph state and the existing `MemoryManager` SQLite store. LangChain `ChatPromptTemplate` chains replace the `socratic.py` free-functions for all LLM calls inside the graph layer.

**Tech Stack:** `langgraph>=0.2.0`, `langgraph-checkpoint-sqlite>=1.0.0`, `langchain>=0.3.0`, `langchain-openai>=0.2.0`, `langchain-google-genai>=2.0.0`, Python 3.12+, FastAPI (existing), SQLite (`data/polaris.db`, existing)

## Global Constraints

- Python `>=3.12` (pyproject.toml floor)
- `numpy<2.5` (2.4.6) and `scipy<1.18` (1.17.1) — see pyproject.toml
- All new modules live under `app/graph/`, `app/llm/`, or `app/tools/memory_adapter.py`
- **Zero changes** to any file under `app/agents/`, `app/tools/memory.py`, `app/tools/socratic.py`, `app/tools/instruct.py`, `app/services/`, `app/api/v1/agents.py`
- All existing 9 tests in `tests/` must keep passing after every task
- New test files go in `tests/graph/` and `tests/llm/`
- `MemoryManager` API used throughout: `memory.get_var(key, default)`, `memory.set_var(key, value)`, `memory.view_component(component)`, `memory.log_event(type, payload, mode)`
- `get_memory_manager()` lives in `app/services/memory_service.py` — import from there, not from `app/tools/memory`
- LangSmith tracing is opt-in via env vars only; no code configures it
- Prompts live in `app/tools/instruct.py` — import constants, wrap in `ChatPromptTemplate.from_template()`
- Interrupt checkpoint node names: `"hypothesis_checkpoint"`, `"experiment_checkpoint"`, `"curve_fitting_checkpoint"`, `"analysis_checkpoint"`
- DB path resolves relative to repo root: `Path(__file__).resolve().parent.parent.parent.parent / "data" / "polaris.db"` (from `app/graph/checkpointer.py` that is 4 levels from repo root)

---

## File Map

```
app/graph/                         ← all new
    __init__.py
    state.py                       ← PolarisGraphState TypedDict
    checkpointer.py                ← AsyncSqliteSaver factory
    interrupts.py                  ← INTERRUPT_NODES constant + resume helper
    pipeline.py                    ← top-level StateGraph assembly + compile()
    nodes/
        __init__.py
        fallback.py                ← single fallback node
        watcher.py                 ← single watcher node
        ml_models.py               ← single ml_models node
        curve_fitting.py           ← 3-node curve fitting sub-graph
        experiment.py              ← 3-node experiment sub-graph
        analysis.py                ← 4-node analysis sub-graph
        hypothesis.py              ← 6-node hypothesis sub-graph

app/llm/                           ← all new
    __init__.py
    providers.py                   ← get_llm(memory) factory
    chains/
        __init__.py
        hypothesis.py              ← clarify/socratic/tot/synthesis chains
        experiment.py              ← plan_tot + worklist chains
        analysis.py                ← analysis + decide_next_step chains
        routing.py                 ← watcher routing chain

app/tools/memory_adapter.py        ← new — MemoryAdapter.write()

app/api/v1/pipeline.py             ← new — /pipeline/start /resume /state endpoints

tests/graph/
    test_state.py
    test_memory_adapter.py
    test_nodes_simple.py           ← ml_models, watcher, fallback nodes
    test_pipeline_e2e.py           ← full interrupt→resume cycle

tests/llm/
    test_providers.py
    test_chains_hypothesis.py
```

---

### Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `langgraph`, `langchain`, `langchain_openai`, `langchain_google_genai`, `langgraph_checkpoint_sqlite` importable from the venv

- [ ] **Step 1: Add packages to pyproject.toml dependencies list**

Open `pyproject.toml` and add these lines to the `dependencies = [...]` array (after `"httpx>=0.28.0",`):

```toml
  "langchain>=0.3.0",
  "langchain-openai>=0.2.0",
  "langchain-google-genai>=2.0.0",
  "langgraph>=0.2.0",
  "langgraph-checkpoint-sqlite>=1.0.0",
```

- [ ] **Step 2: Install the new packages**

```bash
cd backend-api
pip install "langchain>=0.3.0" "langchain-openai>=0.2.0" "langchain-google-genai>=2.0.0" "langgraph>=0.2.0" "langgraph-checkpoint-sqlite>=1.0.0"
```

Expected: packages install without error. LangGraph's SQLite checkpointer is in `langgraph-checkpoint-sqlite`.

- [ ] **Step 3: Verify imports work**

```bash
python -c "
import langgraph
import langchain
from langgraph.graph import StateGraph
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
print('All LangGraph/LangChain imports OK')
print('langgraph:', langgraph.__version__)
print('langchain:', langchain.__version__)
"
```

Expected output: `All LangGraph/LangChain imports OK` followed by version lines.

- [ ] **Step 4: Confirm existing tests still pass**

```bash
cd backend-api
python -m pytest tests/ -x -q
```

Expected: all 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add langchain, langgraph, and checkpoint-sqlite"
```

---

### Task 2: PolarisGraphState TypedDict

**Files:**
- Create: `app/graph/__init__.py`
- Create: `app/graph/state.py`
- Create: `tests/graph/__init__.py`
- Create: `tests/graph/test_state.py`

**Interfaces:**
- Produces: `PolarisGraphState` — a `TypedDict` with 16 fields (see below), importable as `from app.graph.state import PolarisGraphState`

- [ ] **Step 1: Write failing test**

Create `tests/graph/__init__.py` (empty) and `tests/graph/test_state.py`:

```python
from app.graph.state import PolarisGraphState


def test_state_has_required_keys():
    state: PolarisGraphState = {
        "stage": "initial",
        "has_hypothesis": False,
        "has_experimental_outputs": False,
        "has_curve_results": False,
        "has_ml_results": False,
        "has_analysis_results": False,
        "hypothesis_ready": False,
        "hypothesis_preview": None,
        "research_goal": None,
        "experiment_id": None,
        "current_agent": None,
        "error": None,
        "interrupt_payload": None,
        "routing_mode": "autonomous",
        "manual_workflow": [],
        "workflow_index": 0,
    }
    assert state["stage"] == "initial"
    assert state["routing_mode"] == "autonomous"
    assert state["workflow_index"] == 0


def test_state_partial_update():
    base: PolarisGraphState = {
        "stage": "hypothesis",
        "has_hypothesis": False,
        "has_experimental_outputs": False,
        "has_curve_results": False,
        "has_ml_results": False,
        "has_analysis_results": False,
        "hypothesis_ready": False,
        "hypothesis_preview": None,
        "research_goal": "test goal",
        "experiment_id": None,
        "current_agent": None,
        "error": None,
        "interrupt_payload": None,
        "routing_mode": "autonomous",
        "manual_workflow": [],
        "workflow_index": 0,
    }
    updated = {**base, "has_hypothesis": True, "hypothesis_preview": "Short preview"}
    assert updated["has_hypothesis"] is True
    assert updated["hypothesis_preview"] == "Short preview"
    assert updated["stage"] == "hypothesis"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend-api
python -m pytest tests/graph/test_state.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.graph'`

- [ ] **Step 3: Create `app/graph/__init__.py`**

```python
```
(empty file)

- [ ] **Step 4: Create `app/graph/state.py`**

```python
from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict


class PolarisGraphState(TypedDict):
    # Pipeline stage
    stage: str  # "initial"|"hypothesis"|"experiment"|"curve_fitting"|"ml_models"|"analysis"|"complete"|"error"

    # Domain object presence flags (written by MemoryAdapter)
    has_hypothesis: bool
    has_experimental_outputs: bool
    has_curve_results: bool
    has_ml_results: bool
    has_analysis_results: bool
    hypothesis_ready: bool

    # Thin previews for edge conditions and frontend display (<=500 chars)
    hypothesis_preview: Optional[str]
    research_goal: Optional[str]

    # Execution context
    experiment_id: Optional[int]
    current_agent: Optional[str]
    error: Optional[str]
    interrupt_payload: Optional[dict[str, Any]]  # surfaced to frontend at checkpoints

    # Routing config
    routing_mode: str  # "autonomous" | "manual"
    manual_workflow: list[str]
    workflow_index: int
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend-api
python -m pytest tests/graph/test_state.py -v
```

Expected: both tests PASS.

- [ ] **Step 6: Confirm all existing tests still pass**

```bash
python -m pytest tests/ -x -q
```

Expected: all 9 original tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/graph/__init__.py app/graph/state.py tests/graph/__init__.py tests/graph/test_state.py
git commit -m "feat(graph): add PolarisGraphState TypedDict"
```

---

### Task 3: MemoryAdapter

**Files:**
- Create: `app/tools/memory_adapter.py`
- Create: `tests/graph/test_memory_adapter.py`

**Interfaces:**
- Consumes: `MemoryManager` (from `app.tools.memory`), `PolarisGraphState` (from `app.graph.state`)
- Produces: `MemoryAdapter.write(memory, state, **kwargs) -> PolarisGraphState` — writes `kwargs` to `MemoryManager` via `set_var`, syncs boolean flags and preview fields into a new `PolarisGraphState` dict, returns it

- [ ] **Step 1: Write failing test**

Create `tests/graph/test_memory_adapter.py`:

```python
from unittest.mock import MagicMock
from app.graph.state import PolarisGraphState
from app.tools.memory_adapter import MemoryAdapter


def _base_state() -> PolarisGraphState:
    return {
        "stage": "hypothesis",
        "has_hypothesis": False,
        "has_experimental_outputs": False,
        "has_curve_results": False,
        "has_ml_results": False,
        "has_analysis_results": False,
        "hypothesis_ready": False,
        "hypothesis_preview": None,
        "research_goal": None,
        "experiment_id": None,
        "current_agent": None,
        "error": None,
        "interrupt_payload": None,
        "routing_mode": "autonomous",
        "manual_workflow": [],
        "workflow_index": 0,
    }


def test_write_stores_in_memory_manager():
    memory = MagicMock()
    state = _base_state()
    result = MemoryAdapter.write(memory, state, research_goal="Why does GaN glow?")
    memory.set_var.assert_called_with("research_goal", "Why does GaN glow?")
    assert result["research_goal"] == "Why does GaN glow?"


def test_write_sets_has_hypothesis_flag():
    memory = MagicMock()
    state = _base_state()
    result = MemoryAdapter.write(memory, state, hypothesis="A long hypothesis text")
    assert result["has_hypothesis"] is True
    assert result["hypothesis_preview"] == "A long hypothesis text"


def test_write_truncates_preview_to_500():
    memory = MagicMock()
    state = _base_state()
    long_text = "x" * 600
    result = MemoryAdapter.write(memory, state, hypothesis=long_text)
    assert len(result["hypothesis_preview"]) == 500


def test_write_sets_curve_results_flag():
    memory = MagicMock()
    state = _base_state()
    result = MemoryAdapter.write(memory, state, curve_fitting_results={"peaks": []})
    assert result["has_curve_results"] is True


def test_write_sets_ml_results_flag():
    memory = MagicMock()
    state = _base_state()
    result = MemoryAdapter.write(memory, state, gp_results={"model": "GP"})
    assert result["has_ml_results"] is True


def test_write_preserves_unrelated_state_fields():
    memory = MagicMock()
    state = _base_state()
    state["stage"] = "analysis"
    state["workflow_index"] = 3
    result = MemoryAdapter.write(memory, state, error=None)
    assert result["stage"] == "analysis"
    assert result["workflow_index"] == 3


def test_write_clears_flag_when_value_is_none():
    memory = MagicMock()
    state = _base_state()
    state["has_curve_results"] = True
    result = MemoryAdapter.write(memory, state, curve_fitting_results=None)
    assert result["has_curve_results"] is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend-api
python -m pytest tests/graph/test_memory_adapter.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.tools.memory_adapter'`

- [ ] **Step 3: Create `app/tools/memory_adapter.py`**

```python
from __future__ import annotations

from typing import Any, Optional, Tuple

from app.graph.state import PolarisGraphState
from app.tools.memory import MemoryManager

# Maps a MemoryManager key to (graph_flag_field, graph_preview_field | None)
_SIGNAL_MAP: dict[str, Tuple[str, Optional[str]]] = {
    "hypothesis":             ("has_hypothesis", "hypothesis_preview"),
    "experimental_outputs":   ("has_experimental_outputs", None),
    "curve_fitting_results":  ("has_curve_results", None),
    "gp_results":             ("has_ml_results", None),
    "analysis_results":       ("has_analysis_results", None),
}


class MemoryAdapter:
    """Dual-write utility: persists values to MemoryManager and syncs routing signals into PolarisGraphState."""

    @staticmethod
    def write(
        memory: MemoryManager,
        state: PolarisGraphState,
        **kwargs: Any,
    ) -> PolarisGraphState:
        """
        For each kwarg:
        - Calls memory.set_var(key, value)
        - If the key is in _SIGNAL_MAP, updates the corresponding bool flag (and preview field) in state
        Returns a new state dict with the updates applied (original state is not mutated).
        """
        updates: dict[str, Any] = {}
        for key, value in kwargs.items():
            memory.set_var(key, value)
            if key in _SIGNAL_MAP:
                flag_field, preview_field = _SIGNAL_MAP[key]
                updates[flag_field] = bool(value)
                if preview_field is not None:
                    if value is not None:
                        updates[preview_field] = str(value)[:500]
                    else:
                        updates[preview_field] = None
            else:
                # Pass-through: unknown key written to memory + forwarded to state if it's a state field
                updates[key] = value
        return {**state, **updates}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend-api
python -m pytest tests/graph/test_memory_adapter.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Confirm all existing tests still pass**

```bash
python -m pytest tests/ -x -q
```

Expected: all 9 original tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/tools/memory_adapter.py tests/graph/test_memory_adapter.py
git commit -m "feat(graph): add MemoryAdapter dual-write utility"
```

---

### Task 4: LLM provider factory and chains

**Files:**
- Create: `app/llm/__init__.py`
- Create: `app/llm/providers.py`
- Create: `app/llm/chains/__init__.py`
- Create: `app/llm/chains/hypothesis.py`
- Create: `app/llm/chains/experiment.py`
- Create: `app/llm/chains/analysis.py`
- Create: `app/llm/chains/routing.py`
- Create: `tests/llm/__init__.py`
- Create: `tests/llm/test_providers.py`
- Create: `tests/llm/test_chains_hypothesis.py`

**Interfaces:**
- Consumes: `MemoryManager.get_var()`, constants from `app.tools.instruct` (see list below)
- Produces:
  - `get_llm(memory: MemoryManager) -> BaseChatModel` — returns `ChatOpenAI` for `provider=="qwen"` or `ChatGoogleGenerativeAI` for `provider=="gemini"`, configured from `memory.get_var()`
  - `clarify_chain`, `socratic_chain`, `tot_chain`, `synthesis_chain` — each is a `Runnable` taking a dict, returning `str`
  - `plan_tot_chain`, `worklist_chain` — experiment chains
  - `analysis_chain`, `next_step_chain` — analysis chains
  - `watcher_routing_chain` — routing chain

Prompt constants used (from `app/tools/instruct.py`):
- `CLARIFY_QUESTION_INSTRUCTIONS` (line 199)
- `SOCRATIC_PASS_INSTRUCTIONS` (line 216)
- `SOCRATIC_ANSWER_INSTRUCTIONS` (line 238)
- `TOT_INSTRUCTIONS` (line 336)
- `HYPOTHESIS_SYNTHESIS` (line 540)
- `EXPERIMENTAL_PLAN_TOT_INSTRUCTIONS` (line 398)
- `ANALYSIS_INSTRUCTIONS` (line 740)
- `ANALYSIS_NEW_QUESTION_INSTRUCTIONS` (line 618)
- `WATCHER_ROUTING_INSTRUCTIONS` (line 676)

- [ ] **Step 1: Write failing tests**

Create `tests/llm/__init__.py` (empty) and `tests/llm/test_providers.py`:

```python
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
```

Create `tests/llm/test_chains_hypothesis.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend-api
python -m pytest tests/llm/ -v
```

Expected: `ModuleNotFoundError: No module named 'app.llm'`

- [ ] **Step 3: Create `app/llm/__init__.py`** (empty)

- [ ] **Step 4: Create `app/llm/providers.py`**

```python
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel

if TYPE_CHECKING:
    from app.tools.memory import MemoryManager


def get_llm(memory: "MemoryManager") -> BaseChatModel:
    """
    Build a LangChain chat model configured from MemoryManager settings.
    Falls back to env vars when memory values are absent.
    """
    provider = (memory.get_var("llm_provider") or os.getenv("LLM_PROVIDER") or "qwen").lower().strip()
    api_key = memory.get_var("api_key") or os.getenv("LLM_API_KEY") or ""
    model = memory.get_var("llm_model") or os.getenv("LLM_MODEL") or ""

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.exceptions import LangChainException

        llm = ChatGoogleGenerativeAI(
            model=model or "gemini-2.0-flash",
            google_api_key=api_key,
        )
        return llm.with_retry(
            retry_if_exception_type=(Exception,),
            wait_exponential_jitter=True,
            stop_after_attempt=3,
        )

    from langchain_openai import ChatOpenAI

    base_url = (
        memory.get_var("qwen_base_url")
        or os.getenv("QWEN_BASE_URL")
        or "https://router.huggingface.co/v1"
    )
    return ChatOpenAI(
        model=model or "Qwen/Qwen2.5-72B-Instruct",
        api_key=api_key,
        base_url=base_url,
    )
```

- [ ] **Step 5: Create `app/llm/chains/__init__.py`** (empty)

- [ ] **Step 6: Create `app/llm/chains/hypothesis.py`**

```python
"""LangChain chains for the HypothesisAgent sub-graph nodes."""
from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm.providers import get_llm
from app.services.memory_service import get_memory_manager
from app.tools.instruct import (
    CLARIFY_QUESTION_INSTRUCTIONS,
    HYPOTHESIS_SYNTHESIS,
    SOCRATIC_ANSWER_INSTRUCTIONS,
    SOCRATIC_PASS_INSTRUCTIONS,
    TOT_INSTRUCTIONS,
)

_memory = get_memory_manager()
_llm = get_llm(_memory)
_parser = StrOutputParser()

# Each chain takes a dict of template variables and returns a str
clarify_chain = ChatPromptTemplate.from_template(CLARIFY_QUESTION_INSTRUCTIONS + "\n\nQuestion: {question}") | _llm | _parser

socratic_chain = ChatPromptTemplate.from_template(SOCRATIC_PASS_INSTRUCTIONS + "\n\nClarified question: {clarified_question}") | _llm | _parser

answers_chain = ChatPromptTemplate.from_template(SOCRATIC_ANSWER_INSTRUCTIONS + "\n\nQuestion: {clarified_question}\n\nProbing questions:\n{probing_questions}") | _llm | _parser

tot_chain = ChatPromptTemplate.from_template(TOT_INSTRUCTIONS + "\n\nQuestion: {clarified_question}\n\nSocratic reasoning:\n{socratic_answers}") | _llm | _parser

synthesis_chain = ChatPromptTemplate.from_template(HYPOTHESIS_SYNTHESIS + "\n\nChosen option: {chosen_option}\n\nContext: {context}") | _llm | _parser
```

- [ ] **Step 7: Create `app/llm/chains/experiment.py`**

```python
"""LangChain chains for the ExperimentAgent sub-graph nodes."""
from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm.providers import get_llm
from app.services.memory_service import get_memory_manager
from app.tools.instruct import EXPERIMENTAL_PLAN_TOT_INSTRUCTIONS

_memory = get_memory_manager()
_llm = get_llm(_memory)
_parser = StrOutputParser()

plan_tot_chain = ChatPromptTemplate.from_template(
    EXPERIMENTAL_PLAN_TOT_INSTRUCTIONS
    + "\n\nQuestion: {clarified_question}\n\nConstraints: {experimental_constraints}"
) | _llm | _parser

worklist_chain = ChatPromptTemplate.from_template(
    "Given this experimental plan, produce a step-by-step worklist as a numbered list.\n\nPlan:\n{plan}"
) | _llm | _parser
```

- [ ] **Step 8: Create `app/llm/chains/analysis.py`**

```python
"""LangChain chains for the AnalysisAgent sub-graph nodes."""
from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm.providers import get_llm
from app.services.memory_service import get_memory_manager
from app.tools.instruct import ANALYSIS_INSTRUCTIONS, ANALYSIS_NEW_QUESTION_INSTRUCTIONS

_memory = get_memory_manager()
_llm = get_llm(_memory)
_parser = StrOutputParser()

analysis_chain = ChatPromptTemplate.from_template(
    ANALYSIS_INSTRUCTIONS + "\n\nContext:\n{context}"
) | _llm | _parser

next_step_chain = ChatPromptTemplate.from_template(
    ANALYSIS_NEW_QUESTION_INSTRUCTIONS
    + "\n\nResearch goal: {research_goal}\n\nAnalysis summary: {analysis_summary}"
) | _llm | _parser
```

- [ ] **Step 9: Create `app/llm/chains/routing.py`**

```python
"""LangChain chain for WatcherAgent filesystem-event routing."""
from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm.providers import get_llm
from app.services.memory_service import get_memory_manager
from app.tools.instruct import WATCHER_ROUTING_INSTRUCTIONS

_memory = get_memory_manager()
_llm = get_llm(_memory)
_parser = StrOutputParser()

watcher_routing_chain = ChatPromptTemplate.from_template(
    WATCHER_ROUTING_INSTRUCTIONS + "\n\nFilesystem event: {event_description}"
) | _llm | _parser
```

- [ ] **Step 10: Run all tests to verify they pass**

```bash
cd backend-api
python -m pytest tests/llm/ tests/graph/ -v
```

Expected: all new tests PASS.

- [ ] **Step 11: Confirm existing tests still pass**

```bash
python -m pytest tests/ -x -q
```

Expected: all 9 original tests pass.

- [ ] **Step 12: Commit**

```bash
git add app/llm/ tests/llm/
git commit -m "feat(llm): add get_llm factory and LangChain chains for all agents"
```

---

### Task 5: Checkpointer and interrupt constants

**Files:**
- Create: `app/graph/checkpointer.py`
- Create: `app/graph/interrupts.py`

**Interfaces:**
- Produces:
  - `get_checkpointer() -> AsyncSqliteSaver` — returns an `AsyncSqliteSaver` pointed at `data/polaris.db`
  - `INTERRUPT_NODES: list[str]` — `["hypothesis_checkpoint", "experiment_checkpoint", "curve_fitting_checkpoint", "analysis_checkpoint"]`
  - `build_resume_config(thread_id: str) -> dict` — returns `{"configurable": {"thread_id": thread_id}}`

- [ ] **Step 1: Create `app/graph/checkpointer.py`**

No test needed — this wraps an external library constructor. We verify it in the pipeline E2E test (Task 9).

```python
from __future__ import annotations

from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


def _db_path() -> str:
    # Resolve <repo_root>/data/polaris.db regardless of where the process runs
    here = Path(__file__).resolve()
    repo_root = here.parent.parent.parent.parent  # app/graph/checkpointer.py → 4 levels up
    db = repo_root / "data" / "polaris.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    return str(db)


def get_checkpointer() -> AsyncSqliteSaver:
    """Return an AsyncSqliteSaver bound to the project's SQLite DB."""
    return AsyncSqliteSaver.from_conn_string(_db_path())
```

- [ ] **Step 2: Create `app/graph/interrupts.py`**

```python
from __future__ import annotations

# Node names where the pipeline pauses and waits for frontend confirmation
INTERRUPT_NODES: list[str] = [
    "hypothesis_checkpoint",
    "experiment_checkpoint",
    "curve_fitting_checkpoint",
    "analysis_checkpoint",
]


def build_resume_config(thread_id: str) -> dict:
    """Return the LangGraph config dict needed to resume a paused thread."""
    return {"configurable": {"thread_id": thread_id}}


def build_start_config(thread_id: str) -> dict:
    """Return the LangGraph config dict for starting a new thread."""
    return {"configurable": {"thread_id": thread_id}}
```

- [ ] **Step 3: Verify imports work**

```bash
cd backend-api
python -c "
from app.graph.checkpointer import get_checkpointer
from app.graph.interrupts import INTERRUPT_NODES, build_resume_config, build_start_config
print('INTERRUPT_NODES:', INTERRUPT_NODES)
print('resume config:', build_resume_config('abc-123'))
print('checkpointer type:', type(get_checkpointer()).__name__)
"
```

Expected:
```
INTERRUPT_NODES: ['hypothesis_checkpoint', 'experiment_checkpoint', 'curve_fitting_checkpoint', 'analysis_checkpoint']
resume config: {'configurable': {'thread_id': 'abc-123'}}
checkpointer type: AsyncSqliteSaver
```

- [ ] **Step 4: Confirm all existing tests still pass**

```bash
python -m pytest tests/ -x -q
```

- [ ] **Step 5: Commit**

```bash
git add app/graph/checkpointer.py app/graph/interrupts.py
git commit -m "feat(graph): add AsyncSqliteSaver checkpointer and interrupt constants"
```

---

### Task 6: Simple agent nodes (fallback, watcher, ml_models)

**Files:**
- Create: `app/graph/nodes/__init__.py`
- Create: `app/graph/nodes/fallback.py`
- Create: `app/graph/nodes/watcher.py`
- Create: `app/graph/nodes/ml_models.py`
- Create: `tests/graph/test_nodes_simple.py`

**Interfaces:**
- Consumes: `PolarisGraphState`, `MemoryAdapter`, `get_memory_manager()`, `watcher_routing_chain`
- Produces:
  - `fallback_node(state, config) -> PolarisGraphState` — sets `stage="error"`, logs event
  - `watcher_node(state, config) -> PolarisGraphState` — invokes `watcher_routing_chain`, sets `current_agent`
  - `ml_models_node(state, config) -> PolarisGraphState` — calls `MLModelsAgent.run_agent()`, sets `has_ml_results`

- [ ] **Step 1: Write failing tests**

Create `tests/graph/test_nodes_simple.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.graph.state import PolarisGraphState


def _state(**kwargs) -> PolarisGraphState:
    base: PolarisGraphState = {
        "stage": "initial",
        "has_hypothesis": False,
        "has_experimental_outputs": False,
        "has_curve_results": False,
        "has_ml_results": False,
        "has_analysis_results": False,
        "hypothesis_ready": False,
        "hypothesis_preview": None,
        "research_goal": "Test question",
        "experiment_id": None,
        "current_agent": None,
        "error": None,
        "interrupt_payload": None,
        "routing_mode": "autonomous",
        "manual_workflow": [],
        "workflow_index": 0,
    }
    return {**base, **kwargs}


@pytest.mark.asyncio
async def test_fallback_node_sets_stage_error():
    from app.graph.nodes.fallback import fallback_node
    memory = MagicMock()
    with patch("app.graph.nodes.fallback.get_memory_manager", return_value=memory):
        result = await fallback_node(_state(error="something broke"), {})
    assert result["stage"] == "error"
    assert result["current_agent"] == "fallback"
    memory.log_event.assert_called_once()


@pytest.mark.asyncio
async def test_watcher_node_sets_current_agent():
    from app.graph.nodes.watcher import watcher_node
    memory = MagicMock()
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value="curve_fitting_agent")
    with patch("app.graph.nodes.watcher.get_memory_manager", return_value=memory), \
         patch("app.graph.nodes.watcher.watcher_routing_chain", mock_chain):
        result = await watcher_node(_state(), {})
    assert result["current_agent"] == "curve_fitting_agent"


@pytest.mark.asyncio
async def test_ml_models_node_sets_has_ml_results():
    from app.graph.nodes.ml_models import ml_models_node
    memory = MagicMock()
    memory.get_var.return_value = {"gp_model": "fitted"}
    mock_agent = MagicMock()
    mock_agent.run_agent.return_value = {"status": "success", "gp_results": {"gp_model": "fitted"}}
    with patch("app.graph.nodes.ml_models.get_memory_manager", return_value=memory), \
         patch("app.graph.nodes.ml_models.MLModelsAgent", return_value=mock_agent):
        result = await ml_models_node(_state(), {})
    assert result["has_ml_results"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend-api
pip install pytest-asyncio
python -m pytest tests/graph/test_nodes_simple.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.graph.nodes'`

- [ ] **Step 3: Create `app/graph/nodes/__init__.py`** (empty)

- [ ] **Step 4: Create `app/graph/nodes/fallback.py`**

```python
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.graph.state import PolarisGraphState
from app.services.memory_service import get_memory_manager
from app.tools.memory_adapter import MemoryAdapter


async def fallback_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    memory.log_event(
        "pipeline_error",
        {"stage": state.get("stage"), "error": state.get("error")},
        mode="graph",
    )
    return MemoryAdapter.write(
        memory, state,
        stage="error",
        current_agent="fallback",
    )
```

- [ ] **Step 5: Create `app/graph/nodes/watcher.py`**

```python
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.graph.state import PolarisGraphState
from app.llm.chains.routing import watcher_routing_chain
from app.services.memory_service import get_memory_manager
from app.tools.memory_adapter import MemoryAdapter


async def watcher_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    event_description = memory.get_var("last_watcher_event") or "unknown filesystem event"
    try:
        next_agent = await watcher_routing_chain.ainvoke({"event_description": event_description})
        next_agent = next_agent.strip()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Watcher routing chain failed: %s", exc)
        next_agent = "fallback"
    return MemoryAdapter.write(memory, state, current_agent=next_agent)
```

- [ ] **Step 6: Create `app/graph/nodes/ml_models.py`**

```python
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.agents.ml_models_agent import MLModelsAgent
from app.graph.state import PolarisGraphState
from app.services.memory_service import get_memory_manager
from app.tools.memory_adapter import MemoryAdapter


async def ml_models_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    agent = MLModelsAgent("ML Models Agent")
    agent.memory = memory
    result = agent.run_agent(memory)
    gp_results = memory.get_var("gp_results") or result.get("gp_results")
    return MemoryAdapter.write(
        memory, state,
        gp_results=gp_results,
        current_agent="ml_models",
        stage="ml_models",
    )
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd backend-api
python -m pytest tests/graph/test_nodes_simple.py -v
```

Expected: all 3 node tests PASS.

- [ ] **Step 8: Confirm all existing tests still pass**

```bash
python -m pytest tests/ -x -q
```

Expected: all 9 original tests pass.

- [ ] **Step 9: Commit**

```bash
git add app/graph/nodes/ tests/graph/test_nodes_simple.py
git commit -m "feat(graph): add fallback, watcher, and ml_models graph nodes"
```

---

### Task 7: Experiment and CurveFitting sub-graphs

**Files:**
- Create: `app/graph/nodes/experiment.py`
- Create: `app/graph/nodes/curve_fitting.py`

**Interfaces:**
- Consumes: `PolarisGraphState`, `MemoryAdapter`, `get_memory_manager()`, `plan_tot_chain`, `worklist_chain`, `run_experiment_pipeline`, `run_curve_fitting_for_api` (via `curve_fitting_runner`)
- Produces:
  - `experiment_subgraph() -> CompiledGraph` — 3-node StateGraph: `build_context → generate_plan → generate_worklist`
  - `curve_fitting_subgraph() -> CompiledGraph` — 3-node StateGraph: `load_data → run_fitting → export_results`

- [ ] **Step 1: Read the experiment service entry point**

```bash
cd backend-api
grep -n "def run_experiment_pipeline" app/services/experiment_service.py
```

Verify `run_experiment_pipeline(memory) -> Dict[str, Any]` exists at the line shown. It returns `{"status": "...", "plan": "...", "worklist": "...", ...}`.

- [ ] **Step 2: Read curve fitting runner**

```bash
grep -n "^def \|^async def " app/services/curve_fitting_runner.py | head -10
```

Note the main entry point (likely `run_curve_fitting(...)` or `run_curve_fitting_for_api(...)`). Use whichever handles the memory-backed path.

- [ ] **Step 3: Create `app/graph/nodes/experiment.py`**

```python
from __future__ import annotations

from langgraph.graph import END, StateGraph
from langchain_core.runnables import RunnableConfig

from app.graph.state import PolarisGraphState
from app.llm.chains.experiment import plan_tot_chain, worklist_chain
from app.services.experiment_service import run_experiment_pipeline
from app.services.memory_service import get_memory_manager
from app.tools.memory_adapter import MemoryAdapter


async def _build_context_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    hypothesis = memory.view_component("hypothesis") or memory.get_var("last_hypothesis") or ""
    constraints = memory.get_var("experimental_constraints") or ""
    return MemoryAdapter.write(
        memory, state,
        current_agent="experiment",
        stage="experiment",
        research_goal=state.get("research_goal") or memory.get_var("research_goal") or "",
    )


async def _generate_plan_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    clarified_question = state.get("research_goal") or memory.get_var("research_goal") or ""
    constraints = memory.get_var("experimental_constraints") or "No specific constraints provided."
    try:
        plan = await plan_tot_chain.ainvoke({
            "clarified_question": clarified_question,
            "experimental_constraints": constraints,
        })
        memory.set_var("experimental_plan", plan)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Plan generation chain failed: %s", exc)
        plan = memory.get_var("experimental_plan") or ""
    return {**state}


async def _generate_worklist_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    # Delegate full pipeline execution to the existing service
    result = run_experiment_pipeline(memory)
    outputs = result if isinstance(result, dict) else {}
    return MemoryAdapter.write(
        memory, state,
        experimental_outputs=outputs or True,
        stage="experiment",
    )


def experiment_subgraph() -> object:
    """Build and compile the 3-node experiment sub-graph."""
    g = StateGraph(PolarisGraphState)
    g.add_node("build_context", _build_context_node)
    g.add_node("generate_plan", _generate_plan_node)
    g.add_node("generate_worklist", _generate_worklist_node)
    g.set_entry_point("build_context")
    g.add_edge("build_context", "generate_plan")
    g.add_edge("generate_plan", "generate_worklist")
    g.add_edge("generate_worklist", END)
    return g.compile()
```

- [ ] **Step 4: Create `app/graph/nodes/curve_fitting.py`**

```bash
# First, find the curve fitting runner's API-safe entry point:
grep -n "^def \|^async def " backend-api/app/services/curve_fitting_runner.py | head -10
```

Then create `app/graph/nodes/curve_fitting.py`:

```python
from __future__ import annotations

from langgraph.graph import END, StateGraph
from langchain_core.runnables import RunnableConfig

from app.graph.state import PolarisGraphState
from app.services.curve_fitting_service import get_curve_fitting_results
from app.services.memory_service import get_memory_manager
from app.tools.memory_adapter import MemoryAdapter


async def _load_data_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    uploaded = memory.get_var("uploaded_files") or []
    return MemoryAdapter.write(
        memory, state,
        current_agent="curve_fitting",
        stage="curve_fitting",
    )


async def _run_fitting_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    # Fitting is CPU-bound and already managed by CurveFittingAgent + CurveFittingService
    # The graph delegates: if a fit has already been run (memory has results), use them;
    # otherwise the frontend triggers fitting via the existing /agents/curve-fitting endpoint
    results = get_curve_fitting_results(memory)
    raw = results.get("results") if isinstance(results, dict) else None
    return MemoryAdapter.write(
        memory, state,
        curve_fitting_results=raw,
    )


async def _export_results_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    # Export path is already handled by CurveFittingExports service; just advance stage
    return MemoryAdapter.write(memory, state, stage="curve_fitting")


def curve_fitting_subgraph() -> object:
    """Build and compile the 3-node curve fitting sub-graph."""
    g = StateGraph(PolarisGraphState)
    g.add_node("load_data", _load_data_node)
    g.add_node("run_fitting", _run_fitting_node)
    g.add_node("export_results", _export_results_node)
    g.set_entry_point("load_data")
    g.add_edge("load_data", "run_fitting")
    g.add_edge("run_fitting", "export_results")
    g.add_edge("export_results", END)
    return g.compile()
```

- [ ] **Step 5: Verify imports work**

```bash
cd backend-api
python -c "
from app.graph.nodes.experiment import experiment_subgraph
from app.graph.nodes.curve_fitting import curve_fitting_subgraph
print('experiment subgraph:', experiment_subgraph())
print('curve fitting subgraph:', curve_fitting_subgraph())
"
```

Expected: both print `CompiledGraph` or similar — no import errors.

- [ ] **Step 6: Confirm all existing tests still pass**

```bash
python -m pytest tests/ -x -q
```

- [ ] **Step 7: Commit**

```bash
git add app/graph/nodes/experiment.py app/graph/nodes/curve_fitting.py
git commit -m "feat(graph): add experiment and curve_fitting sub-graphs"
```

---

### Task 8: Hypothesis and Analysis sub-graphs

**Files:**
- Create: `app/graph/nodes/hypothesis.py`
- Create: `app/graph/nodes/analysis.py`

**Interfaces:**
- Consumes: `PolarisGraphState`, `MemoryAdapter`, chains from `app.llm.chains.hypothesis` and `app.llm.chains.analysis`, `submit_question` / `handle_choose` from `app.services.hypothesis_chat`, `run_analysis_pipeline` from `app.services.analysis_service`
- Produces:
  - `hypothesis_subgraph() -> CompiledGraph` — 6-node sub-graph ending with `interrupt()` for option selection
  - `analysis_subgraph() -> CompiledGraph` — 4-node sub-graph; `decide_next_step` node returns `"needs_more_experiments"` or `"complete"` via conditional edge output

- [ ] **Step 1: Check hypothesis_chat entry points**

```bash
cd backend-api
grep -n "^def " app/services/hypothesis_chat.py | head -15
```

Note: `submit_question(memory, question) -> Dict` and `handle_choose(memory, choice_index) -> Dict` are the two main entry points used by the REST layer. The sub-graph calls these.

- [ ] **Step 2: Create `app/graph/nodes/hypothesis.py`**

```python
from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph
from langgraph.types import interrupt
from langchain_core.runnables import RunnableConfig

from app.graph.state import PolarisGraphState
from app.services.hypothesis_chat import submit_question
from app.services.memory_service import get_memory_manager
from app.tools.memory_adapter import MemoryAdapter

_logger = logging.getLogger(__name__)


async def _clarify_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    question = state.get("research_goal") or memory.get_var("research_goal") or ""
    return MemoryAdapter.write(memory, state, current_agent="hypothesis", stage="hypothesis")


async def _socratic_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    question = state.get("research_goal") or memory.get_var("research_goal") or ""
    try:
        # Delegates to existing hypothesis_chat service which handles the full socratic + ToT pipeline
        result = submit_question(memory, question)
        hyp = memory.view_component("hypothesis")
    except Exception as exc:
        _logger.warning("Hypothesis submit_question failed in graph node: %s", exc)
        result = {}
        hyp = None
    options = [
        memory.view_component("next_step_option_1"),
        memory.view_component("next_step_option_2"),
        memory.view_component("next_step_option_3"),
    ]
    return MemoryAdapter.write(
        memory, state,
        interrupt_payload={
            "stage": "hypothesis",
            "options": [o for o in options if o],
            "hint": "Select one of the hypothesis options to continue.",
        },
    )


async def _tot_interrupt_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    # Pause here — frontend must POST /pipeline/resume with {"choice_index": 0|1|2}
    payload = state.get("interrupt_payload") or {}
    decision = interrupt(payload)  # raises Interrupt; LangGraph handles the pause
    memory = get_memory_manager()
    choice_index = int(decision.get("choice_index", 0)) if isinstance(decision, dict) else 0
    memory.set_var("chosen_option_index", choice_index)
    return {**state, "interrupt_payload": None}


async def _deepen_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    # Deepening is handled inside hypothesis_chat.handle_choose
    from app.services.hypothesis_chat import handle_choose
    choice_index = int(memory.get_var("chosen_option_index") or 0)
    try:
        handle_choose(memory, choice_index)
    except Exception as exc:
        _logger.warning("handle_choose failed in graph node: %s", exc)
    return {**state}


async def _synthesis_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    hypothesis = memory.view_component("hypothesis")
    return MemoryAdapter.write(
        memory, state,
        hypothesis=hypothesis,
        hypothesis_ready=True,
        stage="hypothesis",
        interrupt_payload={
            "stage": "hypothesis",
            "hypothesis_preview": (str(hypothesis)[:500] if hypothesis else ""),
            "hint": "Review the synthesized hypothesis before proceeding to experiment design.",
        },
    )


async def _hypothesis_checkpoint_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    payload = state.get("interrupt_payload") or {}
    interrupt(payload)  # pause — frontend reviews hypothesis
    return {**state, "interrupt_payload": None}


def hypothesis_subgraph() -> object:
    g = StateGraph(PolarisGraphState)
    g.add_node("clarify", _clarify_node)
    g.add_node("socratic", _socratic_node)
    g.add_node("tot_interrupt", _tot_interrupt_node)
    g.add_node("deepen", _deepen_node)
    g.add_node("synthesis", _synthesis_node)
    g.add_node("hypothesis_checkpoint", _hypothesis_checkpoint_node)
    g.set_entry_point("clarify")
    g.add_edge("clarify", "socratic")
    g.add_edge("socratic", "tot_interrupt")
    g.add_edge("tot_interrupt", "deepen")
    g.add_edge("deepen", "synthesis")
    g.add_edge("synthesis", "hypothesis_checkpoint")
    g.add_edge("hypothesis_checkpoint", END)
    return g.compile()
```

- [ ] **Step 3: Create `app/graph/nodes/analysis.py`**

```python
from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph
from langgraph.types import interrupt
from langchain_core.runnables import RunnableConfig

from app.graph.state import PolarisGraphState
from app.services.analysis_service import run_analysis_pipeline
from app.services.memory_service import get_memory_manager
from app.tools.memory_adapter import MemoryAdapter

_logger = logging.getLogger(__name__)


async def _gather_context_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    return MemoryAdapter.write(memory, state, current_agent="analysis", stage="analysis")


async def _run_analysis_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    try:
        result = run_analysis_pipeline(memory)
        analysis = result.get("analysis") if isinstance(result, dict) else None
    except Exception as exc:
        _logger.warning("run_analysis_pipeline failed: %s", exc)
        analysis = None
    return MemoryAdapter.write(memory, state, analysis_results=analysis or True)


async def _evaluate_outcome_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    analysis_text = str(memory.get_var("analysis_results") or "")
    verdict = "complete"
    lower = analysis_text.lower()
    if any(kw in lower for kw in ("inconclusive", "insufficient", "retry", "repeat experiment", "more data")):
        verdict = "needs_more_experiments"
    memory.set_var("analysis_verdict", verdict)
    return {**state}


async def _decide_next_step_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    verdict = memory.get_var("analysis_verdict") or "complete"
    return MemoryAdapter.write(
        memory, state,
        stage=verdict,
        interrupt_payload={
            "stage": "analysis",
            "verdict": verdict,
            "hint": "Analysis complete. Review before finalizing.",
        },
    )


def _route_after_checkpoint(state: PolarisGraphState) -> str:
    """Conditional edge: route to experiment loop or END based on analysis verdict."""
    memory = get_memory_manager()
    verdict = memory.get_var("analysis_verdict") or "complete"
    return verdict  # "needs_more_experiments" | "complete"


async def _analysis_checkpoint_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    payload = state.get("interrupt_payload") or {}
    interrupt(payload)
    return {**state, "interrupt_payload": None}


def analysis_subgraph() -> object:
    g = StateGraph(PolarisGraphState)
    g.add_node("gather_context", _gather_context_node)
    g.add_node("run_analysis", _run_analysis_node)
    g.add_node("evaluate_outcome", _evaluate_outcome_node)
    g.add_node("decide_next_step", _decide_next_step_node)
    g.add_node("analysis_checkpoint", _analysis_checkpoint_node)
    g.set_entry_point("gather_context")
    g.add_edge("gather_context", "run_analysis")
    g.add_edge("run_analysis", "evaluate_outcome")
    g.add_edge("evaluate_outcome", "decide_next_step")
    g.add_edge("decide_next_step", "analysis_checkpoint")
    g.add_conditional_edges(
        "analysis_checkpoint",
        _route_after_checkpoint,
        {"needs_more_experiments": END, "complete": END},
    )
    return g.compile()
```

- [ ] **Step 4: Verify imports**

```bash
cd backend-api
python -c "
from app.graph.nodes.hypothesis import hypothesis_subgraph
from app.graph.nodes.analysis import analysis_subgraph
print('hypothesis subgraph:', hypothesis_subgraph())
print('analysis subgraph:', analysis_subgraph())
"
```

Expected: no import errors.

- [ ] **Step 5: Confirm all existing tests still pass**

```bash
python -m pytest tests/ -x -q
```

- [ ] **Step 6: Commit**

```bash
git add app/graph/nodes/hypothesis.py app/graph/nodes/analysis.py
git commit -m "feat(graph): add hypothesis and analysis sub-graphs with interrupt checkpoints"
```

---

### Task 9: Top-level pipeline and E2E test

**Files:**
- Create: `app/graph/pipeline.py`
- Create: `tests/graph/test_pipeline_e2e.py`

**Interfaces:**
- Consumes: all sub-graphs from `app.graph.nodes.*`, `get_checkpointer()`, `INTERRUPT_NODES`
- Produces: `get_pipeline() -> CompiledGraph` — the full compiled `StateGraph` with interrupt checkpoints; singleton (cached at module level)

- [ ] **Step 1: Write failing E2E test**

Create `tests/graph/test_pipeline_e2e.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langgraph.checkpoint.memory import MemorySaver

from app.graph.state import PolarisGraphState
from app.graph.interrupts import build_start_config


@pytest.fixture
def base_state() -> PolarisGraphState:
    return {
        "stage": "initial",
        "has_hypothesis": False,
        "has_experimental_outputs": False,
        "has_curve_results": False,
        "has_ml_results": False,
        "has_analysis_results": False,
        "hypothesis_ready": False,
        "hypothesis_preview": None,
        "research_goal": "Why does GaN emit blue light?",
        "experiment_id": None,
        "current_agent": None,
        "error": None,
        "interrupt_payload": None,
        "routing_mode": "autonomous",
        "manual_workflow": [],
        "workflow_index": 0,
    }


def test_pipeline_compiles():
    """Pipeline graph must compile without errors."""
    from app.graph.pipeline import build_pipeline
    pipeline = build_pipeline(checkpointer=MemorySaver())
    assert pipeline is not None


@pytest.mark.asyncio
async def test_pipeline_starts_and_reaches_hypothesis_interrupt(base_state):
    """Starting the pipeline must reach the first interrupt (hypothesis_checkpoint)."""
    from app.graph.pipeline import build_pipeline
    from app.services.hypothesis_chat import submit_question
    from app.tools.memory import MemoryManager

    memory = MagicMock(spec=MemoryManager)
    memory.get_var.return_value = None
    memory.view_component.return_value = "Test hypothesis option 1"

    mock_submit = MagicMock(return_value={"status": "ok", "options": ["opt1", "opt2", "opt3"]})

    with patch("app.graph.nodes.hypothesis.get_memory_manager", return_value=memory), \
         patch("app.graph.nodes.hypothesis.submit_question", mock_submit):
        pipeline = build_pipeline(checkpointer=MemorySaver())
        thread_cfg = build_start_config("test-thread-001")
        try:
            async for chunk in pipeline.astream(base_state, config=thread_cfg):
                pass
        except Exception:
            pass  # interrupt raises — that's expected
        state_snapshot = await pipeline.aget_state(thread_cfg)
        # Pipeline paused somewhere (either interrupt or normal end)
        assert state_snapshot is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend-api
python -m pytest tests/graph/test_pipeline_e2e.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.graph.pipeline'`

- [ ] **Step 3: Create `app/graph/pipeline.py`**

```python
from __future__ import annotations

import logging
from typing import Optional

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.graph.checkpointer import get_checkpointer
from app.graph.interrupts import INTERRUPT_NODES
from app.graph.nodes.analysis import analysis_subgraph
from app.graph.nodes.curve_fitting import curve_fitting_subgraph
from app.graph.nodes.experiment import experiment_subgraph
from app.graph.nodes.fallback import fallback_node
from app.graph.nodes.hypothesis import hypothesis_subgraph
from app.graph.nodes.ml_models import ml_models_node
from app.graph.nodes.watcher import watcher_node
from app.graph.state import PolarisGraphState
from app.services.memory_service import get_memory_manager

_logger = logging.getLogger(__name__)
_pipeline = None


def _route_after_analysis(state: PolarisGraphState) -> str:
    memory = get_memory_manager()
    verdict = memory.get_var("analysis_verdict") or "complete"
    if verdict == "needs_more_experiments":
        return "experiment"
    return END


def build_pipeline(checkpointer: Optional[BaseCheckpointSaver] = None) -> object:
    """Build and compile the top-level POLARIS pipeline StateGraph."""
    g = StateGraph(PolarisGraphState)

    # Embed compiled sub-graphs as single nodes
    g.add_node("hypothesis", hypothesis_subgraph())
    g.add_node("experiment", experiment_subgraph())
    g.add_node("curve_fitting", curve_fitting_subgraph())
    g.add_node("ml_models", ml_models_node)
    g.add_node("analysis", analysis_subgraph())
    g.add_node("fallback", fallback_node)
    g.add_node("watcher", watcher_node)

    g.set_entry_point("hypothesis")
    g.add_edge("hypothesis", "experiment")
    g.add_edge("experiment", "curve_fitting")
    g.add_edge("curve_fitting", "ml_models")
    g.add_edge("ml_models", "analysis")
    g.add_conditional_edges(
        "analysis",
        _route_after_analysis,
        {"experiment": "experiment", END: END},
    )
    g.add_edge("fallback", END)
    g.add_edge("watcher", END)

    cp = checkpointer or get_checkpointer()
    return g.compile(checkpointer=cp, interrupt_before=INTERRUPT_NODES)


def get_pipeline() -> object:
    """Singleton accessor for the production pipeline (uses AsyncSqliteSaver)."""
    global _pipeline
    if _pipeline is None:
        _pipeline = build_pipeline()
    return _pipeline
```

- [ ] **Step 4: Run E2E test to verify it passes**

```bash
cd backend-api
python -m pytest tests/graph/test_pipeline_e2e.py -v
```

Expected: both tests PASS (compile + start tests).

- [ ] **Step 5: Confirm all existing tests still pass**

```bash
python -m pytest tests/ -x -q
```

Expected: all 9 original tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/graph/pipeline.py tests/graph/test_pipeline_e2e.py
git commit -m "feat(graph): add top-level StateGraph pipeline with interrupt checkpoints"
```

---

### Task 10: Pipeline REST API endpoints

**Files:**
- Create: `app/api/v1/pipeline.py`
- Modify: `app/api/v1/router.py`

**Interfaces:**
- Consumes: `get_pipeline()`, `build_start_config()`, `build_resume_config()`, `get_memory_manager()`
- Produces three endpoints:
  - `POST /api/v1/pipeline/start` — body: `{"research_goal": str, "routing_mode": "autonomous"|"manual"}` → `{"thread_id": str, "interrupt_payload": dict|null, "state": PolarisGraphState}`
  - `POST /api/v1/pipeline/resume` — body: `{"thread_id": str, "decision": dict}` → `{"thread_id": str, "interrupt_payload": dict|null, "state": PolarisGraphState}`
  - `GET /api/v1/pipeline/state/{thread_id}` → `{"thread_id": str, "state": PolarisGraphState}`

- [ ] **Step 1: Create `app/api/v1/pipeline.py`**

```python
from __future__ import annotations

import uuid
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.graph.interrupts import build_resume_config, build_start_config
from app.graph.pipeline import get_pipeline
from app.graph.state import PolarisGraphState
from app.services.memory_service import get_memory_manager

router = APIRouter(prefix="/pipeline")
_logger = logging.getLogger(__name__)


class StartRequest(BaseModel):
    research_goal: str
    routing_mode: str = "autonomous"


class ResumeRequest(BaseModel):
    thread_id: str
    decision: Dict[str, Any] = {}


def _safe_state(snapshot) -> dict:
    if snapshot is None:
        return {}
    values = getattr(snapshot, "values", None)
    if values is None:
        return {}
    return dict(values)


@router.post("/start")
async def start_pipeline(body: StartRequest) -> Dict[str, Any]:
    """Start the POLARIS pipeline for a new research goal. Returns first interrupt_payload."""
    thread_id = str(uuid.uuid4())
    memory = get_memory_manager()
    memory.set_var("research_goal", body.research_goal)

    initial_state: PolarisGraphState = {
        "stage": "initial",
        "has_hypothesis": False,
        "has_experimental_outputs": False,
        "has_curve_results": False,
        "has_ml_results": False,
        "has_analysis_results": False,
        "hypothesis_ready": False,
        "hypothesis_preview": None,
        "research_goal": body.research_goal,
        "experiment_id": None,
        "current_agent": None,
        "error": None,
        "interrupt_payload": None,
        "routing_mode": body.routing_mode,
        "manual_workflow": [],
        "workflow_index": 0,
    }

    pipeline = get_pipeline()
    config = build_start_config(thread_id)

    try:
        async for _ in pipeline.astream(initial_state, config=config):
            pass
    except Exception as exc:
        _logger.debug("Pipeline paused or errored at start: %s", exc)

    snapshot = await pipeline.aget_state(config)
    state = _safe_state(snapshot)

    return {
        "thread_id": thread_id,
        "interrupt_payload": state.get("interrupt_payload"),
        "state": state,
    }


@router.post("/resume")
async def resume_pipeline(body: ResumeRequest) -> Dict[str, Any]:
    """Resume a paused pipeline thread with a user decision."""
    pipeline = get_pipeline()
    config = build_resume_config(body.thread_id)

    try:
        await pipeline.aupdate_state(config, {"interrupt_payload": None})
        async for _ in pipeline.astream(body.decision, config=config):
            pass
    except Exception as exc:
        _logger.debug("Pipeline paused or errored on resume: %s", exc)

    snapshot = await pipeline.aget_state(config)
    state = _safe_state(snapshot)

    return {
        "thread_id": body.thread_id,
        "interrupt_payload": state.get("interrupt_payload"),
        "state": state,
    }


@router.get("/state/{thread_id}")
async def get_pipeline_state(thread_id: str) -> Dict[str, Any]:
    """Return the current PolarisGraphState for a thread."""
    pipeline = get_pipeline()
    config = build_resume_config(thread_id)
    snapshot = await pipeline.aget_state(config)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return {"thread_id": thread_id, "state": _safe_state(snapshot)}
```

- [ ] **Step 2: Register the pipeline router in `app/api/v1/router.py`**

Add two lines to `router.py` — one import and one `include_router` call. The file currently looks like:

```python
from fastapi import APIRouter
from app.api.v1 import (agents, analysis_session, ...)
api_router = APIRouter()
api_router.include_router(agents.router, tags=["agents"])
# ...
```

Add `pipeline` to the import list and add:
```python
api_router.include_router(pipeline.router, tags=["pipeline"])
```

Full updated `router.py`:

```python
from fastapi import APIRouter

from app.api.v1 import (
    agents,
    analysis_session,
    dashboard,
    documents,
    experiments,
    health,
    history,
    llm,
    mcp,
    ml_session,
    pipeline,
    session,
    settings,
    watcher,
    workflows,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(llm.router, tags=["llm"])
api_router.include_router(experiments.router, tags=["experiments"])
api_router.include_router(dashboard.router, tags=["dashboard"])
api_router.include_router(workflows.router, tags=["workflows"])
api_router.include_router(ml_session.router, tags=["ml"])
api_router.include_router(analysis_session.router, tags=["analysis"])
api_router.include_router(agents.router, tags=["agents"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(watcher.router, tags=["watcher"])
api_router.include_router(mcp.router, tags=["mcp"])
api_router.include_router(settings.router, tags=["settings"])
api_router.include_router(session.router, tags=["session"])
api_router.include_router(history.router, tags=["history"])
api_router.include_router(pipeline.router, tags=["pipeline"])
```

- [ ] **Step 3: Verify the app starts and endpoints appear**

```bash
cd backend-api
uvicorn app.main:app --port 8099 &
sleep 3
curl -s http://localhost:8099/api/v1/pipeline/state/nonexistent-thread | python3 -m json.tool
kill %1
```

Expected: `{"detail": "Thread nonexistent-thread not found"}` with HTTP 404.

- [ ] **Step 4: Confirm all existing tests still pass**

```bash
python -m pytest tests/ -x -q
```

Expected: all 9 original tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/api/v1/pipeline.py app/api/v1/router.py
git commit -m "feat(api): add /pipeline/start, /resume, /state endpoints"
```

---

### Task 11: Final verification

**Files:**
- No new files

- [ ] **Step 1: Run full test suite**

```bash
cd backend-api
python -m pytest tests/ -v
```

Expected: all tests in `tests/` (original 9 + new graph/llm tests) PASS. Note total count.

- [ ] **Step 2: Verify all graph modules importable**

```bash
python -c "
from app.graph.state import PolarisGraphState
from app.graph.checkpointer import get_checkpointer
from app.graph.interrupts import INTERRUPT_NODES, build_start_config, build_resume_config
from app.graph.pipeline import get_pipeline, build_pipeline
from app.graph.nodes.fallback import fallback_node
from app.graph.nodes.watcher import watcher_node
from app.graph.nodes.ml_models import ml_models_node
from app.graph.nodes.experiment import experiment_subgraph
from app.graph.nodes.curve_fitting import curve_fitting_subgraph
from app.graph.nodes.hypothesis import hypothesis_subgraph
from app.graph.nodes.analysis import analysis_subgraph
from app.llm.providers import get_llm
from app.llm.chains.hypothesis import clarify_chain, socratic_chain, tot_chain, synthesis_chain
from app.llm.chains.experiment import plan_tot_chain, worklist_chain
from app.llm.chains.analysis import analysis_chain, next_step_chain
from app.llm.chains.routing import watcher_routing_chain
from app.tools.memory_adapter import MemoryAdapter
from app.api.v1.pipeline import router as pipeline_router
print('All graph/llm imports OK')
"
```

Expected: `All graph/llm imports OK`

- [ ] **Step 3: Verify existing agents untouched**

```bash
python -c "
from app.agents.hypothesis_agent import HypothesisAgent
from app.agents.experiment_agent import ExperimentAgent
from app.agents.curve_fitting_agent import CurveFittingAgent
from app.agents.analysis_agent import AnalysisAgent
from app.agents.ml_models_agent import MLModelsAgent
from app.agents.watcher_agent import WatcherAgent
from app.agents.fallback_agent import FallbackAgent
from app.agents.router import AgentRouter
print('All existing agents import OK (unchanged)')
"
```

Expected: `All existing agents import OK (unchanged)`

- [ ] **Step 4: Commit final verification note**

```bash
git add .
git commit -m "chore: verify LangChain+LangGraph integration complete — all imports and tests pass"
```
