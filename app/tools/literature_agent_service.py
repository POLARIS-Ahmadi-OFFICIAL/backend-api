"""POLARIS-facing service contract for LiteratureAgent.

The service deliberately uses files and subprocesses rather than importing the
large embedded LiteratureAgent runtime into the long-lived Streamlit process.
"""

from __future__ import annotations

import csv
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    from app.tools.agent_contract import AgentResult, AgentTask
except ImportError:
    from agent_contract import AgentResult, AgentTask


STAGES = {"extract_batch", "vision_pass", "sanitize_summaries", "integrate_and_model", "knowledge_graph"}


@dataclass
class LiteratureAgentConfig:
    controller: str = r"E:\LiteratureAgentProject\literature_agent_full_end_to_end_v21_3_english_sanitizer.py"
    base_csv: str = r"C:\Users\jorda\Downloads\Perovskite_database_content_all_data.csv"
    ontology_path: str = r"E:\LiteratureAgentProject\config\perovskite_ontology_library_v19.json"
    work_dir: str = r"E:\LiteratureAgent\lit_outputs"
    integration_out_dir: str = r"E:\LiteratureAgent\artifacts_literature_dataset_update"
    model_script: str = r"E:\LiteratureAgent\pce_then_stability_same_approach.py"
    model_out_dir: str = r"E:\LiteratureAgent\artifacts_pce_then_stability_lit_updated"
    knowledge_graph_out_dir: str = r"E:\LiteratureAgent\artifacts_literature_knowledge_graph"
    job_dir: str = r"E:\LiteratureAgent\polaris_jobs"
    python_executable: str = sys.executable
    llm_api_url: str = "http://localhost:11434/v1/chat/completions"
    llm_model: str = "qwen2.5:7b"
    vision_model: str = "qwen2.5vl:7b-q4_K_M"

    @classmethod
    def load(cls, path: str | Path | None = None) -> "LiteratureAgentConfig":
        config_path = Path(path or os.getenv("POLARIS_LITERATURE_CONFIG", "")).expanduser() if (
            path or os.getenv("POLARIS_LITERATURE_CONFIG")
        ) else None
        payload: dict[str, Any] = {}
        if config_path and config_path.exists():
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        env_map = {
            "controller": "LITERATURE_AGENT_CONTROLLER",
            "base_csv": "LITERATURE_AGENT_BASE_CSV",
            "ontology_path": "LITERATURE_AGENT_ONTOLOGY",
            "work_dir": "LITERATURE_AGENT_WORK_DIR",
            "integration_out_dir": "LITERATURE_AGENT_INTEGRATION_DIR",
            "model_script": "LITERATURE_AGENT_MODEL_SCRIPT",
            "model_out_dir": "LITERATURE_AGENT_MODEL_DIR",
            "knowledge_graph_out_dir": "LITERATURE_AGENT_KG_DIR",
            "job_dir": "LITERATURE_AGENT_JOB_DIR",
        }
        for field_name, env_name in env_map.items():
            if os.getenv(env_name):
                payload[field_name] = os.environ[env_name]
        return cls(**{key: value for key, value in payload.items() if key in cls.__dataclass_fields__})


@dataclass
class LiteratureJob:
    job_id: str
    stage: str
    status: str
    command: list[str]
    created_at: float
    updated_at: float
    pid: int | None = None
    return_code: int | None = None
    log_path: str | None = None
    request: dict[str, Any] = field(default_factory=dict)


