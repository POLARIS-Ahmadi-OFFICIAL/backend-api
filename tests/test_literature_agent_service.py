from app.tools.literature_agent_service import LiteratureAgentConfig, LiteratureAgentService
from app.tools.agent_contract import AgentTask
from app.tools.polaris_orchestrator import PolarisOrchestrator


def test_health_and_artifact_contract():
    service = LiteratureAgentService(LiteratureAgentConfig.load())
    health = service.health()
    assert health["service"] == "LiteratureAgent"
    assert "extract_batch" in health["stages"]
    assert "all_records_csv" in service.artifact_manifest()


def test_commands_preserve_pass_contract():
    service = LiteratureAgentService(LiteratureAgentConfig.load())
    extract = service.build_command("extract_batch", {"max_papers": 2, "search_query": "perovskite stability"})
    assert "--disable_google_drive" in extract
    assert "--inline_vision" in extract
    assert "perovskite stability" in extract
    integrate = service.build_command("integrate_and_model", {})
    assert "--skip_literature_agent" in integrate


def test_orchestrator_evidence_contract():
    result = PolarisOrchestrator().dispatch(
        AgentTask("literature_agent", "evidence_packet", {"query": "perovskite stability", "limit": 1})
    )
    assert result.status == "completed"
    assert "papers" in result.data
    assert "relationships" in result.data
    assert "provenance" in result.data
