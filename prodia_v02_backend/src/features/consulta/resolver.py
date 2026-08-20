"""Nombre de entidad → identidad resuelta (nivel + valor + rama).

Portado de `consulta_v2/cuantificar/resolver.py` (230 líneas). Es la parte
**conversacional** que `shared/catalogo_entidades` dejó fuera a propósito en F2
(su docstring lo declara: "lo conversacional del origen es F4 y no entra aquí").

Aquí NO interviene el LLM: la política es determinista.

**Las tres reglas que resuelven las 151 colisiones de nombre reales** —el panel
Fundación las mostró contra el 139, con APIAY/CASTILLA/CUSIANA/CHICHIMENE/
RUBIALES como duras:

1. **Colapso por conjunto físico de `fuente_id`.** Si un nombre existe en
   varios niveles pero todos cubren exactamente las mismas fuentes, la colisión
   es *redundante* y se resuelve sola: RUBIALES es campo, activo y fuente a la
   vez, pero es el mismo dato. Solo si hay ≥2 conjuntos distintos se pregunta.
2. **Prioridad Campo (D-D5).** Si entre los grupos hay exactamente un campo y
   ninguna filial, se responde como Campo y se ofrece el activo como zoom.
3. **Puente de nivel (R2).** `dim_fuente.gerencia` NO es una lista pura de
   gerencias: 8 de sus 17 valores son VICEPRESIDENCIAS mal nombradas en el
   esquema de origen. Se marca `puente=True` para rotularlo bien, sin tocar el
   nivel con el que se consulta. **El cálculo se hace en vivo** (`vps - gers`),
   nunca con una lista fija: si la jerarquía cambia, se actualiza solo.

**Diferencias con el origen**, ambas deliberadas:

- **La sesión se inyecta**, no se toma de un engine global. Así los tests usan
  el doble de F1/F2 y ningún test sale a la red.
- **Las cachés van bajo lock con doble chequeo** (A1). El origen usa `global X;
  if X is not None`, así que N peticiones concurrentes construyen el índice N
  veces — y este hace 7 consultas.
"""

from __future__ import annotations

import threading
from typing import Any, TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.features.consulta.normaliza import norm


class Identidad(TypedDict, total=False):
    """Una entidad resuelta. `zoom` lista los activos que la contienen cuando
    se aplicó la prioridad Campo; `puente` marca el level-shift de R2."""

    nivel: str
    rama: str
    valor: str
    zoom: list[dict[str, Any]]
    puente: bool


class Ambiguo(TypedDict):
    """Colisión genuina: el llamador debe contrapreguntar."""

    ambiguo: list[dict[str, Any]]


# nivel → (SQL de valores distintos, rama). Rama A = ECP, B = filial.
# ⚠️ U3: el SQL se copia IDÉNTICO del origen. El activo sale de
# `core.map_campo_activo`, NUNCA de `dim_fuente.activos` — ese es un bucket de
# portafolio que para APIAY agrupaba 13 campos cuando el activo real tiene 4.
_NIVELES: tuple[tuple[str, str, str], ...] = (
    (
        "fuente",
        "SELECT DISTINCT nombre FROM core.dim_fuente "
        "WHERE NULLIF(TRIM(nombre),'') IS NOT NULL",
        "A",
    ),
    (
        "campo",
        "SELECT DISTINCT campo FROM core.dim_fuente "
        "WHERE NULLIF(TRIM(campo),'') IS NOT NULL",
        "A",
    ),
    (
        "activo",
        "SELECT DISTINCT activo FROM core.map_campo_activo "
        "WHERE NULLIF(TRIM(activo),'') IS NOT NULL",
        "A",
    ),
    (
        "gerencia",
        "SELECT DISTINCT gerencia FROM core.dim_fuente "
        "WHERE NULLIF(TRIM(gerencia),'') IS NOT NULL",
        "A",
    ),
    (
        "operador",
        "SELECT DISTINCT operador FROM core.dim_fuente "
        "WHERE NULLIF(TRIM(operador),'') IS NOT NULL",
        "A",
    ),
    (
        "vicepresidencia",
        "SELECT DISTINCT codigo FROM core.dim_vicepresidencia "
        "WHERE NULLIF(TRIM(codigo),'') IS NOT NULL",
        "A",
    ),
    (
        "filial",
        "SELECT DISTINCT nombre FROM core.dim_empresa "
        "WHERE NULLIF(TRIM(nombre),'') IS NOT NULL",
        "B",
    ),
)

