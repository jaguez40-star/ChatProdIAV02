"""SQL de diferidas históricas — SQLite `ECP_DIFERIDAS`.

Portado de `routes/api.py:597-612`.

⚠️ **NUNCA usar `SELECT count(*)` a secas sobre `AVM_DATADIF`.** Los índices
`ix_dd_event`/`ix_dd_cover` de esa BD están dañados, y SQLite resuelve el
conteo con un `SCAN USING COVERING INDEX` que revienta con *"database disk
image is malformed"*. Las consultas de abajo filtran o agrupan por columnas de
texto, lo que fuerza escaneo de tabla y funciona; el conteo de incidentes se
hace en Python tras el `GROUP BY`, igual que en el origen.

Detalle completo del daño en `src/shared/db_diferidas.py`.
"""

from __future__ import annotations

import sqlite3
from typing import Any

# Una pasada por consulta, no cinco. El origen hacía 5 escaneos de una tabla de
# 1,14 M de filas (~3,5 s); agrupando en Python baja a ~0,7 s. La caché de
# arriba deja las reaperturas casi instantáneas.


class DiferidasRepository:
    """Consultas sobre `AVM_DATADIF`. Recibe la conexión, no la abre."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._conexion = conexion

    def _where(self, campos: list[str]) -> tuple[str, list[Any]]:
        """Filtro por CAMPO o AREA. Sin campos, alcance global."""
        if not campos:
            return "1=1", []
        marcadores = ",".join("?" * len(campos))
        clausula = (
            f"(UPPER(TRIM(CAMPO)) IN ({marcadores}) "
            f"OR UPPER(TRIM(AREA)) IN ({marcadores}))"
        )
        return clausula, campos + campos

    def incidentes(self, campos: list[str]) -> list[tuple[Any, ...]]:
        """Un INCIDENTE por (pozo, inicio, fin, causa), no una fila por día.

        El grano de la tabla es día-pozo: sin colapsar, un evento de 30 días
        contaría 30 veces y el Pareto mediría duración, no frecuencia.

        El año sale de `MIN(EVENT_DATE)` porque `INI_DATE`/`END_DATE` tienen
        formato mixto y no son fiables para agrupar.
        """
        clausula, params = self._where(campos)
        return self._conexion.execute(
            "SELECT COMPLETION, CAUSE_NIVEL4, CAUSE_NIVEL2, "
            "MIN(substr(EVENT_DATE,1,4)) AS anio "
            f"FROM AVM_DATADIF WHERE {clausula} "
            "GROUP BY COMPLETION, INI_DATE, END_DATE, CAUSE_NIVEL4, CAUSE_NIVEL2",
            params,
        ).fetchall()

    def volumen_perdido(self, campos: list[str]) -> list[tuple[Any, ...]]:
        """Volumen perdido por causa — se SUMA sobre TODAS las filas-día.

        Al revés que los incidentes: `ACEITE_PERDIDO`/`GAS_PERDIDO` son valores
        diarios, así que aquí NO se deduplica.
        """
        clausula, params = self._where(campos)
        return self._conexion.execute(
            "SELECT CAUSE_NIVEL4, SUM(COALESCE(ACEITE_PERDIDO,0)) AS aceite, "
            "SUM(COALESCE(GAS_PERDIDO,0)) AS gas "
            f"FROM AVM_DATADIF WHERE {clausula} GROUP BY CAUSE_NIVEL4",
            params,
        ).fetchall()
