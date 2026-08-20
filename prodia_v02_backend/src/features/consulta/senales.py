"""Control 2 — señales indirectas de clasificación fallida → `sospecha`.

Portado de `consulta_v2/senales.py` (110 líneas), con dos cambios de fondo.

**La sospecha NO corrige nada.** Es una señal débil: su único efecto es subir el
caso al tope de la cola de revisión (Control 3). Tratarla como veredicto
convertiría una corazonada en dato de entrenamiento, y este es justo el dato que
alimenta el crecimiento del golden.

## Las señales

1. **Reformulación inmediata** — el MISMO USUARIO envía otra pregunta muy
   parecida dentro de la ventana. El emparejamiento es **por usuario, jamás por
   `conversacion_id`**: el flujo real cruza chats con IDs distintos (se prueba en
   Test Clas y se repite en Consulta), así que por conversación no casaría nunca.

2. ~~Cambio a motor v1~~ — **muerta en V02**. En el origen el frontend empujaba
   esta señal cuando el usuario repetía la pregunta en el motor v1. Aquí v1 no
   existe (plan F4 §9): solo hay v2. Se documenta y no se porta, en vez de dejar
   código que no puede dispararse.

3. **Abandono tras `desconocido`** — el usuario no vuelve a preguntar en toda la
   ventana. Con una excepción que hay que conservar: si la salida fue
   `regex+filtro` (OUT por filtro de dominio), es una salida **confiada** —
   abandonar tras un off-topic es lo esperado, no un síntoma. Solo cuenta si
   quien decidió `desconocido` fue el LLM.

## Los dos cambios respecto al origen

**Ninguna aritmética de fechas dentro del SQL.** El origen usa
`now() - make_interval(secs => :win)`, que es PostgreSQL puro; aquí la libreta
vive en `db_auth`, que es **SQLite** (DA-2), y `make_interval` no existe. Los
instantes se calculan en Python y viajan como parámetros. La ganancia va más
allá de la portabilidad: las tres señales pasan a ser **probables sin base de
datos** pasando fechas fijas. En el origen no hay ni un test de `escanear()`.

**El escaneo no se dispara solo.** El origen lo llama dentro de `GET /log`, con
un `except: pass` alrededor, así que cada refresco de la tabla recorría todos los
pendientes lanzando dos consultas por fila — y si fallaba, nadie se enteraba.
Aquí es una operación explícita (`POST /senales/escanear`) que devuelve lo que
hizo. Se conserva la decisión de fondo del origen (P4: sin scheduler) y también
su acotado: solo filas `pendiente` de los últimos `escaneo_dias`.
"""

from __future__ import annotations

import datetime as dt
import functools
import pathlib
from typing import Any

import yaml
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.features.consulta.libreta import marcar_sospecha
from src.features.consulta.normaliza import norm

_RUTA_CFG = pathlib.Path(__file__).parent / "config" / "clasificacion_feedback.yaml"

# La puntuación no la retira `norm()` (lo advierte su propio docstring), así que
# «RUBIALES?» y «RUBIALES» serían tokens distintos y bajarían la similitud sin
# motivo. El origen resuelve esto repitiendo un `.strip()` en cinco sitios; aquí
# se hace una vez, dentro de la tokenización.
_PUNTUACION = "¿?¡!.,;:()[]{}\"'«»"


@functools.lru_cache(maxsize=1)
def _cfg() -> dict[str, Any]:
    """Umbrales del Control 2, leídos una sola vez.

    🔑 **Perezoso a propósito.** El pre-commit corre `gen:types`, que importa
    `src.main` entero; si este YAML se leyera en tiempo de import, la regla de
    CERO I/O al importar se rompería y el test-espía la cazaría.
    """
    datos = yaml.safe_load(_RUTA_CFG.read_text(encoding="utf-8"))
    return dict(datos)


def _tokens(texto: str) -> set[str]:
    return {t.strip(_PUNTUACION) for t in norm(texto).split() if t.strip(_PUNTUACION)}


