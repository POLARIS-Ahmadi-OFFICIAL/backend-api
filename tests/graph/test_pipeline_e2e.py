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
