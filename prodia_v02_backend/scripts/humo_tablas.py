"""Prueba de humo de la feature `tablas` contra el PostgreSQL REAL (139).

Para qué sirve: los tests automáticos usan un doble y NUNCA tocan Postgres, así que no
pueden detectar los fallos que solo aparecen con datos de verdad — como los dos que ya
costaron un fix (`dims` con números en vez de texto, y el 503 que no cubría el fallo de
la dependencia). Este script recorre TODAS las hojas y tablas de un reporte real y
reporta cuáles se pintan bien y cuáles revientan.

Uso (en la máquina con VPN):

    cd prodia_v02_backend
    uv run python scripts/humo_tablas.py            # usa el reporte más reciente
    uv run python scripts/humo_tablas.py 1042       # un reporte concreto

No modifica nada: solo lee. Sale con código 1 si encontró algún fallo, para poder usarlo
como verificación automatizable.
"""

from __future__ import annotations

import sys
import time
import traceback
from typing import Any

from src.features.tablas.repositories import TablasRepository
from src.features.tablas.services import TablasService
from src.shared.db_prod import check_prod_connection, get_prod_session_factory

LIMITE_SEGUNDOS_LENTO = 3.0


def _encabezado(texto: str) -> None:
    print()
    print("=" * 78)
    print(texto)
    print("=" * 78)


def _cronometrar(funcion: Any) -> tuple[Any, float, Exception | None]:
    inicio = time.perf_counter()
    try:
        return funcion(), time.perf_counter() - inicio, None
    except Exception as exc:  # noqa: BLE001 — el objetivo es reportar, no propagar
        return None, time.perf_counter() - inicio, exc


