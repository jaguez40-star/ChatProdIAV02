@echo off
setlocal enableextensions
pushd "%~dp0"
title Desplegar ProdIA V02 (139)
color 0E

REM ==========================================================================
REM  Despliegue de una version nueva de ProdIA V02.
REM
REM  Hereda el patron del sistema viejo (desplegar_version.bat), que es el que
REM  el 139 ya usa: git pull -> dependencias -> migraciones -> build -> arranque.
REM  No hay zip ni copia manual.
REM
REM  Lo que NO hace:
REM   - No toca el .env, que no se versiona y lleva las credenciales del 139.
REM   - No migra datos: daily_report_prod es el MISMO Postgres del sistema
REM     viejo (decision U3). No hay ETL de corte.
REM   - No retira nada del sistema viejo. Eso es el Bloque 5 de F6, manual y
REM     verificado paso a paso.
REM
REM  Uso:  desplegar_v02.bat
REM ==========================================================================

echo.
echo ===========================================================
echo  DESPLIEGUE - ProdIA V02
echo  Raiz: %CD%
echo ===========================================================
echo.
echo  Este script:
echo    1. Baja el codigo nuevo desde GitHub (git pull)
echo    2. Sincroniza las dependencias (uv sync + pnpm install)
echo    3. Aplica las migraciones de db_auth (idempotentes)
echo    4. Compila el frontend (pnpm build)
echo    5. Arranca el servicio en :6034
echo.
choice /c SN /m "Confirmas el despliegue (S/N)"
if errorlevel 2 (
    echo Cancelado.
    goto :fin
)

set "PATH=%USERPROFILE%\.local\bin;%PATH%"

REM ── [1/4] Codigo nuevo ───────────────────────────────────────────────────
echo.
echo [1/4] git pull...
git pull
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo el git pull. Revisa si hay cambios locales sin commitear
    echo         en el 139 ^(por ejemplo el .env, que NO se versiona y debe
    echo         conservarse^). Corrige y reintenta.
    goto :fail
)
echo       Codigo actualizado.

REM ── [2/4] Dependencias ───────────────────────────────────────────────────
REM  Un despliegue que no sincroniza dependencias funciona hasta el dia en que
REM  alguien anade una libreria, y entonces falla con un ImportError en
REM  arranque que parece un bug del codigo.
echo.
echo [2/4] Sincronizando dependencias...
pushd "prodia_v02_backend"
call uv sync
if errorlevel 1 (
    popd
    echo [ERROR] Fallo "uv sync".
    goto :fail
)
popd
call pnpm install --frozen-lockfile
if errorlevel 1 (
    echo [ERROR] Fallo "pnpm install --frozen-lockfile".
    echo         Si el lockfile cambio, commitealo antes de desplegar.
    goto :fail
)
echo       Dependencias al dia.

REM ── [3/4] Migraciones ────────────────────────────────────────────────────
echo.
echo [3/4] Aplicando migraciones de db_auth...
pushd "prodia_v02_backend"
call uv run alembic upgrade head
if errorlevel 1 (
    popd
    echo [ERROR] Fallo "alembic upgrade head".
    goto :fail
)
call uv run alembic current
popd
echo       Migraciones aplicadas.

REM ── [4/4] Arranque ───────────────────────────────────────────────────────
REM  Start_Prod.bat compila el frontend, libera el puerto y levanta uvicorn
REM  con el rodeo del trampoline (WDAC / "os error 4551").
echo.
echo [4/4] Arrancando el servicio...
echo.
echo ===========================================================
echo  DESPLIEGUE COMPLETO - arrancando
echo    ProdIA V02  -^> http://0.0.0.0:6034
echo    Health      -^> http://localhost:6034/api/v1/health
echo ===========================================================
echo.
echo  El sistema viejo sigue intacto en :8020 y :8088.
echo  Verifica la paridad antes de retirar nada:
echo     cd prodia_v02_backend
echo     uv run python scripts/humo_paridad.py
echo.

call "%~dp0Start_Prod.bat"
goto :fin

:fail
echo.
echo ===========================================================
echo  DESPLIEGUE ABORTADO - revisa el error de arriba.
echo  El servicio anterior sigue como estaba: este script no
echo  detiene nada hasta el paso 4.
echo ===========================================================
popd
endlocal
pause
exit /b 1

:fin
popd
endlocal
