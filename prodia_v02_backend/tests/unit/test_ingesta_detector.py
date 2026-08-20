"""Tests del detector NEW/STD y de los normalizadores de filiales.

La bifurcación NEW/STD decide si se cargan los facts de ECP o se saltan enteros, así que
un fallo aquí no da error: produce una ingesta a medias que parece correcta.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from src.features.ingesta.detector import HOJAS_RAW, nombres_de_hojas, tiene_raw
from src.features.ingesta.transforms import (
    BZ_DIA,
    BZ_MES,
    BZ_PRG,
    norm_emp,
    norm_prod,
    split_label,
)

# Réplica del `xl/workbook.xml` real: declara el namespace `r`, que los atributos
# `r:id` de cada hoja usan. Sin declararlo, el XML no es válido.
_WORKBOOK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>{hojas}</sheets>
</workbook>"""


def _crear_xlsm(ruta: Path, hojas: list[str]) -> Path:
    """Fabrica un .xlsm mínimo: solo el `xl/workbook.xml` que el detector lee."""
    etiquetas = "".join(
        f'<sheet name="{h}" sheetId="{i}" r:id="rId{i}"/>'
        for i, h in enumerate(hojas, 1)
    )
    with zipfile.ZipFile(ruta, "w") as archivo:
        archivo.writestr("xl/workbook.xml", _WORKBOOK_XML.format(hojas=etiquetas))
    return ruta


# ── tiene_raw ────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_reporte_new_trae_las_tres_hojas_crudas() -> None:
    assert (
        tiene_raw({"BDP_datos_dia", "BDP_datos_mes", "BDP_Programa", "INICIO"}) is True
    )


@pytest.mark.unit
def test_reporte_std_no_trae_las_hojas_crudas() -> None:
    assert tiene_raw({"INICIO", "PROGRAMA", "COMENTARIOS"}) is False


@pytest.mark.unit
def test_falta_una_sola_hoja_cruda_y_ya_no_es_new() -> None:
    """Son las TRES o ninguna: con dos, los facts de ECP quedarían incompletos."""
    assert tiene_raw({"BDP_datos_dia", "BDP_datos_mes"}) is False


# ── nombres_de_hojas ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_lee_los_nombres_de_hoja_del_zip(tmp_path: Path) -> None:
    ruta = _crear_xlsm(tmp_path / "r.xlsm", ["INICIO", "NEW MES-AÑO", "COMENTARIOS"])

    assert nombres_de_hojas(ruta) == {"INICIO", "NEW MES-AÑO", "COMENTARIOS"}


@pytest.mark.unit
def test_detecta_un_reporte_new_desde_el_archivo(tmp_path: Path) -> None:
    ruta = _crear_xlsm(tmp_path / "new.xlsm", [*HOJAS_RAW, "INICIO"])

    assert tiene_raw(nombres_de_hojas(ruta)) is True


@pytest.mark.unit
def test_archivo_corrupto_devuelve_set_vacio_sin_reventar(tmp_path: Path) -> None:
    """El listado de archivos disponibles no debe caerse por un archivo corrupto."""
    corrupto = tmp_path / "corrupto.xlsm"
    corrupto.write_bytes(b"esto no es un zip")

    assert nombres_de_hojas(corrupto) == set()


@pytest.mark.unit
def test_archivo_inexistente_devuelve_set_vacio(tmp_path: Path) -> None:
    assert nombres_de_hojas(tmp_path / "no-existe.xlsm") == set()


@pytest.mark.unit
def test_zip_valido_sin_workbook_devuelve_set_vacio(tmp_path: Path) -> None:
    ruta = tmp_path / "sin_workbook.xlsm"
    with zipfile.ZipFile(ruta, "w") as archivo:
        archivo.writestr("otra/cosa.xml", "<x/>")

    assert nombres_de_hojas(ruta) == set()


# ── Columnas bronze ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_las_columnas_bronze_conservan_su_numero_exacto() -> None:
    """El loader construye el INSERT desde estas listas: si cambia el número o el
    orden, los datos se desplazan de columna SIN error."""
    assert len(BZ_DIA) == 30
    assert len(BZ_MES) == 59
    assert len(BZ_PRG) == 14


@pytest.mark.unit
@pytest.mark.parametrize("columnas", [BZ_DIA, BZ_MES, BZ_PRG])
def test_las_columnas_bronze_no_tienen_duplicados(columnas: list[str]) -> None:
    assert len(columnas) == len(set(columnas))


@pytest.mark.unit
def test_el_orden_de_las_primeras_columnas_es_el_pactado() -> None:
    assert BZ_DIA[:3] == ["concepto", "socio", "operador"]
    assert BZ_MES[:3] == ["concepto", "socio", "ba_id"]
    assert BZ_PRG[:3] == ["fecha", "vice", "gerencia"]


# ── Normalizadores ───────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("variante", ["EAI", "EA", "AMERICA", "  america  "])
def test_las_variantes_de_la_misma_filial_se_unifican(variante: str) -> None:
    """Sin esto, la misma empresa entraría como tres filas distintas en las dimensiones."""
    assert norm_emp(variante) == "America"


@pytest.mark.unit
def test_una_empresa_desconocida_se_conserva_sin_espacios() -> None:
    assert norm_emp("  Nueva Filial  ") == "Nueva Filial"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("entrada", "esperado"), [("BLANCO", "BLANCOS"), ("crudo", "CRUDO")]
)
def test_normaliza_productos_conocidos(entrada: str, esperado: str) -> None:
    assert norm_prod(entrada) == esperado


@pytest.mark.unit
def test_un_producto_desconocido_se_descarta() -> None:
    """A diferencia de la empresa: el producto decide la escala de la cifra (A5), y
    admitir uno arbitrario propagaría un error de unidades."""
    assert norm_prod("PLASMA") is None


@pytest.mark.unit
def test_separa_etiqueta_y_producto() -> None:
    assert split_label("Hocol (crudo)") == ("Hocol", "crudo")


@pytest.mark.unit
def test_una_etiqueta_sin_parentesis_no_encaja() -> None:
    assert split_label("Hocol") == (None, None)


@pytest.mark.unit
def test_normalizadores_toleran_none() -> None:
    assert norm_emp(None) is None
    assert norm_prod(None) is None
