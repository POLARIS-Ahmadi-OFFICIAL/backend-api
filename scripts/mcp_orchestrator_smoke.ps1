param(
    [Parameter(Mandatory = $false)]
    [string]$OrchestratorUrl = "http://127.0.0.1:8010",

    [Parameter(Mandatory = $false)]
    [string]$Query = "perovskite solar cell stability"
)

$ErrorActionPreference = "Stop"

function Invoke-JsonPost {
    param(
        [string]$Url,
        [hashtable]$Body
    )
    $json = $Body | ConvertTo-Json -Depth 10
    return Invoke-RestMethod -Method Post -Uri $Url -ContentType "application/json" -Body $json
}

Write-Host "==> Health"
Invoke-RestMethod -Method Get -Uri "$OrchestratorUrl/health" | ConvertTo-Json -Depth 10

Write-Host "==> MCP Tools"
Invoke-RestMethod -Method Get -Uri "$OrchestratorUrl/tools" | ConvertTo-Json -Depth 10

Write-Host "==> Search Papers (hybrid)"
Invoke-JsonPost -Url "$OrchestratorUrl/search-papers" -Body @{
    query = $Query
    year_min = 2021
    year_max = 2026
    max_candidates = 5
    source_mode = "hybrid"
} | ConvertTo-Json -Depth 20

Write-Host "==> Propose Hypothesis (history-gated)"
Invoke-JsonPost -Url "$OrchestratorUrl/propose-hypothesis" -Body @{
    hypothesis_text = "Use additive engineering for improved perovskite stability under humidity stress."
    material_hint = "FA/Cs perovskite"
    source = "smoke-test"
    record_if_allowed = $false
} | ConvertTo-Json -Depth 20

Write-Host "Done."