def main() -> int:
    _encabezado("1. Conexión a db_prod (servidor 139)")
    if not check_prod_connection():
        print("  FALLO: no hay conexión. ¿Está la VPN activa?")
        print("  Sin conexión no hay nada que probar.")
        return 1
    print("  OK — PostgreSQL responde.")

    sesion = get_prod_session_factory()()
    service = TablasService(TablasRepository(sesion))
    fallos: list[str] = []
    lentas: list[str] = []

    # ── Árbol ────────────────────────────────────────────────────────────────
    _encabezado("2. Árbol de reportes")
    arbol, segundos, error = _cronometrar(service.arbol_reportes)
    if error is not None:
        print(f"  FALLO en {segundos:.2f}s: {type(error).__name__}: {error}")
        traceback.print_exc()
        return 1
    total_dias = sum(len(m.dias) for a in arbol for m in a.meses)
    print(f"  OK en {segundos:.2f}s — {len(arbol)} años, {total_dias} reportes.")
    if segundos > LIMITE_SEGUNDOS_LENTO:
        lentas.append(f"arbol ({segundos:.2f}s)")
    if not arbol:
        print("  AVISO: no hay reportes en core.config_reporte. Nada más que probar.")
        return 1
    print(f"  Años encontrados: {[a.anio for a in arbol]}")

    # ── Reporte a inspeccionar ───────────────────────────────────────────────
    if len(sys.argv) > 1:
        reporte_id = int(sys.argv[1])
    else:
        reporte_id = arbol[0].meses[0].dias[0].reporte_id
    print(f"  Reporte elegido para el barrido: {reporte_id}")

    # ── Hojas ────────────────────────────────────────────────────────────────
    _encabezado(f"3. Hojas del reporte {reporte_id}")
    hojas_out, segundos, error = _cronometrar(
        lambda: service.hojas_de_reporte(reporte_id)
    )
    if error is not None or hojas_out is None:
        print(f"  FALLO en {segundos:.2f}s: {type(error).__name__}: {error}")
        return 1
    print(f"  OK en {segundos:.2f}s — {len(hojas_out.hojas)} hojas.")
    if segundos > LIMITE_SEGUNDOS_LENTO:
        lentas.append(f"hojas ({segundos:.2f}s)")

    # ── Barrido de TODAS las tablas ──────────────────────────────────────────
    _encabezado("4. Contenido de cada tabla (aquí es donde aparecen los bugs)")
    print(f"  {'HOJA':<28} {'IDX':>4} {'MODO':<8} {'FILAS':>6} {'TOTAL':>9} {'SEG':>6}")
    print(f"  {'-' * 28} {'-' * 4} {'-' * 8} {'-' * 6} {'-' * 9} {'-' * 6}")
    modos_vistos: dict[str, int] = {}

    for hoja in hojas_out.hojas:
        for tabla in hoja.tablas:
            datos, segundos, error = _cronometrar(
                lambda h=hoja.hoja, i=tabla.tabla_idx: service.datos_tabla(  # type: ignore[misc]
                    reporte_id, h, i
                )
            )
            etiqueta = f"{hoja.hoja}[{tabla.tabla_idx}]"
            if error is not None or datos is None:
                print(
                    f"  {hoja.hoja[:28]:<28} {tabla.tabla_idx:>4} "
                    f"*** {type(error).__name__} ***"
                )
                print(f"      -> {str(error)[:300]}")
                fallos.append(f"{etiqueta}: {type(error).__name__}: {str(error)[:160]}")
                continue

            modos_vistos[datos.modo] = modos_vistos.get(datos.modo, 0) + 1
            marca = " LENTA" if segundos > LIMITE_SEGUNDOS_LENTO else ""
            if segundos > LIMITE_SEGUNDOS_LENTO:
                lentas.append(f"{etiqueta} ({segundos:.2f}s)")
            print(
                f"  {hoja.hoja[:28]:<28} {tabla.tabla_idx:>4} {datos.modo:<8} "
                f"{len(datos.filas):>6} {datos.total_filas:>9} {segundos:>6.2f}{marca}"
            )

            # Comprobaciones de coherencia que un ojo humano no haría en 40 tablas.
            if datos.filas and len(datos.filas[0].valores) != len(datos.meses):
                fallos.append(
                    f"{etiqueta}: DESALINEADA — {len(datos.filas[0].valores)} valores "
                    f"para {len(datos.meses)} columnas"
                )
            if len(datos.filas) > 100:
                fallos.append(
                    f"{etiqueta}: devolvió {len(datos.filas)} filas (tope: 100)"
                )
            if datos.total_filas < len(datos.filas):
                fallos.append(
                    f"{etiqueta}: total_filas ({datos.total_filas}) < filas devueltas "
                    f"({len(datos.filas)})"
                )

    print()
    print(f"  Modos encontrados: {modos_vistos or 'ninguno'}")
    for modo in ("fechas", "matriz", "texto"):
        if modo not in modos_vistos:
            print(
                f"  AVISO: no se probó ninguna tabla en modo '{modo}' en este reporte."
            )

    # ── Reportes, cobertura y KPI ────────────────────────────────────────────
    _encabezado("5. Reportes, cobertura y KPI de producción")
    for nombre, funcion in (
        ("listar_reportes", service.listar_reportes),
        ("cobertura", service.cobertura),
    ):
        resultado, segundos, error = _cronometrar(funcion)
        if error is not None:
            print(f"  {nombre}: FALLO {type(error).__name__}: {str(error)[:200]}")
            fallos.append(f"{nombre}: {type(error).__name__}")
        else:
            print(f"  {nombre}: OK en {segundos:.2f}s — {len(resultado or [])} filas.")
            if segundos > LIMITE_SEGUNDOS_LENTO:
                lentas.append(f"{nombre} ({segundos:.2f}s)")

    fecha = arbol[0].meses[0].dias[0]
    fecha_iso = f"{arbol[0].anio:04d}-{arbol[0].meses[0].mes:02d}-{fecha.dia:02d}"
    kpis, segundos, error = _cronometrar(lambda: service.produccion_dia(fecha_iso))
    if error is not None:
        print(f"  produccion_dia({fecha_iso}): FALLO {type(error).__name__}: {error}")
        fallos.append(f"produccion_dia: {type(error).__name__}")
    else:
        print(f"  produccion_dia({fecha_iso}): OK en {segundos:.2f}s")
        for kpi in kpis or []:
            print(f"      {kpi.tipo_producto:<20} {kpi.vol_estimado}")

    # ── Resumen ──────────────────────────────────────────────────────────────
    _encabezado("RESUMEN")
    if lentas:
        print(f"  Consultas lentas (>{LIMITE_SEGUNDOS_LENTO}s): {len(lentas)}")
        for aviso in lentas:
            print(f"    - {aviso}")
    if fallos:
        print(f"  FALLOS: {len(fallos)}")
        for fallo in fallos:
            print(f"    - {fallo}")
        print()
        print("  Copia estos fallos y pásalos para corregirlos.")
        return 1

    print("  Sin fallos. Todas las tablas del reporte se sirvieron correctamente.")
    print(
        "  NOTA: esto verifica que no revientan y que son coherentes; que los NÚMEROS"
    )
    print("  sean los correctos hay que compararlo contra el sistema viejo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