# Palabras funcionales que NO son entidades: evitan que el backstop de n-gramas
# tome "mes" o "crudo" por un nombre propio.
_STOP = frozenset(
    {
        "QUE",
        "ES",
        "DE",
        "DEL",
        "LA",
        "EL",
        "LO",
        "LOS",
        "LAS",
        "UN",
        "UNA",
        "EN",
        "Y",
        "O",
        "A",
        "AL",
        "POR",
        "PARA",
        "CON",
        "SIN",
        "SU",
        "SUS",
        "PRODUCCION",
        "PRODUJO",
        "PRODUCE",
        "CUANTO",
        "CUANTA",
        "CUANTOS",
        "COMO",
        "CUAL",
        "CUALES",
        "DAME",
        "MUESTRAME",
        "MES",
        "CRUDO",
        "GAS",
        "BLANCOS",
        "BARRILES",
        "ABRIL",
        "MAYO",
        "MARZO",
        "ENERO",
        "FEBRERO",
    }
)

# Columna de `dim_fuente` que define el conjunto físico de cada nivel.
_COLUMNA_FUENTE = {
    "fuente": "nombre",
    "campo": "campo",
    "gerencia": "gerencia",
    "operador": "operador",
}
_CLAVE_ACTIVO = "__activo__"

# Prioridad al colapsar una colisión: el Campo gana.
_PRIORIDAD = {"campo": 5, "activo": 3, "gerencia": 2, "fuente": 1, "pozo": 1}

_PUNTUACION = "¿?¡!.,;:()[]{}\"'`"


class _Caches:
    """Las tres cachés del resolver, juntas y bajo un solo lock."""

    def __init__(self) -> None:
        self.indice: dict[str, list[dict[str, Any]]] | None = None
        self.conjuntos: dict[str, dict[str, frozenset[int]]] | None = None
        self.vp_robustez: frozenset[str] | None = None
        self.lock = threading.Lock()


_CACHE = _Caches()


def reset_cache() -> None:
    """Vacía las cachés. Solo para tests."""
    with _CACHE.lock:
        _CACHE.indice = None
        _CACHE.conjuntos = None
        _CACHE.vp_robustez = None


# ── Índice invertido nombre → identidades ────────────────────────────────────


def _construir_indice(db: Session) -> dict[str, list[dict[str, Any]]]:
    idx: dict[str, list[dict[str, Any]]] = {}
    for nivel, sql, rama in _NIVELES:
        for (valor,) in db.execute(text(sql)):
            clave = norm(valor)
            if not clave:
                continue
            idx.setdefault(clave, []).append(
                {"nivel": nivel, "rama": rama, "valor": (valor or "").strip()}
            )
    return idx


def _indice(db: Session) -> dict[str, list[dict[str, Any]]]:
    en_cache = _CACHE.indice
    if en_cache is not None:
        return en_cache
    with _CACHE.lock:
        en_cache = _CACHE.indice
        if en_cache is not None:
            return en_cache
        construido = _construir_indice(db)
        _CACHE.indice = construido
        return construido


def resolver(texto: str, db: Session) -> list[dict[str, Any]]:
    """Match EXACTO contra el catálogo. `[]` si no hay ninguno."""
    return list(_indice(db).get(norm(texto), []))


