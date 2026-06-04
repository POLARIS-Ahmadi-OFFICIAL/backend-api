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
    $json = $Body | ConvertTo-Json -Depth 20
    return Invoke-RestMethod -Method Post -Uri $Url -ContentType "application/json" -Body $json
}

Write-Host "==> list_processed_papers"
$list = Invoke-JsonPost -Url "$OrchestratorUrl/process-paper" -Body @{
    action = "list_processed_papers"
}
$list | ConvertTo-Json -Depth 20

$slug = $null
if ($list.result -and $list.result.papers -and $list.result.papers.Count -gt 0) {
    $slug = $list.result.papers[0].paper_slug
}
if (-not $slug -and $list.result -and $list.result.processed_papers -and $list.result.processed_papers.Count -gt 0) {
    $slug = $list.result.processed_papers[0].paper_slug
}
if (-not $slug -and $list.result -and $list.result.processed_papers -and $list.result.processed_papers.Count -gt 0) {
    $slug = $list.result.processed_papers[0].slug
}

if ($slug) {
    Write-Host "==> get_saved_paper_output (paper_slug=$slug)"
    $saved = Invoke-JsonPost -Url "$OrchestratorUrl/process-paper" -Body @{
        action = "get_saved_paper_output"
        paper_slug = $slug
    }
    $saved | ConvertTo-Json -Depth 20
} else {
    Write-Host "No processed paper found; running process_batch max_papers=1..."
    $batch = Invoke-JsonPost -Url "$OrchestratorUrl/process-paper" -Body @{
        action = "process_batch"
        query = $Query
        year_min = 2021
        year_max = 2026
        max_papers = 1
        run_mode = "resume"
        force_reprocess = $false
        reset_output = $false
    }
    $batch | ConvertTo-Json -Depth 20

    Write-Host "==> list_processed_papers (post-batch)"
    $list2 = Invoke-JsonPost -Url "$OrchestratorUrl/process-paper" -Body @{
        action = "list_processed_papers"
    }
    $list2 | ConvertTo-Json -Depth 20
}

Write-Host "Done."
