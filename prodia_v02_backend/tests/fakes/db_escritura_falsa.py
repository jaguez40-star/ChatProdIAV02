"""Doble de sesión PostgreSQL para el ETL de Ingesta (F3) — hallazgo V2 del plan.

**Por qué existe uno nuevo en vez de extender `prod_db_falsa.py`.** Aquel doble reconoce
consultas por subcadenas de `SELECT` y lanza `ConsultaNoReconocidaError` ante cualquier
otra cosa; lo usan `tablas` (F1) y `analisis` (F2), que solo leen. F3 **escribe**, así que
todos sus tests caerían en ese error. Tocar el doble de lectura para acomodar escrituras
arriesgaba romper dos features que ya funcionan, por eso este es un archivo aparte.

**Qué hace distinto.** No pretende devolver datos: pretende **registrar lo que el ETL
escribió** para poder afirmarlo en los tests. Cada `execute` guarda la sentencia y sus
parámetros, y expone consultas cómodas (`inserciones_en`, `borrados_en`, `filas_escritas_en`).

**La red de seguridad principal**: cualquier `DELETE` sin `WHERE reporte_id` aborta el test
en el acto con `BorradoSinAcotarError`. En el origen, la idempotencia se apoya en
`DELETE WHERE reporte_id=:r` antes de reinsertar; un `WHERE` que se pierda en un refactor
no rompería ningún test convencional —seguiría "funcionando"— pero **borraría la tabla
entera** en producción. Aquí es imposible que pase inadvertido.

También simula el ciclo transaccional (`begin`/`commit`/`rollback`) para poder verificar
que un fallo a mitad del ETL revierte y que el evento final dice `revertido` (G2), y el
`pg_advisory_xact_lock` (G4).
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.exc import OperationalError

# Un DELETE del ETL SIEMPRE se acota por reporte_id (y a veces también por hoja).
_DELETE = re.compile(
    r"^\s*DELETE\s+FROM\s+(?P<tabla>[\w.]+)", re.IGNORECASE | re.DOTALL
)
_INSERT = re.compile(
    r"^\s*INSERT\s+INTO\s+(?P<tabla>[\w.]+)", re.IGNORECASE | re.DOTALL
)
_UPDATE = re.compile(r"^\s*UPDATE\s+(?P<tabla>[\w.]+)", re.IGNORECASE | re.DOTALL)
_ACOTA_REPORTE = re.compile(r"reporte_id\s*=\s*:", re.IGNORECASE)


class BorradoSinAcotarError(AssertionError):
    """Un DELETE sin `WHERE reporte_id=:...` — borraría la tabla entera."""


class Escritura:
    """Una sentencia de escritura registrada, con sus parámetros."""

    def __init__(self, verbo: str, tabla: str, sql: str, parametros: Any) -> None:
        self.verbo = verbo
        self.tabla = tabla
        self.sql = sql
        self.parametros = parametros

    @property
    def filas(self) -> int:
        """Cuántas filas movió: `executemany` recibe una lista de dicts."""
        if isinstance(self.parametros, list):
            return len(self.parametros)
        return 1 if self.parametros is not None else 0

    def __repr__(self) -> str:  # pragma: no cover — solo para leer fallos de test
        return f"<{self.verbo} {self.tabla} filas={self.filas}>"


class _Resultado:
    """Lo que devuelve `execute`: cubre los tres usos del ETL."""

    def __init__(
        self,
        filas: list[dict[str, Any]] | None = None,
        escalar: Any = None,
        rowcount: int = 0,
    ) -> None:
        self._filas = filas or []
        self._escalar = escalar
        self.rowcount = rowcount

    def mappings(self) -> _Resultado:
        return self

    def all(self) -> list[Any]:
        return self._filas

    def first(self) -> Any:
        return self._filas[0] if self._filas else None

    def scalar(self) -> Any:
        return self._escalar

    def scalar_one(self) -> Any:
        return self._escalar


class SesionEscrituraFalsa:
    """Sustituye a `Session` en los tests del ETL. No toca PostgreSQL.

    `respuestas` fija qué devuelve una consulta cuyo SQL contenga una clave dada
    (p. ej. `{"RETURNING reporte_id": 1042}`). `fallar_en` hace que reviente la primera
    sentencia que contenga esa subcadena, para provocar un rollback a mitad del ETL.
    """

    def __init__(
        self,
        respuestas: dict[str, Any] | None = None,
        fallar_en: str | None = None,
    ) -> None:
        self._respuestas = respuestas or {}
        self._fallar_en = fallar_en
        self.escrituras: list[Escritura] = []
        self.sentencias: list[str] = []
        self.transacciones_abiertas = 0
        self.commits = 0
        self.rollbacks = 0
        self.locks_tomados: list[Any] = []

    # ── API que consume el repositorio ───────────────────────────────────────

    def execute(self, clausula: Any, parametros: Any = None) -> _Resultado:
        sql = str(clausula)
        self.sentencias.append(sql)

        if self._fallar_en and self._fallar_en in sql:
            raise OperationalError(sql, {}, Exception("fallo simulado a mitad del ETL"))

        if "pg_advisory" in sql.lower():
            self.locks_tomados.append(parametros)
            return _Resultado(escalar=True)

        self._registrar_si_es_escritura(sql, parametros)

        for clave, valor in self._respuestas.items():
            if clave in sql:
                if isinstance(valor, list):
                    return _Resultado(filas=valor)
                return _Resultado(escalar=valor, filas=[{"valor": valor}])
        return _Resultado()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        return None

    # ── Registro y la red de seguridad ───────────────────────────────────────

    def _registrar_si_es_escritura(self, sql: str, parametros: Any) -> None:
        borrado = _DELETE.match(sql)
        if borrado is not None:
            if not _ACOTA_REPORTE.search(sql):
                raise BorradoSinAcotarError(
                    "DELETE sin `WHERE reporte_id=:...` — borraría la tabla entera.\n"
                    f"SQL:\n{sql}"
                )
            self.escrituras.append(
                Escritura("DELETE", borrado.group("tabla"), sql, parametros)
            )
            return

        insercion = _INSERT.match(sql)
        if insercion is not None:
            self.escrituras.append(
                Escritura("INSERT", insercion.group("tabla"), sql, parametros)
            )
            return

        actualizacion = _UPDATE.match(sql)
        if actualizacion is not None:
            self.escrituras.append(
                Escritura("UPDATE", actualizacion.group("tabla"), sql, parametros)
            )

    # ── Consultas para los asserts ───────────────────────────────────────────

    def escrituras_en(self, tabla: str) -> list[Escritura]:
        return [e for e in self.escrituras if e.tabla.lower() == tabla.lower()]

    def inserciones_en(self, tabla: str) -> list[Escritura]:
        return [e for e in self.escrituras_en(tabla) if e.verbo == "INSERT"]

    def borrados_en(self, tabla: str) -> list[Escritura]:
        return [e for e in self.escrituras_en(tabla) if e.verbo == "DELETE"]

    def filas_escritas_en(self, tabla: str) -> int:
        return sum(e.filas for e in self.inserciones_en(tabla))

    def tablas_tocadas(self) -> set[str]:
        return {e.tabla for e in self.escrituras}

    def hubo_upsert_en(self, tabla: str) -> bool:
        """Que un INSERT lleve `ON CONFLICT` es lo que lo hace idempotente."""
        return any("on conflict" in e.sql.lower() for e in self.inserciones_en(tabla))
