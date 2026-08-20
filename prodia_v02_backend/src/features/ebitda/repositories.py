"""SQL del EBITDA Inspector — BD operacional ROBUSTEZ (schema `ops`).

Portado de `INGESTA/Rep_Prod/backend/app/features/ebitda/api.py`.
**El SQL se conserva IDÉNTICO al origen** (U3). Solo lectura: ProdIA V02 consume
la BD de Robustez V02, no la administra.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

# (label, key, tabla, columna, tipo, signo) — el ORDEN es el del waterfall.
#
# `signo` decide cómo se lleva el valor guardado a la barra del gráfico:
#   pos    → tal cual (los totales acumulados)
#   negabs → -abs(v): los costos operativos se guardan positivos y restan
#   neg    → -v: cargos de `financial_results` guardados en positivo
#   asis   → tal cual, porque el dato YA trae signo negativo (renta,
#            financieros, diferencia en cambio)
#
# Mezclar estos modos invierte barras del waterfall sin ningún error visible.
COMPONENTES: list[tuple[str, str, str, str, str, str]] = [
    ("Ingresos", "ingresos", "fr", "revenue_oil_real_kusd", "total", "pos"),
    (
        "M. Subsuelo",
        "subsuelo",
        "oc",
        "maintenance_subsurface_a_kusd",
        "delta",
        "negabs",
    ),
    ("Dilución", "dilucion", "oc", "dilution_real_a_kusd", "delta", "negabs"),
    ("Tratamiento", "tratamiento", "oc", "treatment_a_kusd", "delta", "negabs"),
    ("Energía", "energia", "oc", "energy_a_kusd", "delta", "negabs"),
    ("Transporte", "transporte", "oc", "transport_real_a_kusd", "delta", "negabs"),
    ("Costos Fijos", "costos_fijos", "oc", "costs_fixed_a_kusd", "delta", "negabs"),
    ("Gasto", "gasto", "oc", "expenses_a_kusd", "delta", "negabs"),
    ("EBITDA", "ebitda", "fr", "ebitda_a_kusd", "total", "pos"),
    ("Amortización", "amortiz", "fr", "amortiz_a_kusd", "delta", "neg"),
    ("Depreciación", "deprec", "fr", "deprec_a_kusd", "delta", "neg"),
    (
        "Impuestos Costos y Gastos",
        "imp_cosgas",
        "fr",
        "imp_cosgas_a_kusd",
        "delta",
        "neg",
    ),
    ("Impairment", "impair", "fr", "impair_a_kusd", "delta", "neg"),
    ("UTILID. OPERATIVA (EBIT)", "util_oper", "fr", "util_oper_a_kusd", "total", "pos"),
    ("Impuesto de renta", "imp_renta", "fr", "imp_renta_a_kusd", "delta", "asis"),
    ("Financieros netos", "finan_netos", "fr", "finan_netos_a_kusd", "delta", "asis"),
    (
        "Diferencia en cambio",
        "dif_en_cambio",
        "fr",
        "dif_en_cambio_a_kusd",
        "delta",
        "asis",
    ),
    ("UTILID. NETA (NOPAT)", "util_neta", "fr", "util_neta_a_kusd", "total", "pos"),
]


def _sanear(expresion: str) -> str:
    """Neutraliza los `Infinity`/`NaN` que la BD guarda como texto.

    Es A6 aplicado en SQL: sin esto, un valor no finito rompe la serialización
    JSON en silencio o llega al frontend como un número que no puede pintar.
    """
    return f"NULLIF(NULLIF(NULLIF({expresion},'Infinity'),'-Infinity'),'NaN')"


class EbitdaRepository:
    """Consultas contra `ops.*`. Recibe la sesión, no la abre."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def waterfall(
        self, anio: int, mes: int, nivel: str = "", entidades: list[str] | None = None
    ) -> RowMapping | None:
        """Suma de los 18 componentes + barriles, para el periodo y el ámbito.

        `entidades` puede traer varios valores: un foco agrupa N campos. El
        `DISTINCT ON (uwi)` de `wells_attributes` evita multiplicar filas cuando
        un pozo tiene varias entradas de atributos.
        """
        sumas = ", ".join(
            f"SUM({_sanear(tabla + '.' + columna)}) AS {clave}"
            for (_label, clave, tabla, columna, _tipo, _signo) in COMPONENTES
        )
        sumas += f", SUM({_sanear('flr.total_bbl_blend')}) AS total_bls"

        params: dict[str, Any] = {"y": anio, "m": mes}
        join_atributos = ""
        filtro_entidad = ""

        if nivel in ("activo", "campo") and entidades:
            columna = "active" if nivel == "activo" else "field"
            join_atributos = (
                "JOIN (SELECT DISTINCT ON (uwi) uwi, active, field "
                "FROM ops.wells_attributes "
                "ORDER BY uwi, well_status, pend_id_cc, zone) wa ON wa.uwi = fr.uwi"
            )
            marcadores = ",".join(f":e{i}" for i in range(len(entidades)))
            filtro_entidad = f" AND UPPER(TRIM(wa.{columna})) IN ({marcadores})"
            for indice, valor in enumerate(entidades):
                params[f"e{indice}"] = valor

        consulta = text(
            f"SELECT {sumas} "
            "FROM ops.financial_results fr "
            "JOIN ops.operating_costs oc "
            "ON (oc.uwi,oc.year,oc.month,oc.well_status,oc.pend_id_cc,oc.zone) "
            "= (fr.uwi,fr.year,fr.month,fr.well_status,fr.pend_id_cc,fr.zone) "
            "JOIN ops.flow_rates flr "
            "ON (flr.uwi,flr.year,flr.month,flr.well_status,flr.pend_id_cc,flr.zone) "
            "= (fr.uwi,fr.year,fr.month,fr.well_status,fr.pend_id_cc,fr.zone) "
            f"{join_atributos} "
            f"WHERE fr.year = :y AND fr.month = :m{filtro_entidad}"
        )
        return self._db.execute(consulta, params).mappings().first()


class PeriodoProdRepository:
    """Último mes con REAL en `db_prod` — alinea el periodo del EBITDA.

    Vive aquí y no en `analisis` porque esta feature necesita su propia sesión
    de `db_prod`: son dos engines distintos y ADR-001 prohíbe importar de otra
    feature.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def ultimo_mes_con_real(self) -> tuple[int, int] | None:
        fecha = self._db.execute(
            text(
                "SELECT MAX(m.fecha) FROM core.fact_produccion_mes_ecp m "
                "JOIN core.dim_escenario es ON es.escenario_id=m.escenario_id "
                "WHERE es.nombre='REAL'"
            )
        ).scalar()
        return (fecha.year, fecha.month) if fecha else None
