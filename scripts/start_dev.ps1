<#
Starts the prototype for development on Windows, from a double-click on start_dev.cmd:

  1. checks that Python 3.11+ and Node.js are installed, and that ports 8000 and 5180 are free;
  2. the first time only, creates backend\.venv with requirements.txt and installs the web packages (npm ci);
     later runs install again only when backend\requirements.txt or web\package-lock.json has changed;
  3. opens the backend (uvicorn, port 8000) and the web dashboard (Vite, port 5180) in two Windows Terminal tabs,
     or in two PowerShell windows where Windows Terminal is not installed; the Web tab waits for the backend;
  4. opens http://localhost:5180 in the browser once the dashboard answers.

The backend runs as it does when started by hand: SQLite (backend\uav.db) unless DATABASE_URL is set.
Ctrl+C in a tab stops that server. Nothing that is already running is stopped.

    scripts\start_dev.cmd                    # what the double-click runs
    scripts\start_dev.ps1 -PlainWindows      # two PowerShell windows even where Windows Terminal is installed
#>
[CmdletBinding()]
param(
    [switch]$PlainWindows,
    # Set by this script for the two tabs it opens.
    [ValidateSet('Backend', 'Web')]
    [string]$Part
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # Invoke-WebRequest's progress bar slows Windows PowerShell down

$Self = $PSCommandPath
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Web = Join-Path $Root 'web'
$VenvPython = Join-Path $Backend '.venv\Scripts\python.exe'
# The ports are fixed in web\vite.config.ts (5180, with /api and /ws forwarded to 8000).
$BackendPort = 8000
$WebPort = 5180
$HealthUrl = "http://127.0.0.1:$BackendPort/api/health"
$WebUrl = "http://localhost:$WebPort"
$PythonNeeded = [version]'3.11'  # datetime.UTC, enum.StrEnum

function Write-Step([string]$Text) { Write-Host "== $Text" -ForegroundColor Cyan }

# Runs a program and stops with a message if it fails. Only the exit code counts: pip and npm print warnings on
# stderr, which Windows PowerShell can turn into errors under ErrorActionPreference Stop.
function Invoke-Program([string]$What, [scriptblock]$Command) {
    $ErrorActionPreference = 'Continue'
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE). Read the messages above." }
}