def similitud(a: str, b: str) -> float:
    """Jaccard sobre tokens normalizados, de 0.0 a 1.0. Función pura.

    P3 del origen: **no** se usa `pg_trgm`. Una señal débil no justifica una
    extensión de base de datos — y aquí, además, la libreta es SQLite.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


class _FilaPendiente:
    """Lo que el escaneo necesita saber de una fila, sin arrastrar la tabla."""

    __slots__ = ("id", "ts", "usuario", "texto", "grupo", "capa")

    def __init__(self, fila: Any) -> None:
        self.id = int(fila["id"])
        self.ts = fila["ts"]
        self.usuario = fila["usuario"]
        self.texto = str(fila["texto_pregunta"])
        self.grupo = str(fila["grupo_asignado"])
        self.capa = str(fila["capa_resolutora"])


def _a_fecha(valor: Any) -> dt.datetime | None:
    """`ts` llega como `datetime` desde PostgreSQL y como texto desde SQLite."""
    if isinstance(valor, dt.datetime):
        return valor
    if isinstance(valor, str):
        try:
            return dt.datetime.fromisoformat(valor)
        except ValueError:
            return None
    return None


def _pendientes(db: Session, desde: dt.datetime) -> list[_FilaPendiente]:
    filas = db.execute(
        text("""
            SELECT id, ts, usuario, texto_pregunta, grupo_asignado, capa_resolutora
              FROM clasificacion_log
             WHERE veredicto = 'pendiente' AND ts >= :desde
             ORDER BY ts
            """),
        {"desde": desde},
    ).mappings()
    return [_FilaPendiente(f) for f in filas]


def _siguiente_del_usuario(
    db: Session, fila: _FilaPendiente, hasta: dt.datetime
) -> str | None:
    """La siguiente pregunta del mismo usuario dentro de la ventana."""
    resultado = db.execute(
        text("""
            SELECT texto_pregunta
              FROM clasificacion_log
             WHERE id <> :id
               AND (usuario = :usuario OR (:usuario IS NULL AND usuario IS NULL))
               AND ts > :desde AND ts <= :hasta
             ORDER BY ts
             LIMIT 1
            """),
        {"id": fila.id, "usuario": fila.usuario, "desde": fila.ts, "hasta": hasta},
    ).scalar()
    return str(resultado) if resultado is not None else None


def _hubo_actividad_posterior(db: Session, fila: _FilaPendiente) -> bool:
    resultado = db.execute(
        text("""
            SELECT 1
              FROM clasificacion_log
             WHERE id <> :id
               AND (usuario = :usuario OR (:usuario IS NULL AND usuario IS NULL))
               AND ts > :desde
             LIMIT 1
            """),
        {"id": fila.id, "usuario": fila.usuario, "desde": fila.ts},
    ).scalar()
    return resultado is not None


def escanear(db: Session, ahora: dt.datetime | None = None) -> dict[str, int]:
    """Recorre los pendientes recientes y marca las sospechas. Devuelve qué hizo.

    `ahora` es inyectable para poder probar las ventanas con fechas fijas, sin
    esperar 600 segundos ni depender del reloj de la máquina.
    """
    cfg = _cfg()
    ahora = ahora or dt.datetime.now()
    ventana_ref = int(cfg["ventana_reformulacion_seg"])
    ventana_aband = int(cfg["ventana_abandono_seg"])
    umbral = float(cfg["similitud_reformulacion"])
    dias = int(cfg.get("escaneo_dias", 7))

    filas = _pendientes(db, ahora - dt.timedelta(days=dias))
    nuevas = 0

    for fila in filas:
        marca = _a_fecha(fila.ts)
        if marca is None:
            continue

        # Señal 1 — reformulación inmediata.
        siguiente = _siguiente_del_usuario(
            db, fila, marca + dt.timedelta(seconds=ventana_ref)
        )
        if siguiente is not None and similitud(fila.texto, siguiente) >= umbral:
            nuevas += marcar_sospecha(
                db, fila.id, "señal indirecta: reformulación inmediata"
            )
            continue

        # Señal 3 — abandono tras un `desconocido` que decidió el LLM.
        #
        # El OUT-por-filtro (`regex+filtro`) queda fuera a propósito: es una
        # salida CONFIADA del clasificador ante algo fuera de dominio, y que el
        # usuario no insista es la reacción esperada, no un síntoma de fallo.
        if fila.grupo == "desconocido" and fila.capa in ("llm", "regex+llm"):
            vencida = ahora > marca + dt.timedelta(seconds=ventana_aband)
            if vencida and not _hubo_actividad_posterior(db, fila):
                nuevas += marcar_sospecha(
                    db, fila.id, "señal indirecta: abandono tras desconocido"
                )

    return {"sospechas_nuevas": nuevas, "filas_revisadas": len(filas)}
