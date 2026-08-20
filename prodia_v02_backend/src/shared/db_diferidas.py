"""Acceso a `ECP_DIFERIDAS.db` — histórico de producción diferida (SQLite).

Quinta fuente de datos del sistema. No usa SQLAlchemy sino `sqlite3` directo,
igual que el origen (`routes/api.py:609`): son dos consultas de agregación
sobre una tabla de 1,14 M de filas, sin ORM ni sesiones de por medio.

⚠️ **La BD tiene daño parcial, y hay que conocerlo para no tropezar.**
Verificado el 2026-08-20 sobre el fichero que el sistema viejo usa en
producción:

| Objeto                            | Estado    | ¿Se consulta? |
|-----------------------------------|-----------|---------------|
| `AVM_DATADIF` (datos)             | ✅ sana — 1.142.599 filas, 2023-2025 | Sí |
| `AVM_DATADIF_BACK` (respaldo)     | 🔴 corrupta (rootpage 1389)          | No |
| Índices `ix_dd_event`/`ix_dd_cover` | 🔴 corruptos                       | No |

Consecuencias prácticas:

1. **`PRAGMA quick_check` falla** y no significa que los datos estén mal: falla
   por `AVM_DATADIF_BACK`, una tabla de respaldo que nadie consulta.
2. **NUNCA hacer `SELECT count(*) FROM AVM_DATADIF` a secas.** SQLite lo
   optimiza con `SCAN USING COVERING INDEX ix_dd_event` (confirmado con
   `EXPLAIN QUERY PLAN`) y revienta con *"database disk image is malformed"*.
   Si alguna vez hace falta contar, usar `NOT INDEXED`. Las consultas reales
   filtran por `UPPER(TRIM(CAMPO))`, que no puede usar esos índices y fuerza
   escaneo de tabla: por eso funcionan.
3. **Solo lectura, siempre** (`mode=ro`). Con índices dañados, una escritura o
   un `VACUUM` accidental podrían propagar el daño a los datos sanos.

Cero I/O en tiempo de import (AP-2): abrir la conexión es responsabilidad de
`abrir_conexion()`, nunca del módulo.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from src.core.config import get_settings


def ruta_diferidas() -> Path | None:
    """Ruta configurada, o `None` si no está definida o el fichero no existe.

    `None` es un estado normal: la feature degrada con `sin_datos` + motivo y
    HTTP 200. El fichero pesa 954 MB, vive fuera del repo y puede faltar en
    desarrollo o en una máquina recién clonada.
    """
    configurada = get_settings().diferidas_db_path.strip()
    if not configurada:
        return None
    ruta = Path(configurada)
    if not ruta.is_absolute():
        # Relativa al directorio del backend, no al CWD: el proceso puede
        # arrancar desde la raíz del monorepo o desde `prodia_v02_backend/`.
        ruta = Path(__file__).resolve().parent.parent.parent / configurada
    return ruta if ruta.exists() else None


@contextmanager
def abrir_conexion(ruta: Path) -> Generator[sqlite3.Connection, None, None]:
    """Conexión SOLO LECTURA a la BD de diferidas.

    `mode=ro` no es una preferencia: es lo que impide que un error de código
    escriba sobre un fichero con índices dañados.
    """
    conexion = sqlite3.connect(f"file:{ruta.as_posix()}?mode=ro", uri=True)
    try:
        # La BD guarda UTF-8 pero arrastra filas con bytes inválidos (nombres de
        # causa con tildes mal codificadas). Sin esto, `sqlite3` lanza
        # UnicodeDecodeError a mitad del recorrido y tumba la petición entera
        # por un puñado de filas mal escritas.
        conexion.text_factory = lambda b: b.decode("utf-8", "replace")
        yield conexion
    finally:
        conexion.close()