function Test-Url([string]$Url) {
    try { return (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { return $false }
}

function Wait-Url([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Url $Url) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

# The py launcher first: "python" can be the Microsoft Store shortcut, which only offers to install Python.
function Find-Python {
    $ErrorActionPreference = 'Continue'
    foreach ($candidate in @(@{ Exe = 'py'; Args = @('-3') }, @{ Exe = 'python'; Args = @() })) {
        if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) { continue }
        $pyArgs = $candidate.Args
        $text = (& $candidate.Exe @pyArgs --version 2>&1) | Out-String
        if ($text -match 'Python (\d+\.\d+\.\d+)') {
            return [pscustomobject]@{ Exe = $candidate.Exe; Args = $candidate.Args; Version = [version]$Matches[1] }
        }
    }
    return $null
}

function Find-Node {
    if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        return $null
    }
    if (((& node --version) | Out-String) -match 'v(\d+\.\d+\.\d+)') { return [version]$Matches[1] }
    return $null
}

function Get-BusyPorts {
    $listening = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
        ForEach-Object { $_.Port }
    return @($BackendPort, $WebPort) | Where-Object { $listening -contains $_ }
}

# What was installed is remembered as the SHA-256 of the file it came from, kept inside the folder it was installed
# into (both are ignored by git), so deleting .venv or node_modules installs again too.
function Test-Stamp([string]$Stamp, [string]$Source) {
    if (-not (Test-Path -LiteralPath $Stamp)) { return $false }
    return (Get-Content -LiteralPath $Stamp -Raw).Trim() -eq (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
}

function Write-Stamp([string]$Stamp, [string]$Source) {
    Set-Content -LiteralPath $Stamp -Value (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash -Encoding Ascii
}

function Install-Backend($Python) {
    $requirements = Join-Path $Backend 'requirements.txt'
    $stamp = Join-Path $Backend '.venv\.start_dev.sha256'
    if ((Test-Path -LiteralPath $VenvPython) -and (Test-Stamp $stamp $requirements)) {
        Write-Host 'Backend packages: up to date'
        return
    }
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Write-Step 'Creating backend\.venv'
        $pyArgs = $Python.Args
        Invoke-Program 'Creating backend\.venv' { & $Python.Exe @pyArgs -m venv (Join-Path $Backend '.venv') }
    }
    Write-Step 'Installing backend\requirements.txt'
    Invoke-Program 'pip install' { & $VenvPython -m pip install --disable-pip-version-check -r $requirements }
    Write-Stamp $stamp $requirements
}

function Install-Web {
    $lock = Join-Path $Web 'package-lock.json'
    $stamp = Join-Path $Web 'node_modules\.start_dev.sha256'
    if (Test-Stamp $stamp $lock) {
        Write-Host 'Web packages: up to date'
        return
    }
    # npm ci installs exactly what package-lock.json lists, and never rewrites it as npm install can.
    Write-Step 'Installing the web packages (npm ci)'
    Push-Location -LiteralPath $Web
    try { Invoke-Program 'npm ci' { & npm.cmd ci --no-audit --no-fund } } finally { Pop-Location }
    Write-Stamp $stamp $lock
}

function Start-Servers {
    $folders = [ordered]@{ Backend = $Backend; Web = $Web }
    $terminal = Get-Command wt.exe -ErrorAction SilentlyContinue
    if ($terminal -and -not $PlainWindows) {
        $arguments = @('-w', 'new')
        foreach ($name in $folders.Keys) {
            if ($arguments.Count -gt 2) { $arguments += ';' }
            $arguments += @('new-tab', '--title', $name, '--suppressApplicationTitle', '-d', $folders[$name],
                'powershell.exe', '-NoLogo', '-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass',
                '-File', $Self, '-Part', $name)
        }
        Invoke-Program 'Opening Windows Terminal' { & $terminal.Source @arguments }
        Write-Host 'Opened Windows Terminal with two tabs: Backend and Web.'
        return
    }
    foreach ($name in $folders.Keys) {
        # Start-Process joins its arguments with spaces, so the script's path is quoted here.
        Start-Process powershell.exe -WorkingDirectory $folders[$name] -ArgumentList (
            "-NoLogo -NoProfile -NoExit -ExecutionPolicy Bypass -File `"$Self`" -Part $name")
    }
    Write-Host 'Opened two PowerShell windows: Backend and Web.'
}

if ($Part -eq 'Backend') {
    $Host.UI.RawUI.WindowTitle = 'Backend'
    # Only the host and database name of DATABASE_URL: its password comes before the @.
    $database = if ($env:DATABASE_URL) { 'DATABASE_URL, ' + ($env:DATABASE_URL -replace '^.*@', '' -replace '\?.*$', '') }
                else { 'SQLite, backend\uav.db' }
    Write-Host "Backend on http://127.0.0.1:$BackendPort ($database). Ctrl+C stops it." -ForegroundColor Cyan
    Set-Location -LiteralPath $Backend
    & $VenvPython -m uvicorn app.main:app --port $BackendPort
    return
}

if ($Part -eq 'Web') {
    $Host.UI.RawUI.WindowTitle = 'Web'
    Write-Host "Waiting for the backend ($HealthUrl)..." -ForegroundColor Cyan
    if (-not (Wait-Url $HealthUrl 120)) {
        Write-Host ('The backend did not answer within 2 minutes, so the web dashboard was not started. Read the ' +
            'Backend tab, close both tabs, then run start_dev.cmd again.') -ForegroundColor Red
        return
    }
    Write-Host "Web dashboard on $WebUrl. Ctrl+C stops it." -ForegroundColor Cyan
    Set-Location -LiteralPath $Web
    & npm.cmd run dev
    return
}

$started = Get-Date
try {
    Write-Step 'Checking Python, Node.js and the ports'
    $python = Find-Python
    if (-not $python) {
        throw ('Python was not found. Install Python 3.11 or newer from https://www.python.org/downloads/ ' +
            '(tick "Add python.exe to PATH"), then run start_dev.cmd again.')
    }
    if ($python.Version -lt $PythonNeeded) {
        throw "Python $($python.Version) is too old: the backend needs 3.11 or newer (https://www.python.org/downloads/)."
    }
    $node = Find-Node
    if (-not $node) {
        throw 'Node.js was not found. Install it from https://nodejs.org/ (npm comes with it), then run start_dev.cmd again.'
    }
    # Vite 8 runs on Node.js 20.19+ and 22.12+.
    if ($node -lt [version]'20.19' -or ($node.Major -in 21, 22 -and $node -lt [version]'22.12')) {
        throw "Node.js $node is too old: the web dashboard needs 20.19, 22.12 or newer (https://nodejs.org/)."
    }
    Write-Host "Python $($python.Version), Node.js $node"
    if ($python.Version -lt [version]'3.14' -or $node.Major -lt 26) {
        Write-Host 'Note: the project was tried with Python 3.14 and Node.js 26 only.' -ForegroundColor Yellow
    }
    $busy = @(Get-BusyPorts)
    if ($busy.Count -gt 0) {
        $which = if ($busy.Count -gt 1) { "Ports $($busy -join ' and ') are" } else { "Port $busy is" }
        throw ("$which already in use, so nothing was started. If the backend or the dashboard is already running, " +
            "use it ($WebUrl) or close it first. Nothing was stopped.")
    }

    Install-Backend $python
    Install-Web

    Write-Step 'Starting the backend and the web dashboard'
    Start-Servers
    Write-Step "Waiting for $WebUrl"
    if (-not (Wait-Url $HealthUrl 180)) { throw 'The backend did not answer within 3 minutes. Read the Backend tab.' }
    if (-not (Wait-Url $WebUrl 120)) { throw 'The web dashboard did not answer within 2 minutes. Read the Web tab.' }
    Start-Process $WebUrl
    Write-Host ('Ready after {0:N0} s: {1} is open in the browser.' -f ((Get-Date) - $started).TotalSeconds, $WebUrl) `
        -ForegroundColor Green
} catch {
    Write-Host "start_dev: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
