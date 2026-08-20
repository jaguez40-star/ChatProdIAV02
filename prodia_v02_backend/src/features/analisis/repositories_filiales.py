"""SQL del segmento FILIALES y de la tarjeta P50 (president).

Portado de `INGESTA/Rep_Prod/backend/app/features/analisis/api.py:2001-2619`.
**El SQL se conserva IDÉNTICO al origen** (U3).

⚠️ **Fuente distinta a ECP.** Las filiales viven en
`core.fact_produccion_diaria` (grano día-empresa), no en los facts ECP:

- `tipo_id=1` → REAL · `tipo_id=2` → PROGRAMA (la meta, no hay PPTO).
- La comparación es **MISMA-VENTANA**: solo los días con REAL (CTE `rd`).
  Comparar 17 días de REAL contra un PROGRAMA de mes completo daría ~55 %
  siempre, que es un artefacto del corte, no un incumplimiento.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

Fila = RowMapping

# Solo los días que tienen REAL: es lo que hace justa la comparación.
_CTE_DIAS_CON_REAL = (
    "WITH rd AS (SELECT DISTINCT fecha FROM core.fact_produccion_diaria "
    "WHERE tipo_id=1 AND fecha BETWEEN :ini AND :fin) "
)


class FilialesRepository:
    """Consultas de filiales y de la hoja REPORTE_PRESIDENT."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Ámbito temporal ──────────────────────────────────────────────────────

    def max_fecha_real(self, empresa_id: int | None = None) -> Any:
        if empresa_id is None:
            return self._db.execute(
                text(
                    "SELECT MAX(fecha) FROM core.fact_produccion_diaria WHERE tipo_id=1"
                )
            ).scalar()
        return self._db.execute(
            text(
                "SELECT MAX(fecha) FROM core.fact_produccion_diaria "
                "WHERE tipo_id=1 AND empresa_id=:eid"
            ),
            {"eid": empresa_id},
        ).scalar()

    def dias_con_real(self, ini: str, fin: str, empresa_id: int | None = None) -> int:
        if empresa_id is None:
            resultado = self._db.execute(
                text(
                    "SELECT COUNT(DISTINCT fecha) FROM core.fact_produccion_diaria "
                    "WHERE tipo_id=1 AND fecha BETWEEN :ini AND :fin"
                ),
                {"ini": ini, "fin": fin},
            ).scalar()
        else:
            resultado = self._db.execute(
                text(
                    "SELECT COUNT(DISTINCT fecha) FROM core.fact_produccion_diaria "
                    "WHERE tipo_id=1 AND empresa_id=:eid AND fecha BETWEEN :ini AND :fin"
                ),
                {"eid": empresa_id, "ini": ini, "fin": fin},
            ).scalar()
        return int(resultado or 0)

    # ── KPIs del grupo ───────────────────────────────────────────────────────

    def kpis_misma_ventana(self, ini: str, fin: str) -> Sequence[Fila]:
        """REAL vs PROGRAMA por producto, solo en los días con REAL."""
        return (
            self._db.execute(
                text(
                    _CTE_DIAS_CON_REAL + "SELECT tp.nombre AS prod, "
                    "SUM(CASE WHEN fp.tipo_id=1 THEN fp.valor_produccion END) AS real_mtd, "
                    "SUM(CASE WHEN fp.tipo_id=2 THEN fp.valor_produccion END) AS prog_mtd "
                    "FROM core.fact_produccion_diaria fp "
                    "JOIN core.dim_tipo_producto tp "
                    "ON tp.tipo_producto_id = fp.producto_id "
                    "WHERE fp.fecha IN (SELECT fecha FROM rd) GROUP BY 1"
                ),
                {"ini": ini, "fin": fin},
            )
            .mappings()
            .all()
        )

    def curva_diaria(self, ini: str, fin: str) -> Sequence[Fila]:
        return (
            self._db.execute(
                text(
                    "SELECT fp.fecha AS fecha, tp.nombre AS prod, "
                    "SUM(fp.valor_produccion) AS vol "
                    "FROM core.fact_produccion_diaria fp "
                    "JOIN core.dim_tipo_producto tp "
                    "ON tp.tipo_producto_id = fp.producto_id "
                    "WHERE fp.tipo_id=1 AND fp.fecha BETWEEN :ini AND :fin "
                    "GROUP BY 1, 2 ORDER BY 1"
                ),
                {"ini": ini, "fin": fin},
            )
            .mappings()
            .all()
        )

    def gap_por_empresa(self, ini: str, fin: str, producto: str) -> Sequence[Fila]:
        """Descomposición del gap por EMPRESA, misma ventana."""
        return (
            self._db.execute(
                text(
                    _CTE_DIAS_CON_REAL + "SELECT e.nombre AS campo, "
                    "SUM(CASE WHEN fp.tipo_id=1 THEN fp.valor_produccion ELSE 0 END) AS vreal, "
                    "SUM(CASE WHEN fp.tipo_id=2 THEN fp.valor_produccion ELSE 0 END) AS vprog "
                    "FROM core.fact_produccion_diaria fp "
                    "JOIN core.dim_tipo_producto tp "
                    "ON tp.tipo_producto_id = fp.producto_id "
                    "JOIN core.dim_empresa e ON e.empresa_id = fp.empresa_id "
                    "WHERE tp.nombre = :prod AND fp.fecha IN (SELECT fecha FROM rd) "
                    "GROUP BY 1"
                ),
                {"ini": ini, "fin": fin, "prod": producto},
            )
            .mappings()
            .all()
        )

    def programa_mes_completo(self, ini: str, fin: str) -> float:
        """PROGRAMA de crudo del MES COMPLETO — target de cierre para el pace."""
        resultado = self._db.execute(
            text(
                "SELECT SUM(fp.valor_produccion) FROM core.fact_produccion_diaria fp "
                "JOIN core.dim_tipo_producto tp ON tp.tipo_producto_id = fp.producto_id "
                "WHERE tp.nombre='CRUDO' AND fp.tipo_id=2 "
                "AND fp.fecha BETWEEN :ini AND :fin"
            ),
            {"ini": ini, "fin": fin},
        ).scalar()
        return float(resultado or 0)

    def promedio_mensual_del_anio(
        self, anio: int, mes_ini: str, empresa_id: int | None = None
    ) -> Sequence[Fila]:
        """Promedio mensual del REAL en meses COMPLETOS previos al actual.

        Es la base de comparación de las tarjetas: las filiales no tienen PPTO,
        así que la referencia es su propia historia del año (Opción B del
        usuario, 2026-07-21). Nunca se fabrica una meta.
        """
        filtro_empresa = "AND fp.empresa_id = :eid " if empresa_id is not None else ""
        params: dict[str, Any] = {"y0": f"{anio:04d}-01-01", "mes_ini": mes_ini}
        if empresa_id is not None:
            params["eid"] = empresa_id

        return (
            self._db.execute(
                text(
                    "WITH mens AS ("
                    "SELECT tp.nombre AS prod, date_trunc('month', fp.fecha) AS m, "
                    "SUM(fp.valor_produccion) AS tot "
                    "FROM core.fact_produccion_diaria fp "
                    "JOIN core.dim_tipo_producto tp "
                    "ON tp.tipo_producto_id = fp.producto_id "
                    "WHERE fp.tipo_id = 1 " + filtro_empresa + "AND fp.fecha >= :y0 "
                    "AND fp.fecha < :mes_ini GROUP BY 1, 2) "
                    "SELECT prod, AVG(tot) AS promedio FROM mens GROUP BY 1"
                ),
                params,
            )
            .mappings()
            .all()
        )

    # ── Una filial ───────────────────────────────────────────────────────────

    def listar_empresas(self) -> Sequence[Fila]:
        return (
            self._db.execute(
                text(
                    "SELECT empresa_id, nombre FROM core.dim_empresa "
                    "WHERE NULLIF(TRIM(nombre),'') IS NOT NULL ORDER BY empresa_id"
                )
            )
            .mappings()
            .all()
        )

    def empresa_id_de(self, nombre: str) -> int | None:
        resultado = self._db.execute(
            text(
                "SELECT empresa_id FROM core.dim_empresa "
                "WHERE UPPER(TRIM(nombre)) = UPPER(TRIM(:n))"
            ),
            {"n": nombre},
        ).scalar()
        return int(resultado) if resultado is not None else None

    def mtd_de_empresa(self, empresa_id: int, ini: str, fin: str) -> Sequence[Fila]:
        return (
            self._db.execute(
                text(
                    "SELECT tp.nombre AS prod, SUM(fp.valor_produccion) AS tot "
                    "FROM core.fact_produccion_diaria fp "
                    "JOIN core.dim_tipo_producto tp "
                    "ON tp.tipo_producto_id = fp.producto_id "
                    "WHERE fp.tipo_id=1 AND fp.empresa_id=:eid "
                    "AND fp.fecha BETWEEN :ini AND :fin GROUP BY 1"
                ),
                {"eid": empresa_id, "ini": ini, "fin": fin},
            )
            .mappings()
            .all()
        )

    def meses_completos_del_anio(self, empresa_id: int, anio: int, mes_ini: str) -> int:
        """Meses previos con cobertura COMPLETA (>=20 días) que sostienen el
        promedio. Sin ellos la tendencia no tiene base y se declara."""
        resultado = self._db.execute(
            text(
                "SELECT COUNT(*) FROM ("
                "SELECT date_trunc('month', fecha) AS m "
                "FROM core.fact_produccion_diaria "
                "WHERE tipo_id=1 AND empresa_id=:eid AND fecha >= :y0 "
                "AND fecha < :mes_ini "
                "GROUP BY 1 HAVING COUNT(DISTINCT fecha) >= 20) t"
            ),
            {"eid": empresa_id, "y0": f"{anio:04d}-01-01", "mes_ini": mes_ini},
        ).scalar()
        return int(resultado or 0)

    def serie_mensual_de_empresa(self, empresa_id: int) -> Sequence[Fila]:
        """Serie mensual completa de una filial, con los días de cada mes.

        Los días se devuelven para poder excluir los meses casi vacíos: un mes
        con 1 día distorsiona la tendencia (Nov-2025 en el corpus real).
        """
        return (
            self._db.execute(
                text(
                    "SELECT date_trunc('month', fp.fecha) AS m, tp.nombre AS prod, "
                    "SUM(fp.valor_produccion) AS tot, "
                    "COUNT(DISTINCT fp.fecha) AS dias "
                    "FROM core.fact_produccion_diaria fp "
                    "JOIN core.dim_tipo_producto tp "
                    "ON tp.tipo_producto_id = fp.producto_id "
                    "WHERE fp.tipo_id=1 AND fp.empresa_id=:e "
                    "GROUP BY 1, 2 ORDER BY 1"
                ),
                {"e": empresa_id},
            )
            .mappings()
            .all()
        )

    # ── President (tarjeta P50) ──────────────────────────────────────────────

    def reporte_con_president(self, periodo: str | None = None) -> int | None:
        """Reporte más reciente que tenga la hoja REPORTE_PRESIDENT.

        🔑 Se ordena por `fecha_reporte`, NUNCA por `MAX(reporte_id)`: el id es
        un serial por ORDEN DE INGESTA, no cronológico. En dev, mayo se ingirió
        primero (ids 1-18) y marzo después (ids 108-139), así que `MAX(id)`
        devolvía MARZO teniendo mayo cargado — el encabezado mostraba un mes
        distinto al del resto del panel y las tarjetas parecían contradecirse.
        """
        if periodo:
            resultado = self._db.execute(
                text(
                    "SELECT cr.reporte_id FROM core.config_reporte cr "
                    "WHERE to_char(cr.fecha_reporte,'YYYY-MM') = :p "
                    "AND EXISTS (SELECT 1 FROM core.fact_tabla_hoja f "
                    "WHERE f.reporte_id = cr.reporte_id "
                    "AND f.hoja = 'REPORTE_PRESIDENT') "
                    "ORDER BY cr.fecha_reporte DESC LIMIT 1"
                ),
                {"p": periodo},
            ).scalar()
        else:
            resultado = self._db.execute(
                text(
                    "SELECT cr.reporte_id FROM core.config_reporte cr "
                    "WHERE EXISTS (SELECT 1 FROM core.fact_tabla_hoja f "
                    "WHERE f.reporte_id = cr.reporte_id "
                    "AND f.hoja = 'REPORTE_PRESIDENT') "
                    "ORDER BY cr.fecha_reporte DESC LIMIT 1"
                )
            ).scalar()
        return int(resultado) if resultado is not None else None

    def fecha_de_reporte(self, reporte_id: int) -> Any:
        return self._db.execute(
            text("SELECT fecha_reporte FROM core.config_reporte WHERE reporte_id=:r"),
            {"r": reporte_id},
        ).scalar()

    def medidas_president(self, reporte_id: int) -> Sequence[Fila]:
        return (
            self._db.execute(
                text(
                    "SELECT dims->>'entidad' AS ent, dims->>'medida' AS med, "
                    "valor AS valor FROM core.fact_tabla_hoja "
                    "WHERE hoja='REPORTE_PRESIDENT' AND reporte_id=:r"
                ),
                {"r": reporte_id},
            )
            .mappings()
            .all()
        )
