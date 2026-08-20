@echo off
setlocal enableextensions
pushd "%~dp0"
title ProdIA V02 - PRODUCCION (:6034)
color 0A

REM ==========================================================================
REM  ProdIA V02 - Arranque de PRODUCCION.
REM
REM  Diferencias con Start_Back.bat / Start_Front.bat, que son de DESARROLLO:
REM
REM   1. UN SOLO PUERTO (6034). El backend sirve el frontend compilado
REM      (SERVE_STATIC=true), asi que no hay dev server de Vite ni :6033, y
REM      CORS deja de intervenir porque todo comparte origen.
REM   2. SIN --reload. El recargador vigila el arbol de ficheros y reinicia el
REM      proceso; en produccion eso es consumo y una caida esperando ocurrir.
REM   3. Rodea el trampoline de uv. Ver el bloque de abajo: en el 139 esto NO
REM      es opcional.
REM
REM  Uso:  Start_Prod.bat
REM ==========================================================================

echo.
echo ===========================================================
echo  ProdIA V02 - PRODUCCION
echo  Raiz: %CD%
echo ===========================================================
echo.

REM ── El .env es obligatorio: sin el no hay BD, ni LDAP, ni SECRET_KEY ──
if not exist "prodia_v02_backend\.env" (
    echo [ERROR] No existe prodia_v02_backend\.env
    echo         Copia .env.example a .env y completalo.
    echo         En produccion: APP_ENV=production y SERVE_STATIC=true
    goto :fail
)

REM ── Aviso si el .env no esta puesto en modo produccion ──
findstr /b /c:"SERVE_STATIC=true" "prodia_v02_backend\.env" >nul 2>&1
if errorlevel 1 (
    echo [AVISO] SERVE_STATIC no esta en "true" en el .env.
    echo         Sin el, el backend NO sirve el frontend y la aplicacion
    echo         quedaria solo como API. Continuo igual por si es a proposito.
    echo.
)

set "PATH=%USERPROFILE%\.local\bin;%PATH%"

REM ── [1/4] Liberar el puerto ──────────────────────────────────────────────
REM  Patron heredado del sistema viejo (iniciar_backends.bat): sin esto, un
REM  proceso anterior a medio morir deja el puerto tomado y uvicorn falla con
REM  WinError 10048, que no dice nada util sobre la causa.
echo [1/4] Liberando el puerto 6034 si esta ocupado...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":6034" ^| findstr "LISTENING"') do taskkill /F /PID %%p >nul 2>&1

REM ── [2/4] Compilar el frontend ───────────────────────────────────────────
echo [2/4] Compilando el frontend (pnpm build)...
call pnpm install --frozen-lockfile
if errorlevel 1 goto :fail_pnpm
call pnpm run build
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo "pnpm build". El backend arrancaria SIN frontend.
    goto :fail
)
if not exist "prodia_v02_frontend\dist\index.html" (
    echo [ERROR] pnpm build termino pero no hay dist\index.html
    goto :fail
)
echo       OK  dist\index.html generado.

REM ── [3/4] Migraciones ────────────────────────────────────────────────────
REM  Idempotente: si ya estan aplicadas, no hace nada.
echo [3/4] Aplicando migraciones de la BD de autenticacion...
pushd "prodia_v02_backend"
call uv run alembic upgrade head
if errorlevel 1 (
    popd
    echo [ERROR] Fallo "alembic upgrade head". El backend NO arranca sin un
    echo         esquema valido de db_auth: abortaria en el lifespan.
    goto :fail
)

REM ── [4/4] Arrancar ───────────────────────────────────────────────────────
REM
REM  🔑 EL RODEO DEL TRAMPOLINE — en el 139 esto NO es opcional.
REM
REM  El .venv\Scripts\python.exe de uv es un "trampoline" (un .exe pequeno que
REM  relanza al interprete real). Una directiva de Control de aplicaciones de
REM  Windows —WDAC, Smart App Control o el EDR corporativo— lo bloquea, y el
REM  fallo es "os error 4551", que no menciona ni antivirus ni politica: parece
REM  una instalacion rota de Python.
REM
REM  El sistema viejo ya pago este diagnostico y su solucion se hereda literal:
REM  lanzar con el interprete BASE (el que declara pyvenv.cfg) exportando
REM  PYTHONPATH al site-packages del venv. Equivale a activar el entorno, pero
REM  sin ejecutar el trampoline.
REM
REM  Si no se halla el interprete base, cae a "uv run": funciona en cualquier
REM  maquina sin la restriccion, y en el 139 fallaria de forma ruidosa en vez
REM  de silenciosa.
echo [4/4] Levantando uvicorn en http://0.0.0.0:6034
echo.

set "BASEPY="
for /f "tokens=1,* delims= " %%a in ('type ".venv\pyvenv.cfg" 2^>nul ^| findstr /b /c:"home"') do set "HOMEDIR=%%b"
if defined HOMEDIR (
    set "HOMEDIR=%HOMEDIR:= %"
    for /f "tokens=* delims== " %%h in ("%HOMEDIR%") do set "HOMEDIR=%%h"
    if exist "%HOMEDIR%\python.exe" set "BASEPY=%HOMEDIR%\python.exe"
)

if defined BASEPY (
    echo       Interprete base ^(sin trampoline^): %BASEPY%
    set "PYTHONPATH=%CD%\.venv\Lib\site-packages"
    "%BASEPY%" -m uvicorn src.main:app --host 0.0.0.0 --port 6034
) else (
    echo       AVISO: no se hallo el interprete base; usando "uv run".
    echo              Si esta maquina tiene WDAC/EDR, aqui saldria "os error 4551".
    uv run uvicorn src.main:app --host 0.0.0.0 --port 6034
)

popd
echo.
echo [ProdIA V02] Backend detenido.
goto :fin

:fail_pnpm
echo.
echo [ERROR] Fallo "pnpm install --frozen-lockfile".
goto :fail

:fail
echo.
echo ===========================================================
echo  ARRANQUE ABORTADO - revisa el error de arriba.
echo ===========================================================
popd
endlocal
pause
exit /b 1

:fin
popd
endlocal
pause
