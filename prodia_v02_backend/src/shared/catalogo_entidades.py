"""Catálogo de entidades ECP — normalización y composición de activos.

Portado de `INGESTA/Rep_Prod/backend/app/features/consulta/{resolver,normaliza}.py`.

**Por qué está en `shared/` y no en una feature.** En el origen, `analisis`
importaba de `consulta` (`analisis/api.py:4`), lo que aquí violaría ADR-001
(cero imports cross-feature). Como F2 (Análisis) y F4 (Consulta) necesitan la
misma composición de activos, vive en `shared/`: si divergieran, el tablero y
el chat darían cifras distintas para la misma entidad.

Se porta SOLO la parte de catálogo. Lo conversacional del origen
(`resolver()`, `buscar_en_texto`, `termino_candidato`, `_STOP`,
`clave_fisica`) es F4 y no entra aquí.

🔑 **EL ACTIVO NO SALE DE `dim_fuente`** (auditoría del origen 2026-07-16,
verificada contra la BD). La jerarquía real del negocio es
`campo → ACTIVO → gerencia → vicepresidencia`, y:

- `dim_fuente.activos` **NO** es el activo: es un bucket de portafolio
  (OPERADOS / NO OPERADOS / MENORES + agrupaciones regionales, 18 valores).
  Para APIAY agrupaba 13 campos cuando el activo real tiene 4 → cifras
  infladas. **Eliminado como fuente.**
- `dim_fuente.grupo1` ("área") es una taxonomía previa, parecida pero distinta
  (62 valores; KIMERA→CPO-09, GIGANTE→NEIVA, PAUTO SUR→RECETOR discrepan del
  catálogo real). No existe en el modelo mental del negocio. **Eliminado.**
- El catálogo real son 52 activos en `core.map_campo_activo` (migración 008).

⚠️ `pozo` sigue siendo un ALIAS de `fuente`: el grano de pozo NO existe en esta
BD (deuda heredada del sistema viejo).

**Cero I/O en tiempo de import** (AP-2): el índice se construye en la primera
llamada. `scripts/export_openapi.py` importa `src.main` en cada `git commit`
(hook `gen-types-check`) y en CI; construir el índice al importar haría que
esos flujos intentaran consultar el Postgres del 139 sin VPN.
"""

from __future__ import annotations

import threading
import unicodedata

from sqlalchemy import text
from sqlalchemy.orm import Session

# Índice `campo_normalizado → activo`, cacheado por proceso.
#
# H3/A1 — lock + doble chequeo. En el origen (`resolver.py:27,100`) estos
# globales se llenaban sin protección: con N peticiones concurrentes (el
# prefetch del login dispara varias), N hilos construían el índice a la vez.
# Es el mismo defecto que la regla A1 describe para `Eventos_OW.xlsx`.
_CAMPO_A_ACTIVO: dict[str, str] | None = None
_LOCK_INDICE = threading.Lock()


def norm(texto: str | None) -> str:
    """UPPER + trim + colapsa espacios + pliega acentos y ñ.

    Es el MISMO criterio que usa el índice y que debe usar cualquier
    comparación contra él: el `.xlsx` de eventos viene en NFC ('CAÑO SUR ESTE')
    y nadie normaliza del lado de Postgres, así que un match literal sería byte
    a byte y una fuente en NFD rompería campos EN SILENCIO.
    """
    descompuesto = unicodedata.normalize("NFKD", (texto or "").strip().upper())
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(sin_tildes.split())


def _construir_indice(db: Session) -> dict[str, str]:
    filas = db.execute(
        text("SELECT campo_norm, activo FROM core.map_campo_activo")
    ).all()
    return {str(campo): str(activo) for campo, activo in filas if campo and activo}


def _indice(db: Session) -> dict[str, str]:
    """Índice cacheado por proceso, construido una sola vez (lock + doble chequeo)."""
    global _CAMPO_A_ACTIVO
    if _CAMPO_A_ACTIVO is not None:
        return _CAMPO_A_ACTIVO
    with _LOCK_INDICE:
        # Doble chequeo: otro hilo pudo construirlo mientras esperábamos.
        if _CAMPO_A_ACTIVO is None:
            _CAMPO_A_ACTIVO = _construir_indice(db)
        return _CAMPO_A_ACTIVO


def reset_cache() -> None:
    """Vacía el índice. Solo para tests — en producción el catálogo no cambia
    sin un despliegue."""
    global _CAMPO_A_ACTIVO
    with _LOCK_INDICE:
        _CAMPO_A_ACTIVO = None


def fuentes_de_activo(db: Session, activo: str) -> list[int]:
    """`fuente_id` que componen un ACTIVO, vía `core.map_campo_activo`.

    Fuente ÚNICA de la composición del activo: la usan el tablero (F2) y el
    chat (F4), de modo que no pueden divergir.

    D-A3 (2026-07-16) — **no se rescatan fuentes con `campo` NULL usando
    `nombre`**: son ruido de ingesta y el rescate alteraba cifras ya validadas
    (Chichimene sumaba +56.003 bl al colar 3 filas NULL homónimas).
    """
    clave = norm(activo)
    if not clave:
        return []

    indice = _indice(db)
    campos = [campo for campo, act in indice.items() if norm(act) == clave]
    if not campos:
        return []

    filas = db.execute(
        text(
            "SELECT fuente_id, campo FROM core.dim_fuente "
            "WHERE NULLIF(TRIM(campo),'') IS NOT NULL"
        )
    ).all()
    campos_set = set(campos)
    return sorted(
        int(fuente_id) for fuente_id, campo in filas if norm(campo) in campos_set
    )


def campos_de_activo(db: Session, activo: str) -> list[str]:
    """Campos que componen un ACTIVO, según el catálogo.

    Independiente de si tienen datos: es el catálogo, no el fact. Sustituye al
    `data/Activo_campo.csv` que usaban las rutas Flask del origen — dos fuentes
    del mismo mapa hacían que el panel de Diferidas discrepara del tablero para
    la misma entidad (H11).
    """
    filas = db.execute(
        text(
            "SELECT campo FROM core.map_campo_activo "
            "WHERE UPPER(TRIM(activo)) = :activo ORDER BY campo"
        ),
        {"activo": (activo or "").strip().upper()},
    ).all()
    return [str(campo) for (campo,) in filas]


def activo_de_campo(db: Session, campo: str) -> str | None:
    """ACTIVO al que pertenece un CAMPO, o `None`.

    `None` es legítimo: un campo de un tercero, o uno ambiguo sin veredicto
    (AULLADOR). Dirección inversa de `campos_de_activo`.
    """
    resultado = db.execute(
        text("SELECT activo FROM core.map_campo_activo WHERE campo_norm = :campo"),
        {"campo": norm(campo)},
    ).scalar()
    return str(resultado) if resultado is not None else None
