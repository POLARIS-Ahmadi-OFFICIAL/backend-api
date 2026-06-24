# POLARIS — LangChain + LangGraph Integration Design

**Date:** 2026-06-24  
**Status:** Approved  
**Approach:** Full Decomposition (Option B) with Federated State (Option C)

---

## 1. Motivation

POLARIS currently uses a custom `AgentRouter` with confidence scoring to orchestrate 7 agents. The goal is to replace this with LangChain + LangGraph so that:

- The full pipeline is expressed as a first-class state machine with conditional branching and loops
- Human-in-the-loop checkpoints pause execution between stages, letting the web/mobile/desktop frontends present review screens before continuing
- Every LLM call is a discrete, observable, replayable graph node — full LangSmith tracing with no extra instrumentation
- The codebase uses industry-standard primitives, making it easier to extend and hire for

---

## 2. Core Decisions

| Decision | Choice | Reason |
|---|---|---|
| Graph drives flow vs. API drives flow | Graph drives, API subscribes | Human-in-the-loop checkpoints require the graph to own execution state |
| State persistence | Federated: LangGraph checkpointer (execution) + MemoryManager (domain) | LangGraph state holds lightweight routing signals; full domain objects stay in SQLite |
| Migration depth | Full decomposition — each agent becomes a sub-graph | Per-step observability and mid-agent resumability require nodes, not monolithic black boxes |
| Existing code | Additive only — no existing files modified | 22 existing tests keep passing throughout migration |

---

## 3. Graph State Schema

```python
# app/graph/state.py
class PolarisGraphState(TypedDict):
    # Routing signals
    stage: str                      # "initial" | "hypothesis" | "experiment" | "curve_fitting" | "ml_models" | "analysis" | "complete" | "error"
    has_hypothesis: bool
    has_experimental_outputs: bool
    has_curve_results: bool
    has_ml_results: bool
    has_analysis_results: bool
    hypothesis_ready: bool

    # Thin previews for display and edge conditions (≤500 chars)
    hypothesis_preview: Optional[str]
    research_goal: Optional[str]

    # Execution context
    experiment_id: Optional[int]
    current_agent: Optional[str]
    error: Optional[str]
    interrupt_payload: Optional[dict]   # data surfaced to frontend at checkpoints

    # Routing config
    routing_mode: str               # "autonomous" | "manual"
    manual_workflow: list[str]
    workflow_index: int
```

Full domain objects (hypothesis text, curve fitting JSON, ML results, interaction history) remain in `MemoryManager` / SQLite unchanged.

---

## 4. Top-Level Pipeline Graph

```
__start__
    │
    ▼
[hypothesis_graph]
    │  interrupt_before: "hypothesis_checkpoint"
    │  interrupt_payload: { stage, hypothesis_preview, hint: "review hypothesis" }
    ▼
[experiment_graph]
    │  interrupt_before: "experiment_checkpoint"
    │  interrupt_payload: { stage, plan_preview, worklist_url }
    ▼
[curve_fitting_graph]
    │  interrupt_before: "curve_fitting_checkpoint"
    │  interrupt_payload: { stage, data_file, fit_quality_preview }
    ▼
[ml_models_graph]
    │
    ▼
[analysis_graph]
    │  interrupt_before: "analysis_checkpoint"
    │  interrupt_payload: { stage, analysis_preview, decision }
    │
    ├── conditional edge: "needs_more_experiments" → experiment_graph
    └── conditional edge: "complete" → END

[error_node] ← catches unhandled exceptions from any node → fallback_graph → END
```

**Interrupt/resume flow:**
1. `POST /api/v1/pipeline/start` — creates `thread_id` (UUID), starts graph, returns first `interrupt_payload`
2. Frontend displays review screen using `interrupt_payload`
3. `POST /api/v1/pipeline/resume` — passes `thread_id` + user decision, graph continues from checkpoint
4. `GET /api/v1/pipeline/state` — returns current `PolarisGraphState` for a `thread_id`

Existing per-agent endpoints (`POST /agents/hypothesis`, etc.) are kept as-is for direct invocations.

**`AgentRouter` (`router.py`) is retired** — replaced by LangGraph `StateGraph` + conditional edges. File is kept for rollback but not called by any new code.

---

## 5. Agent Sub-Graphs

Each agent becomes a `StateGraph` compiled to a `CompiledGraph` and embedded as a node in the top-level pipeline.

