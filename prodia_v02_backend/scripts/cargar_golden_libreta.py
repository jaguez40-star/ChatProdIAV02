"""Carga los casos del golden en la libreta, para verlos en Test Clas.

    uv run python scripts/cargar_golden_libreta.py [--confirmar-produccion]

**Por qué existe.** El golden es el EXAMEN del clasificador y vive en un YAML;
por diseño (H3 del origen) el runner clasifica con `log=False` para no ensuciar
la cola de revisión con casos sintéticos. Pero el revisor necesita **ver** esos
75 casos junto al tráfico real: es lo que permite comparar «cómo clasifica lo
que ya sabemos» contra «cómo clasifica lo que llega».

**Tres propiedades que se conservan del origen:**

1. **Idempotente** — borra las filas `usuario='golden'` antes de insertar. Solo
   toca lo que él mismo creó; jamás roza el tráfico real.
2. **Distinguible** — `usuario='golden'`, para poder filtrarlo o excluirlo.
3. **Fuera de la cola** — cada fila se marca confirmada o corregida según el
   YAML, así que **no entra a pendientes**. La cola sigue mostrando solo lo que
   de verdad falta revisar; si los 75 casos aterrizaran ahí, taparían el tráfico
   real que es lo que aporta información nueva.

**Y una que se añade.** El script del origen imprime a qué base apunta y confía
en que el operador lea. Aquí **se niega a escribir** si no es una base local,
salvo `--confirmar-produccion` explícito — mismo criterio que `humo_ingesta.py`
de F3, y por la misma razón: escribir en la libreta del 139 por accidente
contaminaría el dato que alimenta el crecimiento del golden.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — en un CLI, no poder reconfigurar no es fatal
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.features.consulta import libreta  # noqa: E402
from src.features.consulta.maquina import clasificar_nucleo  # noqa: E402
from src.shared.db_auth import SessionLocal  # noqa: E402

USUARIO = "golden"

_GOLDEN = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "features"
    / "consulta"
    / "golden"
    / "clasificacion_golden.yaml"
)


def _sin_entidad(_texto: str) -> str | None:
    """Detector nulo: el golden mide las capas del clasificador, no el catálogo.

    Con un detector real haría falta VPN, y la resolución de entidades
    enmascararía qué está decidiendo cada capa. Mismo criterio que
    `golden_consulta.py`.
    """
    return None


def _es_local(url: str) -> bool:
    return "localhost" in url or "127.0.0.1" in url or url.startswith("sqlite")


def main() -> int:
    parser = argparse.ArgumentParser(description="Carga el golden en la libreta")
    parser.add_argument(
        "--confirmar-produccion",
        action="store_true",
        help="permite escribir en una base que no es local",
    )
    args = parser.parse_args()

    url = get_settings().database_url
    print(f"Base objetivo: {url}")
    if not _es_local(url) and not args.confirmar_produccion:
        print("ABORTADO: la base no es local y este script ESCRIBE.")
        print("Si es lo que quieres, repite con --confirmar-produccion.")
        return 1

    casos: Any = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8"))
    if not isinstance(casos, list):
        print(f"{_GOLDEN.name}: se esperaba una lista de casos.")
        return 1
    print(f"Casos en el golden: {len(casos)}")

    db = SessionLocal()
    try:
        borradas = db.execute(
            text("DELETE FROM clasificacion_log WHERE usuario = :u"), {"u": USUARIO}
        ).rowcount
        db.commit()
        if borradas:
            print(f"Limpieza: {borradas} fila(s) 'golden' previas borradas.")

        aciertos = fallos = 0
        for indice, caso in enumerate(casos, start=1):
            pregunta = str(caso["pregunta"])
            esperado = str(caso["esperado"])

            resultado = clasificar_nucleo(pregunta, detectar_entidad=_sin_entidad)
            obtenido = str(resultado["grupo"])
            capa = str(resultado["capa_resolutora"])
            acierta = obtenido == esperado
            aciertos, fallos = (
                (aciertos + 1, fallos) if acierta else (aciertos, fallos + 1)
            )

            log_id = libreta.registrar(
                db,
                texto=pregunta,
                grupo=obtenido,
                capa=capa,
                entidad=resultado.get("entidad_cruda"),
                llm_diag=resultado.get("llm_diag"),
                usuario=USUARIO,
                conversacion_id=USUARIO,
            )
            if log_id is not None:
                # El golden ya trae la respuesta correcta escrita a mano, así que
                # el veredicto se conoce sin que nadie tenga que juzgarlo.
                libreta.poner_veredicto(
                    db,
                    log_id,
                    "confirmado_revision" if acierta else "corregido_revision",
                    grupo_correcto=None if acierta else esperado,
                    fuente="revision",
                    nota="golden set — respuesta esperada escrita a mano",
                )

            marca = "OK " if acierta else "!! "
            print(
                f"  [{indice:2}/{len(casos)}] {marca}{obtenido:<12} "
                f"(esperado {esperado:<12}) vía {capa:<14} · {pregunta[:50]}"
            )

        print(f"\nResumen: {aciertos} aciertos · {fallos} fallos de {len(casos)}")
        resumen = libreta.resumir(db)
        print(
            f"Libreta: {resumen['total']} filas · "
            f"pct_capa1 = {resumen['pct_capa1']}%"
        )
        print("Listo. Abre Test Clas en el navegador para verlos.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
