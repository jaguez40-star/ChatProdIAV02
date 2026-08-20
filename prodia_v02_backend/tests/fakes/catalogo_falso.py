"""Doble de sesión para el resolver de entidades (F4).

Reconoce cada consulta por una subcadena distintiva de su SQL y **falla
ruidosamente** si aparece una que no conoce — mismo criterio que
`prod_db_falsa` de F1/F2: si el repositorio cambia su SQL, el test lo dice en
vez de devolver vacío en silencio.

El catálogo que monta es pequeño pero reproduce las tres situaciones que la
política de resolución tiene que distinguir:

- **RUBIALES** — colisión REDUNDANTE: campo, activo y fuente cubren la misma
  fuente física, así que se resuelve sola.
- **APIAY** — colisión con prioridad Campo (D-D5): un campo y un activo con
  conjuntos distintos, se responde Campo y se ofrece el activo como zoom.
- **HOCOL** — colisión GENUINA: filial y campo, dos cosas distintas.
- **GOR** — gerencia que en robustez es en realidad vicepresidencia (puente R2).
"""

from __future__ import annotations

from typing import Any


class _Resultado:
    def __init__(self, filas: list[tuple[Any, ...]]) -> None:
        self._filas = filas

    def __iter__(self) -> Any:
        return iter(self._filas)

    def all(self) -> list[tuple[Any, ...]]:
        return list(self._filas)


# (fuente_id, nombre, campo, gerencia, operador)
_DIM_FUENTE: list[tuple[int, str, str, str, str]] = [
    (1, "RUBIALES", "RUBIALES", "GOR", "ECOPETROL"),
    (2, "APIAY", "APIAY", "GOR", "ECOPETROL"),
    (3, "SURIA", "SURIA", "GOR", "ECOPETROL"),
    (4, "HOCOL", "HOCOL", "GAA", "TERCERO"),
]

# (campo_norm, activo)
_MAP_CAMPO_ACTIVO: list[tuple[str, str]] = [
    ("RUBIALES", "RUBIALES"),  # activo = campo → conjunto idéntico → redundante
    ("APIAY", "APIAY"),
    ("SURIA", "APIAY"),  # APIAY como activo cubre 2 campos → conjunto distinto
]

_VICEPRESIDENCIAS: list[str] = ["VRO", "VEX"]
_EMPRESAS: list[str] = ["HOCOL", "PERMIAN"]

# GOR es vicepresidencia en robustez pero "gerencia" en dim_fuente (puente R2).
_ROB_VP: list[str] = ["GOR", "GAA"]
_ROB_GERENCIA: list[str] = ["GAA"]  # GAA es ambas → NO se relabela


class SesionCatalogoFalsa:
    """Sustituye a `Session` para los tests del resolver."""

    def __init__(self, *, sin_robustez: bool = False) -> None:
        self.sin_robustez = sin_robustez
        self.consultas: list[str] = []

    def execute(self, consulta: Any, _params: Any = None) -> _Resultado:
        sql = str(consulta)
        self.consultas.append(sql)

        if "FROM core.dim_fuente" in sql and "fuente_id" in sql:
            return _Resultado([tuple(f) for f in _DIM_FUENTE])
        if "DISTINCT nombre FROM core.dim_fuente" in sql:
            return _Resultado([(f[1],) for f in _DIM_FUENTE])
        if "DISTINCT campo FROM core.dim_fuente" in sql:
            return _Resultado([(f[2],) for f in _DIM_FUENTE])
        if "DISTINCT gerencia FROM core.dim_fuente" in sql:
            return _Resultado([(f[3],) for f in _DIM_FUENTE])
        if "DISTINCT operador FROM core.dim_fuente" in sql:
            return _Resultado([(f[4],) for f in _DIM_FUENTE])
        if "DISTINCT activo FROM core.map_campo_activo" in sql:
            return _Resultado([(a,) for a in {m[1] for m in _MAP_CAMPO_ACTIVO}])
        if "campo_norm, activo FROM core.map_campo_activo" in sql:
            return _Resultado([tuple(m) for m in _MAP_CAMPO_ACTIVO])
        if "core.dim_vicepresidencia" in sql:
            return _Resultado([(v,) for v in _VICEPRESIDENCIAS])
        if "core.dim_empresa" in sql:
            return _Resultado([(e,) for e in _EMPRESAS])
        if "rob_vicepresidencia FROM core.map_campo_robustez" in sql:
            if self.sin_robustez:
                raise RuntimeError("map_campo_robustez no existe en este entorno")
            return _Resultado([(v,) for v in _ROB_VP])
        if "rob_gerencia FROM core.map_campo_robustez" in sql:
            if self.sin_robustez:
                raise RuntimeError("map_campo_robustez no existe en este entorno")
            return _Resultado([(g,) for g in _ROB_GERENCIA])

        raise AssertionError(
            f"El doble del catálogo no reconoce este SQL:\n{sql}\n"
            "Si el resolver cambió su consulta, actualiza el doble."
        )
