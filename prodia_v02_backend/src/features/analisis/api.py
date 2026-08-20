"""Router `analisis` — F2, Análisis avanzado de producción.

Portado de `INGESTA/Rep_Prod/backend/app/features/analisis/api.py`.

Acceso: **todo usuario autenticado** (misma decisión que F1). No lleva
`require_admin`: basta el deny-by-default del `AuthMiddleware`.

⚠️ **Los endpoints son `def` (sync), NO `async def`** — desviación DELIBERADA
del precedente de F1 (`tablas/api.py`, que usa `async def`). Motivo: esta
feature ejecuta SQLAlchemy síncrona y, en los bloques siguientes, llamadas
bloqueantes a Ollama con `timeout=180`. Un `async def` con trabajo bloqueante
dentro **congela el event loop y con él toda la aplicación** —login incluido—
durante esos 3 minutos. Declarándolos `def`, Starlette los ejecuta en su
threadpool y el resto de peticiones sigue atendiéndose.

H9 — `db_prod` es crítica para ESTA feature, pero no para el arranque: si
PostgreSQL cae, estos endpoints devuelven 503 y el backend sigue en pie.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.logger import get_logger
from src.features.analisis.repositories import AnalisisRepository
from src.features.analisis.repositories_catalogo import CatalogoRepository
from src.features.analisis.repositories_ejecutivo import EjecutivoRepository
from src.features.analisis.repositories_filiales import FilialesRepository
from src.features.analisis.schemas import (
    CatalogoOut,
    CoberturaOut,
    DensidadOut,
    DesempenoOut,
    HuellaOut,
)
from src.features.analisis.services_catalogo import CatalogoService
from src.features.analisis.services_desempeno import DesempenoService
from src.features.analisis.services_ejecutivo_panel import EjecutivoService
from src.features.analisis.services_filiales_panel import FilialesService
from src.shared.cache_ttl import CacheTTL, clave_de
from src.shared.db_prod import get_prod_db

logger = get_logger("analisis.api")

router = APIRouter(prefix="/analisis", tags=["Análisis"])

RESPUESTAS_COMUNES: dict[int | str, dict[str, str]] = {
    401: {"description": "No autenticado — falta la cookie de sesión o es inválida"},
    503: {"description": "PostgreSQL (`db_prod`) no disponible"},
}


# Caché A4 de los paneles caros. Se crea UNA vez por proceso (no por
# petición): el single-flight solo sirve si todos los hilos comparten la misma
# instancia. Sin esto, el prefetch del login dispararía N cálculos idénticos.
_cache_paneles: CacheTTL[DesempenoOut] = CacheTTL(
    ttl_s=get_settings().analisis_cache_ttl_s
)


_cache_ejecutivo: CacheTTL[dict[str, Any]] = CacheTTL(
    ttl_s=get_settings().analisis_cache_ttl_s
)


def _panel_es_cacheable(resultado: dict[str, Any]) -> bool:
    """Criterio portado del proxy del sistema viejo: nunca cachear un error ni
    un vacio -- dejaria el panel roto durante los 15 minutos del TTL."""
    if resultado.get("encontrada") is False or resultado.get("sin_datos"):
        return False
    return (resultado.get("meta") or {}).get("generado_por") != "error"


def _es_cacheable(resultado: DesempenoOut) -> bool:
    """Nunca se cachea un fallo ni un vacío: dejaría el panel roto durante todo
    el TTL sin posibilidad de reintentar."""
    return resultado.encontrada and not resultado.sin_datos


def get_desempeno_service(db: Session = Depends(get_prod_db)) -> DesempenoService:
    return DesempenoService(AnalisisRepository(db))


def get_ejecutivo_service(db: Session = Depends(get_prod_db)) -> EjecutivoService:
    return EjecutivoService(EjecutivoRepository(db))


def get_filiales_service(db: Session = Depends(get_prod_db)) -> FilialesService:
    return FilialesService(FilialesRepository(db))


def get_catalogo_service(db: Session = Depends(get_prod_db)) -> CatalogoService:
    """Dependencia de la Fundación de datos. Los tests la sustituyen vía
    `app.dependency_overrides[get_prod_db]`."""
    return CatalogoService(CatalogoRepository(db))


def _error_db(exc: SQLAlchemyError, operacion: str) -> HTTPException:
    """Traduce un fallo de PostgreSQL a 503. El detalle interno va al log, no
    al cliente: el contrato de error nunca filtra el mensaje del driver (L1)."""
    logger.error("db_prod_no_disponible", operacion=operacion, error=str(exc))
    return HTTPException(
        status_code=503,
        detail="La base de datos de producción no está disponible. Intente más tarde.",
    )


# ── Fundación de datos ───────────────────────────────────────────────────────


@router.get(
    "/catalogo",
    response_model=CatalogoOut,
    summary="Catálogo de entidades y colisiones de nombre",
    description=(
        "Cardinalidad por nivel de la jerarquía ECP, lista completa de entidades "
        "por nivel, y los nombres que COLISIONAN entre niveles.\n\n"
        "La `severidad` de cada colisión decide si el chat contrapregunta: "
        "`dura`/`media` sí, `blanda` aplica el default 'campo' con aviso."
    ),
    responses=RESPUESTAS_COMUNES,
)
def catalogo(service: CatalogoService = Depends(get_catalogo_service)) -> CatalogoOut:
    try:
        return service.catalogo()
    except SQLAlchemyError as exc:
        raise _error_db(exc, "catalogo") from exc


@router.get(
    "/densidad",
    response_model=DensidadOut,
    summary="Densidad temporal del dato diario",
    description=(
        "Días con dato, huecos y racha máxima de días CONTINUOS sobre "
        "`core.fact_produccion_dia_ecp`, más un semáforo por familia "
        "estadística.\n\n"
        "**`aplica_ecp=False` no es un error**: las vicepresidencias y las "
        "filiales no tienen grano diario ECP, así que su serie va vacía."
    ),
    responses=RESPUESTAS_COMUNES,
)
def densidad(
    entidad: str | None = Query(
        None, description="Filtra por entidad (fuente/campo/área/activo/gerencia)."
    ),
    service: CatalogoService = Depends(get_catalogo_service),
) -> DensidadOut:
    try:
        return service.densidad(entidad)
    except SQLAlchemyError as exc:
        raise _error_db(exc, "densidad") from exc


@router.get(
    "/huella",
    response_model=HuellaOut,
    summary="Huella de datos por fact y escenario",
    description=(
        "METADATA: cuenta FILAS, no barriles. Muestra en qué facts "
        "estructurados vive una entidad y con qué escenarios.\n\n"
        "No consulta `fact_tabla_hoja` (P50/DPP/Whatsapp): son hojas derivadas."
    ),
    responses=RESPUESTAS_COMUNES,
)
def huella(
    entidad: str | None = Query(None, description="Sin entidad, panorama global."),
    service: CatalogoService = Depends(get_catalogo_service),
) -> HuellaOut:
    try:
        return service.huella(entidad)
    except SQLAlchemyError as exc:
        raise _error_db(exc, "huella") from exc


@router.get(
    "/cobertura",
    response_model=CoberturaOut,
    summary="Cobertura del reporte por hoja",
    description=(
        "Todas las hojas del reporte agrupadas en 5 categorías. La métrica es "
        "el nº de REPORTES (`COUNT DISTINCT reporte_id`), **no** la suma de "
        "filas insertadas: esa sobre-cuenta ~26x por los upserts idempotentes.\n\n"
        "Con `entidad`, añade en cuántos reportes aparece esa entidad por hoja."
    ),
    responses=RESPUESTAS_COMUNES,
)
def cobertura(
    entidad: str | None = Query(None, description="Filtra la presencia por entidad."),
    service: CatalogoService = Depends(get_catalogo_service),
) -> CoberturaOut:
    try:
        return service.cobertura(entidad)
    except SQLAlchemyError as exc:
        raise _error_db(exc, "cobertura") from exc


# ── Desempeño del mes ────────────────────────────────────────────────────────


@router.get(
    "/desempeno",
    summary="Desempeño del mes: REAL vs PPTO, curva diaria y ritmo del año",
    description=(
        "KPIs mensuales por producto, curva diaria y producción mensual del "
        "año para la entidad y el periodo resueltos.\n\n"
        "**Los KPIs salen 100 % del fact MENSUAL**: día y mes usan medidas "
        "distintas para algunos productos (BLANCOS difiere ~2x), así que la "
        "curva diaria sirve solo para la forma, nunca para el cumplimiento.\n\n"
        "**`cumplimiento: null` no es 0 %**: significa que el producto no tiene "
        "meta en el periodo. Los campos que producen SIN presupuesto se "
        "declaran en `campos_sin_meta` en vez de inventarles una.\n\n"
        "**`periodo_ok: false`** indica que el periodo pedido no está soportado "
        "(solo mes: 'mayo', 'mayo 2026', 'mes pasado') y se sirvió el último "
        "mes con dato."
    ),
    responses=RESPUESTAS_COMUNES,
)
def desempeno(
    entidad: str | None = Query(None, description="Entidad a analizar."),
    nivel: str | None = Query(
        None,
        description=(
            "Nivel de la entidad: campo | activo | fuente | gerencia | "
            "operador | vicepresidencia. Sin nivel se resuelve por OR-unión."
        ),
    ),
    periodo: str | None = Query(
        None, description="Periodo en texto libre. Solo mes en v1."
    ),
    segmento: str = Query(
        "ecp", description="ecp | filiales. Filiales cambia fuente Y reglas."
    ),
    service: DesempenoService = Depends(get_desempeno_service),
    filiales: FilialesService = Depends(get_filiales_service),
) -> Any:
    try:
        clave = clave_de(
            "/analisis/desempeno",
            {
                "entidad": entidad,
                "nivel": nivel,
                "periodo": periodo,
                "segmento": segmento,
            },
        )
        if segmento == "filiales":
            return _cache_ejecutivo.obtener_o_calcular(
                clave, filiales.desempeno, _panel_es_cacheable
            )
        return _cache_paneles.obtener_o_calcular(
            clave,
            lambda: service.desempeno(entidad, nivel, periodo),
            _es_cacheable,
        )
    except SQLAlchemyError as exc:
        raise _error_db(exc, "desempeno") from exc


@router.get(
    "/desempeno_insight",
    summary="Titular ejecutivo: chips, curva de crudo y lectura",
    description=(
        "Cumplimiento por producto con su chip de estado, curva diaria de crudo "
        "con el valle anotado, descomposicion del gap del producto mas bajo y "
        "pace de cierre.\n\n"
        "Con `entidad`, el valle se explica POR esa entidad usando el comentario "
        "que ella (o su grupo) reporto: la atribucion declara SIEMPRE quien lo "
        "reporto de verdad. Sin `entidad`, se lista la tabla global de eventos.\n\n"
        "La prosa la redacta el LLM solo si `EJECUTIVO_USAR_LLM=true`; si no, se "
        "compone de forma determinista. `meta.generado_por` lo declara."
    ),
    responses=RESPUESTAS_COMUNES,
)
def desempeno_insight(
    entidad: str | None = Query(None, description="Entidad a analizar."),
    nivel: str | None = Query(None, description="Nivel de la entidad."),
    periodo: str | None = Query(None, description="Periodo (solo mes en v1)."),
    segmento: str = Query("ecp", description="ecp | filiales."),
    service: EjecutivoService = Depends(get_ejecutivo_service),
    filiales: FilialesService = Depends(get_filiales_service),
) -> dict[str, Any]:
    try:
        clave = clave_de(
            "/analisis/desempeno_insight",
            {
                "entidad": entidad,
                "nivel": nivel,
                "periodo": periodo,
                "segmento": segmento,
            },
        )
        if segmento == "filiales":
            return _cache_ejecutivo.obtener_o_calcular(
                clave, filiales.desempeno_insight, _panel_es_cacheable
            )
        return _cache_ejecutivo.obtener_o_calcular(
            clave,
            lambda: service.desempeno_insight(entidad, nivel, periodo),
            _panel_es_cacheable,
        )
    except SQLAlchemyError as exc:
        raise _error_db(exc, "desempeno_insight") from exc


@router.get(
    "/ejecutivo",
    summary="Analisis Ejecutivo multi-seccion",
    description=(
        "Tarjetas KPI de cierre, focos por producto (orden fijo "
        "Crudo-Gas-Blancos), gap RECONCILIADO por campo, valle, pace, flags y "
        "las 4 secciones ejecutivas.\n\n"
        "**El composer determinista es el entregable por defecto**: las 4 "
        "secciones nunca vienen vacias. El LLM solo pule la prosa cuando "
        "`EJECUTIVO_USAR_LLM=true`, y `meta.generado_por` declara cual se uso.\n\n"
        "`pulir=false` salta el pulido del LLM (lo usa el motor conversacional, "
        "que descarta la prosa y no debe esperar 180 s por ella).\n\n"
        "Cacheado 15 min (A4): sin esa cache, cada peticion re-invocaria al LLM "
        "y las generaciones se encolarian hasta reventar el timeout."
    ),
    responses=RESPUESTAS_COMUNES,
)
def ejecutivo(
    entidad: str | None = Query(None, description="Entidad a analizar."),
    nivel: str | None = Query(None, description="Nivel de la entidad."),
    periodo: str | None = Query(None, description="Periodo (solo mes en v1)."),
    pulir: bool = Query(True, description="False = sin pulido del LLM."),
    segmento: str = Query("ecp", description="ecp | filiales."),
    service: EjecutivoService = Depends(get_ejecutivo_service),
    filiales: FilialesService = Depends(get_filiales_service),
) -> dict[str, Any]:
    try:
        clave = clave_de(
            "/analisis/ejecutivo",
            {
                "entidad": entidad,
                "nivel": nivel,
                "periodo": periodo,
                "pulir": pulir,
                "segmento": segmento,
            },
        )
        if segmento == "filiales":
            return _cache_ejecutivo.obtener_o_calcular(
                clave, filiales.ejecutivo, _panel_es_cacheable
            )
        return _cache_ejecutivo.obtener_o_calcular(
            clave,
            lambda: service.ejecutivo(entidad, nivel, periodo, pulir),
            _panel_es_cacheable,
        )
    except SQLAlchemyError as exc:
        raise _error_db(exc, "ejecutivo") from exc


# -- Filiales y compromiso corporativo --------------------------------------


@router.get(
    "/tendencia_filial",
    summary="Tendencia de UNA filial: proyeccion de cierre vs su promedio 2026",
    description=(
        "Panel exclusivo de una filial. Las filiales NO tienen presupuesto, "
        "asi que la referencia es su PROPIA historia del ano: el mes en curso "
        "se lleva a proyeccion de cierre y se compara contra el promedio "
        "mensual de 2026.\n\n"
        "`sin_tendencia: true` significa que no hay meses completos previos "
        "que sostengan el promedio: se declara en vez de mostrar una "
        "variacion sin base."
    ),
    responses=RESPUESTAS_COMUNES,
)
def tendencia_filial(
    empresa: str = Query(..., description="Nombre de la filial."),
    periodo: str | None = Query(None, description="Reservado (v1 usa el ultimo mes)."),
    service: FilialesService = Depends(get_filiales_service),
) -> dict[str, Any]:
    try:
        clave = clave_de(
            "/analisis/tendencia_filial",
            {"empresa": empresa, "periodo": periodo},
        )
        return _cache_ejecutivo.obtener_o_calcular(
            clave,
            lambda: service.tendencia_filial(empresa),
            _panel_es_cacheable,
        )
    except SQLAlchemyError as exc:
        raise _error_db(exc, "tendencia_filial") from exc


@router.get(
    "/president",
    summary="Tarjeta P50: compromiso corporativo por producto",
    description=(
        "Medidas de la hoja REPORTE_PRESIDENT en escala **kbpe corporativa**, "
        "que NO es la del fact diario. Aplicarle la conversion de MSCF daria "
        "un valor mil veces menor sin ningun error visible (A5).\n\n"
        "El endpoint es AGNOSTICO a la referencia: entrega todas las medidas "
        "y el cumplimiento vs P50; que semaforo usar lo decide el frontend.\n\n"
        "Sin `periodo` toma el reporte mas reciente que tenga la hoja, "
        "ordenando por FECHA -- el `reporte_id` es un serial por orden de "
        "ingesta y no es cronologico."
    ),
    responses=RESPUESTAS_COMUNES,
)
def president(
    periodo: str | None = Query(None, description="Periodo YYYY-MM."),
    service: FilialesService = Depends(get_filiales_service),
) -> dict[str, Any]:
    try:
        clave = clave_de("/analisis/president", {"periodo": periodo})
        return _cache_ejecutivo.obtener_o_calcular(
            clave,
            lambda: service.president(periodo),
            _panel_es_cacheable,
        )
    except SQLAlchemyError as exc:
        raise _error_db(exc, "president") from exc
