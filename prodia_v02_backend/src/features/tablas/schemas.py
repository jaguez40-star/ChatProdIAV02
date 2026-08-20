"""DTOs de salida de la feature `tablas` (F1 — Control + Tablas).

Portados desde `INGESTA/Rep_Prod/backend/app/features/{tablas,reportes,kpis_prod}/api.py`
del sistema viejo, que devolvía `dict` sin tipar. Aquí se tipan explícitamente porque
`mypy strict = true` corre sobre `src` (hallazgo H3 del plan F1): el portado literal del
SQL se conserva, pero el contrato de salida deja de ser `Any`.

El `modo` de `TablaDatosOut` es un `Literal` deliberado, no un `str` libre: el frontend
hace dispatch por ese campo y debe poder validarlo (espíritu de Q5 — nunca un fallback
silencioso ante un tipo no reconocido).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Árbol de reportes ────────────────────────────────────────────────────────


class DiaArbolOut(BaseModel):
    """Un día del árbol: apunta al reporte que se puede abrir."""

    dia: int = Field(..., description="Día del mes (1-31).", examples=[15])
    reporte_id: int = Field(
        ..., description="Id del reporte de ese día.", examples=[1042]
    )
    tipo: str | None = Field(
        None, description="Tipo de archivo origen del reporte.", examples=["ECP"]
    )
    archivo: str | None = Field(
        None,
        description="Nombre del archivo origen.",
        examples=["Reporte_Produccion_2026-08-15.xlsm"],
    )


class MesArbolOut(BaseModel):
    mes: int = Field(..., description="Número de mes (1-12).", examples=[8])
    mes_nombre: str = Field(
        ..., description="Nombre del mes en español.", examples=["Agosto"]
    )
    dias: list[DiaArbolOut] = Field(..., description="Días con reporte, descendente.")


class AnioArbolOut(BaseModel):
    anio: int = Field(..., description="Año.", examples=[2026])
    meses: list[MesArbolOut] = Field(..., description="Meses con reporte, descendente.")


# ── Hojas y tablas lógicas de un reporte ─────────────────────────────────────


class TablaLogicaOut(BaseModel):
    """Una tabla lógica dentro de una hoja (los ítems clicables del visor)."""

    tabla_idx: int = Field(
        ..., description="Índice de la tabla dentro de la hoja.", examples=[1]
    )
    tabla_label: str | None = Field(
        None, description="Etiqueta de la tabla.", examples=["PRODUCCION MES"]
    )
    filas: int = Field(
        ..., description="Número de registros de la tabla.", examples=[240]
    )


class HojaReporteOut(BaseModel):
    hoja: str = Field(..., description="Nombre de la hoja.", examples=["NEW MES-AÑO"])
    tablas: list[TablaLogicaOut] = Field(..., description="Tablas lógicas de la hoja.")


class HojasReporteOut(BaseModel):
    """Desglose de un reporte — se carga bajo demanda al expandir un día."""

    reporte_id: int = Field(
        ..., description="Id del reporte consultado.", examples=[1042]
    )
    hojas: list[HojaReporteOut] = Field(
        ..., description="Hojas del reporte con sus tablas."
    )


# ── Contenido de una tabla (formato ancho) ───────────────────────────────────


class FilaTablaOut(BaseModel):
    """Una fila del visor en formato ancho.

    `valores` admite `float` (modos `fechas`/`matriz`) y `str` (modo `texto`,
    COMENTARIOS) porque el origen unifica ambos en la misma estructura y el
    frontend hace dispatch por `TablaDatosOut.modo`.

    `dims` es `Any` a propósito: en `core.fact_tabla_hoja` la columna `dims` es **JSONB**
    y los extractores meten ahí lo que trae cada hoja — cadenas (`{"campo": "CASTILLA"}`)
    pero también números (`{"anio": 2026}`) y booleanos. Tiparlo como `dict[str, str|None]`
    hacía reventar la serialización con `ValidationError` en cuanto una hoja traía un
    número, y el fallo NO aparecía en los tests (que usan dims de texto): solo contra el
    corpus real. El visor únicamente muestra estos valores, no opera con ellos.
    """

    dims: dict[str, Any] = Field(
        ...,
        description="Valores de las columnas de dimensión de la fila (JSONB libre).",
    )
    valores: list[float | str | None] = Field(
        ..., description="Valores alineados posicionalmente con `meses`."
    )


class TablaDatosOut(BaseModel):
    """Contenido de una tabla en formato ancho, en uno de los tres modos.

    - `fechas`: columnas = fechas (serie temporal).
    - `matriz`: columnas = categorías (`dims.columna`), fecha NULL; se conserva el
      orden de aparición porque en las matrices el orden de columnas es significativo.
    - `texto`: COMENTARIOS, desde su fact dedicado de texto.
    """

    modo: Literal["fechas", "matriz", "texto"] = Field(
        "fechas", description="Modo de presentación de la tabla."
    )
    vacia: bool = Field(False, description="True si la tabla no tiene registros.")
    dimensiones: list[str] = Field(
        ..., description="Nombres de las columnas de dimensión."
    )
    meses: list[str] = Field(
        ...,
        description="Cabeceras de columna (fechas ISO, categorías o campos de texto).",
    )
    filas: list[FilaTablaOut] = Field(
        ..., description="Filas mostradas — recortadas a CAP_FILAS."
    )
    total_filas: int = Field(
        0,
        description="Total de filas de la tabla (puede superar las devueltas en `filas`).",
    )


# ── Reportes y cobertura ─────────────────────────────────────────────────────


class ReporteOut(BaseModel):
    reporte_id: int = Field(..., description="Id del reporte.", examples=[1042])
    fecha_reporte: date = Field(..., description="Fecha del reporte.")
    tipo_archivo: str | None = Field(None, description="Tipo de archivo origen.")
    tiene_raw: bool | None = Field(None, description="Si conserva las hojas RAW.")
    nivel_detalle: str | None = Field(None, description="Nivel de detalle del reporte.")


class CoberturaOut(BaseModel):
    """Cuántos registros aportó cada reporte a cada fact — diagnóstico de ingesta."""

    reporte_id: int = Field(..., description="Id del reporte.", examples=[1042])
    tipo_archivo: str | None = Field(None, description="Tipo de archivo origen.")
    ecp_mes: int = Field(..., description="Filas en `fact_produccion_mes_ecp`.")
    ecp_dia: int = Field(..., description="Filas en `fact_produccion_dia_ecp`.")
    filiales: int = Field(..., description="Filas en `fact_produccion_diaria`.")


# ── KPIs de producción ───────────────────────────────────────────────────────


class ProduccionDiaOut(BaseModel):
    """Volumen estimado por tipo de producto para una fecha (grupo ECOPETROL)."""

    tipo_producto: str = Field(
        ..., description="Nombre del tipo de producto.", examples=["CRUDO"]
    )
    vol_estimado: float | None = Field(
        None,
        description="Volumen estimado sumado. `None` si el dato no es finito (A6).",
    )
