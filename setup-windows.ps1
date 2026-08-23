[CmdletBinding()]
param(
    [switch] $SkipDependencyInstall,
    [switch] $SkipCatalogBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$skillSource = Join-Path $repoRoot "skill\generate-inuyasha-manga-art"
$skillTarget = Join-Path $HOME ".agents\skills\generate-inuyasha-manga-art"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$launcher = Join-Path $skillTarget "scripts\run-python.ps1"
$workflowRoot = Join-Path $repoRoot "workflow\reference-workflow"

if (-not (Test-Path -LiteralPath $skillSource -PathType Container)) {
    throw "Run this script from the cloned inuyasha-art-workflow repository."
}

$pyCommand = Get-Command py -ErrorAction SilentlyContinue
if ($pyCommand) {
    & $pyCommand.Source -3 -m venv (Join-Path $repoRoot ".venv")
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python 3 is required. Install it from https://www.python.org/downloads/windows/ and rerun this script."
    }
    & $pythonCommand.Source -m venv (Join-Path $repoRoot ".venv")
}
if ($LASTEXITCODE -ne 0) {
    throw "Creating the Python virtual environment failed."
}

if (-not $SkipDependencyInstall) {
    & $venvPython -m pip install --no-cache-dir --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
    & $venvPython -m pip install --no-cache-dir -r (Join-Path $repoRoot "requirements-dev.txt")
    if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $skillTarget) | Out-Null
if (Test-Path -LiteralPath $skillTarget) {
    $backupSuffix = Get-Date -Format "yyyyMMdd-HHmmss"
    $skillBackup = "$skillTarget.backup-$backupSuffix"
    Move-Item -LiteralPath $skillTarget -Destination $skillBackup
    Write-Host "Previous skill moved to: $skillBackup"
}
Copy-Item -LiteralPath $skillSource -Destination $skillTarget -Recurse

[Environment]::SetEnvironmentVariable("INUYASHA_WORKFLOW_HOME", $repoRoot, "User")
$env:INUYASHA_WORKFLOW_HOME = $repoRoot
$env:INUYASHA_PYTHON = $venvPython
git -C $repoRoot config core.longpaths true

if (-not $SkipCatalogBuild) {
    & $launcher (Join-Path $skillTarget "scripts\build_reference_index.py") --workflow-root $workflowRoot
    if ($LASTEXITCODE -ne 0) { throw "Reference catalog build failed." }
    & $launcher (Join-Path $skillTarget "scripts\validate_workflow.py")
    if ($LASTEXITCODE -ne 0) { throw "Workflow validation failed." }
}

$pdftoppm = Get-Command pdftoppm -ErrorAction SilentlyContinue
if (-not $pdftoppm) {
    Write-Warning "pdftoppm is not installed. Image references work normally; PDF-page rendering needs Poppler on PATH."
}

Write-Host "Windows setup complete."
Write-Host "Skill: $skillTarget"
Write-Host "Workflow: $workflowRoot"
Write-Host "Restart Codex so it discovers the installed skill and persisted environment variable."
