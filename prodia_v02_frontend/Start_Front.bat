@echo off
REM ===================================================================
REM  ProdIA V02 - Arranque del frontend (Vite + React 19) en :6033
REM  Proxy /api -> backend :6034 (ver vite.config.ts)
REM  Uso: doble clic, o "Start_Front.bat" desde una consola.
REM ===================================================================
setlocal
cd /d "%~dp0"

echo.
echo [ProdIA V02] Frontend - directorio: %CD%
echo.

REM --- pnpm disponible? ---
where pnpm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se encontro "pnpm" en el PATH.
    echo         Instalalo con: npm install -g pnpm
    echo.
    pause
    exit /b 1
)

REM --- dependencias instaladas? ---
if not exist "node_modules" (
    echo [1/2] node_modules ausente - ejecutando "pnpm install" desde la raiz...
    pushd ..
    pnpm install
    set INSTALL_ERR=%errorlevel%
    popd
    if not "%INSTALL_ERR%"=="0" (
        echo.
        echo [ERROR] Fallo "pnpm install".
        echo.
        pause
        exit /b 1
    )
) else (
    echo [1/2] Dependencias ya instaladas.
)

echo.
echo [2/2] Levantando Vite en http://localhost:6033
echo       El backend debe estar corriendo en :6034 (Start_Back.bat).
echo       Ctrl+C para detener.
echo.
pnpm run dev

echo.
echo [ProdIA V02] Frontend detenido.
pause
endlocal
