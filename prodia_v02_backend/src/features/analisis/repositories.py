"""SQL de Desempeño ECP — ámbito, KPIs mensuales, curva diaria y ritmo.

Portado de `INGESTA/Rep_Prod/backend/app/features/analisis/api.py:391-666`.
**El SQL se conserva IDÉNTICO al origen** (U3). Los comentarios que explican el
porqué de cada decisión vienen del origen y se preservan: cada uno es un bug ya
pagado.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import RowMapping, bindparam, text
from sqlalchemy.orm import Session

Fila = RowMapping

# 'activo' NO es una columna de dim_fuente: se compone desde
# core.map_campo_activo vía `catalogo_entidades` — MISMA fuente que usa el chat,
# para que el tablero y la conversación no puedan divergir.
# `activos`/`grupo1` quedaron fuera: la primera es un bucket de portafolio
# (OPERADOS/NO OPERADOS/MENORES), la segunda una taxonomía previa.
# ⚠️ 'pozo' es un ALIAS de 'fuente': el grano de pozo NO existe en esta BD.
NIVEL_A_COLUMNA = {
    "fuente": "nombre",
    "pozo": "nombre",
    "campo": "campo",
    "gerencia": "gerencia",
    "operador": "operador",
}


class AnalisisRepository:
    """Consultas de Desempeño ECP. Recibe la sesión, no la abre."""

    def __init__(self, db: Session) -> None:
        self._db = db

    @property
    def db(self) -> Session:
        """Expuesta para `catalogo_entidades`, que recibe la sesión inyectada."""
        return self._db

    # ── Resolución de ámbito ─────────────────────────────────────────────────

    def fuentes_por_columna(self, columna: str, entidad: str) -> list[int]:
        """Nivel específico → columna exacta (D-C2). `columna` sale de
        `NIVEL_A_COLUMNA`, nunca del usuario: no hay inyección posible."""
        filas = self._db.execute(
            text(
                f"SELECT fuente_id FROM core.dim_fuente WHERE UPPER(TRIM({columna}))=:e"
            ),
            {"e": entidad},
        ).all()
        return [int(fid) for (fid,) in filas]

    def fuentes_union(self, entidad: str) -> list[int]:
        """Sin nivel → OR-unión sobre 4 columnas (compat, D-C3)."""
        filas = self._db.execute(
            text("""
                SELECT fuente_id FROM core.dim_fuente
                WHERE UPPER(TRIM(nombre))=:e OR UPPER(TRIM(campo))=:e
                   OR UPPER(TRIM(gerencia))=:e OR UPPER(TRIM(operador))=:e
            """),
            {"e": entidad},
        ).all()
        return [int(fid) for (fid,) in filas]

    def vice_id_de(self, entidad: str) -> int | None:
        resultado = self._db.execute(
            text(
                "SELECT vice_id FROM core.dim_vicepresidencia "
                "WHERE UPPER(TRIM(codigo))=:e"
            ),
            {"e": entidad},
        ).scalar()
        return int(resultado) if resultado is not None else None

    def _where_ambito(
        self, ids: list[int], vice_id: int | None, alias: str = ""
    ) -> tuple[str, dict[str, Any]]:
        """Construye el WHERE del ámbito. Sin ids ni vice_id → TRUE (global)."""
        prefijo = f"{alias}." if alias else ""
        condiciones: list[str] = []
        params: dict[str, Any] = {}
        if ids:
            condiciones.append(f"{prefijo}fuente_id IN :ids")
            params["ids"] = ids
        if vice_id is not None:
            condiciones.append(f"{prefijo}vice_id = :vid")
            params["vid"] = vice_id
        where = "(" + " OR ".join(condiciones) + ")" if condiciones else "TRUE"
        return where, params

    def _preparar(self, sql: str, params: dict[str, Any]) -> Any:
        consulta = text(sql)
        if "ids" in params:
            consulta = consulta.bindparams(bindparam("ids", expanding=True))
        return consulta

    def max_fecha_diaria(self, ids: list[int], vice_id: int | None) -> Any:
        where, params = self._where_ambito(ids, vice_id)
        sql = f"SELECT MAX(fecha) FROM core.fact_produccion_dia_ecp WHERE {where}"
        return self._db.execute(self._preparar(sql, params), params).scalar()

    def max_fecha_mensual_real(self, ids: list[int], vice_id: int | None) -> Any:
        """Fallback cuando no hay grano diario: último mes con REAL mensual."""
        where, params = self._where_ambito(ids, vice_id, alias="m")
        sql = f"""
            SELECT MAX(m.fecha) FROM core.fact_produccion_mes_ecp m
            JOIN core.dim_escenario es ON es.escenario_id = m.escenario_id
            WHERE es.nombre='REAL' AND {where}"""
        return self._db.execute(self._preparar(sql, params), params).scalar()

    # ── KPIs mensuales ───────────────────────────────────────────────────────

    def kpis_mes(self, ids: list[int], vice_id: int | None, fin: str) -> Sequence[Fila]:
        """REAL vs PPTO por producto — SOLO mensual (VERIFICADO H1 del origen).

        🔑 H1: el `volumen` de cada producto vive en UN SOLO proceso
        (CRUDO→PROD_TOTAL, GAS→VENTA-GRAVABLE, BLANCOS→GAS CONVERTIDO MME); los
        demás procesos van en NULL. Por eso `SUM(m.volumen)` sobre TODOS los
        procesos NO doble-cuenta y es ROBUSTO al mapeo — no hay que hard-codear
        el proceso por producto. **NO filtrar por proceso.**
        """
        where, params = self._where_ambito(ids, vice_id, alias="m")
        params["fin"] = fin
        sql = f"""
            SELECT tp.nombre AS prod, es.nombre AS esc, SUM(m.volumen) AS vol
            FROM core.fact_produccion_mes_ecp m
            JOIN core.dim_tipo_producto tp ON tp.tipo_producto_id = m.tipo_producto_id
            JOIN core.dim_escenario es ON es.escenario_id = m.escenario_id
            WHERE m.fecha = :fin AND es.nombre IN ('REAL','PPTO') AND {where}
            GROUP BY 1, 2"""
        return self._db.execute(self._preparar(sql, params), params).mappings().all()

    def escenarios_mes(
        self, ids: list[int], vice_id: int | None, fin: str, escenarios: list[str]
    ) -> Sequence[Fila]:
        """Valores de escenarios de presupuesto (OPERATIVO/CONTABLE).

        AISLADO de `kpis_mes` a propósito (AF-4.2 del origen): meter estos
        escenarios en aquel `IN` cambiaría `sin_cierre` — un producto con fila
        OPERATIVO pero sin REAL/PPTO crearía entrada y volvería `sin_cierre`
        False cuando debía ser True, una regresión del tablero.
        """
        where, params = self._where_ambito(ids, vice_id, alias="m")
        params["fin"] = fin
        params["escs"] = escenarios
        sql = f"""
            SELECT tp.nombre AS prod, es.nombre AS esc, SUM(m.volumen) AS vol
            FROM core.fact_produccion_mes_ecp m
            JOIN core.dim_tipo_producto tp ON tp.tipo_producto_id = m.tipo_producto_id
            JOIN core.dim_escenario es ON es.escenario_id = m.escenario_id
            WHERE m.fecha = :fin AND es.nombre IN :escs AND {where}
            GROUP BY 1, 2"""
        consulta = text(sql).bindparams(bindparam("escs", expanding=True))
        if ids:
            consulta = consulta.bindparams(bindparam("ids", expanding=True))
        return self._db.execute(consulta, params).mappings().all()

    # ── Curva diaria ─────────────────────────────────────────────────────────

    def curva_diaria(
        self, ids: list[int], vice_id: int | None, ini: str, fin: str
    ) -> Sequence[Fila]:
        """Curva diaria REAL — SOLO forma/tendencia, NO alimenta los KPIs (H2).

        🔑 H2: día y mes usan MEDIDAS distintas para algunos productos
        (BLANCOS: día ≈1,9M vs mes ≈0,9M). Por eso los KPIs salen 100 % de
        `mes` y `día` se usa SOLO para la curva.
        """
        where, params = self._where_ambito(ids, vice_id, alias="d")
        params["ini"] = ini
        params["fin"] = fin
        sql = f"""
            SELECT d.fecha AS fecha, tp.nombre AS prod, SUM(d.volumen) AS vol
            FROM core.fact_produccion_dia_ecp d
            JOIN core.dim_tipo_producto tp ON tp.tipo_producto_id = d.tipo_producto_id
            WHERE d.fecha BETWEEN :ini AND :fin AND {where}
            GROUP BY 1, 2 ORDER BY 1"""
        return self._db.execute(self._preparar(sql, params), params).mappings().all()

    # ── Ritmo mensual del año ────────────────────────────────────────────────

    def real_mensual_del_anio(
        self, ids: list[int], vice_id: int | None, anio: int
    ) -> Sequence[Fila]:
        """REAL mensual de cada mes del año — mismo fact MENSUAL que la tarjeta,
        así que las cifras del gráfico y de la tarjeta reconcilian EXACTO."""
        where, params = self._where_ambito(ids, vice_id, alias="m")
        params["yy"] = anio
        sql = f"""
            SELECT EXTRACT(month FROM m.fecha)::int AS mes, tp.nombre AS prod,
                   SUM(m.volumen) AS vol
            FROM core.fact_produccion_mes_ecp m
            JOIN core.dim_tipo_producto tp ON tp.tipo_producto_id = m.tipo_producto_id
            JOIN core.dim_escenario es ON es.escenario_id = m.escenario_id
            WHERE es.nombre = 'REAL' AND EXTRACT(year FROM m.fecha) = :yy AND {where}
            GROUP BY 1, 2 ORDER BY 1"""
        return self._db.execute(self._preparar(sql, params), params).mappings().all()

    # ── Campos sin meta (D-A4) ───────────────────────────────────────────────

    def campos_sin_meta(self, ids: list[int], fin: str) -> Sequence[Fila]:
        """Campos que PRODUCEN pero no tienen PPTO en el mes, por producto.

        D-A4: el PPTO se carga POR CAMPO y hay campos que producen sin meta
        asignada (15 de 128 en crudo/may-2026; en el activo APIAY son 3 de 4).
        Sumar su REAL contra un PPTO que no los cubre infla el cumplimiento, así
        que se DECLARAN en vez de inventarles meta. Se descartó
        `PPTO = 1.25*REAL`: daba 80 % constante y hundía APIAY de 108,8 % a
        63,0 % con 385.409 bl de presupuesto fabricado.
        """
        consulta = text("""
            SELECT COALESCE(NULLIF(TRIM(f.campo),''), TRIM(f.nombre)) AS campo,
                   tp.nombre AS producto,
                   SUM(CASE WHEN es.nombre='REAL' THEN m.volumen ELSE 0 END) AS real,
                   SUM(CASE WHEN es.nombre='PPTO' THEN m.volumen ELSE 0 END) AS ppto
            FROM core.fact_produccion_mes_ecp m
            JOIN core.dim_fuente f         ON f.fuente_id        = m.fuente_id
            JOIN core.dim_tipo_producto tp ON tp.tipo_producto_id = m.tipo_producto_id
            JOIN core.dim_escenario es     ON es.escenario_id     = m.escenario_id
            WHERE m.fecha = :fin AND es.nombre IN ('REAL','PPTO') AND m.fuente_id IN :ids
            GROUP BY 1, 2
            HAVING SUM(CASE WHEN es.nombre='REAL' THEN m.volumen ELSE 0 END) > 0
               AND SUM(CASE WHEN es.nombre='PPTO' THEN m.volumen ELSE 0 END) = 0
            ORDER BY 3 DESC
        """).bindparams(bindparam("ids", expanding=True))
        return self._db.execute(consulta, {"fin": fin, "ids": ids}).mappings().all()
