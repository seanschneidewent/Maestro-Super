#Requires -Version 5.1
<#
.SYNOPSIS
    Start Maestro-Super local development environment.
.DESCRIPTION
    1. Starts Docker Desktop if not running
    2. Starts Postgres container via Docker Compose
    3. Waits for Postgres health check
    4. Installs Python dependencies (if needed)
    5. Runs alembic migrations
    6. Starts backend (uvicorn --reload) in a new terminal
    7. Starts frontend (pnpm dev) in a new terminal
    8. Prints URLs and status
#>

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiDir = Join-Path $RepoRoot "services\api"
$WebDir = Join-Path $RepoRoot "apps\web"
$VenvPython = Join-Path $ApiDir "venv\Scripts\python.exe"
$VenvPip = Join-Path $ApiDir "venv\Scripts\pip.exe"
$VenvActivate = Join-Path $ApiDir "venv\Scripts\Activate.ps1"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Maestro Local Dev Startup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Docker Desktop ---
Write-Host "[1/7] Checking Docker..." -ForegroundColor Yellow
$dockerRunning = docker info 2>&1 | Select-String "Server Version"
if (-not $dockerRunning) {
    Write-Host "  Starting Docker Desktop..." -ForegroundColor Gray
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    $timeout = 60
    $elapsed = 0
    while ($elapsed -lt $timeout) {
        Start-Sleep -Seconds 3
        $elapsed += 3
        $dockerRunning = docker info 2>&1 | Select-String "Server Version"
        if ($dockerRunning) { break }
        Write-Host "  Waiting for Docker... ($elapsed/$timeout sec)" -ForegroundColor Gray
    }
    if (-not $dockerRunning) {
        Write-Host "  ERROR: Docker did not start within $timeout seconds." -ForegroundColor Red
        exit 1
    }
}
Write-Host "  Docker is running." -ForegroundColor Green

# --- Step 2: Docker Compose ---
Write-Host "[2/7] Starting Postgres container..." -ForegroundColor Yellow
Push-Location $RepoRoot
docker compose up -d
Pop-Location
Write-Host "  Postgres container started." -ForegroundColor Green

# --- Step 3: Wait for health ---
Write-Host "[3/7] Waiting for Postgres health check..." -ForegroundColor Yellow
$maxWait = 30
$waited = 0
$health = ""
while ($waited -lt $maxWait) {
    $health = docker inspect --format='{{.State.Health.Status}}' maestro-postgres 2>&1
    if ($health -eq "healthy") { break }
    Start-Sleep -Seconds 2
    $waited += 2
    Write-Host "  Waiting... ($waited/$maxWait sec) status=$health" -ForegroundColor Gray
}
if ($health -ne "healthy") {
    Write-Host "  ERROR: Postgres did not become healthy within $maxWait sec." -ForegroundColor Red
    exit 1
}
Write-Host "  Postgres is healthy." -ForegroundColor Green

# --- Step 4: Python dependencies ---
Write-Host "[4/7] Checking Python dependencies..." -ForegroundColor Yellow
if (-not (Test-Path $VenvPython)) {
    Write-Host "  ERROR: Python venv not found at $VenvPython" -ForegroundColor Red
    Write-Host "  Run: cd services\api && python -m venv venv" -ForegroundColor Yellow
    exit 1
}
& $VenvPip install -q -r (Join-Path $ApiDir "requirements.txt") 2>&1 | Out-Null
Write-Host "  Dependencies installed." -ForegroundColor Green

# --- Step 5: Alembic migrations ---
Write-Host "[5/7] Running alembic migrations..." -ForegroundColor Yellow
Push-Location $ApiDir
& $VenvPython -m alembic upgrade head
Pop-Location
Write-Host "  Migrations complete." -ForegroundColor Green

# --- Step 6: Start backend ---
Write-Host "[6/7] Starting backend (uvicorn)..." -ForegroundColor Yellow
$backendCmd = "Set-Location '$ApiDir'; & '$VenvActivate'; uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd
Write-Host "  Backend starting at http://localhost:8000" -ForegroundColor Green

# --- Step 7: Start frontend ---
Write-Host "[7/7] Starting frontend (pnpm dev)..." -ForegroundColor Yellow
$frontendCmd = "Set-Location '$WebDir'; pnpm dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd
Write-Host "  Frontend starting at http://localhost:3000" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Local dev environment is running!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "  Frontend: http://localhost:3000" -ForegroundColor White
Write-Host "  Postgres: localhost:5432 (maestro/maestro)" -ForegroundColor White
Write-Host "  Debug:    services/api/debug/last-query.json" -ForegroundColor White
Write-Host ""
Write-Host "  To seed data: .\scripts\seed-local-db.ps1" -ForegroundColor Gray
Write-Host "  To stop all:  docker compose down" -ForegroundColor Gray
Write-Host ""
