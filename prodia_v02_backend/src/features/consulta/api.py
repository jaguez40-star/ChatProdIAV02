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

# 🔑 ADR-001: este es el ÚNICO módulo de `consulta` que importa `analisis`.
# El motor recibe estos servicios como parámetros y nunca conoce su origen.
from src.features.analisis.repositories import AnalisisRepository
from src.features.analisis.services_desempeno import DesempenoService, escenario_mes
from src.features.consulta import libreta, maquina, plantilla, resolver, subrouter
from src.features.consulta.ejecutor import ejecutar
from src.features.consulta.memoria import MEMORIA
from src.features.consulta.niveles import _como_dict
from src.features.consulta.normaliza import norm
from src.features.consulta.schemas import (
    PreguntarIn,
    RespuestaQ,
    VeredictoIn,
    VeredictoOut,
)
from src.features.consulta.slots import extraer_slots
from src.shared import catalogo_entidades
from src.shared.db_auth import get_db
from src.shared.db_prod import get_prod_db

logger = get_logger("consulta.api")

router = APIRouter(prefix="/consulta", tags=["Consulta"])

# Nivel temporal del ejecutor → tipo de panel del frontend. Los nombres son los
# de la unión discriminada de `consultaTypes.ts`: un tipo que no esté ahí hace
# que el frontend pinte el aviso de Q5 en vez de una tarjeta falsa.
_TIPO_PANEL: dict[str, str] = {
    "N1": "cuant_kpi",  # la cifra de un mes contra su referencia
    "N2": "cuant_kpi",  # acumulado — mismo contrato, otra ventana
    "N3": "cuant_serie",  # serie mensual
    "N4": "cuant_var",  # variación entre dos periodos
}

RESPUESTAS_COMUNES: dict[int | str, dict[str, str]] = {
    401: {"description": "No autenticado — falta la cookie de sesión o es inválida"},
    503: {"description": "PostgreSQL (`db_prod`) no disponible"},
}


