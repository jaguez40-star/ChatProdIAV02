"""Tests de `TablasService` — pivote a formato ancho, árbol y saneado A6.

Usan el doble `SesionProdFalsa` (ver `tests/fakes/prod_db_falsa.py`): NUNCA tocan
PostgreSQL, porque el CI no levanta ninguno (H1 del plan F1).

Lo que se prueba aquí es la lógica portada del sistema viejo, que es donde están los bugs
de código. La fidelidad del SQL contra el corpus real (50M+ filas) se verifica a mano
contra el 139 (R3), no aquí.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from src.features.tablas.repositories import TablasRepository
from src.features.tablas.services import TablasService
from tests.fakes.prod_db_falsa import (
    FILAS_MATRIZ,
    SesionProdFalsa,
)


def _service(datos: dict[str, Any] | None = None) -> TablasService:
    return TablasService(TablasRepository(SesionProdFalsa(datos=datos)))  # type: ignore[arg-type]


# ── Árbol de reportes ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_arbol_agrupa_por_anio_mes_dia() -> None:
    arbol = _service().arbol_reportes()

    assert [a.anio for a in arbol] == [2026, 2025]  # descendente
    meses_2026 = arbol[0].meses
    assert len(meses_2026) == 1
    assert meses_2026[0].mes == 8
    assert meses_2026[0].mes_nombre == "Agosto"  # nombre en español
    assert [d.dia for d in meses_2026[0].dias] == [15, 14]  # descendente


@pytest.mark.unit
def test_arbol_conserva_metadata_del_reporte() -> None:
    dia = _service().arbol_reportes()[0].meses[0].dias[0]

    assert dia.reporte_id == 1042
    assert dia.tipo == "ECP"
    assert dia.archivo == "Reporte_2026-08-15.xlsm"


@pytest.mark.unit
def test_arbol_vacio_no_revienta() -> None:
    assert _service({"config_reportes": []}).arbol_reportes() == []


# ── Hojas de un reporte ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_hojas_agrupa_tablas_por_hoja() -> None:
    resultado = _service().hojas_de_reporte(1042)

    assert resultado.reporte_id == 1042
    assert [h.hoja for h in resultado.hojas] == ["COMENTARIOS", "NEW MES-AÑO"]
    assert len(resultado.hojas[1].tablas) == 2
    assert resultado.hojas[1].tablas[0].tabla_label == "PRODUCCION MES"


# ── Tablas lógicas de una hoja ───────────────────────────────────────────────


@pytest.mark.unit
def test_tablas_de_hoja_normal() -> None:
    tablas = _service().tablas_de_hoja(1042, "NEW MES-AÑO")

    assert [t.tabla_idx for t in tablas] == [1, 2]
    assert tablas[0].filas == 240


@pytest.mark.unit
@pytest.mark.parametrize("hoja", ["COMENTARIOS", "comentarios", "  Comentarios  "])
def test_tablas_de_hoja_comentarios_es_caso_aparte(hoja: str) -> None:
    """COMENTARIOS no vive en `fact_tabla_hoja` — devuelve UNA tabla lógica desde su
    fact dedicado, sin importar mayúsculas ni espacios."""
    tablas = _service().tablas_de_hoja(1042, hoja)

    assert len(tablas) == 1
    assert tablas[0].tabla_idx == 1
    assert tablas[0].tabla_label == "COMENTARIOS"
    assert tablas[0].filas == 3


# ── Modo `fechas` ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_datos_modo_fechas_pivota_por_combo_de_dimensiones() -> None:
    tabla = _service().datos_tabla(1042, "NEW MES-AÑO", 1)

    assert tabla.modo == "fechas"
    assert tabla.vacia is False
    assert tabla.dimensiones == ["campo"]
    assert tabla.meses == ["2026-08-01", "2026-08-02"]
    assert tabla.total_filas == 2  # dos combos distintos
    assert tabla.filas[0].dims == {"campo": "CASTILLA"}
    assert tabla.filas[0].valores == [33453.2, 33500.0]


@pytest.mark.unit
def test_datos_modo_fechas_alinea_huecos_como_none() -> None:
    """Un combo sin valor para una fecha deja `None` en esa posición, no descoloca."""
    tabla = _service().datos_tabla(1042, "NEW MES-AÑO", 1)

    chichimene = tabla.filas[1]
    assert chichimene.dims == {"campo": "CHICHIMENE"}
    assert chichimene.valores == [12000.5, None]


@pytest.mark.unit
def test_datos_modo_fechas_orden_de_dimensiones_es_de_aparicion() -> None:
    """`dim_keys` se acumula en orden de aparición para que la cabecera sea estable."""
    filas = [
        {
            "dims": {"campo": "A", "activo": "X"},
            "fecha": date(2026, 8, 1),
            "valor": 1.0,
        },
        {
            "dims": {"activo": "Y", "campo": "B"},
            "fecha": date(2026, 8, 1),
            "valor": 2.0,
        },
    ]
    tabla = _service({"filas_tabla": filas}).datos_tabla(1042, "H", 1)

    assert tabla.dimensiones == ["campo", "activo"]  # no alfabético: de aparición


@pytest.mark.unit
@pytest.mark.parametrize(
    "dims",
    [
        {"anio": 2026},  # JSONB numérico
        {"activo": True},  # JSONB booleano
        {"campo": "CASTILLA", "tabla_idx": 3},  # mixto
        {"campo": None},  # nulo
    ],
)
def test_dims_admite_cualquier_tipo_de_jsonb(dims: dict[str, Any]) -> None:
    """Regresión: `dims` es JSONB y los extractores meten números y booleanos, no solo
    texto. Tiparlo como `dict[str, str|None]` reventaba con ValidationError contra el
    corpus real — y no lo detectaba ningún test, porque el corpus de ejemplo usaba solo
    cadenas."""
    filas = [{"dims": dims, "fecha": date(2026, 8, 1), "valor": 1.0}]

    tabla = _service({"filas_tabla": filas}).datos_tabla(1042, "H", 1)

    assert tabla.filas[0].dims == dims


# ── Modo `matriz` ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_datos_modo_matriz_cuando_ninguna_fila_tiene_fecha() -> None:
    tabla = _service({"filas_tabla": FILAS_MATRIZ}).datos_tabla(1042, "MATRIZ", 1)

    assert tabla.modo == "matriz"
    assert tabla.dimensiones == ["fila"]
    assert tabla.total_filas == 2


@pytest.mark.unit
def test_datos_modo_matriz_preserva_el_orden_de_columnas() -> None:
    """En las matrices el orden de columnas ES el dato — nunca se ordena alfabéticamente
    (si se ordenara, "Meta" iría antes que "Real" y los valores quedarían cruzados)."""
    tabla = _service({"filas_tabla": FILAS_MATRIZ}).datos_tabla(1042, "MATRIZ", 1)

    assert tabla.meses == ["Real", "Meta"]  # orden de aparición, no alfabético
    assert tabla.filas[0].dims == {"fila": "Crudo"}
    assert tabla.filas[0].valores == [100.0, 110.0]


# ── Modo `texto` (COMENTARIOS) ───────────────────────────────────────────────


@pytest.mark.unit
def test_datos_modo_texto_para_comentarios() -> None:
    tabla = _service().datos_tabla(1042, "COMENTARIOS", 1)

    assert tabla.modo == "texto"
    assert tabla.dimensiones == ["producto", "activos", "area"]
    assert tabla.meses == ["Comentario", "Comentario programa", "Comentario extra"]
    assert tabla.filas[0].valores == ["Sin novedad.", "Programa cumplido.", None]


@pytest.mark.unit
def test_datos_comentarios_vacios() -> None:
    tabla = _service({"comentarios": []}).datos_tabla(1042, "COMENTARIOS", 1)

    assert tabla.vacia is True
    assert tabla.filas == []


# ── Tabla vacía, recorte y truncado ──────────────────────────────────────────


@pytest.mark.unit
def test_datos_tabla_vacia() -> None:
    tabla = _service({"filas_tabla": []}).datos_tabla(1042, "H", 1)

    assert tabla.vacia is True
    assert tabla.filas == []
    assert tabla.total_filas == 0


@pytest.mark.unit
def test_datos_recorta_a_cap_filas_pero_total_refleja_todo() -> None:
    """El visor muestra 100 filas; `total_filas` dice cuántas hay de verdad."""
    filas = [
        {"dims": {"campo": f"C{i}"}, "fecha": date(2026, 8, 1), "valor": float(i)}
        for i in range(150)
    ]
    tabla = _service({"filas_tabla": filas}).datos_tabla(1042, "H", 1)

    assert len(tabla.filas) == 100
    assert tabla.total_filas == 150


@pytest.mark.unit
def test_datos_hoja_truncada_pide_las_fechas_aparte() -> None:
    """Si se superó FETCH_MAX, la cabecera de fechas NO puede salir del prefijo cargado:
    se consulta aparte para que sea estable, y el total viene de un count(*)."""
    filas = [
        {"dims": {"campo": "A"}, "fecha": date(2026, 8, 1), "valor": 1.0}
        for _ in range(50_001)
    ]
    tabla = _service({"filas_tabla": filas, "contar_filas_tabla": 987_654}).datos_tabla(
        1042, "BDP_datos_mes", 1
    )

    assert tabla.meses == ["2026-08-01", "2026-08-02"]  # de `fechas_distintas`
    assert tabla.total_filas == 987_654  # de `count(*)`, no del prefijo


# ── A6 — saneado de valores no finitos ───────────────────────────────────────


@pytest.mark.unit
def test_a6_infinity_y_nan_salen_como_none_en_modo_fechas() -> None:
    filas = [
        {"dims": {"campo": "A"}, "fecha": date(2026, 8, 1), "valor": float("inf")},
        {"dims": {"campo": "A"}, "fecha": date(2026, 8, 2), "valor": float("nan")},
    ]
    tabla = _service({"filas_tabla": filas}).datos_tabla(1042, "H", 1)

    assert tabla.filas[0].valores == [None, None]


@pytest.mark.unit
def test_a6_infinity_sale_como_none_en_modo_matriz() -> None:
    filas = [
        {"dims": {"fila": "X", "columna": "C1"}, "fecha": None, "valor": float("-inf")},
    ]
    tabla = _service({"filas_tabla": filas}).datos_tabla(1042, "M", 1)

    assert tabla.filas[0].valores == [None]


@pytest.mark.unit
def test_a6_infinity_sale_como_none_en_kpi_produccion_dia() -> None:
    filas = [{"tipo_producto": "CRUDO", "vol_estimado": float("inf")}]
    kpis = _service({"produccion_dia": filas}).produccion_dia("2026-08-15")

    assert kpis[0].vol_estimado is None


# ── Reportes, cobertura y KPIs ───────────────────────────────────────────────


@pytest.mark.unit
def test_listar_reportes() -> None:
    reportes = _service().listar_reportes()

    assert reportes[0].reporte_id == 1042
    assert reportes[0].fecha_reporte == date(2026, 8, 15)
    assert reportes[0].tiene_raw is True


@pytest.mark.unit
def test_cobertura() -> None:
    cobertura = _service().cobertura()

    assert cobertura[0].ecp_mes == 7776  # ancla de paridad conocida
    assert cobertura[0].ecp_dia == 5209


@pytest.mark.unit
def test_produccion_dia() -> None:
    kpis = _service().produccion_dia("2026-08-15")

    assert [k.tipo_producto for k in kpis] == ["CRUDO", "GAS"]
    assert kpis[1].vol_estimado == 33453.2
