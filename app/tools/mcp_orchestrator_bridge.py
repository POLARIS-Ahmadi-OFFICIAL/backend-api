"""
Helpers for sending hypothesis events to the MCP orchestrator service.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _orchestrator_base_url(memory: Any) -> str:
    host = memory.get_var("mcp_orch_host", "127.0.0.1")
    port = int(memory.get_var("mcp_orch_port", 8010) or 8010)
    return f"http://{host}:{port}"


def _post_json(memory: Any, path: str, payload: Dict[str, Any], timeout: float = 2.5) -> bool:
    try:
        import requests
    except Exception:
        logger.debug("requests unavailable; cannot call orchestrator endpoint")
        return False

    base_url = _orchestrator_base_url(memory)
    try:
        health = requests.get(f"{base_url}/health", timeout=1.2)
        if health.status_code != 200:
            return False
    except Exception:
        return False

    try:
        resp = requests.post(f"{base_url}{path}", json=payload, timeout=timeout)
        return resp.status_code == 200
    except Exception as exc:
        logger.debug(f"Orchestrator bridge call failed for {path}: {exc}")
        return False


def sync_hypothesis_proposal(memory: Any, hypothesis_text: str, source: str = "hypothesis_agent") -> bool:
    if not hypothesis_text or not str(hypothesis_text).strip():
        return False
    payload = {
        "hypothesis_text": str(hypothesis_text)[:4000],
        "material_hint": "",
        "source": source,
        "record_if_allowed": True,
    }
    return _post_json(memory, "/propose-hypothesis", payload, timeout=3.0)


def sync_hypothesis_outcome(
    memory: Any,
    hypothesis_text: str,
    status: str,
    evidence_summary: str = "",
    source: str = "analysis_agent",
) -> bool:
    if not hypothesis_text or not str(hypothesis_text).strip():
        return False
    payload = {
        "hypothesis_text": str(hypothesis_text)[:4000],
        "status": status,
        "material_hint": "",
        "evidence_summary": (evidence_summary or "")[:2000],
        "source": source,
    }
    return _post_json(memory, "/record-hypothesis-outcome", payload, timeout=4.0)

