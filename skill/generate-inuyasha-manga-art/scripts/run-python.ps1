[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $PythonArgs
)

$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptDirectory "..\..\.."))

$candidates = [System.Collections.Generic.List[object]]::new()
if ($env:INUYASHA_PYTHON) {
    $candidates.Add([pscustomobject]@{
        Source = "INUYASHA_PYTHON"
        Path = $env:INUYASHA_PYTHON
    }) | Out-Null
}
$repoPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $repoPython) {
    $candidates.Add([pscustomobject]@{
        Source = "the repository .venv"
        Path = $repoPython
    }) | Out-Null
}
if ($env:INUYASHA_WORKFLOW_HOME) {
    $workflowPython = Join-Path $env:INUYASHA_WORKFLOW_HOME ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $workflowPython) {
        $candidates.Add([pscustomobject]@{
            Source = "INUYASHA_WORKFLOW_HOME/.venv"
            Path = $workflowPython
        }) | Out-Null
    }
}

foreach ($entry in $candidates) {
    $sourceName = $entry.Source
    $candidate = $entry.Path
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "The Python selected from $sourceName is not executable: $candidate"
    }
    & $candidate -c "import PIL" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "The Python selected from $sourceName cannot import Pillow: $candidate. Run setup-windows.ps1 to repair the repository-only .venv, or set INUYASHA_PYTHON for this process. No package was installed automatically."
    }
    & $candidate @PythonArgs
    exit $LASTEXITCODE
}

$launcher = Get-Command py -ErrorAction SilentlyContinue
if ($launcher) {
    & $launcher.Source -3 -c "import PIL" 2>$null
    if ($LASTEXITCODE -eq 0) {
        & $launcher.Source -3 @PythonArgs
        exit $LASTEXITCODE
    }
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & $python.Source -c "import PIL" 2>$null
    if ($LASTEXITCODE -eq 0) {
        & $python.Source @PythonArgs
        exit $LASTEXITCODE
    }
}

throw "No Python 3 environment with Pillow was found. Run setup-windows.ps1 to create the repository-only .venv, or set INUYASHA_PYTHON for this process. No package was installed automatically."