### HypothesisAgent sub-graph (~6 nodes)
```
clarify_question → socratic_pass → answer_questions → tot_generation
    → [interrupt: user picks option 1/2/3]
    → deepen_thoughts → hypothesis_synthesis → analysis_report
```

### ExperimentAgent sub-graph (~3 nodes)
```
build_experimental_context → generate_plan_tot → generate_worklist
```

### CurveFittingAgent sub-graph (~3 nodes)
```
load_data → run_peak_fitting → export_results
```

### AnalysisAgent sub-graph (~4 nodes)
```
gather_context → run_llm_analysis → evaluate_hypothesis_outcome → decide_next_step
```
`decide_next_step` emits `"needs_more_experiments"` or `"complete"` to the top-level graph.

### MLModelsAgent, WatcherAgent, FallbackAgent
Single nodes — their logic is already effectively one step.

**Node function signature:**
```python
# get_memory_manager() is a module-level helper in each node file that returns the
# MemoryManager instance (session-scoped, passed via thread config or module singleton)
async def clarify_question_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager(config)
    result = await clarify_chain.ainvoke({"question": state["research_goal"]})
    return MemoryAdapter.write(memory, state, clarified_question=result)
```

---

## 6. LangChain LLM Layer

All LLM calls migrate from `socratic.py` / `llm_client.py` to LangChain `ChatPromptTemplate` + `RunnableSequence` chains.

### Provider factory (replaces `llm_client.py`)
```python
# app/llm/providers.py
def get_llm(memory: MemoryManager) -> BaseChatModel:
    provider = memory.get_var("llm_provider", "qwen")
    api_key = memory.get_var("api_key")
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=memory.get_var("llm_model", "gemini-2.0-flash"),
            google_api_key=api_key,
        ).with_retry(retry_if_exception_type=(RateLimitError,), wait_exponential_jitter=True)
    return ChatOpenAI(
        model=memory.get_var("llm_model", "Qwen/Qwen2.5-72B-Instruct"),
        api_key=api_key,
        base_url=memory.get_var("qwen_base_url", "https://router.huggingface.co/v1"),
    )
```

### Chain construction (replaces `socratic.py`)
```python
# app/llm/chains/hypothesis.py
clarify_chain   = ChatPromptTemplate.from_template(CLARIFY_QUESTION_INSTRUCTIONS) | get_llm() | StrOutputParser()
socratic_chain  = ChatPromptTemplate.from_template(SOCRATIC_PASS_INSTRUCTIONS)    | get_llm() | StrOutputParser()
tot_chain       = ChatPromptTemplate.from_template(TOT_INSTRUCTIONS)               | get_llm() | StrOutputParser()
synthesis_chain = ChatPromptTemplate.from_template(HYPOTHESIS_SYNTHESIS)           | get_llm() | StrOutputParser()
```

Prompt strings in `app/tools/instruct.py` are **kept unchanged** — wrapped in `ChatPromptTemplate.from_template()` rather than f-string formatted.

**LangSmith tracing** is enabled via environment variables only — no code changes needed:
```
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<key>
LANGCHAIN_PROJECT=polaris
```

`socratic.py` and `llm_client.py` are deprecated (not deleted) — replaced by `app/llm/`.

---

## 7. Persistence & MemoryAdapter

### LangGraph checkpointer
```python
# app/graph/checkpointer.py
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

DB_PATH = str(Path(__file__).parent.parent.parent / "data" / "polaris.db")  # <repo>/data/polaris.db
checkpointer = AsyncSqliteSaver.from_conn_string(DB_PATH)

# INTERRUPT_NODES is a list[str] constant defined in interrupts.py listing node names that pause execution
INTERRUPT_NODES = ["hypothesis_checkpoint", "experiment_checkpoint", "curve_fitting_checkpoint", "analysis_checkpoint"]

pipeline = top_level_graph.compile(
    checkpointer=checkpointer,
    interrupt_before=INTERRUPT_NODES,
)
```

Uses the existing `data/polaris.db` — no new database files.

