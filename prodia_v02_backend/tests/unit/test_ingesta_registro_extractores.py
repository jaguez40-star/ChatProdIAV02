"""Tests del registro de extractores y de las familias `mesano` y `raw`.

El registro es la pieza que decide qué extractor procesa cada hoja. Si un patrón deja de
encajar, esa hoja simplemente no se ingiere — sin error, sin aviso. Por eso se verifica
contra los nombres de hoja REALES del reporte NEW, no contra nombres inventados.
"""

from __future__ import annotations

import datetime as dt

import pytest

from src.features.ingesta.extractores import (
    HOJAS_MODELADAS,
    buscar_hoja,
    extractores_aplicables,
)
from src.features.ingesta.extractores.mesano import extraer_mesano
from src.features.ingesta.extractores.raw import (
    extraer_bdp_datos_dia,
    extraer_bdp_datos_mes,
    extraer_bdp_programa,
    extraer_datos_mes,
    extraer_td_datos_dia,
)
from tests.fakes.hoja_sintetica import hoja_desde_celdas, hoja_desde_filas

ENE = dt.date(2026, 1, 1)

# Nombres de hoja tal cual aparecen en el reporte NEW real.
HOJAS_REALES_NEW = [
    "(Bitacora)", "BDP_Programa", "BDP_datos_dia", "BDP_datos_mes",
    "Balance de blancos VPI", "CALCULO DE TRIMESTRE", "COMENTARIOS",
    "Comparativo_Dia", "DATOS_MES", "INICIO", "NEW MES-AÑO", "Nuevo Whatsapp",
    "Operativa", "P50 Acumulado", "P50 Quemado 2024 ECP y Filiales",
    "POP Filiales y Exploración", "PROGRAMA", "Producción filiales",
    "REPORTE DE PRODUCCIÓN", "REPORTE_PRESIDENT", "Reporte DPP",
    "Reporte Whatsapp", "TD_datos_dia", "Variables",
]  # fmt: skip


# ── El registro ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_el_registro_tiene_los_diecisiete_extractores() -> None:
    assert len(HOJAS_MODELADAS) == 17


@pytest.mark.unit
def test_todas_las_hojas_del_reporte_new_encuentran_su_extractor() -> None:
    """Las 17 hojas modeladas deben encajar con los nombres reales del archivo."""
    aplicables = extractores_aplicables(HOJAS_REALES_NEW)

    assert len(aplicables) == 17
    assert len({hoja for hoja, _ in aplicables}) == 17  # ninguna hoja repetida


@pytest.mark.unit
def test_el_nombre_truncado_a_31_caracteres_sigue_encajando() -> None:
    """Excel trunca los nombres de hoja a 31 caracteres y este los roza exactamente:
    por eso los patrones anclan al inicio y no exigen el final."""
    nombre = "P50 Quemado 2024 ECP y Filiales"
    assert len(nombre) == 31

    patron = HOJAS_MODELADAS[0][0]
    assert patron.match(nombre) is not None


@pytest.mark.unit
def test_un_reporte_std_solo_usa_los_extractores_de_sus_hojas() -> None:
    """Un STD no trae las hojas BDP_*; que falten no es un error, es su naturaleza."""
    hojas_std = [h for h in HOJAS_REALES_NEW if not h.startswith("BDP_")]

    aplicables = extractores_aplicables(hojas_std)

    assert len(aplicables) == 14


@pytest.mark.unit
def test_nuevo_whatsapp_no_se_confunde_con_reporte_whatsapp() -> None:
    """El archivo trae ambas hojas; solo 'Reporte Whatsapp' está modelada, y el anclaje
    al inicio es lo que evita capturar la otra."""
    patron = next(p for p, _ in HOJAS_MODELADAS if p.match("Reporte Whatsapp"))

    assert patron.match("Nuevo Whatsapp") is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("hoja", "debe_encajar"),
    [("INICIO", True), ("INICIOS", False), ("DATOS_MES", True), ("DATOS_MESES", False)],
)
def test_los_nombres_cortos_se_anclan_de_forma_estricta(
    hoja: str, debe_encajar: bool
) -> None:
    """Donde el nombre completo es corto y estable, el patrón fija también el final para
    no capturar una hoja parecida."""
    encontrada = extractores_aplicables([hoja])

    assert bool(encontrada) is debe_encajar


