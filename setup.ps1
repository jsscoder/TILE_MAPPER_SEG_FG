# ==============================================================================
# TILE_MAPPER_SEG_FG: One-Click Environment Setup (PowerShell)
# ==============================================================================

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "  TILE_MAPPER_SEG_FG: One-Click Environment Setup (uv)" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

# Add ~/.local/bin to PATH if present
$localBin = Join-Path $env:USERPROFILE ".local\bin"
if (Test-Path (Join-Path $localBin "uv.exe")) {
    $env:Path = "$localBin;$env:Path"
}

# 1. Check for uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[INFO] uv not found. Installing uv via Astral installer..." -ForegroundColor Yellow
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = "$localBin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Error "Failed to install uv automatically. Install manually: https://docs.astral.sh/uv/"
        exit 1
    }
}

Write-Host "[OK] uv is ready: $(uv --version)" -ForegroundColor Green

# 2. Create virtual environment
if (-not (Test-Path ".venv")) {
    Write-Host "[INFO] Creating virtual environment (.venv)..." -ForegroundColor Yellow
    uv venv .venv
} else {
    Write-Host "[OK] Virtual environment (.venv) already exists." -ForegroundColor Green
}

# 3. Install requirements
Write-Host "[INFO] Installing dependencies from req.txt into .venv..." -ForegroundColor Yellow
uv pip install -r req.txt --python .venv

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install dependencies."
    exit $LASTEXITCODE
}

# 4. Handle .env
if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[NOTICE] Created .env template. Please configure your CACTUS_API_KEY." -ForegroundColor Magenta
}

Write-Host ""
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "  [SUCCESS] Environment setup complete!" -ForegroundColor Green
Write-Host "  Activate: .venv\Scripts\Activate.ps1" -ForegroundColor Cyan
Write-Host "  Run:      uv run --python .venv python export_corridor_tiles.py" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Green
