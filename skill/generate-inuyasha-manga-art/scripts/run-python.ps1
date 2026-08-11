[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $PythonArgs
)

$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptDirectory "..\..\.."))

$candidates = [System.Collections.Generic.List[string]]::new()
if ($env:INUYASHA_PYTHON) {
    $candidates.Add($env:INUYASHA_PYTHON)
}
if ($env:INUYASHA_WORKFLOW_HOME) {
    $candidates.Add((Join-Path $env:INUYASHA_WORKFLOW_HOME ".venv\Scripts\python.exe"))
}
$candidates.Add((Join-Path $repoRoot ".venv\Scripts\python.exe"))

foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        & $candidate @PythonArgs
        exit $LASTEXITCODE
    }
}

$launcher = Get-Command py -ErrorAction SilentlyContinue
if ($launcher) {
    & $launcher.Source -3 @PythonArgs
    exit $LASTEXITCODE
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & $python.Source @PythonArgs
    exit $LASTEXITCODE
}

throw "Python 3 was not found. Install it from python.org or run setup-windows.ps1 after Python is installed."
