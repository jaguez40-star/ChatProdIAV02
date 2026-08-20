"""Router `ingesta` — subida de archivos con progreso en vivo (F3).

Un solo camino de entrada (decisión DA-4): se sube el `.xlsm` y el progreso llega por SSE.
El sistema viejo tenía ocho endpoints —listar disponibles, ingerir por nombre, jobs…—
que existían por historia, no por necesidad: la aplicación nueva no lee de una carpeta
compartida, recibe el archivo del navegador.

## Por qué la subida y el proceso van separados

`POST /ingesta/archivo` guarda el archivo y devuelve un identificador; luego
`GET /ingesta/progreso/{id}` abre el flujo de eventos y ejecuta el ETL.

Podrían ser uno solo, pero un `POST` que responde en streaming es incómodo de consumir
desde el navegador: `EventSource` solo hace `GET`. Separarlo permite además validar el
archivo y avisar de una reingesta **antes** de empezar a escribir en la base.

## Validación antes de tocar la base

El orden importa: extensión → tamaño → fecha en el nombre → zip legible. Cada
comprobación es más cara que la anterior, así que se descarta lo barato primero. El
origen no validaba ni el tamaño ni que el zip fuera válido (G11).
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from src.core.config import get_settings
from src.core.logger import get_logger
from src.features.ingesta.detector import nombres_de_hojas, tiene_raw
from src.features.ingesta.schemas import (
    CodigoErrorIngesta,
    ReporteExistente,
)
from src.features.ingesta.services import fecha_de_reporte_valida
from src.features.ingesta.sse import generar_eventos_de_ingesta
from src.shared.db_prod import get_prod_db

logger = get_logger("ingesta.api")

router = APIRouter(prefix="/ingesta", tags=["Ingesta"])

EXTENSIONES_ACEPTADAS = (".xlsm", ".xlsx")

RESPUESTAS_COMUNES: dict[int | str, dict[str, str]] = {
    401: {"description": "No autenticado — falta la cookie de sesión o es inválida"},
    503: {"description": "PostgreSQL (`db_prod`) no disponible"},
}


class ArchivoSubido:
    """Un archivo aceptado y guardado, listo para procesarse."""

    def __init__(self, identificador: str, ruta: Path, hash_contenido: str) -> None:
        self.identificador = identificador
        self.ruta = ruta
        self.hash_contenido = hash_contenido


def _directorio_de_subidas() -> Path:
    destino = Path(get_settings().ingesta_upload_dir)
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _rechazar(
    codigo: CodigoErrorIngesta, detalle: str, estado: int = 422
) -> HTTPException:
    """Error de validación con el código de dominio, para que el frontend pueda
    distinguir 'archivo corrupto' de 'base de datos caída' (G10)."""
    return HTTPException(
        status_code=estado, detail=detalle, headers={"X-Codigo": codigo}
    )


def _validar_nombre(nombre: str) -> None:
    """Extensión y fecha obligatoria en el nombre.

    La fecha `YYYYMMDD` no es un capricho: es la clave única de `config_reporte` y el
    linaje temporal de todo lo que se ingiere. Sin ella no hay dónde colgar el reporte.
    """
    if not nombre.lower().endswith(EXTENSIONES_ACEPTADAS):
        raise _rechazar(
            CodigoErrorIngesta.ARCHIVO_INVALIDO,
            "El archivo debe ser .xlsm o .xlsx.",
            estado=400,
        )
    if fecha_de_reporte_valida(nombre) is None:
        raise _rechazar(
            CodigoErrorIngesta.FECHA_AUSENTE,
            "El nombre del archivo debe contener la fecha en formato YYYYMMDD "
            "(por ejemplo, '20260531_Reporte...'). Es obligatoria para el linaje "
            "del reporte.",
        )


def _guardar_y_validar(archivo: UploadFile) -> ArchivoSubido:
    """Escribe el archivo a disco comprobando el tamaño, y valida que sea un Excel real.

    Se calcula el hash del contenido mientras se escribe: sirve para decirle al usuario
    si el archivo que sube es idéntico al que ya ingirió, algo que el origen no podía
    hacer (`config_reporte.hash_archivo` existía pero nunca se escribía).
    """
    nombre = Path(archivo.filename or "").name  # descarta cualquier ruta
    _validar_nombre(nombre)

    tope_bytes = get_settings().ingesta_max_upload_mb * 1024 * 1024
    identificador = uuid.uuid4().hex
    destino = _directorio_de_subidas() / f"{identificador}__{nombre}"

    resumen = hashlib.sha256()
    escritos = 0
    try:
        with destino.open("wb") as salida:
            while fragmento := archivo.file.read(1024 * 1024):
                escritos += len(fragmento)
                if escritos > tope_bytes:
                    raise _rechazar(
                        CodigoErrorIngesta.ARCHIVO_DEMASIADO_GRANDE,
                        f"El archivo supera el máximo de "
                        f"{get_settings().ingesta_max_upload_mb} MB.",
                        estado=413,
                    )
                resumen.update(fragmento)
                salida.write(fragmento)
    except HTTPException:
        destino.unlink(missing_ok=True)
        raise
    except OSError as excepcion:
        destino.unlink(missing_ok=True)
        logger.error("fallo_al_guardar_subida", error=str(excepcion))
        raise _rechazar(
            CodigoErrorIngesta.ERROR_INTERNO,
            "No se pudo guardar el archivo.",
            estado=500,
        ) from excepcion

    # Que sea un OOXML legible se comprueba aquí y no en el ETL: un zip corrupto debe
    # rechazarse antes de abrir ninguna transacción.
    hojas = nombres_de_hojas(destino)
    if not hojas:
        destino.unlink(missing_ok=True)
        raise _rechazar(
            CodigoErrorIngesta.ARCHIVO_INVALIDO,
            "El archivo no es un Excel válido o no contiene hojas legibles.",
        )

    logger.info(
        "archivo_subido",
        archivo=nombre,
        mb=round(escritos / 1024 / 1024, 1),
        hojas=len(hojas),
        tipo="NEW" if tiene_raw(hojas) else "STD",
    )
    return ArchivoSubido(identificador, destino, resumen.hexdigest())


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get(
    "/reporte-existente",
    response_model=ReporteExistente,
    summary="¿Ya se ingirió un reporte de esta fecha?",
    description=(
        "Comprobación previa a subir, para poder avisar de una reingesta. Es informativa: "
        "reingerir es seguro (el ETL es idempotente), pero conviene que el usuario lo "
        "sepa antes de sobrescribir."
    ),
    responses=RESPUESTAS_COMUNES,
)
async def reporte_existente(
    fecha: str = Query(..., description="Fecha del reporte en ISO (YYYY-MM-DD)."),
    hash_archivo: str | None = Query(
        None, description="SHA-256 del archivo, para saber si es el mismo contenido."
    ),
    db: Session = Depends(get_prod_db),
) -> ReporteExistente:
    from sqlalchemy import text

    try:
        fila = (
            db.execute(
                text(
                    "SELECT reporte_id, archivo_nombre, tipo_archivo, ingested_at, "
                    "hash_archivo FROM core.config_reporte WHERE fecha_reporte = :f"
                ),
                {"f": fecha},
            )
            .mappings()
            .first()
        )
    except SQLAlchemyError as excepcion:
        logger.error("consulta_reporte_existente_fallo", error=str(excepcion))
        raise HTTPException(
            status_code=503,
            detail="La base de datos de producción no está disponible.",
        ) from excepcion

    if fila is None:
        return ReporteExistente(existe=False)
    return ReporteExistente(
        existe=True,
        reporte_id=fila["reporte_id"],
        archivo=fila["archivo_nombre"],
        tipo_archivo=fila["tipo_archivo"],
        ingerido_en=fila["ingested_at"],
        mismo_contenido=(
            fila["hash_archivo"] == hash_archivo if hash_archivo else None
        ),
    )


@router.post(
    "/archivo",
    summary="Subir un .xlsm para ingerir",
    description=(
        "Valida y guarda el archivo. **No lo procesa todavía**: devuelve un identificador "
        "con el que abrir `/ingesta/progreso/{id}`, que es donde corre el ETL y se emiten "
        "los eventos."
    ),
    responses={
        **RESPUESTAS_COMUNES,
        400: {"description": "Extensión no aceptada"},
        413: {"description": "El archivo supera el tamaño máximo"},
        422: {"description": "Falta la fecha en el nombre, o el Excel no es legible"},
    },
)
async def subir_archivo(archivo: UploadFile = File(...)) -> dict[str, Any]:
    subido = _guardar_y_validar(archivo)
    nombre_original = Path(archivo.filename or "").name
    return {
        "id": subido.identificador,
        "archivo": nombre_original,
        "hash": subido.hash_contenido,
        "fecha_reporte": str(fecha_de_reporte_valida(nombre_original)),
    }


@router.get(
    "/progreso/{identificador}",
    summary="Ejecutar la ingesta y seguir su progreso (SSE)",
    description=(
        "Abre un flujo de eventos y procesa el archivo. Los eventos por hoja llegan como "
        "`procesada` —insertada, **pendiente de confirmar**—, y solo el evento final con "
        "estado `confirmado` garantiza que los datos quedaron guardados. Si algo falla, "
        "el evento final es `revertido` e indica en qué hoja."
    ),
    responses=RESPUESTAS_COMUNES,
)
async def progreso_de_ingesta(identificador: str) -> EventSourceResponse:
    directorio = _directorio_de_subidas()
    candidatos = list(directorio.glob(f"{identificador}__*"))
    if not candidatos:
        raise HTTPException(
            status_code=404,
            detail="No hay ningún archivo subido con ese identificador.",
        )

    return EventSourceResponse(
        generar_eventos_de_ingesta(candidatos[0]),
        ping=get_settings().ingesta_sse_heartbeat_s,
    )