### MemoryAdapter
```python
# app/tools/memory_adapter.py
class MemoryAdapter:
    SIGNAL_MAP = {
        "hypothesis":              ("has_hypothesis", "hypothesis_preview"),
        "experimental_outputs":    ("has_experimental_outputs", None),
        "curve_fitting_results":   ("has_curve_results", None),
        "gp_results":              ("has_ml_results", None),
        "analysis_results":        ("has_analysis_results", None),
    }

    @staticmethod
    def write(memory: MemoryManager, state: PolarisGraphState, **kwargs) -> PolarisGraphState:
        updates = {}
        for key, value in kwargs.items():
            memory.set_var(key, value)
            if key in MemoryAdapter.SIGNAL_MAP:
                flag_key, preview_key = MemoryAdapter.SIGNAL_MAP[key]
                updates[flag_key] = bool(value)
                if preview_key:
                    updates[preview_key] = str(value)[:500] if value else None
        return {**state, **updates}
```

`MemoryManager` API (`get_var`, `set_var`, `insert_interaction`, `log_event`) is **completely unchanged**.

---

## 8. File & Module Structure

```
backend-api/app/
├── agents/          # UNCHANGED — all existing agent classes kept
├── graph/           # NEW
│   ├── state.py          # PolarisGraphState TypedDict
│   ├── pipeline.py       # Top-level StateGraph + compile()
│   ├── checkpointer.py   # AsyncSqliteSaver setup
│   ├── interrupts.py     # interrupt point constants + resume helpers
│   └── nodes/            # One file per agent sub-graph
│       ├── hypothesis.py
│       ├── experiment.py
│       ├── curve_fitting.py
│       ├── analysis.py
│       ├── ml_models.py
│       ├── watcher.py
│       └── fallback.py
├── llm/             # NEW
│   ├── providers.py      # get_llm() factory
│   └── chains/           # One file per agent's LLM call set
│       ├── hypothesis.py
│       ├── experiment.py
│       ├── analysis.py
│       └── routing.py
├── tools/
│   ├── memory.py          # UNCHANGED
│   ├── memory_adapter.py  # NEW — MemoryAdapter dual-write utility
│   ├── instruct.py        # UNCHANGED — prompts reused as templates
│   ├── socratic.py        # DEPRECATED (not deleted)
│   └── llm_client.py      # DEPRECATED (not deleted)
└── api/v1/
    ├── agents.py          # UNCHANGED — existing endpoints kept
    └── pipeline.py        # NEW — /pipeline/start, /pipeline/resume, /pipeline/state
```

---

## 9. Error Handling

```python
async def error_recovery_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    memory.log_event("pipeline_error", {"stage": state["stage"], "error": state["error"]})
    return {**state, "current_agent": "fallback", "stage": "error"}
```

- Node-level errors write to `state["error"]` and route to `error_recovery_node`
- Transient LLM failures (429, timeouts) handled by LangChain `with_retry()` before surfacing as node errors
- `FallbackAgent.run_agent()` logic reused inside `graph/nodes/fallback.py`

---

## 10. Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit | Each LangChain chain in `llm/chains/` | Mocked `BaseChatModel`, verifies prompt formatting + output parsing |
| Sub-graph integration | Each `graph/nodes/*.py` sub-graph | In-memory SQLite `MemoryManager`, verifies state transitions + MemoryAdapter dual-writes |
| Pipeline E2E | Full compiled top-level graph | `MemorySaver` checkpointer (in-memory), verifies interrupt → resume → next stage flow |
| Regression | Existing 22 tests in `tests/` | Run unchanged throughout migration — no existing code is modified |

---

## 11. New Dependencies

Add to `pyproject.toml`:

```toml
"langchain>=0.3.0",
"langchain-openai>=0.2.0",
"langchain-google-genai>=2.0.0",
"langgraph>=0.2.0",
"langgraph-checkpoint-sqlite>=1.0.0",
```

---

## 12. Migration Order

1. Add dependencies + verify imports
2. `app/graph/state.py` — `PolarisGraphState` TypedDict
3. `app/tools/memory_adapter.py` — `MemoryAdapter`
4. `app/llm/providers.py` + `app/llm/chains/` — LangChain chains (one agent at a time)
5. `app/graph/nodes/` — sub-graphs (one agent at a time, starting with simplest: `ml_models`, `watcher`, `fallback`)
6. `app/graph/pipeline.py` — top-level `StateGraph` assembly
7. `app/graph/checkpointer.py` + `app/api/v1/pipeline.py` — pipeline REST endpoints
8. Tests at each step
9. Mark `router.py`, `socratic.py`, `llm_client.py` as deprecated
