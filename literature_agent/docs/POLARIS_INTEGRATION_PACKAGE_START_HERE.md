# LiteratureAgent Complete POLARIS Integration Package

This package contains the current LiteratureAgent scientific pipeline and the
first-class POLARIS integration layer. It is intended to be merged into an
existing POLARIS repository.

## What This Package Adds

- A shared `AgentTask` / `AgentResult` contract
- A POLARIS agent registry and orchestrator
- LiteratureAgent as a registered first-class POLARIS agent
- Durable background jobs with logs, status, and cancellation
- Evidence packets combining paper summaries and knowledge-graph relationships
- Literature evidence throughout the reasoning chain:
  - Socratic answers
  - tree-of-thought generation
  - hypothesis synthesis
  - hypothesis evaluation
- Streamlit controls for literature search and extraction jobs
- Search-only, resumable LiteratureAgent expansion

## Package Layout

```text
literature_agent/
  controller/
  config/
  models/
  scripts/
  docs/

polaris_overlay/
  tools/
  config/
  docs/
  tests/
  modified_existing_files/

install_into_polaris.ps1
PACKAGE_MANIFEST.json
```

## Recommended Integration

1. Extract the ZIP outside the POLARIS repository.
2. Review `polaris_overlay/modified_existing_files/` before merging.
3. Run the installer with the target POLARIS repository:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\install_into_polaris.ps1 `
  -PolarisRoot "C:\path\to\polaris"
```

The installer:

- creates a timestamped backup of existing modified files
- copies additive integration modules into `tools/`
- installs configuration, tests, and documentation
- replaces `tools/socratic.py` and `streamlit_app.py` with the integrated versions
- does not copy secrets, OAuth tokens, PDFs, caches, or runtime outputs

## Configure Runtime Paths

Edit:

```text
POLARIS_ROOT\config\literature_agent.json
```

POLARIS should eventually replace local paths with its managed artifact and
secrets configuration.

## Validate

```powershell
Set-Location "C:\path\to\polaris"
$env:POLARIS_LITERATURE_CONFIG = "$PWD\config\literature_agent.json"

python .\tools\literature_agent_cli.py health
python .\tools\polaris_orchestrator_cli.py literature_agent evidence_packet `
  --query perovskite humidity stability T80 `
  --limit 3
```

## Important Runtime Rules

- Keep inline vision disabled during extraction.
- Run `vision_pass` separately.
- Never delete an active LiteratureAgent work directory.
- Preserve strict extraction for device and stability records.
- Keep extraction resumable and cached.
- Use POLARIS-managed secrets; do not commit credentials.
- Treat LiteratureAgent evidence as provenance-bearing evidence, not unsupported truth.

## Not Included

- Google OAuth client secrets or tokens
- API keys
- downloaded PDFs
- raw LLM caches
- the full runtime output corpus
- the baseline Perovskite Database CSV

Existing LiteratureAgent outputs can be connected by configuring `work_dir`,
integration, model, and knowledge-graph paths.

See `CREDENTIALS_SETUP.md` and `.env.example` for the complete credential and
service checklist. Personal tokens and API keys must be supplied separately.