@pytest.mark.unit
def test_buscar_hoja_devuelve_none_si_no_hay_coincidencia() -> None:
    patron = HOJAS_MODELADAS[0][0]

    assert buscar_hoja(["Otra cosa"], patron) is None


# ── NEW MES-AÑO ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_mesano_declara_sus_trece_tablas() -> None:
    resultado = extraer_mesano(hoja_desde_celdas({(1, 1): "vacía"}))  # type: ignore[arg-type]

    assert [t[0] for t in resultado.tablas_declaradas] == list(range(1, 14))


@pytest.mark.unit
def test_mesano_extrae_del_bloque_a_o() -> None:
    hoja = hoja_desde_celdas(
        {(13, 3): ENE, (14, 1): "CRUDO", (14, 2): "VRO", (14, 3): 100.0}
    )

    resultado = extraer_mesano(hoja)  # type: ignore[arg-type]

    filas = [f for f in resultado.filas if f.tabla_idx == 2]
    assert len(filas) == 1
    assert filas[0].dims == {"producto": "CRUDO", "vice": "VRO"}
    assert filas[0].fecha == ENE


@pytest.mark.unit
def test_mesano_extrae_del_bloque_s_ah() -> None:
    """El segundo bloque vive en otras columnas pero comparte estructura."""
    hoja = hoja_desde_celdas(
        {(8, 22): ENE, (9, 20): "CRUDO", (9, 21): "VRO", (9, 22): 200.0}
    )

    resultado = extraer_mesano(hoja)  # type: ignore[arg-type]

    filas = [f for f in resultado.filas if f.tabla_idx == 8]
    assert len(filas) == 1
    assert filas[0].valor == 200.0


@pytest.mark.unit
def test_mesano_solo_acepta_entidades_conocidas_en_las_tablas_de_exploracion() -> None:
    hoja = hoja_desde_celdas(
        {
            (99, 3): ENE,
            (99, 1): "algo", (99, 2): "VEX", (99, 3 + 0): 10.0,
            (100, 1): "ruido", (100, 2): "XXX",
        }
    )  # fmt: skip

    resultado = extraer_mesano(hoja)  # type: ignore[arg-type]

    filas = [f for f in resultado.filas if f.tabla_idx == 6]
    assert all(f.dims["entidad"] in {"VEX", "GRUPO EMPRESARIAL"} for f in filas)


# ── TD_datos_dia y DATOS_MES (tablas dinámicas) ──────────────────────────────


@pytest.mark.unit
def test_td_datos_dia_necesita_las_tres_filas_de_cabecera() -> None:
    hoja = hoja_desde_celdas(
        {
            (19, 6): ENE, (20, 6): "Suma de VOLDISMEZ", (21, 6): "ECOPETROL",
            (22, 1): "CRUDO", (22, 2): "VRO", (22, 6): 50.0,
        }
    )  # fmt: skip

    resultado = extraer_td_datos_dia(hoja)  # type: ignore[arg-type]

    assert len(resultado.filas) == 1
    fila = resultado.filas[0]
    assert fila.dims["medida"] == "VOLDISMEZ"
    assert fila.dims["grupoprod"] == "ECOPETROL"
    assert fila.fecha == ENE


