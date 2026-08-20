"""Router `consulta` — el chat del Motor Q v2 (F4).

Dos endpoints en F4: preguntar y dar veredicto. Los de revisión por lotes y
listado de la libreta son de F5 (Test Clas) y no entran aquí.

**Este módulo es el ÚNICO de la feature que conoce `analisis`**, y esa es la
forma de respetar ADR-001: los módulos del motor reciben los servicios como
parámetros (ver `niveles.py`), y la composición ocurre aquí, en el borde. Un
`import` de `features.analisis` en `ejecutor` o `niveles` volvería a crear el
ciclo que el origen tiene.

**Acceso**: todo usuario autenticado. Basta el deny-by-default del middleware.

🔑 **El usuario sale de la cookie**, nunca del body (ver `schemas.py`).

H9 — `db_prod` es crítica para responder pero no para arrancar: si PostgreSQL
está caído, estos endpoints devuelven 503 con el contrato de error uniforme y
el resto de la aplicación sigue en pie.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.core.logger import get_logger
from src.features.consulta import libreta, maquina, resolver
from src.features.consulta.memoria import MEMORIA
from src.features.consulta.schemas import (
    PreguntarIn,
    RespuestaQ,
    VeredictoIn,
    VeredictoOut,
)
from src.shared.db_auth import get_db
from src.shared.db_prod import get_prod_db

logger = get_logger("consulta.api")

router = APIRouter(prefix="/consulta", tags=["Consulta"])

RESPUESTAS_COMUNES: dict[int | str, dict[str, str]] = {
    401: {"description": "No autenticado — falta la cookie de sesión o es inválida"},
    503: {"description": "PostgreSQL (`db_prod`) no disponible"},
}


def _usuario_de_la_sesion(request: Request) -> str | None:
    """Nombre del usuario autenticado, desde la cookie ya validada."""
    usuario = getattr(request.state, "user", None)
    if usuario is None:
        return None
    return str(getattr(usuario, "username", None) or "")


@router.post(
    "/preguntar",
    response_model=RespuestaQ,
    summary="Clasifica y responde una pregunta del chat",
    responses=RESPUESTAS_COMUNES,
)
def preguntar(
    body: PreguntarIn,
    request: Request,
    db_prod: Session = Depends(get_prod_db),
    db_auth: Session = Depends(get_db),
) -> RespuestaQ:
    """Una pregunta del chat: clasifica, reescribe si es continuación y responde.

    Sync (`def`, no `async def`) como el resto del proyecto: SQLAlchemy es
    síncrona y FastAPI ya ejecuta estas rutas en su threadpool.
    """
    usuario = _usuario_de_la_sesion(request)

    def _detectar_entidad(texto: str) -> str | None:
        """Resuelve contra el catálogo. Nunca lanza: no encontrar entidad es
        un resultado válido, y una caída de BD no debe impedir clasificar."""
        try:
            hit = resolver.buscar_en_texto(texto, db_prod)
        except SQLAlchemyError:
            logger.warning("catalogo_no_disponible", operacion="detectar_entidad")
            return None
        return hit[0] if hit else None

    def _registrar(**kwargs: Any) -> int | None:
        return libreta.registrar(db_auth, **kwargs)

    contexto = MEMORIA.obtener(body.conversacion_id)

    resultado = maquina.clasificar(
        body.texto,
        detectar_entidad=_detectar_entidad,
        contexto=contexto,
        registrar=_registrar,
        usuario=usuario,
        conversacion_id=body.conversacion_id,
    )

    return RespuestaQ(**resultado)


@router.post(
    "/veredicto",
    response_model=VeredictoOut,
    summary="Registra el ✓/✗ del usuario sobre una clasificación",
    responses=RESPUESTAS_COMUNES,
)
def veredicto(
    body: VeredictoIn,
    request: Request,
    db_auth: Session = Depends(get_db),
) -> VeredictoOut:
    """Control 1 de la libreta: el juicio del propio usuario.

    `fuente` la fija el servidor en `"usuario"`: si viniera del cliente, se
    podrían marcar veredictos como si fueran de la revisión por lotes.
    """
    ok = libreta.poner_veredicto(
        db_auth,
        body.log_id,
        body.veredicto,
        grupo_correcto=body.grupo_correcto,
        fuente="usuario",
    )
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Veredicto inválido o el registro no existe.",
        )
    return VeredictoOut(ok=True)
