"""Acceso compartido a los `.xlsm` de muestra para los tests de extractores.

**Por qué está centralizado.** El reporte NEW pesa 125 MB. Cuando cada módulo de test
abría el suyo con un fixture de alcance `module`, dos libros vivos a la vez tumbaban el
proceso con un *access violation* de Windows dentro de openpyxl. Con un único fixture de
alcance `session` el libro se carga una sola vez para toda la suite.

Estos archivos viven FUERA del repo (en el sistema viejo), así que los tests que dependen
de ellos llevan el marcador `muestras` y quedan excluidos del run por defecto — CI no los
tiene. Cuando faltan, los tests se **saltan con motivo visible**; nunca se dan por buenos.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

DIRECTORIO_MUESTRAS = Path(
    r"C:\APLICACIONES\ProdIA\12112025_prodIA\12112025_prodIA\INGESTA\Rep_Prod\Doc_Desing"
)


def hay_muestras() -> bool:
    return DIRECTORIO_MUESTRAS.exists() and any(DIRECTORIO_MUESTRAS.glob("*.xlsm"))


def hoja_de(libro: Any, prefijo: str) -> Any:
    """La primera hoja cuyo nombre empieza por `prefijo`; salta el test si no está.

    Se busca por prefijo, no por nombre exacto, por la misma razón que el registro de
    extractores: Excel trunca los nombres de hoja a 31 caracteres.
    """
    nombre = next(
        (h for h in libro.sheetnames if h.upper().startswith(prefijo.upper())), None
    )
    if nombre is None:
        pytest.skip(f"el archivo de muestra no trae la hoja '{prefijo}'")
    return libro[nombre]
