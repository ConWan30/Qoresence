[CmdletBinding()]
param(
    [switch]$WithGameModels
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path $PSScriptRoot).Path
$venv = Join-Path $root ".venv"
$pythonExe = $null
$pythonArgs = @()

function Test-PythonCommand([string]$command, [string[]]$arguments) {
    try {
        $version = & $command @arguments -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $version -match '^3\.(1[1-9]|[2-9][0-9])$') {
            return $true
        }
    } catch {
    }
    return $false
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    if (Test-PythonCommand "py" @("-3.11")) {
        $pythonExe = "py"
        $pythonArgs = @("-3.11")
    }
}
if (-not $pythonExe -and (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Test-PythonCommand "python" @()) {
        $pythonExe = "python"
        $pythonArgs = @()
    }
}
if (-not $pythonExe) {
    throw "Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/windows/ and run this installer again."
}

Write-Host "Using Python: $pythonExe $($pythonArgs -join ' ')"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    Write-Host "Creating local virtual environment..."
    & $pythonExe @pythonArgs -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the local virtual environment." }
}

$venvPython = Join-Path $venv "Scripts\python.exe"
Write-Host "Updating pip..."
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not update pip." }

$extras = "streamer,controller,screen,visual,twitch,mcp,deck,windows"
$projectSpec = "${root}[$extras]"
Write-Host "Installing Qoresence pilot dependencies..."
& $venvPython -m pip install -e $projectSpec
if ($LASTEXITCODE -ne 0) { throw "Could not install Qoresence dependencies." }

if ($WithGameModels) {
    Write-Host "Installing optional game-model dependencies..."
    & $venvPython -m pip install -e "${root}[game]"
    if ($LASTEXITCODE -ne 0) { throw "Could not install optional game-model dependencies." }
}

Write-Host ""
Write-Host "Qoresence is installed locally in $venv" -ForegroundColor Green
Write-Host "Start the pilot with: .\Start-Qoresence.bat"
Write-Host "AgentGlass remains opt-in and local-only."