def buscar_en_texto(texto: str, db: Session) -> tuple[str, list[dict[str, Any]]] | None:
    """Backstop: escanea por n-gramas, los largos primero.

    Los largos primero para que "CAÑO LIMON" gane a "LIMON". Los unigramas
    saltan `_STOP` porque si no "mes" o "crudo" se resolverían como entidad.
    """
    idx = _indice(db)
    palabras = [p for p in (w.strip(_PUNTUACION) for w in norm(texto).split()) if p]
    n = len(palabras)
    for tamano in range(min(n, 4), 0, -1):
        for inicio in range(0, n - tamano + 1):
            gram = " ".join(palabras[inicio : inicio + tamano])
            if tamano == 1 and gram in _STOP:
                continue
            hit = idx.get(gram)
            if hit:
                return gram, list(hit)
    return None


# ── Colapso por conjunto físico ──────────────────────────────────────────────


def _construir_conjuntos(db: Session) -> dict[str, dict[str, frozenset[int]]]:
    """Qué `fuente_id` cubre cada nombre, por nivel.

    Es lo que permite distinguir una colisión redundante (mismo dato con varios
    nombres) de una genuina (dos cosas distintas que se llaman igual).
    """
    acumulado: dict[str, dict[str, set[int]]] = {
        col: {} for col in _COLUMNA_FUENTE.values()
    }
    acumulado[_CLAVE_ACTIVO] = {}

    filas = db.execute(
        text("SELECT fuente_id, nombre, campo, gerencia, operador FROM core.dim_fuente")
    ).all()
    campo_a_activo = {
        r[0]: r[1]
        for r in db.execute(
            text("SELECT campo_norm, activo FROM core.map_campo_activo")
        )
    }

    for fila in filas:
        fuente_id = fila[0]
        for columna, valor in zip(_COLUMNA_FUENTE.values(), fila[1:], strict=True):
            if valor and str(valor).strip():
                acumulado[columna].setdefault(norm(valor), set()).add(fuente_id)
        campo = fila[2]
        if campo and str(campo).strip():
            activo = campo_a_activo.get(norm(campo))
            if activo:
                acumulado[_CLAVE_ACTIVO].setdefault(norm(activo), set()).add(fuente_id)

    return {
        col: {k: frozenset(v) for k, v in dic.items()} for col, dic in acumulado.items()
    }


def _conjuntos(db: Session) -> dict[str, dict[str, frozenset[int]]]:
    en_cache = _CACHE.conjuntos
    if en_cache is not None:
        return en_cache
    with _CACHE.lock:
        en_cache = _CACHE.conjuntos
        if en_cache is not None:
            return en_cache
        construido = _construir_conjuntos(db)
        _CACHE.conjuntos = construido
        return construido


def clave_fisica(ident: dict[str, Any], db: Session) -> tuple[Any, ...]:
    """Clave para agrupar candidatos de una misma colisión.

    Dos identidades con la misma clave son *el mismo dato con otro nombre*.
    """
    nivel = ident["nivel"]
    rama = ident.get("rama")
    clave = norm(ident["valor"])

    if rama == "B":
        return ("B", clave)
    if nivel == "vicepresidencia":
        return ("VICE", clave)
    if nivel == "activo":
        return ("F", _conjuntos(db)[_CLAVE_ACTIVO].get(clave, frozenset()))

    columna = _COLUMNA_FUENTE.get(nivel)
    if not columna:
        return (nivel, clave)
    return ("F", _conjuntos(db)[columna].get(clave, frozenset()))


# ── Política de colisión ─────────────────────────────────────────────────────


def _representante(grupo: list[dict[str, Any]]) -> dict[str, Any]:
    return max(grupo, key=lambda i: _PRIORIDAD.get(i["nivel"], 0))


def _resolver_colision(
    identidades: list[dict[str, Any]], db: Session
) -> tuple[str, dict[str, Any] | None, list[dict[str, Any]]]:
    """`("auto", rep, reps)` si es redundante; `("ask", None, reps)` si genuina."""
    grupos: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for ident in identidades:
        grupos.setdefault(clave_fisica(ident, db), []).append(ident)

    representantes = [_representante(g) for g in grupos.values()]
    if len(representantes) == 1:
        return ("auto", representantes[0], representantes)
    return ("ask", None, representantes)


