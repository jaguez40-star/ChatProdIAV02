"""SQL de la Fundación de datos — catálogo, densidad, huella y cobertura.

Portado de `INGESTA/Rep_Prod/backend/app/features/analisis/api.py:30-348`.

**El SQL se conserva IDÉNTICO al origen** (U3: se reescribe la capa de acceso,
no las consultas). Están probadas contra el corpus real —`core.fact_tabla_hoja`
supera los 50M de filas— y cada `statement_timeout` es deliberado.

Lo único que cambia respecto al origen: allí cada endpoint abría su propia
conexión con `get_engine().connect()`; aquí la sesión llega inyectada por
`Depends(get_prod_db)` y el repositorio nunca la crea ni la cierra.

Cero lógica de negocio: la severidad de colisiones, el semáforo y el conteo de
huecos viven en `services_catalogo.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import RowMapping, bindparam, text
from sqlalchemy.orm import Session

Fila = RowMapping

# Listado completo de entidades por nivel, para el explorador "ver todas".
NIVELES_SQL: dict[str, str] = {
    "vicepresidencia": (
        "SELECT DISTINCT TRIM(codigo) FROM core.dim_vicepresidencia "
        "WHERE NULLIF(TRIM(codigo),'') IS NOT NULL"
    ),
    "gerencia": (
        "SELECT DISTINCT TRIM(gerencia) FROM core.dim_fuente "
        "WHERE NULLIF(TRIM(gerencia),'') IS NOT NULL"
    ),
    "activo": (
        "SELECT DISTINCT TRIM(activos) FROM core.dim_fuente "
        "WHERE NULLIF(TRIM(activos),'') IS NOT NULL"
    ),
    "area": (
        "SELECT DISTINCT TRIM(grupo1) FROM core.dim_fuente "
        "WHERE NULLIF(TRIM(grupo1),'') IS NOT NULL"
    ),
    "campo": (
        "SELECT DISTINCT TRIM(campo) FROM core.dim_fuente "
        "WHERE NULLIF(TRIM(campo),'') IS NOT NULL"
    ),
    "fuente": (
        "SELECT DISTINCT TRIM(nombre) FROM core.dim_fuente "
        "WHERE NULLIF(TRIM(nombre),'') IS NOT NULL"
    ),
}


class CatalogoRepository:
    """Consultas de la Fundación de datos. Recibe la sesión, no la abre."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Catálogo ─────────────────────────────────────────────────────────────

    def cardinalidad(self) -> Sequence[Fila]:
        return self._db.execute(text("""
            SELECT 'gerencia' nivel, COUNT(DISTINCT NULLIF(TRIM(gerencia),'')) n FROM core.dim_fuente
            UNION ALL SELECT 'activo', COUNT(DISTINCT NULLIF(TRIM(activos),'')) FROM core.dim_fuente
            UNION ALL SELECT 'area',   COUNT(DISTINCT NULLIF(TRIM(grupo1),''))  FROM core.dim_fuente
            UNION ALL SELECT 'campo',  COUNT(DISTINCT NULLIF(TRIM(campo),''))   FROM core.dim_fuente
            UNION ALL SELECT 'fuente', COUNT(DISTINCT NULLIF(TRIM(nombre),''))  FROM core.dim_fuente
        """)).mappings().all()

    def total_vicepresidencias(self) -> int:
        resultado = self._db.execute(
            text("SELECT COUNT(*) FROM core.dim_vicepresidencia")
        ).scalar()
        return int(resultado or 0)

    def colisiones(self) -> Sequence[Fila]:
        """Nombres que existen en más de un nivel de la jerarquía."""
        return self._db.execute(text("""
            WITH niveles AS (
                SELECT DISTINCT UPPER(TRIM(gerencia)) v, 'gerencia' niv FROM core.dim_fuente WHERE NULLIF(TRIM(gerencia),'') IS NOT NULL
                UNION SELECT DISTINCT UPPER(TRIM(activos)), 'activo' FROM core.dim_fuente WHERE NULLIF(TRIM(activos),'') IS NOT NULL
                UNION SELECT DISTINCT UPPER(TRIM(grupo1)),  'area'   FROM core.dim_fuente WHERE NULLIF(TRIM(grupo1),'')  IS NOT NULL
                UNION SELECT DISTINCT UPPER(TRIM(campo)),   'campo'  FROM core.dim_fuente WHERE NULLIF(TRIM(campo),'')   IS NOT NULL
                UNION SELECT DISTINCT UPPER(TRIM(nombre)),  'fuente' FROM core.dim_fuente WHERE NULLIF(TRIM(nombre),'')  IS NOT NULL
            )
            SELECT v AS nombre, COUNT(*) n_niveles, array_agg(niv ORDER BY niv) niveles
            FROM niveles GROUP BY v HAVING COUNT(*) > 1 ORDER BY COUNT(*) DESC, v
        """)).mappings().all()

    def filiales(self) -> list[str]:
        filas = self._db.execute(
            text("SELECT nombre FROM core.dim_empresa ORDER BY nombre")
        ).all()
        return [str(nombre) for (nombre,) in filas]

    def entidades_por_nivel(self) -> dict[str, list[str]]:
        return {
            nivel: sorted(
                str(valor) for (valor,) in self._db.execute(text(sql)).all() if valor
            )
            for nivel, sql in NIVELES_SQL.items()
        }

    # ── Densidad ─────────────────────────────────────────────────────────────

    def fuentes_de_entidad(self, entidad: str) -> list[int]:
        """Resuelve la entidad por 6 columnas de `dim_fuente`, incluida
        `operador` (que trae las filiales como Hocol). MISMO criterio que usa
        `_presencia_entidad`, para que densidad y cobertura no diverjan."""
        filas = self._db.execute(
            text("""
                SELECT fuente_id FROM core.dim_fuente
                WHERE UPPER(TRIM(nombre))=:e OR UPPER(TRIM(campo))=:e
                   OR UPPER(TRIM(grupo1))=:e OR UPPER(TRIM(activos))=:e
                   OR UPPER(TRIM(gerencia))=:e OR UPPER(TRIM(operador))=:e
            """),
            {"e": entidad},
        ).all()
        return [int(fuente_id) for (fuente_id,) in filas]

    def vice_id_de(self, entidad: str) -> int | None:
        """El fact tiene columna `vicepresidencia`, así que los códigos
        VAS/VEX/… sí filtran aunque no estén en `dim_fuente`."""
        resultado = self._db.execute(
            text(
                "SELECT vice_id FROM core.dim_vicepresidencia "
                "WHERE UPPER(TRIM(codigo))=:e"
            ),
            {"e": entidad},
        ).scalar()
        return int(resultado) if resultado is not None else None

    def densidad_global(self) -> Sequence[Fila]:
        return self._db.execute(text("""
                SELECT fecha, COUNT(*) AS filas, COUNT(DISTINCT fuente_id) AS fuentes
                FROM core.fact_produccion_dia_ecp
                GROUP BY fecha ORDER BY fecha
            """)).mappings().all()

    def densidad_de_entidad(
        self, ids: list[int], vice_id: int | None
    ) -> Sequence[Fila]:
        condiciones: list[str] = []
        params: dict[str, Any] = {}
        if ids:
            condiciones.append("fuente_id IN :ids")
            params["ids"] = ids
        if vice_id is not None:
            condiciones.append("vice_id = :vid")
            params["vid"] = vice_id
        if not condiciones:
            return []

        consulta = text(
            """
                    SELECT fecha, COUNT(*) AS filas, COUNT(DISTINCT fuente_id) AS fuentes
                    FROM core.fact_produccion_dia_ecp
                    WHERE """
            + " OR ".join(condiciones)
            + """
                    GROUP BY fecha ORDER BY fecha"""
        )
        if ids:
            consulta = consulta.bindparams(bindparam("ids", expanding=True))
        return self._db.execute(consulta, params).mappings().all()

    # ── Huella ───────────────────────────────────────────────────────────────

    def fijar_timeout(self, segundos: str) -> None:
        """`SET statement_timeout` del origen: estas consultas tocan facts
        grandes y una sin límite podría colgar la petición indefinidamente."""
        self._db.execute(text(f"SET statement_timeout='{segundos}'"))

    def fuentes_para_huella(self, entidad: str) -> list[int]:
        """Sin `gerencia` ni `operador`: la huella del origen resuelve por 4
        columnas, no por 6. Se conserva la diferencia."""
        filas = self._db.execute(
            text("""
                SELECT fuente_id FROM core.dim_fuente
                WHERE UPPER(TRIM(nombre))=:e OR UPPER(TRIM(campo))=:e
                   OR UPPER(TRIM(grupo1))=:e OR UPPER(TRIM(activos))=:e
            """),
            {"e": entidad},
        ).all()
        return [int(fuente_id) for (fuente_id,) in filas]

    def contar_dia_ecp(self, ids: list[int] | None = None) -> int:
        if ids is None:
            resultado = self._db.execute(
                text("SELECT COUNT(*) FROM core.fact_produccion_dia_ecp")
            ).scalar()
        else:
            consulta = text(
                "SELECT COUNT(*) FROM core.fact_produccion_dia_ecp WHERE fuente_id IN :ids"
            ).bindparams(bindparam("ids", expanding=True))
            resultado = self._db.execute(consulta, {"ids": ids}).scalar()
        return int(resultado or 0)

    def mes_ecp_por_escenario(self, ids: list[int] | None = None) -> Sequence[Fila]:
        if ids is None:
            consulta = text("""
            SELECT es.nombre AS nombre, COUNT(*) AS filas FROM core.fact_produccion_mes_ecp m
            JOIN core.dim_escenario es ON es.escenario_id = m.escenario_id
            GROUP BY es.nombre ORDER BY es.nombre""")
            return self._db.execute(consulta).mappings().all()

        consulta = text(
            """
            SELECT es.nombre AS nombre, COUNT(*) AS filas FROM core.fact_produccion_mes_ecp m
            JOIN core.dim_escenario es ON es.escenario_id = m.escenario_id
            WHERE m.fuente_id IN :ids GROUP BY es.nombre ORDER BY es.nombre"""
        ).bindparams(bindparam("ids", expanding=True))
        return self._db.execute(consulta, {"ids": ids}).mappings().all()

    def contar_programa(self, ids: list[int] | None = None, entidad: str = "") -> int:
        if ids is None:
            resultado = self._db.execute(
                text("SELECT COUNT(*) FROM core.fact_programa_ecp")
            ).scalar()
        else:
            consulta = text("""
                SELECT COUNT(*) FROM core.fact_programa_ecp
                WHERE fuente_id IN :ids OR UPPER(TRIM(campo))=:e OR UPPER(TRIM(area))=:e
            """).bindparams(bindparam("ids", expanding=True))
            resultado = self._db.execute(consulta, {"ids": ids, "e": entidad}).scalar()
        return int(resultado or 0)

    # ── Cobertura ────────────────────────────────────────────────────────────

    def hojas_de_ingesta(self) -> Sequence[Fila]:
        """F1 (del origen): la métrica es `COUNT(DISTINCT reporte_id)`, NO
        `SUM(filas_insertadas)` — esta última sobre-cuenta ~26x por los upserts
        idempotentes acumulados en 138 reportes (11,2M vs 435K reales)."""
        return self._db.execute(text("""
            SELECT hoja, tabla_destino, COUNT(DISTINCT reporte_id) reps
            FROM core.ingesta_log
            GROUP BY hoja, tabla_destino
        """)).mappings().all()

    def presencia_en_facts(
        self,
        tabla: str,
        ids: list[int],
        vice_id: int | None,
        extra_cond: str = "",
        entidad: str = "",
    ) -> int:
        """Reportes distintos donde aparece la entidad en un fact ECP."""
        condiciones: list[str] = []
        params: dict[str, Any] = {}
        if ids:
            condiciones.append("fuente_id IN :ids")
            params["ids"] = ids
        if vice_id is not None:
            condiciones.append("vice_id = :vid")
            params["vid"] = vice_id
        if extra_cond:
            condiciones.append(extra_cond)
            params["e"] = entidad
        if not condiciones:
            return 0

        consulta = text(
            f"SELECT COUNT(DISTINCT reporte_id) FROM core.{tabla} "
            "WHERE " + " OR ".join(condiciones)
        )
        if ids:
            consulta = consulta.bindparams(bindparam("ids", expanding=True))
        return int(self._db.execute(consulta, params).scalar() or 0)

    def presencia_en_landing(self, patron: str) -> Sequence[Fila]:
        """Resto de hojas vía `bronze.hoja_landing` (ILIKE sobre el payload
        JSONB), para no tocar los 62M de filas de los facts."""
        return (
            self._db.execute(
                text("""
        SELECT hoja, COUNT(DISTINCT reporte_id) AS reps FROM bronze.hoja_landing
        WHERE payload::text ILIKE :pat ESCAPE '\\' GROUP BY hoja
    """),
                {"pat": patron},
            )
            .mappings()
            .all()
        )
