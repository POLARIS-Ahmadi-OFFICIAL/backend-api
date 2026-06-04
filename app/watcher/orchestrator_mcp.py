"""
Lightweight MCP orchestrator for literature tools + hypothesis gating.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parent.parent
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

try:
    from app.tools.manual_paper_store import ManualPaperStore
    from app.tools.mcp_literature_client import (
        MCPLiteratureClient,
        MCPConnectionError,
        MCPRequestError,
    )
    from app.tools.memory import MemoryManager
except Exception as exc:
    raise

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DEFAULT_MCP_ENDPOINT = os.getenv("LITERATURE_MCP_ENDPOINT", "http://127.0.0.1:8000/mcp")
DEFAULT_MANUAL_PAPER_MANIFEST = os.getenv(
    "MANUAL_PAPER_MANIFEST",
    "data/manual_papers_manifest.json",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _norm(text)))


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta | tb))


def _dedupe_key(item: Dict[str, Any]) -> str:
    doi = _norm(str(item.get("doi") or ""))
    title = _norm(str(item.get("title") or ""))
    raw = f"{doi}|{title}"
    return sha1(raw.encode("utf-8")).hexdigest()


def _extract_structured_payload(mcp_result: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(mcp_result, dict) and mcp_result.get("raw_result"):
        raw = mcp_result["raw_result"]
        if isinstance(raw, dict):
            content = raw.get("content", [])
            for entry in content:
                text = entry.get("text") if isinstance(entry, dict) else None
                if text and isinstance(text, str):
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            return parsed
                    except Exception:
                        continue
    return {}


class SearchPapersRequest(BaseModel):
    query: str
    year_min: int = 2021
    year_max: int = 2026
    max_candidates: int = 25
    source_mode: Literal["manual_only", "mcp_only", "hybrid"] = "hybrid"


class ProcessPaperRequest(BaseModel):
    action: Literal[
        "process_one_paper",
        "process_batch",
        "get_saved_paper_output",
        "list_processed_papers",
        "get_hypothesis_payload",
    ] = "process_one_paper"
    meta: Optional[Dict[str, Any]] = None
    paper_slug: Optional[str] = None
    query: Optional[str] = None
    year_min: int = 2021
    year_max: int = 2026
    max_papers: int = 1
    force_reprocess: bool = False
    run_mode: str = "resume"
    reset_output: bool = False


class ProposeHypothesisRequest(BaseModel):
    hypothesis_text: str = Field(min_length=5)
    material_hint: str = ""
    source: str = "orchestrator"
    record_if_allowed: bool = False


class RecordHypothesisOutcomeRequest(BaseModel):
    hypothesis_text: str = Field(min_length=5)
    status: Literal["positive", "confirmed", "successful", "rejected", "needs_revision"]
    material_hint: str = ""
    evidence_summary: str = ""
    source: str = "orchestrator"


class OrchestratorService:
    def __init__(self, memory: MemoryManager):
        self.memory = memory
        self.memory.init_session()

    def _get_mcp_endpoint(self) -> str:
        cfg = self.memory.get_var("mcp_literature_config", {}) or {}
        return cfg.get("endpoint") or DEFAULT_MCP_ENDPOINT

    def _get_manual_manifest(self) -> str:
        cfg = self.memory.get_var("mcp_literature_config", {}) or {}
        return cfg.get("manual_manifest_path") or DEFAULT_MANUAL_PAPER_MANIFEST

    def _mcp_client(self) -> MCPLiteratureClient:
        return MCPLiteratureClient(endpoint=self._get_mcp_endpoint())

    def list_tools(self) -> Dict[str, Any]:
        tools = self._mcp_client().list_tools()
        return {
            "ok": True,
            "endpoint": self._get_mcp_endpoint(),
            "tools": [{"name": t.name, "description": t.description} for t in tools],
        }

    def search_papers(self, req: SearchPapersRequest) -> Dict[str, Any]:
        manual_rows: List[Dict[str, Any]] = []
        mcp_rows: List[Dict[str, Any]] = []

        if req.source_mode in {"manual_only", "hybrid"}:
            manual_store = ManualPaperStore(self._get_manual_manifest())
            manual_result = manual_store.search(
                query=req.query,
                year_min=req.year_min,
                year_max=req.year_max,
                max_candidates=req.max_candidates,
            )
            manual_rows = manual_result.get("candidates", [])

        if req.source_mode in {"mcp_only", "hybrid"}:
            mcp_result = self._mcp_client().call_tool(
                "search_candidates",
                {
                    "query": req.query,
                    "year_min": req.year_min,
                    "year_max": req.year_max,
                    "max_candidates": req.max_candidates,
                },
            )
            structured = _extract_structured_payload(mcp_result)
            mcp_rows = structured.get("candidates", []) if structured else []

        merged: List[Dict[str, Any]] = []
        seen = set()
        for row in [*manual_rows, *mcp_rows]:
            key = _dedupe_key(row)
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)

        return {
            "ok": True,
            "source_mode": req.source_mode,
            "manual_count": len(manual_rows),
            "mcp_count": len(mcp_rows),
            "merged_count": len(merged),
            "candidates": merged[: req.max_candidates],
        }

    def process_paper(self, req: ProcessPaperRequest) -> Dict[str, Any]:
        tool_args: Dict[str, Any]
        if req.action == "process_one_paper":
            if not req.meta:
                raise HTTPException(status_code=400, detail="meta is required for process_one_paper")
            tool_args = {
                "meta": req.meta,
                "force_reprocess": req.force_reprocess,
                "run_mode": req.run_mode,
            }
        elif req.action == "process_batch":
            tool_args = {
                "query": req.query or "",
                "year_min": req.year_min,
                "year_max": req.year_max,
                "max_papers": req.max_papers,
                "run_mode": req.run_mode,
                "force_reprocess": req.force_reprocess,
                "reset_output": req.reset_output,
            }
        elif req.action in {"get_saved_paper_output", "get_hypothesis_payload"}:
            if not req.paper_slug:
                raise HTTPException(status_code=400, detail="paper_slug is required for this action")
            tool_args = {"paper_slug": req.paper_slug}
        elif req.action == "list_processed_papers":
            tool_args = {}
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action: {req.action}")

        mcp_result = self._mcp_client().call_tool(req.action, tool_args)
        structured = _extract_structured_payload(mcp_result)
        return {
            "ok": True,
            "action": req.action,
            "endpoint": self._get_mcp_endpoint(),
            "result": structured or mcp_result,
        }

    def _history_guard(self, hypothesis_text: str, material_hint: str = "") -> Dict[str, Any]:
        negatives = self.memory.get_negative_hypotheses(limit=None)
        outcomes = self.memory.get_hypothesis_outcomes(limit=500)
        positives = [o for o in outcomes if o.get("status") in {"positive", "confirmed", "successful"}]
        neg_outcomes = [o for o in outcomes if o.get("status") in {"rejected", "needs_revision"}]

        match_reasons: List[Dict[str, Any]] = []
        blocked = False

        check_pool = [
            *[
                {
                    "hypothesis_text": n.get("hypothesis_text", ""),
                    "status": n.get("status", "rejected"),
                    "material_hint": "",
                    "source": "negative_hypotheses",
                }
                for n in negatives
            ],
            *neg_outcomes,
        ]

        normalized_new = _norm(hypothesis_text)
        for item in check_pool:
            existing = _norm(item.get("hypothesis_text", ""))
            if not existing:
                continue
            score = _jaccard(normalized_new, existing)
            exact = normalized_new == existing
            if exact or score >= 0.75:
                blocked = True
                match_reasons.append(
                    {
                        "type": "negative_match",
                        "status": item.get("status"),
                        "similarity": round(score, 3),
                        "source": item.get("source", "history"),
                        "matched_text": item.get("hypothesis_text", "")[:250],
                    }
                )

        positive_hints = []
        norm_material = _norm(material_hint)
        if norm_material:
            for pos in positives:
                hint = _norm(pos.get("material_hint", ""))
                if hint and hint == norm_material:
                    positive_hints.append(
                        {
                            "type": "positive_precedent",
                            "material_hint": pos.get("material_hint", ""),
                            "hypothesis_text": pos.get("hypothesis_text", "")[:250],
                            "source": pos.get("source", ""),
                        }
                    )

        return {
            "blocked": blocked,
            "reasons": match_reasons,
            "positive_precedents": positive_hints,
        }

    def propose_hypothesis(self, req: ProposeHypothesisRequest) -> Dict[str, Any]:
        gate = self._history_guard(req.hypothesis_text, req.material_hint)
        if gate["blocked"]:
            return {
                "ok": True,
                "blocked": True,
                "decision": "blocked_by_history",
                "reasons": gate["reasons"],
                "positive_precedents": gate["positive_precedents"],
            }

        if req.record_if_allowed:
            self.memory.add_hypothesis_outcome(
                hypothesis_text=req.hypothesis_text,
                status="proposed",
                material_hint=req.material_hint,
                evidence_summary="Accepted by orchestrator gating",
                source=req.source,
            )

        return {
            "ok": True,
            "blocked": False,
            "decision": "allowed",
            "positive_precedents": gate["positive_precedents"],
        }

    def record_hypothesis_outcome(self, req: RecordHypothesisOutcomeRequest) -> Dict[str, Any]:
        self.memory.add_hypothesis_outcome(
            hypothesis_text=req.hypothesis_text,
            status=req.status,
            material_hint=req.material_hint,
            evidence_summary=req.evidence_summary,
            source=req.source,
        )
        if req.status in {"rejected", "needs_revision"}:
            self.memory.add_negative_hypothesis(
                hypothesis_text=req.hypothesis_text,
                status=req.status,
                analysis_summary=req.evidence_summary,
            )
        return {"ok": True}


memory = MemoryManager()
service = OrchestratorService(memory=memory)
app = FastAPI(title="POLARIS MCP Orchestrator", version="0.1.0")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "mcp_endpoint": service._get_mcp_endpoint()}


@app.get("/tools")
def tools() -> Dict[str, Any]:
    try:
        return service.list_tools()
    except MCPConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except MCPRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/search-papers")
def search_papers(req: SearchPapersRequest) -> Dict[str, Any]:
    return service.search_papers(req)


@app.post("/process-paper")
def process_paper(req: ProcessPaperRequest) -> Dict[str, Any]:
    try:
        return service.process_paper(req)
    except MCPConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except MCPRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/propose-hypothesis")
def propose_hypothesis(req: ProposeHypothesisRequest) -> Dict[str, Any]:
    return service.propose_hypothesis(req)


@app.post("/record-hypothesis-outcome")
def record_hypothesis_outcome(req: RecordHypothesisOutcomeRequest) -> Dict[str, Any]:
    return service.record_hypothesis_outcome(req)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("MCP_ORCH_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_ORCH_PORT", "8010"))
    uvicorn.run(app, host=host, port=port)
