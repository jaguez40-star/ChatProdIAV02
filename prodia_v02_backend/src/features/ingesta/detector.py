"""Detección NEW vs STD de un `.xlsm` — portado del sistema viejo.

Un reporte es **NEW** si trae las tres hojas crudas (`BDP_*`), y **STD** si no. No es un
error: es una bifurcación del ETL. NEW ⇒ `nivel_detalle='FULL'` y se cargan los facts de
ECP; STD ⇒ `'SIN_ECP'` y esos loaders se saltan enteros.

`nombres_de_hojas` lee **solo** `xl/workbook.xml` del zip, sin abrir el libro con openpyxl:
un `.xlsm` NEW pesa ~125 MB y cargarlo entero para saber qué hojas tiene costaría segundos
por archivo (el listado de disponibles los abre todos). Así es instantáneo.

Devolver un `set` vacío cuando el archivo no es un OOXML válido es deliberado: el listado
de archivos disponibles no debe reventar por un archivo corrupto. Quien necesite
distinguir "corrupto" de "sin hojas" debe comprobarlo aparte — la validación de subida (F3)
sí lo hace.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

# Las tres hojas crudas que definen un reporte NEW.
HOJAS_RAW: frozenset[str] = frozenset(
    {"BDP_datos_dia", "BDP_datos_mes", "BDP_Programa"}
)

_NS_PRINCIPAL = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def tiene_raw(nombres_hojas: set[str] | frozenset[str]) -> bool:
    """True si el libro trae las tres hojas crudas (reporte NEW)."""
    return HOJAS_RAW.issubset(nombres_hojas)


def nombres_de_hojas(ruta: Path | str) -> set[str]:
    """Nombres de hoja leyendo solo `xl/workbook.xml`. Set vacío si no es un OOXML válido."""
    try:
        with zipfile.ZipFile(ruta) as archivo_zip:
            xml = archivo_zip.read("xl/workbook.xml")
    except (zipfile.BadZipFile, KeyError, OSError):
        return set()
    raiz = ET.fromstring(xml)
    return {
        nombre
        for hoja in raiz.iter(f"{{{_NS_PRINCIPAL}}}sheet")
        if (nombre := hoja.get("name"))
    }
