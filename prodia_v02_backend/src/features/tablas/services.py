"""Lógica de negocio de `tablas` — pivote a formato ancho y armado del árbol.

Portado de `INGESTA/Rep_Prod/backend/app/features/tablas/api.py` del sistema viejo, donde
esta lógica vivía dentro de los endpoints. Aquí baja a la capa de servicio (molde `auth`:
el router no calcula).

Reglas preservadas del origen — cada una es una decisión pagada con un bug real:

- El **orden de aparición** de las columnas en modo `matriz` es significativo (no se
  ordena alfabéticamente): en las matrices la posición de la columna ES el dato.
- `FinalizaEvento`-style: una fila con `fecha` NULL no es una fila inválida, define el
  modo `matriz`. Descartarlas perdía tablas enteras.
- `dim_keys` se acumula en orden de aparición para que la cabecera de dimensiones sea
  estable entre llamadas.
- Cuando la hoja viene truncada (`FETCH_MAX`), las columnas de fecha se piden aparte
  (`fechas_distintas`) para que la cabecera no dependa del prefijo cargado.

A6: `_sanitize_col` se aplica a toda columna numérica antes de construir la response —
un Infinity/NaN colado rompe la serialización JSON en silencio.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from typing import Any

from sqlalchemy import RowMapping

from src.features.tablas.repositories import CAP_FILAS, FETCH_MAX, TablasRepository
from src.features.tablas.schemas import (
    AnioArbolOut,
    CoberturaOut,
    DiaArbolOut,
    FilaTablaOut,
    HojaReporteOut,
    HojasReporteOut,
    MesArbolOut,
    ProduccionDiaOut,
    ReporteOut,
    TablaDatosOut,
    TablaLogicaOut,
)
from src.shared.utils import _sanitize_col

MESES_ES = [
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]

HOJA_COMENTARIOS = "COMENTARIOS"

Fila = RowMapping


def _es_comentarios(hoja: str) -> bool:
    return hoja.strip().upper() == HOJA_COMENTARIOS


def _a_float(valor: Any) -> float | None:
    return float(valor) if valor is not None else None


def _tabla_vacia() -> TablaDatosOut:
    """Respuesta de una tabla sin registros — el frontend la distingue por `vacia`."""
    return TablaDatosOut(
        modo="fechas", vacia=True, dimensiones=[], meses=[], filas=[], total_filas=0
    )


class TablasService:
    """Orquesta repositorio + pivote. No abre conexiones ni hace commit (solo lectura)."""

    def __init__(self, repo: TablasRepository) -> None:
        self._repo = repo

    # ── Árbol ────────────────────────────────────────────────────────────────

    def arbol_reportes(self) -> list[AnioArbolOut]:
        """Árbol jerárquico año → mes → día (metadata de reporte)."""
        filas = self._repo.listar_config_reportes()

        arbol: OrderedDict[int, OrderedDict[int, OrderedDict[int, Fila]]] = (
            OrderedDict()
        )
        for fila in filas:
            fecha = fila["fecha_reporte"]
            arbol.setdefault(fecha.year, OrderedDict()).setdefault(
                fecha.month, OrderedDict()
            )[fecha.day] = fila

        resultado: list[AnioArbolOut] = []
        for anio, meses in sorted(arbol.items(), reverse=True):
            meses_out: list[MesArbolOut] = []
            for mes, dias in sorted(meses.items(), reverse=True):
                dias_out = [
                    DiaArbolOut(
                        dia=dia,
                        reporte_id=info["reporte_id"],
                        tipo=info["tipo_archivo"],
                        archivo=info["archivo_nombre"],
                    )
                    for dia, info in sorted(dias.items(), reverse=True)
                ]
                meses_out.append(
                    MesArbolOut(mes=mes, mes_nombre=MESES_ES[mes], dias=dias_out)
                )
            resultado.append(AnioArbolOut(anio=anio, meses=meses_out))
        return resultado

    def hojas_de_reporte(self, reporte_id: int) -> HojasReporteOut:
        filas = self._repo.hojas_de_reporte(reporte_id)

        hojas: OrderedDict[str, list[TablaLogicaOut]] = OrderedDict()
        for fila in filas:
            hojas.setdefault(fila["hoja"], []).append(
                TablaLogicaOut(
                    tabla_idx=fila["tabla_idx"],
                    tabla_label=fila["tabla_label"],
                    filas=fila["filas"],
                )
            )
        return HojasReporteOut(
            reporte_id=reporte_id,
            hojas=[HojaReporteOut(hoja=h, tablas=t) for h, t in hojas.items()],
        )

    # ── Tablas lógicas de una hoja ───────────────────────────────────────────

    def tablas_de_hoja(self, reporte_id: int, hoja: str) -> list[TablaLogicaOut]:
        """COMENTARIOS no vive en `fact_tabla_hoja` (es texto) → 1 tabla lógica desde su
        fact dedicado."""
        if _es_comentarios(hoja):
            total = self._repo.contar_comentarios(reporte_id)
            return [
                TablaLogicaOut(tabla_idx=1, tabla_label=HOJA_COMENTARIOS, filas=total)
            ]
        return [
            TablaLogicaOut(
                tabla_idx=f["tabla_idx"], tabla_label=f["tabla_label"], filas=f["filas"]
            )
            for f in self._repo.listar_tablas_de_hoja(reporte_id, hoja)
        ]

    # ── Contenido de una tabla ───────────────────────────────────────────────

    def datos_tabla(self, reporte_id: int, hoja: str, tabla_idx: int) -> TablaDatosOut:
        if _es_comentarios(hoja):
            return self._datos_comentarios(reporte_id)

        filas = self._repo.leer_filas_tabla(reporte_id, hoja, tabla_idx)
        if not filas:
            return _tabla_vacia()

        # Hoja enorme: solo se cargó un prefijo por id (se pidió FETCH_MAX+1).
        truncada = len(filas) > FETCH_MAX
        if truncada:
            filas = filas[:FETCH_MAX]

        # Todas las filas sin fecha → pivote fila × columna (las matrices son pequeñas).
        if all(f["fecha"] is None for f in filas):
            return self._pivote_matriz(filas)
        return self._pivote_fechas(filas, reporte_id, hoja, tabla_idx, truncada)

    def _datos_comentarios(self, reporte_id: int) -> TablaDatosOut:
        """COMENTARIOS: tabla de TEXTO desde `core.fact_comentarios_produccion`."""
        filas = self._repo.leer_comentarios(reporte_id)
        if not filas:
            return _tabla_vacia()

        columnas = ["Comentario", "Comentario programa", "Comentario extra"]
        salida = [
            FilaTablaOut(
                dims={
                    "producto": f["producto"],
                    "activos": f["activos"],
                    "area": f["area"],
                },
                valores=[
                    f["comentario"],
                    f["comentario_programa"],
                    f["comentario_extra"],
                ],
            )
            for f in filas
        ]
        return TablaDatosOut(
            modo="texto",
            vacia=False,
            dimensiones=["producto", "activos", "area"],
            meses=columnas,
            filas=salida[:CAP_FILAS],
            total_filas=len(salida),
        )

    def _pivote_matriz(self, filas: Sequence[Fila]) -> TablaDatosOut:
        """Columnas = categorías (`dims.columna`), fecha NULL. Se conserva el ORDEN DE
        APARICIÓN: en las matrices el orden de columnas es significativo."""
        columnas: list[str] = []
        for f in filas:
            columna = (f["dims"] or {}).get("columna")
            if columna is not None and columna not in columnas:
                columnas.append(columna)

        por_fila: dict[str | None, dict[str | None, float | None]] = {}
        orden: list[str | None] = []
        for f in filas:
            dims = f["dims"] or {}
            clave = dims.get("fila")
            if clave not in por_fila:
                por_fila[clave] = {}
                orden.append(clave)
            por_fila[clave][dims.get("columna")] = _a_float(f["valor"])

        salida = [
            FilaTablaOut(
                dims={"fila": clave},
                # A6 — ninguna columna numérica sale sin sanear.
                valores=list(_sanitize_col([por_fila[clave].get(c) for c in columnas])),
            )
            for clave in orden
        ]
        return TablaDatosOut(
            modo="matriz",
            vacia=False,
            dimensiones=["fila"],
            meses=columnas,
            filas=salida[:CAP_FILAS],
            total_filas=len(salida),
        )

    def _pivote_fechas(
        self,
        filas: Sequence[Fila],
        reporte_id: int,
        hoja: str,
        tabla_idx: int,
        truncada: bool,
    ) -> TablaDatosOut:
        """Columnas = fechas (serie temporal)."""
        # Orden estable de columnas de dimensión (orden de aparición, no alfabético).
        dim_keys: list[str] = []
        for f in filas:
            for clave in (f["dims"] or {}).keys():
                if clave not in dim_keys:
                    dim_keys.append(clave)

        if truncada:
            # Cabecera estable: TODAS las fechas, no solo las del prefijo cargado.
            meses = self._repo.fechas_distintas(reporte_id, hoja, tabla_idx)
        else:
            meses = sorted(
                {f["fecha"].isoformat() for f in filas if f["fecha"] is not None}
            )

        por_dims: dict[tuple[Any, ...], dict[str, Any]] = {}
        for f in filas:
            dims = f["dims"] or {}
            clave = tuple(dims.get(k) for k in dim_keys)
            if clave not in por_dims:
                por_dims[clave] = {
                    "dims": {k: dims.get(k) for k in dim_keys},
                    "valores": {},
                }
            if f["fecha"] is not None:
                por_dims[clave]["valores"][f["fecha"].isoformat()] = _a_float(
                    f["valor"]
                )

        salida = [
            FilaTablaOut(
                dims=v["dims"],
                # A6 — ninguna columna numérica sale sin sanear.
                valores=list(_sanitize_col([v["valores"].get(m) for m in meses])),
            )
            for v in por_dims.values()
        ]
        # Total de filas del visor (combos distintos): exacto si se cargó todo; si está
        # truncada, count(*) (en hojas RAW truncadas cada combo = 1 registro).
        total = (
            self._repo.contar_filas_tabla(reporte_id, hoja, tabla_idx)
            if truncada
            else len(salida)
        )
        return TablaDatosOut(
            modo="fechas",
            vacia=False,
            dimensiones=dim_keys,
            meses=meses,
            filas=salida[:CAP_FILAS],
            total_filas=total,
        )

    # ── Reportes, cobertura y KPIs ───────────────────────────────────────────

    def listar_reportes(self) -> list[ReporteOut]:
        return [
            ReporteOut.model_validate(dict(f)) for f in self._repo.listar_reportes()
        ]

    def cobertura(self) -> list[CoberturaOut]:
        return [CoberturaOut.model_validate(dict(f)) for f in self._repo.cobertura()]

    def produccion_dia(self, fecha: str) -> list[ProduccionDiaOut]:
        filas = self._repo.produccion_dia(fecha)
        # A6 — la suma puede producir un valor no finito.
        volumenes = _sanitize_col([_a_float(f["vol_estimado"]) for f in filas])
        return [
            ProduccionDiaOut(tipo_producto=f["tipo_producto"], vol_estimado=volumen)
            for f, volumen in zip(filas, volumenes, strict=True)
        ]