@pytest.mark.unit
def test_td_datos_dia_preserva_en_blanco_como_categoria() -> None:
    """'(en blanco)' es un valor real del negocio: convertirlo en None fusionaría
    filas que la fuente distingue."""
    hoja = hoja_desde_celdas(
        {
            (19, 6): ENE, (20, 6): "Suma de PROMEDIO", (21, 6): "SOCIOS",
            (22, 1): "CRUDO", (22, 2): "(en blanco)", (22, 6): 5.0,
        }
    )  # fmt: skip

    resultado = extraer_td_datos_dia(hoja)  # type: ignore[arg-type]

    assert resultado.filas[0].dims["vice"] == "(en blanco)"


@pytest.mark.unit
def test_td_datos_dia_descarta_los_subtotales() -> None:
    hoja = hoja_desde_celdas(
        {
            (19, 6): ENE, (20, 6): "Suma de VOLUMEN", (21, 6): "ECOPETROL",
            (22, 1): "CRUDO", (22, 6): 10.0,
            (23, 1): "Total CRUDO", (23, 6): 999.0,
        }
    )  # fmt: skip

    resultado = extraer_td_datos_dia(hoja)  # type: ignore[arg-type]

    assert [f.valor for f in resultado.filas] == [10.0]


@pytest.mark.unit
def test_td_datos_dia_sin_columnas_de_detalle_no_extrae_nada() -> None:
    resultado = extraer_td_datos_dia(hoja_desde_celdas({(1, 1): "x"}))  # type: ignore[arg-type]

    assert resultado.filas == []
    assert len(resultado.tablas_declaradas) == 1


@pytest.mark.unit
def test_datos_mes_localiza_su_cabecera_por_contenido() -> None:
    """La fila de cabecera cambia entre NEW y STD: se busca 'ESCENARIO' en la columna A."""
    hoja = hoja_desde_celdas(
        {
            (5, 1): "ESCENARIO", (5, 7): ENE,
            (6, 1): "REAL", (6, 2): "CRUDO", (6, 7): 33.0,
        }
    )  # fmt: skip

    resultado = extraer_datos_mes(hoja)  # type: ignore[arg-type]

    assert len(resultado.filas) == 1
    assert resultado.filas[0].dims == {"escenario": "REAL", "producto": "CRUDO"}


@pytest.mark.unit
def test_datos_mes_rellena_los_niveles_padre_hacia_abajo() -> None:
    hoja = hoja_desde_celdas(
        {
            (5, 1): "ESCENARIO", (5, 7): ENE,
            (6, 1): "REAL", (6, 2): "CRUDO", (6, 7): 10.0,
            (7, 3): "VRO", (7, 7): 20.0,
        }
    )  # fmt: skip

    resultado = extraer_datos_mes(hoja)  # type: ignore[arg-type]

    segunda = resultado.filas[1]
    assert segunda.dims["escenario"] == "REAL"  # heredado
    assert segunda.dims["vice"] == "VRO"


@pytest.mark.unit
def test_datos_mes_sin_cabecera_no_extrae_nada() -> None:
    resultado = extraer_datos_mes(hoja_desde_celdas({(1, 1): "otra cosa"}))  # type: ignore[arg-type]

    assert resultado.filas == []


# ── Hojas planas BDP_* ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_bdp_datos_dia_despliega_una_fila_por_medida() -> None:
    hoja = hoja_desde_filas(
        [
            ["FECHA", "CAMPO", "VOLUMEN", "PROMEDIO"],
            [20260101, "CASTILLA", 10.0, 20.0],
        ]
    )

    resultado = extraer_bdp_datos_dia(hoja)  # type: ignore[arg-type]

    assert len(resultado.filas) == 2  # una por medida con valor
    assert {str(f.dims["medida"]) for f in resultado.filas} == {"VOLUMEN", "PROMEDIO"}
    assert all(f.dims["campo"] == "CASTILLA" for f in resultado.filas)


@pytest.mark.unit
def test_bdp_datos_dia_conserva_los_ceros_reales() -> None:
    """Un 0 es un dato, no una ausencia: descartarlo falsearía el promedio."""
    hoja = hoja_desde_filas([["FECHA", "VOLUMEN"], [20260101, 0.0]])

    resultado = extraer_bdp_datos_dia(hoja)  # type: ignore[arg-type]

    assert [f.valor for f in resultado.filas] == [0.0]


