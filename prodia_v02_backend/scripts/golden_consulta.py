"""Gate de los golden sets del Motor Q — script CLI, NO un test.

    uv run python scripts/golden_consulta.py [--set clasificacion|cuantificar|analizar]

**Por qué no es un test de pytest (H7).** El golden ejercita el motor de
verdad: la Capa 2 llama a Ollama y la resolución de entidades consulta el
Postgres del 139. La regla del proyecto es que ningún test sale a la red, y CI
no levanta ninguno de los dos servicios. El sistema de origen tiene el mismo
problema y lo advierte en su propio runner: *"⚠️ NO correr en dev: abre
conexión a Postgres varias veces"*.

Así que esto se ejecuta a mano, contra un entorno con VPN y modelo disponible,
y su resultado se reporta — no bloquea el build.

**Dos métricas, no una:**

- **Exactitud, gate ≥90 %.** Cuántas preguntas se clasifican en su grupo.
- **% resuelto por Capa 1** (regex pura), que NO bloquea. Si baja del 50 %, el
  motor depende demasiado del LLM: hay que engordar patrones antes de dar la
  fase por cerrada. Es una señal de diseño, no un fallo.

Política de crecimiento del origen, que se conserva: *"toda corrección
verificada de la libreta entra aquí con su etiqueta correcta. **Nunca sacar un
caso**"* — cada uno es una regresión permanente.
"""

from __future__ import annotations

import argparse
import sys

# La consola de Windows suele ser cp1252 y revienta al imprimir simbolos
# fuera de latin-1. Mismo arreglo que usa el sistema de origen.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from pathlib import Path
from typing import Any

import yaml

# El script se invoca desde `prodia_v02_backend/`, así que `src` es importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.features.consulta import subrouter  # noqa: E402
from src.features.consulta.maquina import clasificar_nucleo  # noqa: E402
from src.features.consulta.slots import extraer_slots  # noqa: E402

_DIR_GOLDEN = (
    Path(__file__).resolve().parent.parent / "src" / "features" / "consulta" / "golden"
)

GATE = 90


def _casos(nombre: str) -> list[dict[str, Any]]:
    ruta = _DIR_GOLDEN / f"{nombre}_golden.yaml"
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    if not isinstance(datos, list):
        raise SystemExit(f"{ruta.name}: se esperaba una lista de casos")
    return datos


def _sin_entidad(_texto: str) -> str | None:
    """Detector nulo.

    El golden de clasificación mide la CAPA 1 y la CAPA 2, no el catálogo. Con
    un detector real, la resolución de entidades enmascararía qué está
    decidiendo cada capa — y además exigiría VPN para todos los casos.
    """
    return None


def _correr_clasificacion() -> int:
    casos = _casos("clasificacion")
    aciertos = 0
    por_capa: dict[str, int] = {}
    fallos: list[tuple[str, str, str]] = []

    for caso in casos:
        pregunta = caso["pregunta"]
        esperado = caso["esperado"]
        resultado = clasificar_nucleo(pregunta, detectar_entidad=_sin_entidad)
        obtenido = resultado["grupo"]
        capa = resultado["capa_resolutora"]

        por_capa[capa] = por_capa.get(capa, 0) + 1
        if obtenido == esperado:
            aciertos += 1
        else:
            fallos.append((pregunta, esperado, obtenido))

    total = len(casos)
    pct = 100 * aciertos // total if total else 0
    regex = por_capa.get("regex", 0)
    pct_regex = 100 * regex // total if total else 0

    print(f"\nEXACTITUD: {aciertos}/{total} = {pct}%   (gate: >={GATE}%)")
    print(f"CAPA 1 (regex pura): {regex}/{total} = {pct_regex}%")
    if pct_regex < 50:
        print("  AVISO: menos del 50 % lo resuelve la regex; el motor depende")
        print("         demasiado del LLM. Engordar patrones antes de cerrar.")
    for capa, n in sorted(por_capa.items()):
        print(f"  {capa}: {n}")

    if fallos:
        print("\nFALLOS:")
        for pregunta, esperado, obtenido in fallos:
            print(f"  - «{pregunta}»  esperado={esperado}  obtenido={obtenido}")

    return 0 if pct >= GATE else 1


def _correr_cuantificar() -> int:
    """Valida los SLOTS, que son 100 % deterministas.

    No se valida la cifra: cambia con cada ingesta. Lo que tiene que ser
    estable es cómo se interpreta la pregunta.
    """
    casos = _casos("cuantificar")
    aciertos = 0
    fallos: list[str] = []

    for caso in casos:
        pregunta = caso["pregunta"]
        slots = extraer_slots(pregunta)

        problemas = []
        for clave in ("nivel_temporal", "producto", "referencia"):
            esperado = caso.get(clave)
            if esperado is not None and slots.get(clave) != esperado:
                problemas.append(
                    f"{clave}: esperado={esperado} obtenido={slots.get(clave)}"
                )

        if problemas:
            fallos.append(f"«{pregunta}» → {', '.join(problemas)}")
        else:
            aciertos += 1

    total = len(casos)
    pct = 100 * aciertos // total if total else 0
    print(f"\nEXACTITUD: {aciertos}/{total} = {pct}%   (gate: >={GATE}%)")
    if fallos:
        print("\nFALLOS:")
        for f in fallos:
            print(f"  - {f}")

    return 0 if pct >= GATE else 1


def _correr_analizar() -> int:
    """Valida la sub-intención. No usa BD ni LLM: es regex pura."""
    casos = _casos("analizar")
    aciertos = 0
    fallos: list[str] = []

    for caso in casos:
        pregunta = caso["pregunta"]
        esperado = caso.get("sub")
        obtenido = subrouter.sub_intencion(pregunta)
        if esperado is None or obtenido == esperado:
            aciertos += 1
        else:
            fallos.append(f"«{pregunta}» esperado={esperado} obtenido={obtenido}")

    total = len(casos)
    pct = 100 * aciertos // total if total else 0
    print(f"\nEXACTITUD: {aciertos}/{total} = {pct}%   (gate: >={GATE}%)")
    if fallos:
        print("\nFALLOS:")
        for f in fallos:
            print(f"  - {f}")

    return 0 if pct >= GATE else 1


_RUNNERS = {
    "clasificacion": _correr_clasificacion,
    "cuantificar": _correr_cuantificar,
    "analizar": _correr_analizar,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate de los golden sets del Motor Q")
    parser.add_argument(
        "--set",
        dest="conjunto",
        choices=sorted(_RUNNERS),
        help="Cuál correr. Sin este flag, corre los tres.",
    )
    args = parser.parse_args()

    conjuntos = [args.conjunto] if args.conjunto else sorted(_RUNNERS)
    salida = 0
    for nombre in conjuntos:
        print(f"\n{'=' * 60}\n{nombre.upper()}\n{'=' * 60}")
        salida |= _RUNNERS[nombre]()

    return salida


if __name__ == "__main__":
    raise SystemExit(main())
