# POLARIS Live LiteratureAgent Integration

The POLARIS repository currently provides a Streamlit hypothesis workflow, Gemini
reasoning tools, a FutureHouse/Edison literature path, and experimental-analysis
utilities. It does not yet have a formal task bus. The LiteratureAgent integration
therefore provides a lightweight service contract that can be called from the UI,
other agents, notebooks, or a future orchestrator.

## Added Contract

`polaris_integration/literature_agent_service.py` provides:

- health and artifact discovery
- resumable stage launch through subprocess jobs
- job status, logs, and cancellation
- local search across evidence-grounded LiteratureAgent summaries
- concise evidence context for hypothesis reasoning
- stable artifact paths for records, figures, integration, models, and knowledge graph

The service never imports the embedded runtime into Streamlit. Long-running work occurs
in child processes and writes job state under `E:\LiteratureAgent\polaris_jobs`.

## First-Class Agent Contract

`tools.agent_contract` defines shared `AgentTask` and `AgentResult` envelopes.
`tools.polaris_orchestrator.PolarisOrchestrator` registers LiteratureAgent and routes
actions through the same interface that future simulation, experiment, and modeling
agents can implement.

The `evidence_packet` action returns:

- relevant paper summaries with DOI/paper-slug provenance
- relevant scientific relationships from the knowledge graph
- artifact links and corpus provenance
- a prompt-ready formatted context

This packet is consumed during Socratic answering, tree-of-thought generation,
hypothesis synthesis, and hypothesis evaluation.

## POLARIS Installation

Copy these files into the POLARIS repository:

```text
tools/literature_agent_service.py
tools/literature_agent_cli.py
tools/agent_contract.py
tools/polaris_orchestrator.py
tools/polaris_orchestrator_cli.py
config/literature_agent.json
tests/test_literature_agent_service.py
```

Set:

```powershell
$env:POLARIS_LITERATURE_CONFIG="C:\path\to\polaris_ahmadi\config\literature_agent.json"
```

## Examples

Health and artifacts:

```powershell
python .\tools\literature_agent_cli.py health
python .\tools\literature_agent_cli.py artifacts
```

Retrieve local evidence for hypothesis reasoning:

```powershell
python .\tools\literature_agent_cli.py context perovskite humidity stability T80
```

Call LiteratureAgent through the common agent orchestrator:

```powershell
python .\tools\polaris_orchestrator_cli.py literature_agent evidence_packet `
  --query perovskite humidity stability T80 `
  --limit 3
```

Launch a search-only extraction batch:

```powershell
python .\tools\literature_agent_cli.py run extract_batch `
  --max-papers 100 `
  --search-query perovskite solar cell stability T80 retention
```

Inspect or cancel a job:

```powershell
python .\tools\literature_agent_cli.py jobs --job-id <job_id>
python .\tools\literature_agent_cli.py cancel <job_id>
```

## Hypothesis-Agent Usage

Before asking Gemini to evaluate a hypothesis, retrieve local context:

```python
from tools.literature_agent_service import LiteratureAgentService

literature = LiteratureAgentService()
context = literature.evidence_context(hypothesis, limit=5)
prompt = f"{analysis_prompt}\n\n{context}"
```

This makes the local, evidence-grounded literature corpus available to POLARIS while
retaining FutureHouse/Edison as an optional external retrieval source.
