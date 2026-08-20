"""DTOs y eventos de progreso de la Ingesta.

## Los eventos corrigen la mentira del origen (hallazgo G2)

En el sistema viejo, cada hoja emitía `estado: "ok"` **dentro** de la transacción. Si algo
fallaba después, se revertía todo —incluida la bitácora en BD— pero el usuario ya había
visto treinta hojas en verde. Terminaba con un error genérico y sin forma de saber que
**nada** se había guardado.

Aquí el vocabulario distingue las dos cosas:

- Por hoja: `procesando` → `procesada` (leída e insertada, **pendiente de confirmar**),
  `vacia` (no produjo filas) o `error`.
- Al final: `confirmado` (commit hecho, los datos están) o `revertido` (rollback, no
  quedó nada), y en este caso **en qué hoja falló**.

`vacia` no existía en el origen y es la señal de G5: un extractor cuyo layout cambió
devuelve cero filas sin dar error. Marcarlo aparte de `procesada` es lo que hace visible
un cambio de layout en vez de dejarlo pasar por bueno.

## Códigos de error

`CodigoErrorIngesta` cubre el hallazgo G10: el origen solo tenía `str(excepcion)`, así que
el frontend no podía distinguir "el archivo está corrupto" de "PostgreSQL está caído" —
dos situaciones con acciones opuestas para el usuario.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class CodigoErrorIngesta(StrEnum):
    """Qué salió mal, en términos que el usuario pueda accionar."""

    ARCHIVO_INVALIDO = "ARCHIVO_INVALIDO"
    """No es un .xlsm/.xlsx legible, o el zip está corrupto."""

    FECHA_AUSENTE = "FECHA_AUSENTE"
    """El nombre del archivo no trae la fecha YYYYMMDD obligatoria."""

    ARCHIVO_DEMASIADO_GRANDE = "ARCHIVO_DEMASIADO_GRANDE"
    """Supera el tope configurado."""

    HOJA_ILEGIBLE = "HOJA_ILEGIBLE"
    """Una hoja reventó al extraerse — normalmente, un cambio de layout."""

    BD_NO_DISPONIBLE = "BD_NO_DISPONIBLE"
    """PostgreSQL no responde. No es culpa del archivo."""

    ERROR_INTERNO = "ERROR_INTERNO"
    """Cualquier otra cosa. El correlation_id lleva al detalle en los logs."""


# ── Resultado de una ingesta ─────────────────────────────────────────────────


class TablaIngerida(BaseModel):
    """Una tabla lógica y cuántas filas aportó."""

    tabla_idx: int = Field(..., description="Índice de la tabla dentro de la hoja.")
    tabla_label: str = Field(..., description="Etiqueta de la tabla.")
    filas: int = Field(..., description="Filas insertadas. Puede ser 0 (ver `vacia`).")


class HojaIngerida(BaseModel):
    """Resumen de una hoja procesada."""

    hoja: str = Field(..., description="Nombre de la hoja en el libro.")
    destino: str = Field(..., description="Tabla de destino en PostgreSQL.")
    filas: int = Field(..., description="Filas insertadas desde esta hoja.")
    tablas: list[TablaIngerida] = Field(
        default_factory=list, description="Desglose por tabla lógica, si aplica."
    )


class ResultadoIngesta(BaseModel):
    """Lo que produjo una ingesta completa y confirmada."""

    archivo: str = Field(..., description="Nombre del archivo ingerido.")
    reporte_id: int = Field(..., description="Id del reporte creado o actualizado.")
    fecha_reporte: dt.date | None = Field(
        None, description="Fecha del reporte, tomada del nombre del archivo."
    )
    tipo_archivo: Literal["NEW", "STD"] = Field(
        ..., description="NEW si trae las tres hojas BDP_*; STD si no."
    )
    tiene_raw: bool = Field(..., description="Si el libro trae las hojas crudas.")
    filas_por_destino: dict[str, int] = Field(
        default_factory=dict, description="Filas escritas en cada tabla de destino."
    )
    hojas: list[HojaIngerida] = Field(
        default_factory=list, description="Detalle por hoja procesada."
    )
    tablas_vacias: list[str] = Field(
        default_factory=list,
        description=(
            "Tablas declaradas que no produjeron ninguna fila. Puede ser normal, o "
            "indicar que el layout de esa hoja cambió (G5)."
        ),
    )

    @property
    def total_filas(self) -> int:
        return sum(self.filas_por_destino.values())


# ── Eventos de progreso ──────────────────────────────────────────────────────

EstadoHoja = Literal["procesando", "procesada", "vacia", "error"]


class EventoInicio(BaseModel):
    """Primera señal: qué archivo se va a procesar y cuántas hojas trae."""

    tipo: Literal["inicio"] = "inicio"
    archivo: str
    tipo_archivo: Literal["NEW", "STD"]
    hojas: list[str] = Field(..., description="Todas las hojas del libro.")
    total: int = Field(..., description="Número de hojas a recorrer.")


class EventoHoja(BaseModel):
    """Avance de una hoja.

    `procesada` significa "insertada, pendiente de confirmar": hasta que llegue un
    `EventoFin` con estado `confirmado`, estos datos podrían revertirse (G2).
    """

    tipo: Literal["hoja"] = "hoja"
    hoja: str
    estado: EstadoHoja
    destino: str | None = Field(None, description="Tabla de destino, si ya se conoce.")
    filas: int | None = Field(None, description="Filas insertadas desde esta hoja.")
    tablas: list[TablaIngerida] = Field(
        default_factory=list, description="Desglose por tabla lógica."
    )
    detalle: str | None = Field(None, description="Mensaje, presente cuando hay error.")


class EventoAvance(BaseModel):
    """Progreso dentro de una hoja larga — evita el silencio en las hojas pesadas."""

    tipo: Literal["avance"] = "avance"
    hoja: str
    destino: str
    filas: int = Field(..., description="Filas acumuladas hasta ahora.")


class EventoFin(BaseModel):
    """Cierre. **Es el único evento que dice si los datos quedaron guardados.**

    - `confirmado`: la transacción hizo commit; lo que se vio en verde está en la base.
    - `revertido`: hubo rollback. **Nada** se guardó, aunque las hojas anteriores se
      hubieran reportado como procesadas.
    """

    tipo: Literal["fin"] = "fin"
    estado: Literal["confirmado", "revertido"]
    resultado: ResultadoIngesta | None = Field(
        None, description="Presente solo si se confirmó."
    )
    code: CodigoErrorIngesta | None = Field(
        None, description="Presente solo si se revirtió."
    )
    hoja: str | None = Field(
        None, description="Hoja en la que falló, cuando se puede determinar."
    )
    detalle: str | None = Field(None, description="Mensaje para el usuario.")


EventoIngesta = EventoInicio | EventoHoja | EventoAvance | EventoFin


# ── Peticiones y respuestas de la API ────────────────────────────────────────


class ReporteExistente(BaseModel):
    """Respuesta de la comprobación previa a subir un archivo."""

    existe: bool = Field(..., description="Si ya hay un reporte con esa fecha.")
    reporte_id: int | None = None
    archivo: str | None = Field(None, description="Nombre del archivo ya ingerido.")
    tipo_archivo: str | None = None
    ingerido_en: dt.datetime | None = Field(
        None, description="Cuándo se ingirió el que ya existe."
    )
    mismo_contenido: bool | None = Field(
        None,
        description=(
            "Si el archivo que se pretende subir es idéntico al ya ingerido, comparando "
            "el hash. `None` si no se aportó hash."
        ),
    )
