$ErrorActionPreference = "Stop"

if (-not (Test-Path "backend\.env")) {
    Copy-Item "backend\.env.example" "backend\.env"
    Write-Host ""
    Write-Host "Created backend\.env from .env.example." -ForegroundColor Green
    Write-Host "Open backend\.env in Notepad and paste at least one API key." -ForegroundColor Yellow
    Write-Host "Easiest: get a free Cerebras key at https://cloud.cerebras.ai" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Press Enter once you have edited backend\.env to continue..."
    Read-Host
}

docker compose up --build