def _prioridad_campo(
    representantes: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """D-D5: con exactamente un campo y ninguna filial, se responde como Campo.

    Los activos que también casaban se devuelven como `zoom`: la respuesta
    ofrece subir de nivel sin obligar a contrapreguntar.
    """
    if any(r.get("rama") == "B" for r in representantes):
        return None, []
    campos = [r for r in representantes if r["nivel"] == "campo"]
    if len(campos) != 1:
        return None, []
    return campos[0], [r for r in representantes if r["nivel"] == "activo"]


# ── Puente de nivel (R2) ─────────────────────────────────────────────────────


def _vp_robustez(db: Session) -> frozenset[str]:
    """Códigos que en robustez son EXCLUSIVAMENTE vicepresidencia.

    Se calcula en vivo como `vps - gers`: de los 17 valores de
    `dim_fuente.gerencia`, 8 son VP sin ambigüedad y 3 existen como ambas cosas
    —esos NO se relabelan, gana el nivel más específico—. Hardcodear la lista
    la dejaría obsoleta en cuanto cambie la jerarquía.

    Degrada con gracia: si `map_campo_robustez` no está, devuelve vacío y
    simplemente no se marca ningún puente.
    """
    en_cache = _CACHE.vp_robustez
    if en_cache is not None:
        return en_cache

    with _CACHE.lock:
        en_cache = _CACHE.vp_robustez
        if en_cache is not None:
            return en_cache
        try:
            vps = {
                v
                for (v,) in db.execute(
                    text(
                        "SELECT DISTINCT rob_vicepresidencia FROM core.map_campo_robustez "
                        "WHERE rob_vicepresidencia IS NOT NULL"
                    )
                )
            }
            gerencias = {
                v
                for (v,) in db.execute(
                    text(
                        "SELECT DISTINCT rob_gerencia FROM core.map_campo_robustez "
                        "WHERE rob_gerencia IS NOT NULL"
                    )
                )
            }
        except Exception:
            # Sin evidencia no se relabela nada. Nunca lanza: el puente es una
            # mejora de rótulo, no un requisito para responder.
            _CACHE.vp_robustez = frozenset()
            return _CACHE.vp_robustez

        calculado = frozenset(norm(v) for v in (vps - gerencias) if v)
        _CACHE.vp_robustez = calculado
        return calculado


def _marcar_puente(ident: dict[str, Any], db: Session) -> dict[str, Any]:
    """Marca `puente=True` si el nivel dice "gerencia" pero el valor es en
    realidad una vicepresidencia. **El nivel de consulta NO se toca**: solo
    cambia cómo se rotula la entidad en el texto."""
    if ident.get("nivel") == "gerencia" and norm(ident["valor"]) in _vp_robustez(db):
        ident["puente"] = True
    return ident


# ── Entrada pública ──────────────────────────────────────────────────────────


def resolver_unico(texto: str, db: Session) -> dict[str, Any] | None:
    """Resuelve el texto a UNA identidad, o declara la ambigüedad.

    - Sin match → `None`.
    - Una identidad → esa.
    - Colisión redundante → automática, con el representante de mayor nivel.
    - Colisión con un solo campo → Campo directo, con zoom a activo (D-D5).
    - Colisión genuina → `{"ambiguo": [...]}`, y el llamador contrapregunta.
    """
    identidades = resolver(texto, db)
    if not identidades:
        # No hubo match exacto: quizá llegó la frase entera en vez del nombre.
        hit = buscar_en_texto(texto, db)
        if hit:
            identidades = hit[1]
    if not identidades:
        return None

    if len(identidades) == 1:
        resuelta = dict(identidades[0])
        resuelta["zoom"] = []
        return _marcar_puente(resuelta, db)

    modo, representante, representantes = _resolver_colision(identidades, db)
    zoom: list[dict[str, Any]] = []
    if modo == "ask":
        rep_campo, zoom = _prioridad_campo(representantes)
        if rep_campo is not None:
            modo, representante = "auto", rep_campo

    if modo == "auto" and representante is not None:
        resuelta = dict(representante)
        resuelta["zoom"] = zoom
        return _marcar_puente(resuelta, db)

    return {"ambiguo": representantes}
