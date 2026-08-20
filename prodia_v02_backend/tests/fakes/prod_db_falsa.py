"""Doble de la sesión de `db_prod` (PostgreSQL) para los tests — hallazgo H1/H2 del plan F1.

**Por qué existe.** El CI (`.github/workflows/ci.yml`) NO levanta ningún PostgreSQL: corre
`uv run pytest` justo después de `uv sync`, sin `services:` ni `PROD_DATABASE_URL`. Y el
mecanismo de override que ya usa la suite para `db_auth` (monkeypatch de `SessionLocal`) no
sirve aquí: `db_prod` no expone un `SessionLocal` de módulo, construye el engine con
`get_prod_engine()` cacheado por `@lru_cache`. Sin este doble, cualquier test que ejercite
un endpoint de `tablas` intentaría conectar al servidor real (10.100.26.139) y fallaría en
CI — sin VPN y sin red.

**Por qué un doble y no un SQLite en memoria.** El SQL de `tablas` se porta idéntico del
sistema viejo y es específico de PostgreSQL: `dims` es JSONB (SQLite lo daría como texto),
y `hojas_de_reporte` usa `UNION ALL ... HAVING` con semántica que SQLite no reproduce igual.
Un "equivalente" en SQLite daría falsa confianza: verde en tests, roto contra el 139. Este
doble no pretende validar el SQL (eso lo hace la verificación humana contra Postgres real,
R3) sino la **lógica de pivote** y el **contrato HTTP**, que es donde están los bugs de
código.

Cada consulta se reconoce por una subcadena distintiva de su SQL. Si el SQL de
`repositories.py` cambia y deja de coincidir, el test falla ruidosamente con
`ConsultaNoReconocidaError` en vez de devolver datos silenciosamente equivocados.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.exc import OperationalError


class ConsultaNoReconocidaError(AssertionError):
    """El SQL no coincide con ninguna consulta conocida — el doble quedó desfasado."""


class _ResultadoFalso:
    """Imita lo que devuelve `Session.execute()` en los tres usos del repositorio:
    `.mappings().all()`, `.all()` y `.scalar()`."""

    def __init__(
        self,
        filas: list[dict[str, Any]] | None = None,
        tuplas: list[tuple[Any, ...]] | None = None,
        escalar: Any = None,
    ) -> None:
        self._filas = filas or []
        self._tuplas = tuplas or []
        self._escalar = escalar

    def mappings(self) -> _ResultadoFalso:
        return self

    def all(self) -> list[Any]:
        return self._tuplas if self._tuplas else self._filas

    def scalar(self) -> Any:
        return self._escalar


class SesionProdFalsa:
    """Sustituye a `sqlalchemy.orm.Session` en los tests de `tablas`.

    `datos` permite a cada test fijar qué devuelve cada consulta; lo que no se fija usa el
    corpus de ejemplo de abajo. Con `fallar=True` toda consulta lanza `OperationalError`,
    que es como se simula "PostgreSQL caído" para verificar el 503 (H9).
    """

    def __init__(
        self, datos: dict[str, Any] | None = None, fallar: bool = False
    ) -> None:
        self._datos = datos or {}
        self._fallar = fallar
        self.consultas: list[str] = []

    def _valor(self, clave: str, por_defecto: Any) -> Any:
        return self._datos.get(clave, por_defecto)

    def execute(
        self, clausula: Any, parametros: dict[str, Any] | None = None
    ) -> _ResultadoFalso:
        if self._fallar:
            raise OperationalError("SELECT 1", {}, Exception("conexión rechazada"))

        sql = str(clausula)
        self.consultas.append(sql)

        # ── tablas lógicas y comentarios ─────────────────────────────────────
        if "count(*) FROM core.fact_comentarios_produccion" in sql:
            return _ResultadoFalso(escalar=self._valor("contar_comentarios", 3))
        if "GROUP BY tabla_idx, tabla_label" in sql:
            return _ResultadoFalso(filas=self._valor("tablas_de_hoja", TABLAS_DE_HOJA))
        if "x.comentario_programa" in sql:
            return _ResultadoFalso(filas=self._valor("comentarios", COMENTARIOS))

        # ── contenido de una tabla ───────────────────────────────────────────
        if "SELECT dims, fecha, valor" in sql:
            return _ResultadoFalso(filas=self._valor("filas_tabla", FILAS_FECHAS))
        if "SELECT DISTINCT fecha" in sql:
            return _ResultadoFalso(
                tuplas=self._valor("fechas_distintas", FECHAS_DISTINTAS)
            )
        if "count(*) FROM core.fact_tabla_hoja" in sql:
            return _ResultadoFalso(escalar=self._valor("contar_filas_tabla", 0))

        # ── árbol y hojas ────────────────────────────────────────────────────
        if "UNION ALL" in sql:
            return _ResultadoFalso(
                filas=self._valor("hojas_de_reporte", HOJAS_DE_REPORTE)
            )
        if "archivo_nombre" in sql:
            return _ResultadoFalso(
                filas=self._valor("config_reportes", CONFIG_REPORTES)
            )

        # ── reportes, cobertura y KPIs ───────────────────────────────────────
        if "tiene_raw" in sql:
            return _ResultadoFalso(filas=self._valor("reportes", REPORTES))
        if "AS ecp_mes" in sql:
            return _ResultadoFalso(filas=self._valor("cobertura", COBERTURA))
        if "SUM(e.vol_estimado)" in sql:
            return _ResultadoFalso(filas=self._valor("produccion_dia", PRODUCCION_DIA))

        raise ConsultaNoReconocidaError(
            f"El doble de db_prod no reconoce este SQL:\n{sql}"
        )

    def close(self) -> None:  # la dependencia real la cierra en su `finally`
        return None


# ── Corpus de ejemplo ────────────────────────────────────────────────────────
# Refleja la forma real de los datos: `dims` es un dict (JSONB en Postgres) y
# `fecha` es None en las matrices, no una fila inválida.

CONFIG_REPORTES: list[dict[str, Any]] = [
    {
        "reporte_id": 1042,
        "fecha_reporte": date(2026, 8, 15),
        "tipo_archivo": "ECP",
        "archivo_nombre": "Reporte_2026-08-15.xlsm",
    },
    {
        "reporte_id": 1041,
        "fecha_reporte": date(2026, 8, 14),
        "tipo_archivo": "ECP",
        "archivo_nombre": "Reporte_2026-08-14.xlsm",
    },
    {
        "reporte_id": 990,
        "fecha_reporte": date(2025, 12, 31),
        "tipo_archivo": "FILIALES",
        "archivo_nombre": "Reporte_2025-12-31.xlsm",
    },
]

HOJAS_DE_REPORTE: list[dict[str, Any]] = [
    {"hoja": "COMENTARIOS", "tabla_idx": 1, "tabla_label": "COMENTARIOS", "filas": 3},
    {
        "hoja": "NEW MES-AÑO",
        "tabla_idx": 1,
        "tabla_label": "PRODUCCION MES",
        "filas": 240,
    },
    {"hoja": "NEW MES-AÑO", "tabla_idx": 2, "tabla_label": "METAS", "filas": 120},
]

TABLAS_DE_HOJA: list[dict[str, Any]] = [
    {"tabla_idx": 1, "tabla_label": "PRODUCCION MES", "filas": 240},
    {"tabla_idx": 2, "tabla_label": "METAS", "filas": 120},
]

# Modo `fechas`: dos combos de dimensiones × dos fechas.
FILAS_FECHAS: list[dict[str, Any]] = [
    {"dims": {"campo": "CASTILLA"}, "fecha": date(2026, 8, 1), "valor": 33453.2},
    {"dims": {"campo": "CASTILLA"}, "fecha": date(2026, 8, 2), "valor": 33500.0},
    {"dims": {"campo": "CHICHIMENE"}, "fecha": date(2026, 8, 1), "valor": 12000.5},
    {"dims": {"campo": "CHICHIMENE"}, "fecha": date(2026, 8, 2), "valor": None},
]

# Modo `matriz`: todas sin fecha; el orden de `columna` es significativo.
FILAS_MATRIZ: list[dict[str, Any]] = [
    {"dims": {"fila": "Crudo", "columna": "Real"}, "fecha": None, "valor": 100.0},
    {"dims": {"fila": "Crudo", "columna": "Meta"}, "fecha": None, "valor": 110.0},
    {"dims": {"fila": "Gas", "columna": "Real"}, "fecha": None, "valor": 50.0},
    {"dims": {"fila": "Gas", "columna": "Meta"}, "fecha": None, "valor": 55.0},
]

FECHAS_DISTINTAS: list[tuple[date]] = [(date(2026, 8, 1),), (date(2026, 8, 2),)]

COMENTARIOS: list[dict[str, Any]] = [
    {
        "producto": "CRUDO",
        "activos": "CASTILLA",
        "area": "ORIENTE",
        "comentario": "Sin novedad.",
        "comentario_programa": "Programa cumplido.",
        "comentario_extra": None,
    },
]

REPORTES: list[dict[str, Any]] = [
    {
        "reporte_id": 1042,
        "fecha_reporte": date(2026, 8, 15),
        "tipo_archivo": "ECP",
        "tiene_raw": True,
        "nivel_detalle": "COMPLETO",
    },
]

COBERTURA: list[dict[str, Any]] = [
    {
        "reporte_id": 1042,
        "tipo_archivo": "ECP",
        "ecp_mes": 7776,
        "ecp_dia": 5209,
        "filiales": 0,
    },
]

PRODUCCION_DIA: list[dict[str, Any]] = [
    {"tipo_producto": "CRUDO", "vol_estimado": 700000.0},
    {"tipo_producto": "GAS", "vol_estimado": 33453.2},
]
