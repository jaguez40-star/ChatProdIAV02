"""Acceso a datos de la feature `tablas` — PostgreSQL `daily_report_prod`, esquema `core.*`.

Portado de `INGESTA/Rep_Prod/backend/app/features/{tablas,reportes,kpis_prod}/api.py`.

**El SQL se conserva IDÉNTICO al origen** (U3: se reescribe la capa de acceso, no el
esquema ni las consultas). Están probadas contra el corpus real — `core.fact_tabla_hoja`
supera los 50M de filas y cada `LIMIT`/índice de estas consultas es deliberado; los
comentarios que explican el porqué vienen del origen y se preservan.

Lo único que cambia respecto al origen: allí cada endpoint abría su propia conexión con
`get_engine().connect()`; aquí la sesión llega inyectada por `Depends(get_prod_db)` y el
repositorio nunca la crea ni la cierra (L4 — engines separados, el ciclo de vida lo maneja
la dependencia de FastAPI).

Cero lógica de negocio: el pivote a formato ancho vive en `services.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

# El visor solo muestra las primeras N filas (la BD guarda todo; ver total_filas).
CAP_FILAS = 100
# Tope de filas que se cargan para armar la tabla ancha (protege hojas RAW enormes).
FETCH_MAX = 50_000


class TablasRepository:
    """Consultas contra `core.*` de `daily_report_prod`. Recibe la sesión, no la abre."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Tablas lógicas de una hoja ───────────────────────────────────────────

    def contar_comentarios(self, reporte_id: int) -> int:
        """COMENTARIOS no vive en `fact_tabla_hoja` (es texto) — fact dedicado."""
        resultado = self._db.execute(
            text(
                "SELECT count(*) FROM core.fact_comentarios_produccion WHERE reporte_id=:r"
            ),
            {"r": reporte_id},
        ).scalar()
        return int(resultado or 0)

    def listar_tablas_de_hoja(self, reporte_id: int, hoja: str) -> Sequence[RowMapping]:
        return (
            self._db.execute(
                text("""
            SELECT tabla_idx, tabla_label, count(*) AS filas
            FROM core.fact_tabla_hoja WHERE reporte_id=:r AND hoja=:h
            GROUP BY tabla_idx, tabla_label ORDER BY tabla_idx"""),
                {"r": reporte_id, "h": hoja},
            )
            .mappings()
            .all()
        )

    # ── Contenido de una tabla ───────────────────────────────────────────────

    def leer_comentarios(self, reporte_id: int) -> Sequence[RowMapping]:
        return (
            self._db.execute(
                text("""
                SELECT tp.nombre AS producto, x.activos, x.area,
                       x.comentario, x.comentario_programa, x.comentario_extra
                FROM core.fact_comentarios_produccion x
                LEFT JOIN core.dim_tipo_producto tp ON tp.tipo_producto_id = x.tipo_producto_id
                WHERE x.reporte_id=:r ORDER BY x.id"""),
                {"r": reporte_id},
            )
            .mappings()
            .all()
        )

    def leer_filas_tabla(
        self, reporte_id: int, hoja: str, tabla_idx: int
    ) -> Sequence[RowMapping]:
        """Carga ACOTADA (LIMIT FETCH_MAX): protege el visor de hojas RAW enormes
        (p.ej. BDP_datos_mes, ~314K). Como cada extractor emite las filas de un mismo
        combo de dims de forma contigua (por id), el prefijo cargado contiene los primeros
        combos COMPLETOS → la tabla ancha se arma bien y luego se recorta a CAP_FILAS.
        Las hojas pequeñas (<FETCH_MAX) se cargan enteras (comportamiento igual).

        Se piden FETCH_MAX+1 filas a propósito: si vuelven más de FETCH_MAX, la hoja está
        truncada (lo detecta el service).
        """
        return (
            self._db.execute(
                text("""
            SELECT dims, fecha, valor FROM core.fact_tabla_hoja
            WHERE reporte_id=:r AND hoja=:h AND tabla_idx=:i ORDER BY id LIMIT :fm"""),
                {"r": reporte_id, "h": hoja, "i": tabla_idx, "fm": FETCH_MAX + 1},
            )
            .mappings()
            .all()
        )

    def fechas_distintas(self, reporte_id: int, hoja: str, tabla_idx: int) -> list[str]:
        """Solo para hojas truncadas: columnas = TODAS las fechas (header estable, no
        solo las del prefijo cargado)."""
        filas = self._db.execute(
            text(
                "SELECT DISTINCT fecha FROM core.fact_tabla_hoja "
                "WHERE reporte_id=:r AND hoja=:h AND tabla_idx=:i AND fecha IS NOT NULL "
                "ORDER BY fecha"
            ),
            {"r": reporte_id, "h": hoja, "i": tabla_idx},
        ).all()
        return [d.isoformat() for (d,) in filas]

    def contar_filas_tabla(self, reporte_id: int, hoja: str, tabla_idx: int) -> int:
        """Total del visor cuando la hoja está truncada: en las hojas RAW truncadas
        cada combo = 1 registro → count(*) = nº de combos mostrable."""
        resultado = self._db.execute(
            text(
                "SELECT count(*) FROM core.fact_tabla_hoja "
                "WHERE reporte_id=:r AND hoja=:h AND tabla_idx=:i AND fecha IS NOT NULL"
            ),
            {"r": reporte_id, "h": hoja, "i": tabla_idx},
        ).scalar()
        return int(resultado or 0)

    # ── Árbol de reportes ────────────────────────────────────────────────────

    def listar_config_reportes(self) -> Sequence[RowMapping]:
        """NO incluye el desglose de hojas/tablas — eso se carga bajo demanda vía
        `hojas_de_reporte`. Con el corpus real (`core.fact_tabla_hoja` > 50M filas)
        agregar sobre TODOS los reportes a la vez en una sola consulta tardaba minutos;
        esta consulta solo toca `config_reporte` (una fila por reporte) y es instantánea
        sin importar cuántos reportes existan.
        """
        return self._db.execute(text("""
        SELECT reporte_id, fecha_reporte, tipo_archivo, archivo_nombre
        FROM core.config_reporte
        ORDER BY fecha_reporte DESC
    """)).mappings().all()

    def hojas_de_reporte(self, reporte_id: int) -> Sequence[RowMapping]:
        """Desglose de hojas/tablas de UN reporte — carga perezosa al expandir un día.
        Filtrado por `reporte_id`: usa el índice (reporte_id,hoja,tabla_idx) de
        `fact_tabla_hoja` sobre las filas de un solo reporte en vez de agregar la tabla
        completa."""
        return (
            self._db.execute(
                text("""
        SELECT hoja, tabla_idx, tabla_label, COUNT(*) AS filas
        FROM core.fact_tabla_hoja
        WHERE reporte_id = :r
        GROUP BY hoja, tabla_idx, tabla_label
        UNION ALL
        SELECT 'COMENTARIOS' AS hoja, 1 AS tabla_idx, 'COMENTARIOS' AS tabla_label, COUNT(*) AS filas
        FROM core.fact_comentarios_produccion
        WHERE reporte_id = :r
        HAVING COUNT(*) > 0
        ORDER BY hoja, tabla_idx
    """),
                {"r": reporte_id},
            )
            .mappings()
            .all()
        )

    # ── Reportes y cobertura ─────────────────────────────────────────────────

    def listar_reportes(self) -> Sequence[RowMapping]:
        return (
            self._db.execute(
                text(
                    "SELECT reporte_id, fecha_reporte, tipo_archivo, tiene_raw, nivel_detalle "
                    "FROM core.config_reporte ORDER BY fecha_reporte"
                )
            )
            .mappings()
            .all()
        )

    def cobertura(self) -> Sequence[RowMapping]:
        return self._db.execute(text("""
            SELECT r.reporte_id, r.tipo_archivo,
              (SELECT count(*) FROM core.fact_produccion_mes_ecp f WHERE f.reporte_id=r.reporte_id) AS ecp_mes,
              (SELECT count(*) FROM core.fact_produccion_dia_ecp f WHERE f.reporte_id=r.reporte_id) AS ecp_dia,
              (SELECT count(*) FROM core.fact_produccion_diaria f WHERE f.reporte_id=r.reporte_id) AS filiales
            FROM core.config_reporte r ORDER BY r.reporte_id""")).mappings().all()

    # ── KPIs ─────────────────────────────────────────────────────────────────

    def produccion_dia(self, fecha: str) -> Sequence[RowMapping]:
        return (
            self._db.execute(
                text("""
            SELECT tp.nombre AS tipo_producto, SUM(e.vol_estimado) AS vol_estimado
            FROM core.fact_produccion_dia_ecp e
            JOIN core.dim_tipo_producto tp ON tp.tipo_producto_id = e.tipo_producto_id
            WHERE e.fecha = :f AND e.grupo_prod = 'ECOPETROL'
            GROUP BY tp.nombre ORDER BY tp.nombre"""),
                {"f": fecha},
            )
            .mappings()
            .all()
        )
