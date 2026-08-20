"""Router de revisión de la libreta — Test Clas (F5). **Admin-only**.

## Por qué es un router aparte y no tres rutas más en `api.py`

Los dos endpoints de F4 (`/preguntar`, `/veredicto`) son de **todo usuario
autenticado**: cualquiera que use el chat da su ✓/✗ sobre su propia pregunta.
Los tres de aquí son **de administración**: leen el tráfico de todos y emiten
`confirmado_revision`, que la libreta define como la verdad final.

Mezclarlos en un módulo obligaría a poner `require_admin` endpoint por endpoint,
y bastaría con que alguien lo olvidara en el siguiente para abrir la revisión a
todo el mundo en silencio. Con el router separado, el guard va **una vez, en el
constructor**, y cubre todo lo que se monte dentro.

Un no-admin recibe **403**, no una lista vacía: un permiso que se manifiesta
como "no hay datos" es indistinguible de un bug, y manda al usuario a buscar el
problema donde no está.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.features.consulta import libreta, senales
from src.features.consulta.schemas_revision import (
    EscaneoOut,
    FiltroLibreta,
    LibretaOut,
    VeredictoLoteIn,
    VeredictoLoteOut,
)
from src.shared.auth_guards import require_admin
from src.shared.db_auth import get_db

router = APIRouter(
    prefix="/consulta/revision",
    tags=["Consulta · revisión"],
    dependencies=[Depends(require_admin)],
)

RESPUESTAS_COMUNES: dict[int | str, dict[str, str]] = {
    401: {"description": "No autenticado — falta la cookie de sesión o es inválida"},
    403: {"description": "Requiere privilegios de administrador"},
}


@router.get(
    "/libreta",
    response_model=LibretaOut,
    summary="Lista la libreta con sus KPIs (Test Clas)",
    responses=RESPUESTAS_COMUNES,
)
def listar_libreta(
    db: Annotated[Session, Depends(get_db)],
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
    filtro: FiltroLibreta = "todas",
) -> LibretaOut:
    """La cola de revisión y el estado del ciclo.

    **Lectura pura, sin efectos.** El origen llamaba a `senales.escanear()`
    dentro de este GET, así que cada clic en un chip de filtro recorría todos
    los pendientes lanzando dos consultas por fila. El escaneo vive ahora en su
    propio endpoint, que la UI llama una vez al abrir.
    """
    vista = libreta.listar(db, limite=limite, filtro=filtro)
    filas: list[dict[str, Any]] = vista["filas"]
    return LibretaOut(
        filas=[_serializar(f) for f in filas],
        resumen=vista["resumen"],
        # Si vinieron exactamente las que caben, es probable que haya más: se
        # declara en vez de dejar que el revisor crea haber visto toda la cola.
        truncado=len(filas) >= limite,
    )


@router.post(
    "/veredicto-lote",
    response_model=VeredictoLoteOut,
    summary="Aplica varios veredictos de revisión (Control 3)",
    responses=RESPUESTAS_COMUNES,
)
def veredicto_lote(
    body: VeredictoLoteIn,
    db: Annotated[Session, Depends(get_db)],
) -> VeredictoLoteOut:
    """Control 3 por lotes.

    `fuente` la fija el servidor en `"revision"`: es lo que distingue el juicio
    del revisor del ✓/✗ que da el propio usuario en su chat.
    """
    aplicados, total = libreta.poner_veredictos_en_lote(
        db,
        [(i.log_id, i.veredicto, i.grupo_correcto) for i in body.items],
        fuente="revision",
        nota=body.nota,
    )
    return VeredictoLoteOut(ok=True, aplicados=aplicados, total=total)


@router.post(
    "/escanear",
    response_model=EscaneoOut,
    summary="Ejecuta el Control 2 y devuelve qué encontró",
    responses=RESPUESTAS_COMUNES,
)
def escanear_senales(db: Annotated[Session, Depends(get_db)]) -> EscaneoOut:
    """Busca señales indirectas y marca sospechas.

    Explícito a propósito (ver `listar_libreta`). Y **no** se envuelve en un
    `try/except` mudo: si el escaneo falla, el manejador global responde con el
    contrato de error uniforme y su `correlation_id`, que es lo que permite
    encontrarlo en los logs. El origen lo silenciaba.
    """
    return EscaneoOut(**senales.escanear(db))


def _serializar(fila: dict[str, Any]) -> Any:
    """`ts` llega como `datetime` desde PostgreSQL y como texto desde SQLite.

    Pydantic no convierte `datetime` a `str` bajo un campo tipado `str | None`,
    así que se normaliza aquí a ISO-8601 — el formato que el frontend ya sabe
    leer del resto de la API.
    """
    salida = dict(fila)
    for campo in ("ts",):
        valor = salida.get(campo)
        if valor is not None and not isinstance(valor, str):
            salida[campo] = valor.isoformat()
    return salida
