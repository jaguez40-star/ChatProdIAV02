"""Contratos de entrada y salida de `/consulta`.

🔑 **El `usuario` NO viaja en el body.** El origen lo recibe como campo del
request (`Preguntar.usuario`), es decir: el cliente declara quién es. Aquí sale
de la cookie de sesión firmada, que ya validó el middleware de auth. Un campo
de usuario en el body sería suplantación de identidad por diseño.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

GrupoQ = Literal["jerarquizar", "cuantificar", "analizar", "desconocido"]

# Los 9 tipos de panel. El frontend los discrimina con una unión tipada y su
# dispatcher falla en compilación ante un tipo nuevo (Q5): en el sistema viejo,
# `cuant_kpi` —el más común— no estaba registrado y caía al fallback por
# accidente, pintando una tarjeta con campos ajenos sin ningún error visible.
TipoPanel = Literal[
    "cuant_kpi",
    "cuant_serie",
    "cuant_var",
    "cuant_rank",
    "jerarq_arbol",
    "jerarq_operador",
    "jerarq_rank",
    "p50_vp",
    "analiza_foco",
]


class PreguntarIn(BaseModel):
    """Una pregunta del chat."""

    texto: str = Field(min_length=1, max_length=2000)
    conversacion_id: str = Field(min_length=1, max_length=64)


class Panel(BaseModel):
    """El panel que acompaña a una respuesta, si lo hay.

    `datos` es deliberadamente abierto: cada tipo tiene su forma, y quien la
    valida es la unión discriminada del frontend. Cerrarlo aquí obligaría a
    nueve modelos que solo duplicarían esa definición.
    """

    tipo: TipoPanel
    datos: dict[str, Any]


class RespuestaQ(BaseModel):
    """Lo que devuelve el motor por cada pregunta."""

    log_id: int | None = None
    texto_original: str
    grupo: GrupoQ
    grupo_label: str
    capa_resolutora: str
    entidad_cruda: str | None = None
    patrones: list[str] = Field(default_factory=list)
    llm_diag: str | None = None
    timestamp: str
    mensaje: str
    panel: Panel | None = None
    vp_ofrecida: str | None = None
    # Solo presente cuando la pregunta fue una continuación reescrita.
    continuacion: bool | None = None


class VeredictoIn(BaseModel):
    """El juicio del usuario sobre una clasificación (control 1 de la libreta).

    `fuente` NO se acepta del cliente: la pone el servidor según el endpoint.
    Dejarla abierta permitiría que un usuario marcara sus propios veredictos
    como si vinieran de la revisión por lotes.
    """

    log_id: int
    veredicto: Literal["confirmado_usuario", "corregido_usuario"]
    grupo_correcto: GrupoQ | None = None


class VeredictoOut(BaseModel):
    ok: bool
