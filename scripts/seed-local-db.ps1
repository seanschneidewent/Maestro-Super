#Requires -Version 5.1
<#
.SYNOPSIS
    Seed local Postgres with production data from Supabase.
.DESCRIPTION
    Dumps data from Supabase production Postgres and restores into local
    Docker Postgres. Uses --data-only because alembic provides the schema.

    Prerequisites:
    - Docker running with maestro-postgres container healthy
    - PostgreSQL client tools on PATH (psql, pg_dump)
      Install: https://www.postgresql.org/download/windows/
    - Alembic migrations already run (.\scripts\dev.ps1 handles this)

    Alternative if pg_dump is not on PATH:
    You can run pg_dump inside the Docker container instead. See the
    --UsePgDocker flag.
.PARAMETER UsePgDocker
    Use pg_dump/psql from inside the Docker container instead of local PATH.
    Slower but doesn't require PostgreSQL client tools installed.
#>

param(
    [string]$SupabaseHost = "aws-0-us-west-2.pooler.supabase.com",
    [int]$SupabasePort = 5432,
    [string]$SupabaseUser = "postgres.ybyqobdyvbmsiehdmxwp",
    [string]$SupabaseDb = "postgres",
    [string]$SupabasePassword = "SchneidewentM1G@r@nd",
    [string]$LocalHost = "localhost",
    [int]$LocalPort = 5432,
    [string]$LocalUser = "postgres",
    [string]$LocalPassword = "maestro",
    [string]$LocalDb = "maestro",
    [switch]$UsePgDocker
)

$ErrorActionPreference = "Stop"

# Tables to dump (in dependency order)
$tables = @(
    "projects",
    "disciplines",
    "pages",
    "pointers",
    "pointer_references",
    "conversations",
    "queries",
    "query_pages",
    "processing_jobs",
    "usage_events",
    "user_usages",
    "project_memory_files"
)

# Reverse order for truncation (children first)
$reverseTables = @(
    "project_memory_files",
    "user_usages",
    "usage_events",
    "processing_jobs",
    "query_pages",
    "queries",
    "conversations",
    "pointer_references",
    "pointers",
    "pages",
    "disciplines",
    "projects"
)

$dumpFile = Join-Path $PSScriptRoot "supabase-dump.sql"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Maestro Local DB Seeder" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Check Docker container ---
Write-Host "[1/4] Checking maestro-postgres container..." -ForegroundColor Yellow
$health = docker inspect --format='{{.State.Health.Status}}' maestro-postgres 2>&1
if ($health -ne "healthy") {
    Write-Host "  ERROR: maestro-postgres is not healthy (status: $health)" -ForegroundColor Red
    Write-Host "  Run: docker compose up -d  (from repo root)" -ForegroundColor Yellow
    exit 1
}
Write-Host "  Container is healthy." -ForegroundColor Green

# --- Step 2: Dump from Supabase ---
Write-Host "[2/4] Dumping from Supabase production..." -ForegroundColor Yellow
Write-Host "  Host: $SupabaseHost" -ForegroundColor Gray
Write-Host "  Tables: $($tables.Count)" -ForegroundColor Gray

$tableArgs = $tables | ForEach-Object { "--table=$_" }

$env:PGPASSWORD = $SupabasePassword

if ($UsePgDocker) {
    # Run pg_dump from inside the Docker container connecting to Supabase
    $pgDumpCmd = "pg_dump --host=$SupabaseHost --port=$SupabasePort --username=$SupabaseUser --dbname=$SupabaseDb --data-only --no-owner --no-acl --inserts $($tableArgs -join ' ')"
    docker exec -e PGPASSWORD=$SupabasePassword maestro-postgres bash -c "$pgDumpCmd" > $dumpFile
} else {
    $pgDumpArgs = @(
        "--host=$SupabaseHost",
        "--port=$SupabasePort",
        "--username=$SupabaseUser",
        "--dbname=$SupabaseDb",
        "--data-only",
        "--no-owner",
        "--no-acl",
        "--inserts"
    ) + $tableArgs + @("--file=$dumpFile")

    & pg_dump @pgDumpArgs
}

if (-not (Test-Path $dumpFile) -or (Get-Item $dumpFile).Length -eq 0) {
    Write-Host "  ERROR: Dump file is empty or missing." -ForegroundColor Red
    Write-Host "  Make sure pg_dump is on PATH or use -UsePgDocker flag." -ForegroundColor Yellow
    exit 1
}

$dumpSize = [math]::Round((Get-Item $dumpFile).Length / 1MB, 2)
Write-Host "  Dump complete ($dumpSize MB)" -ForegroundColor Green

# --- Step 3: Truncate local tables ---
Write-Host "[3/4] Truncating local tables..." -ForegroundColor Yellow
$env:PGPASSWORD = $LocalPassword

foreach ($t in $reverseTables) {
    & psql -h $LocalHost -p $LocalPort -U $LocalUser -d $LocalDb -c "TRUNCATE TABLE $t CASCADE;" 2>$null
}
Write-Host "  Tables truncated." -ForegroundColor Green

# --- Step 4: Restore into local ---
Write-Host "[4/4] Restoring into local Postgres..." -ForegroundColor Yellow
& psql -h $LocalHost -p $LocalPort -U $LocalUser -d $LocalDb -f $dumpFile -q

Write-Host "  Restore complete." -ForegroundColor Green

# Cleanup
Remove-Item $dumpFile -ErrorAction SilentlyContinue
$env:PGPASSWORD = $null

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Seed complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Local DB: $LocalHost`:$LocalPort/$LocalDb" -ForegroundColor White
Write-Host "  Tables seeded: $($tables.Count)" -ForegroundColor White
Write-Host ""
Write-Host "  To re-seed: .\scripts\seed-local-db.ps1" -ForegroundColor Gray
Write-Host "  To reset DB: docker compose down -v && docker compose up -d" -ForegroundColor Gray
Write-Host ""