@pytest.mark.unit
def test_bdp_datos_dia_es_robusto_al_reordenamiento_de_columnas() -> None:
    """Las columnas se localizan por nombre, no por posición."""
    hoja = hoja_desde_filas([["VOLUMEN", "CAMPO", "FECHA"], [10.0, "APIAY", 20260101]])

    resultado = extraer_bdp_datos_dia(hoja)  # type: ignore[arg-type]

    assert len(resultado.filas) == 1
    assert resultado.filas[0].dims["campo"] == "APIAY"


@pytest.mark.unit
def test_bdp_datos_mes_emite_una_sola_fila_por_registro() -> None:
    """No se despliegan las 10 medidas: serían más de 3 millones de filas."""
    hoja = hoja_desde_filas(
        [
            ["FECHA", "CAMPO", "BPDEQ_M", "VOLUMEN", "BLSEQ"],
            [20260101, "CASTILLA", 100.0, 50.0, 70.0],
        ]
    )

    resultado = extraer_bdp_datos_mes(hoja)  # type: ignore[arg-type]

    assert len(resultado.filas) == 1
    assert resultado.filas[0].valor == 100.0  # BPDEQ_M
    assert "volumen" not in resultado.filas[0].dims  # las otras medidas no son dims


@pytest.mark.unit
def test_bdp_datos_mes_normaliza_las_fechas_descriptivas_a_iso() -> None:
    """Sin normalizar, dos representaciones del mismo día darían dims distintas."""
    hoja = hoja_desde_filas(
        [["FECHA", "FECHAEFPROP", "BPDEQ_M"], [20260101, dt.date(2025, 6, 15), 1.0]]
    )

    resultado = extraer_bdp_datos_mes(hoja)  # type: ignore[arg-type]

    assert resultado.filas[0].dims["fechaefprop"] == "2025-06-15"


@pytest.mark.unit
def test_bdp_programa_conserva_todas_las_columnas_como_dims() -> None:
    """Decisión del usuario: no se pierde ninguna de las 14 columnas del origen."""
    hoja = hoja_desde_filas(
        [
            ["Fecha", "Volumen", "Fecha Version", "Produccion_total", "Part_ECP"],
            [20260101, 10.0, 20251201, 999.0, 0.5],
        ]
    )

    resultado = extraer_bdp_programa(hoja)  # type: ignore[arg-type]

    dims = resultado.filas[0].dims
    assert resultado.filas[0].valor == 10.0  # Volumen
    # Las dims son texto: un numérico se guarda tal como lo estringa Python ('999.0'),
    # igual que en el origen. Lo que importa aquí es que la columna NO se pierda.
    assert dims["produccion_total"] == "999.0"
    assert "part_ecp" in dims
    assert "fecha_version" in dims  # el espacio del encabezado pasa a guion bajo


@pytest.mark.unit
def test_bdp_programa_descarta_el_ruido_de_excel_en_las_dims() -> None:
    hoja = hoja_desde_filas([["Fecha", "Volumen", "Campo"], [20260101, 10.0, "#REF!"]])

    resultado = extraer_bdp_programa(hoja)  # type: ignore[arg-type]

    assert "campo" not in resultado.filas[0].dims


@pytest.mark.unit
@pytest.mark.parametrize(
    "extractor",
    [extraer_bdp_datos_dia, extraer_bdp_datos_mes, extraer_bdp_programa],
)
def test_las_hojas_planas_sin_cabecera_util_no_extraen_nada(extractor: object) -> None:
    hoja = hoja_desde_filas([["OTRA", "COSA"], [1, 2]])

    resultado = extractor(hoja)  # type: ignore[operator]

    assert resultado.filas == []
    assert len(resultado.tablas_declaradas) == 1
