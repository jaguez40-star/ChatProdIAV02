"""Contratos de la revisión de la libreta — Test Clas (F5).

Separados de `schemas.py` por la misma razón que su router: estos son
**admin-only**, los de F4 son de todo usuario autenticado. Tenerlos juntos
invitaría a mezclar los dos niveles de acceso en el mismo `api.py`.

🔑 **`fuente` no se acepta del cliente**, igual que en F4: aquí siempre vale
`"revision"`, porque este es el aparato del Control 3. Si viniera del body, un
usuario podría marcar sus propios veredictos como si fueran de la revisión — y
`confirmado_revision` es, por definición, la verdad final.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.features.consulta.schemas import GrupoQ

# El filtro es un `Literal`, no un `str`: FastAPI rechaza cualquier otro valor
# con 422 antes de tocar la capa de datos. F4 lo tomaba como texto libre y
# degradaba a "todas" en silencio ante una errata — devolvía la libreta entera
# mientras el revisor creía estar viendo solo las sospechas.
FiltroLibreta = Literal["todas", "pendientes", "sospecha", "corregidas"]

VeredictoDeRevision = Literal["confirmado_revision", "corregido_revision"]


class FilaLibreta(BaseModel):
    """Una clasificación con su estado de juicio."""

    id: int
    ts: str | None = None
    usuario: str | None = None
    conversacion_id: str | None = None
    texto_pregunta: str
    grupo_asignado: GrupoQ
    capa_resolutora: str
    entidad_cruda: str | None = None
    llm_diag: str | None = None
    veredicto: str
    grupo_correcto: GrupoQ | None = None
    fuente_veredicto: str | None = None
    nota_revision: str | None = None


class ResumenLibretaOut(BaseModel):
    """Los KPIs del ciclo de crecimiento.

    `pct_capa1` es `None` —no 0— cuando la libreta está vacía: un 0 % afirmaría
    que la regex no resuelve nada, que es una conclusión muy distinta de «aún no
    hay datos».
    """

    total: int
    por_veredicto: dict[str, int]
    pct_capa1: float | None = None


class LibretaOut(BaseModel):
    filas: list[FilaLibreta]
    resumen: ResumenLibretaOut
    # El origen truncaba a 100 filas sin decirlo. Declararlo permite que la UI
    # avise en vez de que el revisor crea haber visto toda la cola.
    truncado: bool = False


class ItemVeredicto(BaseModel):
    log_id: int
    veredicto: VeredictoDeRevision
    grupo_correcto: GrupoQ | None = None


class VeredictoLoteIn(BaseModel):
    """Un lote de juicios del Control 3.

    El tope de 500 no es burocracia: sin él, un cliente podría mandar la libreta
    entera en una petición y el bucle de escritura bloquearía el hilo.
    """

    items: list[ItemVeredicto] = Field(min_length=1, max_length=500)
    nota: str | None = Field(default=None, max_length=500)


class VeredictoLoteOut(BaseModel):
    """Cuántos se aplicaron de cuántos se pidieron.

    Devolver solo `ok: true` escondería que 30 de 100 veredictos no se
    guardaron —por un id que ya no existe, o por una corrección sin grupo—, y el
    revisor daría por juzgada una cola que sigue pendiente.
    """

    ok: bool
    aplicados: int
    total: int


class EscaneoOut(BaseModel):
    """Lo que hizo el Control 2 al pasar.

    El origen se tragaba el resultado con un `except: pass`, así que un escaneo
    roto era indistinguible de uno sin hallazgos.
    """

    sospechas_nuevas: int
    filas_revisadas: int