def _por_nivel_nombrado(
    texto: str, candidatos: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """El candidato cuyo nivel el usuario nombró en la frase, si hay uno solo.

    🔑 Cierra el bucle de la desambiguación. Ante «CASTILLA existe como activo,
    campo y fuente» el usuario responde «campo castilla» — y sin esto la
    pregunta se repite indefinidamente, porque el texto vuelve a resolver a
    tres candidatos.
    """
    t = f" {norm(texto)} "
    coincidencias = [
        c for c in candidatos if f" {norm(str(c.get('nivel') or ''))} " in t
    ]
    return coincidencias[0] if len(coincidencias) == 1 else None


def _jerarquia(entidad: str, db: Session) -> dict[str, Any] | None:
    """Responde «¿qué campos tiene el activo X?» y «¿a qué activo pertenece X?».

    Es la pregunta más elemental del chat, y el motivo de que exista el nivel
    `jerarquizar`: identidad y pertenencia, sin una sola cifra de producción.

    🔑 Sale del CATÁLOGO (`map_campo_activo`), no del fact: un activo tiene sus
    campos aunque ninguno haya reportado hoy. Confundir las dos fuentes es lo
    que hacía que Diferidas y el tablero discreparan para la misma entidad
    (H11 de F2).
    """
    nombre = entidad.strip().upper()

    campos = catalogo_entidades.campos_de_activo(db, nombre)
    if campos:
        return {
            "mensaje": (
                f"El activo {nombre} está compuesto por {len(campos)} "
                f"{'campo' if len(campos) == 1 else 'campos'}."
            ),
            "panel": {
                "tipo": "jerarq_arbol",
                "datos": {
                    "entidad": nombre,
                    "nivel": "activo",
                    "puente": False,
                    "padres": [],
                    "hijos_grupos": [
                        {
                            "nivel": "campo",
                            "items": campos,
                            "total": len(campos),
                            "truncado": False,
                        }
                    ],
                    "pozos": None,
                    "operador": None,
                    "fuera_estructura": False,
                },
            },
        }

    # No es un activo: ¿será un campo? La dirección inversa.
    activo = catalogo_entidades.activo_de_campo(db, nombre)
    if activo:
        hermanos = [c for c in catalogo_entidades.campos_de_activo(db, activo)]
        return {
            "mensaje": f"El campo {nombre} pertenece al activo {activo}.",
            "panel": {
                "tipo": "jerarq_arbol",
                "datos": {
                    "entidad": nombre,
                    "nivel": "campo",
                    "puente": False,
                    "padres": [{"nivel": "activo", "items": [activo]}],
                    "hijos_grupos": (
                        [
                            {
                                "nivel": "campo hermano",
                                "items": [c for c in hermanos if c != nombre],
                                "total": max(len(hermanos) - 1, 0),
                                "truncado": False,
                            }
                        ]
                        if len(hermanos) > 1
                        else []
                    ),
                    "pozos": None,
                    "operador": None,
                    # `activo_de_campo` devuelve None para campos de terceros o
                    # ambiguos sin veredicto: eso NO es un error, es un dato.
                    "fuera_estructura": False,
                },
            },
        }

    return {
        "mensaje": (
            f"«{nombre}» no aparece en el catálogo como activo ni como campo. "
            "Puede ser de un tercero o estar sin clasificar."
        ),
        "panel": None,
    }


def _analisis(texto: str, entidad: str, db: Session) -> dict[str, Any] | None:
    """Responde «por qué», «cómo va a cerrar» y «cómo va contra la meta».

    🔑 Q1 en su forma más pura: **Python calcula, la plantilla redacta.** El
    texto sale de `plantilla`, que recibe las cifras ya computadas por el
    servicio de desempeño de F2. Ninguna cifra pasa por un modelo.

    Cubre tres de las cinco sub-intenciones. `diferidas` y `economia` necesitan
    otras fuentes (`db_diferidas`, `db_ops`) y se cablean aparte; hasta
    entonces se declara, no se finge.
    """
    sub = subrouter.sub_intencion(texto)
    if sub in ("diferidas", "economia"):
        return {
            "mensaje": (
                f"El análisis de {sub} para «{entidad}» todavía no está "
                "disponible en esta versión. Puedo con causas del rezago, "
                "proyección de cierre y avance contra la meta."
            ),
            "panel": None,
        }

    resuelta = resolver.resolver_unico(entidad, db)
    nombre = str((resuelta or {}).get("valor") or entidad).strip().upper()
    nivel = str((resuelta or {}).get("nivel") or "") or None

    servicio = DesempenoService(AnalisisRepository(db))
    datos = _como_dict(servicio.desempeno(entidad=nombre, nivel=nivel))

    if not datos or datos.get("sin_datos") or datos.get("encontrada") is False:
        # Se declara la ausencia; no se redacta un análisis sobre la nada.
        return {
            "mensaje": (
                f"No hay datos de producción para «{nombre}» en el periodo "
                "vigente, así que no puedo analizar su desempeño."
            ),
            "panel": None,
        }

    slots = extraer_slots(texto, nombre)
    # Solo se acota a un producto si el usuario lo NOMBRÓ. Cuando el motor lo
    # asumió por defecto lo deja anotado en `defaults_asumidos`, y en ese caso
    # el análisis cubre los tres productos: acotarlo a crudo porque es el
    # default silenciaría un rezago de gas que el usuario no excluyó.
    producto = (
        slots.get("producto")
        if "producto" not in (slots.get("defaults_asumidos") or [])
        else None
    )

    if sub == "proyeccion":
        mensaje = plantilla.proyeccion(datos, nombre)
    else:
        # `causal` y `referencia` comparten narrativa: dónde está el faltante.
        mensaje = plantilla.causal(datos, nombre, producto)

    return {
        "mensaje": mensaje,
        "panel": {
            "tipo": "analiza_foco",
            "datos": {
                "entidad": nombre,
                "nivel": nivel,
                "segmento": sub,
                "periodo": datos.get("periodo_label") or datos.get("periodo"),
                "productos": [producto] if producto else [],
            },
        },
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

    def _despachar(texto: str, nucleo: dict[str, Any]) -> dict[str, Any] | None:
        """De «entendí la pregunta» a la cifra.

        🔑 **Aquí es donde ADR-001 se respeta.** Este es el único módulo de la
        feature que importa `features/analisis`; el ejecutor recibe el servicio
        como parámetro (`desempeno_fn`) y nunca conoce su origen. Importarlo
        dentro del motor recrearía el ciclo consulta→analisis del sistema viejo.

        Devuelve `None` cuando no hay nada mejor que el mensaje base — por
        ejemplo si la entidad no se resolvió. Nunca lanza hacia arriba: la
        máquina ya envuelve esta llamada, pero un fallo aquí tampoco debe
        perder la clasificación, que sí es correcta y sí se registra.
        """
        if nucleo["grupo"] not in ("cuantificar", "jerarquizar", "analizar"):
            return None

        entidad = nucleo.get("entidad_cruda")
        if not entidad:
            return None

        if nucleo["grupo"] == "jerarquizar":
            return _jerarquia(str(entidad), db_prod)

        if nucleo["grupo"] == "analizar":
            return _analisis(texto, str(entidad), db_prod)

        candidatos = resolver.resolver(str(entidad), db_prod)
        if not candidatos:
            hit = resolver.buscar_en_texto(texto, db_prod)
            candidatos = list(hit[1]) if hit else []
        if not candidatos:
            return None

        if len(candidatos) > 1:
            # 🔑 Si el usuario YA dijo el nivel en esta misma frase —«campo
            # castilla», que es justo como se responde a la contrapregunta—, la
            # colisión está resuelta y preguntar otra vez es un bucle.
            elegido = _por_nivel_nombrado(texto, candidatos)
            if elegido is None:
                niveles = ", ".join(
                    sorted({str(c.get("nivel", "?")) for c in candidatos})
                )
                return {
                    "mensaje": (
                        f"«{entidad}» existe en más de un nivel ({niveles}). "
                        f"¿A cuál te refieres? Respóndeme por ejemplo "
                        f"«campo {entidad}»."
                    ),
                    "panel": None,
                }
            candidatos = [elegido]

        resuelta = candidatos[0]
        slots = extraer_slots(texto, str(resuelta.get("valor") or entidad))

        servicio = DesempenoService(AnalisisRepository(db_prod))

        # El nombre del primer parámetro DEBE ser `entidad`: `EscenarioFn` es un
        # Protocol con `__call__` posicional-o-nombrado, así que mypy compara
        # también los nombres.
        def _escenario(
            entidad: str,
            nivel: str | None = None,
            periodo: str | None = None,
            escenarios: tuple[str, ...] = ("OPERATIVO", "CONTABLE"),
        ) -> dict[str, dict[str, float]]:
            return escenario_mes(
                AnalisisRepository(db_prod),
                entidad,
                nivel=nivel,
                periodo=periodo,
                escenarios=escenarios,
            )

        salida = ejecutar(
            dict(resuelta),
            dict(slots),
            desempeno_fn=servicio.desempeno,
            escenario_fn=_escenario,
        )

        if not salida.get("aplica"):
            # Rechazo honesto del ejecutor: se dice por qué, sin panel.
            return {"mensaje": str(salida.get("texto") or ""), "panel": None}

        return {
            "mensaje": str(salida.get("texto") or ""),
            "panel": {
                "tipo": _TIPO_PANEL.get(salida.get("nivel", "N1"), "cuant_kpi"),
                "datos": salida,
            },
        }

    contexto = MEMORIA.obtener(body.conversacion_id)

    resultado = maquina.clasificar(
        body.texto,
        detectar_entidad=_detectar_entidad,
        contexto=contexto,
        registrar=_registrar,
        usuario=usuario,
        conversacion_id=body.conversacion_id,
        despachar=_despachar,
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
