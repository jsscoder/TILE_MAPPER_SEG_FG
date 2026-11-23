@echo off
setlocal enabledelayedexpansion

echo ==============================================================================
echo   TILE_MAPPER_SEG_FG: One-Click Environment Setup (uv)
echo ==============================================================================
echo.

:: Ensure ~/.local/bin is in PATH for this session if uv was already installed there
if exist "%USERPROFILE%\.local\bin\uv.exe" (
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

:: 1. Check if uv is installed
where uv >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] uv not found. Installing uv via Astral installer...
    powershell -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    where uv >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install uv automatically.
        echo Please install uv manually: https://docs.astral.sh/uv/getting-started/installation/
        pause
        exit /b 1
    )
)

echo [OK] uv is ready:
uv --version

:: 2. Create virtual environment (.venv)
if not exist ".venv" (
    echo.
    echo [INFO] Creating Python virtual environment with uv (.venv)...
    uv venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [OK] Virtual environment (.venv) already exists.
)

:: 3. Install project dependencies
echo.
echo [INFO] Installing dependencies from req.txt into .venv...
uv pip install -r req.txt --python .venv

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

:: 4. Initialize .env if missing
if not exist ".env" (
    if exist ".env.example" (
        echo.
        echo [INFO] Creating .env from .env.example...
        copy .env.example .env >nul
        echo [NOTICE] Created .env template. Please edit it to add your CACTUS_API_KEY.
    )
)

echo.
echo ==============================================================================
echo   [SUCCESS] Environment setup complete!
echo ==============================================================================
echo   Activate environment:
echo     .venv\Scripts\activate
echo.
echo   Or run directly with uv:
echo     uv run --python .venv python export_corridor_tiles.py
echo     uv run --python .venv python bifurcate_tiles_mirage.py
echo ==============================================================================
echo.
pause
