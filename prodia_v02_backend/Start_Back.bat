@echo off
REM ===================================================================
REM  ProdIA V02 - Arranque del backend (FastAPI + uvicorn) en :6034
REM  Uso: doble clic, o "Start_Back.bat" desde una consola.
REM ===================================================================
setlocal
cd /d "%~dp0"

echo.
echo [ProdIA V02] Backend - directorio: %CD%
echo.

REM --- uv disponible? ---
where uv >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se encontro "uv" en el PATH.
    echo         Instalalo con: winget install astral-sh.uv
    echo.
    pause
    exit /b 1
)

REM --- .env presente? el lifespan hace fail-fast sin el ---
if not exist ".env" (
    echo [ERROR] Falta el archivo .env en %CD%
    echo         Copia .env.example a .env y completa los valores.
    echo.
    pause
    exit /b 1
)

REM --- migraciones al dia: db_auth sin esquema valido = el backend no arranca ---
echo [1/2] Aplicando migraciones Alembic (db_auth)...
uv run alembic upgrade head
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo "alembic upgrade head". El backend no arrancaria:
    echo         db_auth sin esquema valido aborta el lifespan.
    echo.
    pause
    exit /b 1
)

echo.
echo [2/2] Levantando uvicorn en http://localhost:6034
echo       Docs: http://localhost:6034/docs   Health: http://localhost:6034/health
echo       Ctrl+C para detener.
echo.
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 6034

echo.
echo [ProdIA V02] Backend detenido.
pause
endlocal
