#!/usr/bin/env bash
# ==============================================================================
# TILE_MAPPER_SEG_FG: One-Click Environment Setup (Bash / Linux / macOS)
# ==============================================================================

set -e

echo "=============================================================================="
echo "  TILE_MAPPER_SEG_FG: One-Click Environment Setup (uv)"
echo "=============================================================================="

# Check if uv is in PATH or ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv &> /dev/null; then
    echo "[INFO] uv not found. Installing uv via Astral installer..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "[OK] uv is ready: $(uv --version)"

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "[INFO] Creating virtual environment (.venv)..."
    uv venv .venv
else
    echo "[OK] Virtual environment (.venv) already exists."
fi

# Install dependencies
echo "[INFO] Installing dependencies from req.txt into .venv..."
uv pip install -r req.txt --python .venv

# Initialize .env
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "[NOTICE] Created .env from .env.example. Please configure your CACTUS_API_KEY."
fi

echo ""
echo "=============================================================================="
echo "  [SUCCESS] Environment setup complete!"
echo "  Activate: source .venv/bin/activate"
echo "  Run:      uv run --python .venv python export_corridor_tiles.py"
echo "=============================================================================="
