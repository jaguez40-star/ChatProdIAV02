"""Prueba de humo del ETL COMPLETO contra el PostgreSQL real.

Ingiere un `.xlsm` de verdad —transacción, bloqueo, extractores, loaders y todo— y luego
comprueba contra la base lo que quedó escrito. Es la verificación que ningún test puede
dar: los tests usan un doble y nunca tocan PostgreSQL.

Comprueba además la **idempotencia**, que es la propiedad más fácil de romper sin darse
cuenta: ingiere el mismo archivo dos veces y verifica que la segunda pasada deja
exactamente los mismos conteos que la primera. Si un `DELETE` perdiera su `WHERE` o un
`UPSERT` su `ON CONFLICT`, aquí se vería.

⚠️ ESCRIBE en la base a la que apunte `PROD_DATABASE_URL`. El script se niega a correr si
no es local.

Uso:
    cd prodia_v02_backend
    uv run python scripts/humo_ingesta.py "<ruta al .xlsm>"
    uv run python scripts/humo_ingesta.py            # usa el NEW de Doc_Desing
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import text

from src.core.config import get_settings
from src.features.ingesta.repositories import IngestaRepository
from src.features.ingesta.schemas import EventoIngesta
from src.features.ingesta.services import IngestaService
from src.shared.db_prod import get_prod_session_factory, get_prod_tx

MUESTRAS = Path(
    r"C:\APLICACIONES\ProdIA\12112025_prodIA\12112025_prodIA\INGESTA\Rep_Prod\Doc_Desing"
)

# Anclas de paridad documentadas en el CLAUDE.md §6.
ANCLAS = {"DATOS_MES": 7776, "TD_datos_dia": 5209}

TABLAS_A_CONTAR = [
    "core.config_reporte",
    "core.fact_tabla_hoja",
    "core.fact_produccion_dia_ecp",
    "core.fact_produccion_mes_ecp",
    "core.fact_programa_ecp",
    "core.fact_comentarios_produccion",
    "core.fact_produccion_diaria",
    "bronze.bdp_datos_mes",
    "bronze.hoja_landing",
]


def _resolver_archivo() -> Path | None:
    if len(sys.argv) > 1:
        ruta = Path(sys.argv[1])
        return ruta if ruta.exists() else None
    candidatos = sorted(MUESTRAS.glob("*New*.xlsm"))
    return candidatos[0] if candidatos else None


def _contar_todo(reporte_id: int | None = None) -> dict[str, int]:
    """Conteo de cada tabla; si se da `reporte_id`, acotado a ese reporte."""
    sesion = get_prod_session_factory()()
    conteos: dict[str, int] = {}
    try:
        for tabla in TABLAS_A_CONTAR:
            filtro = ""
            parametros: dict[str, Any] = {}
            if reporte_id is not None and tabla != "core.config_reporte":
                filtro = " WHERE reporte_id = :r"
                parametros = {"r": reporte_id}
            total = sesion.execute(
                text(f"SELECT count(*) FROM {tabla}{filtro}"), parametros
            ).scalar()
            conteos[tabla] = int(total or 0)
    finally:
        sesion.close()
    return conteos


def _filas_por_hoja(reporte_id: int) -> dict[str, int]:
    sesion = get_prod_session_factory()()
    try:
        filas = (
            sesion.execute(
                text(
                    "SELECT hoja, count(*) AS n FROM core.fact_tabla_hoja "
                    "WHERE reporte_id = :r GROUP BY hoja ORDER BY hoja"
                ),
                {"r": reporte_id},
            )
            .mappings()
            .all()
        )
    finally:
        sesion.close()
    return {fila["hoja"]: fila["n"] for fila in filas}


def _ingerir(ruta: Path, mostrar_progreso: bool) -> Any:
    eventos: list[EventoIngesta] = []

    def observar(evento: EventoIngesta) -> None:
        eventos.append(evento)
        if not mostrar_progreso or evento.tipo != "hoja":
            return
        if evento.estado in ("procesada", "vacia", "error"):
            marca = {"procesada": "ok", "vacia": "--", "error": "!!"}[evento.estado]
            filas = f"{evento.filas:>9,}" if evento.filas is not None else " " * 9
            print(
                f"    [{marca}] {evento.hoja[:36]:<36}{filas}  {evento.destino or ''}"
            )

    resultado = None
    for sesion in get_prod_tx():
        servicio = IngestaService(IngestaRepository(sesion), observador=observar)
        resultado = servicio.ingerir(ruta)
    return resultado, eventos


def main() -> int:
    url = get_settings().prod_database_url
    if "localhost" not in url and "127.0.0.1" not in url:
        print("ABORTADO: PROD_DATABASE_URL no apunta a una base local.")
        print(
            "Este script ESCRIBE. Nunca debe correr contra el servidor de producción."
        )
        return 1

    archivo = _resolver_archivo()
    if archivo is None:
        print(f"No se encontró ningún .xlsm. Pasa la ruta, o deja uno en {MUESTRAS}")
        return 1

    mb = archivo.stat().st_size // 1048576
    print("=" * 78)
    print(f"INGESTA REAL — {archivo.name} ({mb} MB)")
    print("=" * 78)

    antes = _contar_todo()
    print("\n1) PRIMERA INGESTA")
    inicio = time.perf_counter()
    resultado, eventos = _ingerir(archivo, mostrar_progreso=True)
    duracion = time.perf_counter() - inicio

    if resultado is None:
        print("   La ingesta no devolvió resultado.")
        return 1

    print(f"\n   Confirmada en {duracion:.1f} s")
    print(f"   reporte_id={resultado.reporte_id}  tipo={resultado.tipo_archivo}")
    print(f"   filas escritas: {resultado.total_filas:,}")
    if resultado.tablas_vacias:
        print(f"   tablas sin filas: {len(resultado.tablas_vacias)}")

    despues = _contar_todo()
    print("\n2) LO QUE QUEDÓ EN LA BASE")
    for tabla in TABLAS_A_CONTAR:
        delta = despues[tabla] - antes[tabla]
        signo = f"+{delta:,}" if delta > 0 else f"{delta:,}"
        print(f"   {tabla:<38}{despues[tabla]:>12,}  ({signo})")

    print("\n3) ANCLAS DE PARIDAD (CLAUDE.md §6)")
    por_hoja = _filas_por_hoja(resultado.reporte_id)
    fallos: list[str] = []
    for hoja, esperado in ANCLAS.items():
        obtenido = por_hoja.get(hoja, 0)
        estado = "OK " if obtenido == esperado else "MAL"
        print(
            f"   [{estado}] {hoja:<20} esperado {esperado:>8,}   obtenido {obtenido:>8,}"
        )
        if obtenido != esperado:
            fallos.append(f"{hoja}: esperado {esperado}, obtenido {obtenido}")

    print("\n4) IDEMPOTENCIA — se ingiere el MISMO archivo otra vez")
    inicio = time.perf_counter()
    segundo, _ = _ingerir(archivo, mostrar_progreso=False)
    print(f"   Confirmada en {time.perf_counter() - inicio:.1f} s")

    final = _contar_todo()
    for tabla in TABLAS_A_CONTAR:
        if final[tabla] != despues[tabla]:
            fallos.append(
                f"{tabla}: la reingesta cambió el conteo "
                f"({despues[tabla]:,} → {final[tabla]:,})"
            )
    if segundo is not None and segundo.reporte_id != resultado.reporte_id:
        fallos.append("la reingesta creó un reporte nuevo en vez de reemplazar")

    print("\n" + "=" * 78)
    if fallos:
        print(f"RESULTADO: {len(fallos)} PROBLEMA(S)")
        for fallo in fallos:
            print(f"  - {fallo}")
        return 1
    print("RESULTADO: ingesta correcta, anclas exactas e idempotencia verificada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
