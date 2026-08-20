"""DTOs de salida de la feature `analisis` (F2).

Portados de `INGESTA/Rep_Prod/backend/app/features/analisis/api.py`, que
devolvía `dict` sin tipar. Aquí se tipan porque `mypy strict = true` corre
sobre `src`, y porque el frontend hace dispatch por varios de estos campos —
espíritu de Q5: nunca un fallback silencioso ante un tipo no reconocido.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ── Catálogo de entidades ────────────────────────────────────────────────────

Severidad = Literal["dura", "media", "blanda"]
NivelSemaforo = Literal["verde", "amarillo", "rojo"]


class CardinalidadOut(BaseModel):
    nivel: str = Field(..., description="Nivel de la jerarquía.", examples=["campo"])
    n: int = Field(..., description="Entidades distintas en ese nivel.", examples=[128])


class ProductoValidoOut(BaseModel):
    """Producto del conversacional y su valor en `dim_tipo_producto`.

    `agua` NO existe en `dim_tipo_producto` (solo CRUDO/GAS/BLANCOS): por eso
    no aparece aquí y el slot-filling la rechaza.
    """

    termino: str = Field(..., description="Término de negocio.", examples=["aceite"])
    dim: str = Field(..., description="Valor en dim_tipo_producto.", examples=["CRUDO"])


class ColisionOut(BaseModel):
    """Un nombre que existe en más de un nivel de la jerarquía.

    La severidad decide si el chat contrapregunta: `dura`/`media` sí; `blanda`
    aplica el default 'campo' con aviso.
    """

    nombre: str = Field(..., description="Nombre en conflicto.", examples=["RUBIALES"])
    niveles: list[str] = Field(..., description="Niveles donde aparece.")
    n_niveles: int = Field(..., description="Cuántos niveles lo comparten.")
    severidad: Severidad = Field(..., description="dura | media | blanda.")


class ResumenColisionesOut(BaseModel):
    dura: int = 0
    media: int = 0
    blanda: int = 0
    total: int = 0


class CatalogoOut(BaseModel):
    cardinalidad: list[CardinalidadOut]
    productos_validos: list[ProductoValidoOut]
    colisiones: list[ColisionOut]
    resumen_colisiones: ResumenColisionesOut
    filiales: list[str] = Field(..., description="Empresas filiales (rama B).")
    entidades_por_nivel: dict[str, list[str]] = Field(
        ..., description="Lista completa por nivel, para el explorador."
    )


# ── Densidad temporal ────────────────────────────────────────────────────────


class DiaDensidadOut(BaseModel):
    fecha: str = Field(..., description="Fecha ISO.", examples=["2026-05-17"])
    filas: int = Field(..., description="Registros de ese día.")
    fuentes: int = Field(..., description="Fuentes distintas que reportaron.")


class MesDensidadOut(BaseModel):
    anio: int
    mes: int
    mes_nombre: str
    dias_con_data: int
    dias_del_mes: int
    huecos: int = Field(..., description="Días del mes SIN dato.")
    rango: list[str] = Field(..., description="[primer día, último día] con dato.")


class ResumenDensidadOut(BaseModel):
    total_dias: int
    rango: list[str | None] = Field(..., description="[primera, última] fecha global.")
    huecos_totales: int
    racha_maxima: int = Field(
        ..., description="Días CONTINUOS consecutivos con dato (define el semáforo)."
    )


class FamiliaSemaforoOut(BaseModel):
    """Una de las 5 familias estadísticas y si el dato disponible la soporta."""

    familia: str
    nivel: NivelSemaforo
    necesita_continuidad: bool = Field(
        ..., description="True si depende de la racha de días continuos."
    )


class DensidadOut(BaseModel):
    entidad: str | None = None
    aplica_ecp: bool = Field(
        True,
        description=(
            "False si la entidad no tiene grano diario ECP (vicepresidencias y "
            "filiales no lo tienen): la serie va vacía y no es un error."
        ),
    )
    dias: list[DiaDensidadOut] = []
    por_mes: list[MesDensidadOut] = []
    resumen: ResumenDensidadOut
    semaforo: list[FamiliaSemaforoOut] = []


# ── Huella de datos ──────────────────────────────────────────────────────────


class SerieHuellaOut(BaseModel):
    """METADATA: cuenta FILAS, no barriles. Muestra en qué facts vive la entidad."""

    fuente: str = Field(..., description="Etiqueta legible.", examples=["REAL diario"])
    grupo: str = Field(..., description="dia | mes | programa.")
    filas: int
    hoja: str = Field(..., description="Hoja de origen.", examples=["BDP_datos_dia"])


class HuellaOut(BaseModel):
    entidad: str | None = None
    encontrada: bool = True
    series: list[SerieHuellaOut] = []


# ── Cobertura del reporte ────────────────────────────────────────────────────


class HojaCoberturaOut(BaseModel):
    hoja: str
    categoria: str
    reportes_total: int = Field(
        ...,
        description=(
            "Nº de REPORTES donde aparece la hoja (COUNT DISTINCT reporte_id). "
            "NO es la suma de filas insertadas: esa sobre-cuenta ~26x."
        ),
    )
    reportes_entidad: int | None = Field(
        None, description="Reportes donde aparece la ENTIDAD (solo si se filtró)."
    )


class CategoriaCoberturaOut(BaseModel):
    categoria: str
    hojas: list[HojaCoberturaOut]


class CoberturaOut(BaseModel):
    entidad: str | None = None
    total_hojas: int
    categorias: list[CategoriaCoberturaOut]
    hojas_con_entidad: int | None = Field(
        None, description="Cuántas hojas contienen la entidad (solo si se filtró)."
    )


# ── Desempeño del mes ────────────────────────────────────────────────────────


class MesInfoOut(BaseModel):
    anio: int
    mes: int
    nombre: str = Field(..., description="Nombre del mes en español.")
    dias_con_data: int
    dias_del_mes: int
    completo: bool = Field(..., description="True si el mes tiene todos sus días.")


class ProductoDesempenoOut(BaseModel):
    producto: str = Field(..., description="CRUDO | GAS | BLANCOS.")
    real: float
    ppto: float
    cumplimiento: float | None = Field(
        None, description="real/ppto*100. `None` si no hay meta: NO es un 0%."
    )


class CampoSinMetaOut(BaseModel):
    """Campo que PRODUCE pero no tiene PPTO en el mes (D-A4).

    Se declara en vez de inventarle meta: sumar su REAL contra un PPTO que no
    lo cubre infla el cumplimiento del activo.
    """

    campo: str
    producto: str
    real: float


class CurvaOut(BaseModel):
    fechas: list[str] = Field(..., description="Fechas ISO con dato diario.")
    series: dict[str, list[float]] = Field(
        ..., description="{producto: valores alineados con `fechas`}."
    )


class RitmoMensualOut(BaseModel):
    """Producción mensual del año — sale del fact MENSUAL, igual que la tarjeta,
    así que ambas cifras reconcilian exacto."""

    meses: list[str] = Field(..., description="Nombres cortos (Ene, Feb…).")
    meses_num: list[int]
    series: dict[str, list[float | None]] = Field(
        ..., description="{producto: REAL de cada mes; `None` = sin dato}."
    )
    promedio_mes: dict[str, float | None] = Field(
        ..., description="Media de los meses CERRADOS (= hist_prom de la tarjeta)."
    )
    promedio_dia: dict[str, float | None] = Field(
        ...,
        description=(
            "Promedio diario del año. `None` cuando la curva diaria del "
            "producto NO reconcilia con el mensual (p.ej. BLANCOS): el "
            "frontend cae entonces a la media del mes y su título no dice "
            "'vs 2026'."
        ),
    )
    mes_actual: int


class DesempenoOut(BaseModel):
    entidad: str | None = None
    encontrada: bool = True
    sin_datos: bool = False
    aplica_diario: bool = Field(
        default=True, description="False si la entidad no tiene grano diario ECP."
    )
    sin_cierre: bool = Field(
        default=False, description="True si no hay fila mensual REAL/PPTO para el mes."
    )
    periodo_ok: bool = Field(
        default=True,
        description=(
            "False si el periodo pedido no se pudo honrar (año/semana/trimestre "
            "no están soportados): se sirvió el default y hay que declararlo."
        ),
    )
    mes: MesInfoOut | None = None
    por_producto: list[ProductoDesempenoOut] = []
    campos_sin_meta: list[CampoSinMetaOut] = []
    curva: CurvaOut | None = None
    ritmo_mensual: RitmoMensualOut | None = None
