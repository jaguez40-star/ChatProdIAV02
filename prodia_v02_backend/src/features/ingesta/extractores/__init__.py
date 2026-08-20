"""Registro de los 17 extractores y su despachador.

**El orden importa y el emparejamiento es por PREFIJO, no por nombre exacto.** Excel
trunca los nombres de hoja a 31 caracteres, y algunos los rozan: 'P50 Quemado 2024 ECP y
Filiales' mide exactamente 31. Por eso los patrones anclan al inicio (`^`) y no exigen el
final, salvo donde el nombre completo es corto y sí puede fijarse (`^INICIO$`,
`^DATOS_MES$`) — ahí el anclaje estricto evita capturar una hoja parecida.

El recorrido es **sobre el registro**, no sobre las hojas del libro: para cada patrón se
busca la primera hoja que encaje. Así el orden de las tablas resultantes es estable entre
archivos, aunque Excel reordene las pestañas.
"""

from __future__ import annotations

import re

from openpyxl.worksheet.worksheet import Worksheet

from src.features.ingesta.extractores.comunes import (
    Extractor,
    FilaExtraida,
    Grid,
    ResultadoExtractor,
)
from src.features.ingesta.extractores.filiales import (
    extraer_inicio,
    extraer_pop_filiales,
    extraer_produccion_filiales,
)
from src.features.ingesta.extractores.mesano import extraer_mesano
from src.features.ingesta.extractores.p50 import (
    extraer_p50_acumulado,
    extraer_p50_quemado,
)
from src.features.ingesta.extractores.raw import (
    extraer_bdp_datos_dia,
    extraer_bdp_datos_mes,
    extraer_bdp_programa,
    extraer_datos_mes,
    extraer_td_datos_dia,
)
from src.features.ingesta.extractores.reportes import (
    extraer_bitacora,
    extraer_calculo_trimestre,
    extraer_dpp,
    extraer_programa,
    extraer_reporte_president,
    extraer_whatsapp,
)

# (patrón de nombre de hoja, extractor). Todos los patrones son insensibles a
# mayúsculas y toleran las variantes de acentuación que aparecen entre archivos.
HOJAS_MODELADAS: list[tuple[re.Pattern[str], Extractor]] = [
    (re.compile(r"(?i)^P50 Quemado \d{4} ECP y Fili"), extraer_p50_quemado),
    (re.compile(r"(?i)^Producci[oó]n filiales"), extraer_produccion_filiales),
    (re.compile(r"(?i)^\(?\s*bit[aá]cora"), extraer_bitacora),
    (re.compile(r"(?i)^P50 Acumulado"), extraer_p50_acumulado),
    (re.compile(r"(?i)^REPORTE_PRESIDENT$"), extraer_reporte_president),
    (re.compile(r"(?i)^PROGRAMA$"), extraer_programa),
    (re.compile(r"(?i)^Reporte\s+Whatsapp"), extraer_whatsapp),
    (re.compile(r"(?i)^NEW MES-?A[ÑN]O"), extraer_mesano),
    (re.compile(r"(?i)^Reporte\s+DPP"), extraer_dpp),
    (re.compile(r"(?i)^POP Filiales y Explora"), extraer_pop_filiales),
    (re.compile(r"(?i)^C[AÁ]LCULO DE TRIMESTRE"), extraer_calculo_trimestre),
    (re.compile(r"(?i)^INICIO$"), extraer_inicio),
    (re.compile(r"(?i)^TD_datos_dia$"), extraer_td_datos_dia),
    (re.compile(r"(?i)^DATOS_MES$"), extraer_datos_mes),
    (re.compile(r"(?i)^BDP_datos_dia$"), extraer_bdp_datos_dia),
    (re.compile(r"(?i)^BDP_datos_mes$"), extraer_bdp_datos_mes),
    (re.compile(r"(?i)^BDP_Programa$"), extraer_bdp_programa),
]


def buscar_hoja(nombres_de_hoja: list[str], patron: re.Pattern[str]) -> str | None:
    """Primera hoja del libro que encaja con el patrón, o `None`."""
    return next((nombre for nombre in nombres_de_hoja if patron.match(nombre)), None)


def extractores_aplicables(
    nombres_de_hoja: list[str],
) -> list[tuple[str, Extractor]]:
    """Pares (hoja, extractor) que el libro puede alimentar, en el orden del registro.

    Las hojas que el libro no trae simplemente no aparecen: un reporte STD no tiene las
    hojas `BDP_*` y eso no es un error, es su naturaleza.
    """
    aplicables: list[tuple[str, Extractor]] = []
    for patron, extractor in HOJAS_MODELADAS:
        hoja = buscar_hoja(nombres_de_hoja, patron)
        if hoja is not None:
            aplicables.append((hoja, extractor))
    return aplicables


__all__ = [
    "HOJAS_MODELADAS",
    "Extractor",
    "FilaExtraida",
    "Grid",
    "ResultadoExtractor",
    "Worksheet",
    "buscar_hoja",
    "extractores_aplicables",
]
