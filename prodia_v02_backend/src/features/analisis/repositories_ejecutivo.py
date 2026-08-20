"""SQL del bloque Ejecutivo — gap por campo, serie de crudo, ritmo y comentarios.

Portado de `INGESTA/Rep_Prod/backend/app/features/analisis/api.py:772-1860`.
**El SQL se conserva IDÉNTICO al origen** (U3).

Va en su propio módulo (split por sufijo, CLAUDE.md §6) para no engordar
`repositories.py`, que sirve al bloque de Desempeño. Ambos comparten la
construcción del ámbito heredando de `AnalisisRepository`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import bindparam, text

from src.features.analisis.repositories import AnalisisRepository, Fila

# 🔑 2026-07-23: en `fact_comentarios_produccion` el área trae a veces el
# producto como sufijo —`CUPIAGUA (CRUDO)`, `CUSIANA (BLANCOS)`— porque el
# reporte separa el comentario por producto. Son 144 de 648 comentarios de
# mayo-2026. Con el match EXACTO contra `CUPIAGUA` ninguno calzaba: el panel
# decía "sin evento asociado en comentarios" mientras el reporte traía 18
# comentarios de ese campo. SPLIT_PART deja la base del nombre y es inocuo si
# no hay paréntesis.
_AREA_BASE = "UPPER(TRIM(SPLIT_PART(fc.area, '(', 1)))"
_ACTIVOS_BASE = "UPPER(TRIM(SPLIT_PART(fc.activos, '(', 1)))"


class EjecutivoRepository(AnalisisRepository):
    """Consultas del Análisis Ejecutivo. Recibe la sesión, no la abre."""

    def gap_por_campo(
        self, ids: list[int], vice_id: int | None, fin: str, producto: str
    ) -> Sequence[Fila]:
        """REAL y PPTO por CAMPO para un producto — base de la descomposición."""
        where, params = self._where_ambito(ids, vice_id, alias="m")
        params["fin"] = fin
        params["prod"] = producto
        sql = (
            "SELECT COALESCE(NULLIF(TRIM(f.campo),''), f.nombre) AS campo, "
            "SUM(CASE WHEN es.nombre='REAL' THEN m.volumen ELSE 0 END) AS vreal, "
            "SUM(CASE WHEN es.nombre='PPTO' THEN m.volumen ELSE 0 END) AS vppto "
            "FROM core.fact_produccion_mes_ecp m "
            "JOIN core.dim_tipo_producto tp ON tp.tipo_producto_id = m.tipo_producto_id "
            "JOIN core.dim_escenario es ON es.escenario_id = m.escenario_id "
            "JOIN core.dim_fuente f ON f.fuente_id = m.fuente_id "
            "WHERE m.fecha = :fin AND es.nombre IN ('REAL','PPTO') "
            f"AND tp.nombre = :prod AND {where} "
            "GROUP BY 1"
        )
        return self._db.execute(self._preparar(sql, params), params).mappings().all()

    def serie_crudo_diaria(
        self, ids: list[int], vice_id: int | None, ini: str, fin: str
    ) -> Sequence[Fila]:
        """Serie diaria de CRUDO — entrada de la detección de valle."""
        where, params = self._where_ambito(ids, vice_id, alias="d")
        params["ini"] = ini
        params["fin"] = fin
        sql = (
            "SELECT d.fecha AS fecha, SUM(d.volumen) AS vol "
            "FROM core.fact_produccion_dia_ecp d "
            "JOIN core.dim_tipo_producto tp ON tp.tipo_producto_id = d.tipo_producto_id "
            "WHERE tp.nombre='CRUDO' AND d.fecha BETWEEN :ini AND :fin "
            f"AND {where} GROUP BY 1 ORDER BY 1"
        )
        return self._db.execute(self._preparar(sql, params), params).mappings().all()

    def mtd_por_producto(
        self, ids: list[int], vice_id: int | None, ini: str, fin: str
    ) -> Sequence[Fila]:
        """Acumulado y días reportados por producto — para el ritmo diario."""
        where, params = self._where_ambito(ids, vice_id, alias="d")
        params["ini"] = ini
        params["fin"] = fin
        sql = (
            "SELECT tp.nombre AS prod, COUNT(DISTINCT d.fecha) AS ndias, "
            "SUM(d.volumen) AS mtd "
            "FROM core.fact_produccion_dia_ecp d "
            "JOIN core.dim_tipo_producto tp ON tp.tipo_producto_id = d.tipo_producto_id "
            f"WHERE d.fecha BETWEEN :ini AND :fin AND {where} GROUP BY 1"
        )
        return self._db.execute(self._preparar(sql, params), params).mappings().all()

    def historico_del_anio(
        self, ids: list[int], vice_id: int | None, anio: int, mes: int
    ) -> Sequence[Fila]:
        """REAL de los meses ANTERIORES al actual.

        Base de "producción del mes vs promedio del año" para las tarjetas sin
        ritmo diario fiable (p.ej. BLANCOS). NO se usa para Crudo/Gas.
        """
        where, params = self._where_ambito(ids, vice_id, alias="m")
        params["hy"] = anio
        params["hmo"] = mes
        sql = (
            "SELECT tp.nombre AS prod, EXTRACT(month FROM m.fecha)::int AS mes, "
            "SUM(m.volumen) AS vol "
            "FROM core.fact_produccion_mes_ecp m "
            "JOIN core.dim_tipo_producto tp ON tp.tipo_producto_id = m.tipo_producto_id "
            "JOIN core.dim_escenario es ON es.escenario_id = m.escenario_id "
            "WHERE es.nombre = 'REAL' AND EXTRACT(year FROM m.fecha) = :hy "
            f"AND EXTRACT(month FROM m.fecha) < :hmo AND {where} GROUP BY 1, 2"
        )
        return self._db.execute(self._preparar(sql, params), params).mappings().all()

    def nombres_de_entidad(self, ids: list[int], vice_id: int | None) -> list[str]:
        """Nombres (UPPER) con los que la entidad aparece en `dim_fuente`.

        Cruzan contra las columnas de texto de `fact_comentarios_produccion`,
        que NO tiene `fuente_id`. Incluye `grupo1`/`activos` a propósito: son el
        GRUPO con el que el reporte agrupa a la entidad, y a veces el comentario
        del grupo es el único disponible.

        Devuelve `[]` cuando no hay ids ni vice_id — el llamador debe leerlo
        como alcance GLOBAL, no como "sin resultados".
        """
        if ids:
            consulta = text(
                "SELECT nombre, campo, grupo1, activos FROM core.dim_fuente "
                "WHERE fuente_id IN :ids"
            ).bindparams(bindparam("ids", expanding=True))
            filas = self._db.execute(consulta, {"ids": ids}).all()
        elif vice_id is not None:
            filas = self._db.execute(
                text(
                    "SELECT nombre, campo, grupo1, activos FROM core.dim_fuente "
                    "WHERE vice_id = :vid"
                ),
                {"vid": vice_id},
            ).all()
        else:
            return []

        nombres: set[str] = set()
        for fila in filas:
            for valor in fila:
                if valor and str(valor).strip():
                    nombres.add(str(valor).strip().upper())
        return sorted(nombres)

    def comentarios_del_dia(
        self, fecha: Any, nombres: list[str] | None = None
    ) -> Sequence[Fila]:
        """Comentarios del reporte de UN día, opcionalmente acotados a la entidad.

        INS-A (verificado en BD): consultar TODO el rango del valle duplica el
        mismo evento —se repite "en estabilización" cada día— y produce un
        ranking basura. Solo el día de INICIO da los eventos limpios.

        `nombres` acota a la entidad; sin ellos, alcance global. Sin acotar, el
        brief de CASTILLA recibía los eventos de QUIFA/TIBU/CARACARA y el LLM
        explicaba su mes con fallas eléctricas ajenas.
        """
        filtro = ""
        params: dict[str, Any] = {"d": fecha}
        if nombres:
            filtro = f" AND ({_AREA_BASE} IN :names OR {_ACTIVOS_BASE} IN :names)"
            params["names"] = nombres

        consulta = text(
            "SELECT COALESCE(NULLIF(TRIM(fc.area),''), fc.activos) AS campo, "
            "fc.comentario AS comentario "
            "FROM core.fact_comentarios_produccion fc "
            "JOIN core.config_reporte cr ON cr.reporte_id = fc.reporte_id "
            "WHERE cr.fecha_reporte = :d "
            "AND fc.comentario IS NOT NULL AND LENGTH(TRIM(fc.comentario)) > 5" + filtro
        )
        if nombres:
            consulta = consulta.bindparams(bindparam("names", expanding=True))
        return self._db.execute(consulta, params).mappings().all()

    def comentarios_del_campo_en_el_mes(
        self, campo: str, ini: str, fin: str, limite: int = 2
    ) -> Sequence[Fila]:
        """Comentario(s) del reporte para un campo, en TODO el mes.

        Es la fuente/soporte de una atribución de causa. A diferencia de los del
        valle NO se acota a un día: el gap es una comparación mensual, no un
        evento puntual. Sin match real devuelve `[]` — nunca se inventa la causa.
        """
        consulta = text(
            "SELECT cr.fecha_reporte AS fecha, fc.comentario AS comentario "
            "FROM core.fact_comentarios_produccion fc "
            "JOIN core.config_reporte cr ON cr.reporte_id = fc.reporte_id "
            "WHERE cr.fecha_reporte BETWEEN :ini AND :fin "
            "AND fc.comentario IS NOT NULL AND LENGTH(TRIM(fc.comentario)) > 5 "
            f"AND ({_AREA_BASE} = :campo OR {_ACTIVOS_BASE} = :campo) "
            "ORDER BY cr.fecha_reporte DESC LIMIT :lim"
        )
        return (
            self._db.execute(
                consulta,
                {"ini": ini, "fin": fin, "campo": campo.strip().upper(), "lim": limite},
            )
            .mappings()
            .all()
        )
