param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("macOS", "windows", "android", "iOS")]
    [string]$Target,

    [Parameter(Mandatory = $true)]
    [ValidateSet("polaris_desktop", "polaris_mobile")]
    [string]$App,

    [Parameter(Mandatory = $false)]
    [ValidateSet("create", "build", "package", "all")]
    [string]$Step = "all"
)

$ErrorActionPreference = "Stop"

function Invoke-BriefcaseStep {
    param([string]$CmdStep)
    Write-Host "==> briefcase $CmdStep $Target -a $App"
    briefcase $CmdStep $Target -a $App --no-input
}

if ($Step -eq "all") {
    Invoke-BriefcaseStep "create"
    Invoke-BriefcaseStep "build"
    Invoke-BriefcaseStep "package"
} else {
    Invoke-BriefcaseStep $Step
}

Write-Host "Done."