class LiteratureAgentService:
    def __init__(self, config: LiteratureAgentConfig | None = None):
        self.config = config or LiteratureAgentConfig.load()
        self.job_dir = Path(self.config.job_dir)
        self.job_dir.mkdir(parents=True, exist_ok=True)

    def health(self) -> dict[str, Any]:
        paths = {
            "controller": self.config.controller,
            "base_csv": self.config.base_csv,
            "ontology_path": self.config.ontology_path,
            "work_dir": self.config.work_dir,
            "all_records": str(Path(self.config.work_dir) / "csv" / "all_records.csv"),
            "summaries": str(Path(self.config.work_dir) / "paper_summaries_text"),
            "knowledge_graph": self.config.knowledge_graph_out_dir,
        }
        checks = {name: Path(value).exists() for name, value in paths.items()}
        return {
            "ok": checks["controller"] and checks["work_dir"],
            "service": "LiteratureAgent",
            "stages": sorted(STAGES),
            "paths": paths,
            "path_checks": checks,
            "active_jobs": [job.job_id for job in self.list_jobs() if job.status == "running"],
        }

    def build_command(self, stage: str, request: dict[str, Any] | None = None) -> list[str]:
        if stage not in STAGES:
            raise ValueError(f"Unsupported stage: {stage}")
        request = request or {}
        command = [
            self.config.python_executable,
            self.config.controller,
            "--pipeline_stage", stage,
            "--base_csv", self.config.base_csv,
            "--ontology_path", self.config.ontology_path,
            "--work_dir", self.config.work_dir,
            "--integration_out_dir", self.config.integration_out_dir,
            "--model_script", self.config.model_script,
            "--model_out_dir", self.config.model_out_dir,
            "--llm_api_url", self.config.llm_api_url,
            "--llm_model", self.config.llm_model,
            "--vision_model", self.config.vision_model,
            "--allow_embedded_reset", "0",
        ]
        if stage == "extract_batch":
            command += [
                "--run_mode", str(request.get("run_mode", "expand")),
                "--max_papers", str(int(request.get("max_papers", 100))),
                "--full_literature_run",
                "--family_gating", str(request.get("family_gating", "strict")),
                "--inline_vision", "0",
                "--vision_enable", "0",
                "--llm_cache_enable", "1",
                "--disable_google_drive", "1" if request.get("disable_google_drive", True) else "0",
                "--no_require_doi",
            ]
            if request.get("search_query"):
                command += ["--search_query", str(request["search_query"])]
        elif stage == "vision_pass":
            command += [
                "--vision_enable", "1",
                "--vision_only_max_papers", str(int(request.get("max_papers", 0))),
                "--vision_update_mode", str(request.get("vision_update_mode", "append")),
            ]
        elif stage == "integrate_and_model":
            command += ["--skip_literature_agent", "--no_require_doi"]
            if request.get("run_model"):
                command.append("--run_model")
        elif stage == "knowledge_graph":
            command += ["--skip_literature_agent", "--knowledge_graph_out_dir", self.config.knowledge_graph_out_dir]
        return command

    def start_stage(self, stage: str, request: dict[str, Any] | None = None, wait: bool = False) -> dict[str, Any]:
        request = request or {}
        job_id = f"{stage}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        log_path = self.job_dir / f"{job_id}.log"
        command = self.build_command(stage, request)
        now = time.time()
        job = LiteratureJob(job_id, stage, "queued", command, now, now, log_path=str(log_path), request=request)
        self._write_job(job)
        with log_path.open("w", encoding="utf-8") as log:
            runner = Path(__file__).with_name("literature_agent_job_runner.py")
            process = subprocess.Popen(
                [self.config.python_executable, str(runner), str(self.job_dir / f"{job_id}.command.json")],
                cwd=str(Path(self.config.controller).parent),
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        job.pid = process.pid
        job.status = "running"
        job.updated_at = time.time()
        self._write_job(job)
        if wait:
            return_code = process.wait()
            job.return_code = return_code
            job.status = "completed" if return_code == 0 else "failed"
            job.updated_at = time.time()
            self._write_job(job)
        return asdict(job)

    def job_status(self, job_id: str) -> dict[str, Any]:
        job = self._read_job(job_id)
        if job.status == "running" and job.pid and not _pid_exists(job.pid):
            return_code_path = self.job_dir / f"{job_id}.returncode"
            job.return_code = int(return_code_path.read_text()) if return_code_path.exists() else None
            job.status = "completed" if job.return_code in {None, 0} else "failed"
            job.updated_at = time.time()
            self._write_job(job)
        payload = asdict(job)
        payload["log_tail"] = self._log_tail(job.log_path)
        return payload

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        job = self._read_job(job_id)
        if job.status == "running" and job.pid and _pid_exists(job.pid):
            os.kill(job.pid, signal.SIGTERM)
            job.status = "cancelled"
            job.updated_at = time.time()
            self._write_job(job)
        return asdict(job)

    def list_jobs(self) -> list[LiteratureJob]:
        jobs = []
        for path in sorted(self.job_dir.glob("*.json"), reverse=True):
            try:
                jobs.append(LiteratureJob(**json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return jobs

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        terms = [term for term in re.findall(r"[A-Za-z0-9+\-]{3,}", query.lower()) if term not in {"the", "and", "with"}]
        summaries_dir = Path(self.config.work_dir) / "paper_summaries_text"
        metadata = self._record_metadata()
        ranked: list[tuple[int, dict[str, Any]]] = []
        for path in summaries_dir.glob("*_summary.txt"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            lowered = text.lower()
            score = sum(lowered.count(term) for term in terms)
            if score <= 0:
                continue
            slug = path.name.removesuffix("_summary.txt")
            row = metadata.get(slug, {})
            ranked.append(
                (
                    score,
                    {
                        "paper_slug": slug,
                        "title": row.get("Ref_title") or row.get("title") or _title_from_summary(text) or slug,
                        "doi": row.get("Ref_DOI_number") or row.get("doi"),
                        "score": score,
                        "summary_excerpt": _excerpt(text, terms),
                        "summary_path": str(path),
                        "structured_json_path": str(Path(self.config.work_dir) / "json" / f"{slug}.json"),
                    },
                )
            )
        return [item for _, item in sorted(ranked, key=lambda pair: pair[0], reverse=True)[:limit]]

    def search_relationships(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        path = Path(self.config.knowledge_graph_out_dir) / "derived_views" / "learned_scientific_relationships.csv"
        if not path.exists():
            return []
        terms = [term for term in re.findall(r"[A-Za-z0-9+\-]{3,}", query.lower()) if term not in {"the", "and", "with"}]
        ranked = []
        with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
            for row in csv.DictReader(handle):
                text = " ".join(str(row.get(key, "")) for key in ("subject", "relationship", "object")).lower()
                score = sum(text.count(term) for term in terms)
                if score:
                    ranked.append((score, row))
        return [
            {
                "subject": row.get("subject"),
                "relationship": row.get("relationship"),
                "object": row.get("object"),
                "paper_id": row.get("paper_id"),
                "claim_id": row.get("claim_id"),
                "evidence": row.get("evidence") or row.get("evidence_text"),
                "score": score,
            }
            for score, row in sorted(ranked, key=lambda pair: pair[0], reverse=True)[:limit]
        ]

    def evidence_packet(self, query: str, limit: int = 5) -> dict[str, Any]:
        papers = self.search(query, limit=limit)
        relationships = self.search_relationships(query, limit=limit)
        lines = ["Evidence-grounded LiteratureAgent packet:"]
        for index, paper in enumerate(papers, 1):
            lines.append(
                f"\nPaper {index}: {paper['title']}\n"
                f"DOI: {paper.get('doi') or 'not available'} | paper_slug: {paper['paper_slug']}\n"
                f"Summary evidence: {paper['summary_excerpt']}"
            )
        if relationships:
            lines.append("\nLearned scientific relationships:")
            for index, rel in enumerate(relationships, 1):
                lines.append(
                    f"{index}. {rel.get('subject')} -> {rel.get('relationship')} -> {rel.get('object')} "
                    f"[paper={rel.get('paper_id') or 'unknown'}, claim={rel.get('claim_id') or 'unknown'}]"
                )
        return {
            "query": query,
            "papers": papers,
            "relationships": relationships,
            "formatted_context": "\n".join(lines)[:16000],
            "provenance": {
                "work_dir": self.config.work_dir,
                "knowledge_graph_dir": self.config.knowledge_graph_out_dir,
                "paper_count": len(papers),
                "relationship_count": len(relationships),
            },
        }

    def evidence_context(self, query: str, limit: int = 5, max_chars: int = 12000) -> str:
        packet = self.evidence_packet(query, limit=limit)
        if not packet["papers"] and not packet["relationships"]:
            return "No matching locally mined LiteratureAgent evidence was found."
        return packet["formatted_context"][:max_chars]

    def execute_task(self, task: AgentTask) -> AgentResult:
        actions = {
            "health": lambda: self.health(),
            "artifacts": lambda: self.artifact_manifest(),
            "search": lambda: self.search(str(task.payload.get("query", "")), int(task.payload.get("limit", 8))),
            "evidence_packet": lambda: self.evidence_packet(
                str(task.payload.get("query", "")), int(task.payload.get("limit", 5))
            ),
            "job_status": lambda: self.job_status(str(task.payload["job_id"])),
            "cancel_job": lambda: self.cancel_job(str(task.payload["job_id"])),
            "start_stage": lambda: self.start_stage(
                str(task.payload["stage"]), dict(task.payload.get("request", {})), bool(task.payload.get("wait", False))
            ),
        }
        if task.action not in actions:
            return AgentResult(task.task_id, "literature_agent", task.action, "failed", error="Unsupported action")
        data = actions[task.action]()
        return AgentResult(
            task_id=task.task_id,
            agent_id="literature_agent",
            action=task.action,
            status="completed",
            data=data,
            artifacts=self.artifact_manifest() if task.action in {"evidence_packet", "start_stage"} else {},
        )

    def artifact_manifest(self) -> dict[str, Any]:
        work = Path(self.config.work_dir)
        paths = {
            "all_records_csv": work / "csv" / "all_records.csv",
            "paper_registry": work / "paper_registry.json",
            "paper_type_gate_report": work / "paper_type_gate_report.csv",
            "paper_summaries_text": work / "paper_summaries_text",
            "paper_summaries_json": work / "paper_summaries_json",
            "structured_json": work / "json",
            "figure_reports": work / "figure_reports",
            "integration": Path(self.config.integration_out_dir),
            "models": Path(self.config.model_out_dir),
            "knowledge_graph": Path(self.config.knowledge_graph_out_dir),
        }
        return {
            name: {"path": str(path), "exists": path.exists(), "files": _file_count(path)}
            for name, path in paths.items()
        }

    def _record_metadata(self) -> dict[str, dict[str, str]]:
        registry_path = Path(self.config.work_dir) / "paper_registry.json"
        if registry_path.exists():
            try:
                payload = json.loads(registry_path.read_text(encoding="utf-8"))
                papers = payload.get("papers", {}) if isinstance(payload, dict) else {}
                if isinstance(papers, dict):
                    return {
                        str(record.get("slug") or key): record
                        for key, record in papers.items()
                        if isinstance(record, dict) and (record.get("slug") or key)
                    }
            except Exception:
                pass
        csv_path = Path(self.config.work_dir) / "csv" / "all_records.csv"
        if not csv_path.exists():
            return {}
        result: dict[str, dict[str, str]] = {}
        with csv_path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
            for row in csv.DictReader(handle):
                slug = row.get("paper_slug") or row.get("_paper_slug") or row.get("Ref_internal_sample_id")
                if slug:
                    result[str(slug)] = row
        return result

    def _write_job(self, job: LiteratureJob) -> None:
        (self.job_dir / f"{job.job_id}.json").write_text(json.dumps(asdict(job), indent=2), encoding="utf-8")
        (self.job_dir / f"{job.job_id}.command.json").write_text(
            json.dumps({"job_id": job.job_id, "command": job.command, "job_dir": str(self.job_dir)}, indent=2),
            encoding="utf-8",
        )

    def _read_job(self, job_id: str) -> LiteratureJob:
        path = self.job_dir / f"{job_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Unknown LiteratureAgent job: {job_id}")
        return LiteratureJob(**json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def _log_tail(log_path: str | None, lines: int = 30) -> str:
        if not log_path or not Path(log_path).exists():
            return ""
        return "\n".join(Path(log_path).read_text(encoding="utf-8", errors="ignore").splitlines()[-lines:])


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _file_count(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return 1
    return sum(1 for item in path.rglob("*") if item.is_file())


def _title_from_summary(text: str) -> str | None:
    for line in text.splitlines()[:12]:
        cleaned = line.strip().strip("#").strip()
        if cleaned and len(cleaned) > 8 and not cleaned.lower().startswith(("paper summary", "executive summary")):
            return cleaned
    return None


def _excerpt(text: str, terms: list[str], radius: int = 900) -> str:
    lowered = text.lower()
    positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    start = max(0, (min(positions) if positions else 0) - 200)
    return " ".join(text[start : start + radius].split())
