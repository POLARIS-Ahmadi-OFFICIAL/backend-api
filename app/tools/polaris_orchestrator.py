"""Small first-class agent registry/orchestrator for the current POLARIS codebase."""

from __future__ import annotations

from typing import Any, Protocol

from app.tools.agent_contract import AgentResult, AgentTask
from app.tools.literature_agent_service import LiteratureAgentService


class PolarisAgent(Protocol):
    def execute_task(self, task: AgentTask) -> AgentResult: ...


class PolarisOrchestrator:
    def __init__(self):
        self.agents: dict[str, PolarisAgent] = {}
        self.register("literature_agent", LiteratureAgentService())

    def register(self, agent_id: str, agent: PolarisAgent) -> None:
        self.agents[agent_id] = agent

    def dispatch(self, task: AgentTask | dict[str, Any]) -> AgentResult:
        task = task if isinstance(task, AgentTask) else AgentTask(**task)
        agent = self.agents.get(task.agent_id)
        if not agent:
            return AgentResult(
                task_id=task.task_id,
                agent_id=task.agent_id,
                action=task.action,
                status="failed",
                error=f"Unknown POLARIS agent: {task.agent_id}",
            )
        try:
            return agent.execute_task(task)
        except Exception as exc:
            return AgentResult(
                task_id=task.task_id,
                agent_id=task.agent_id,
                action=task.action,
                status="failed",
                error=repr(exc),
            )

    def literature_evidence(self, query: str, limit: int = 5) -> dict[str, Any]:
        result = self.dispatch(
            AgentTask("literature_agent", "evidence_packet", {"query": query, "limit": limit})
        )
        return result.data if result.status == "completed" else {"formatted_context": result.error or "Evidence unavailable."}
