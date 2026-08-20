"""Prueba de humo del chat COMPLETO: de la pregunta a la cifra.

    cd prodia_v02_backend
    uv run python scripts/humo_chat.py
    uv run python scripts/humo_chat.py "cuanto produjo Castilla"

**Por qué existe.** Los 819 tests prueban cada módulo del motor por separado y
los golden miden clasificación y slots. Ninguno recorría el camino entero
—pregunta → clasificar → resolver entidad → ejecutar → panel—, y por eso el
motor pudo quedar SIN CONECTAR sin que nada se pusiera rojo: `maquina.py`
devolvía `panel: None` siempre y el chat contestaba «entendí que preguntas
por CASTILLA» sin dar un solo número.

Este script recorre ese camino contra el Postgres real. Requiere VPN.
Sale con código 1 si alguna pregunta no produce panel.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.features.analisis.repositories import AnalisisRepository  # noqa: E402
from src.features.analisis.services_desempeno import (  # noqa: E402
    DesempenoService,
    escenario_mes,
)
from src.features.consulta import maquina, resolver  # noqa: E402
from src.features.consulta.ejecutor import ejecutar  # noqa: E402
from src.features.consulta.slots import extraer_slots  # noqa: E402
from src.shared.db_prod import (  # noqa: E402
    check_prod_connection,
    get_prod_session_factory,
)

PREGUNTAS = [
    "cuanto produjo Castilla",
    "produccion de crudo de Castilla",
    "cuanto gas produjo Cusiana",
    "produccion acumulada de Castilla",
]


def _despachador(db: Any):
    """Mismo cableado que `api.py`. Si divergen, este script deja de valer."""

    def _despachar(texto: str, nucleo: dict[str, Any]) -> dict[str, Any] | None:
        if nucleo["grupo"] != "cuantificar":
            return None
        cruda = nucleo.get("entidad_cruda")
        if not cruda:
            return None

        candidatos = resolver.resolver(str(cruda), db)
        if not candidatos:
            hit = resolver.buscar_en_texto(texto, db)
            candidatos = list(hit[1]) if hit else []
        if len(candidatos) != 1:
            return None

        resuelta = candidatos[0]
        slots = extraer_slots(texto, str(resuelta.get("valor") or cruda))
        servicio = DesempenoService(AnalisisRepository(db))

        def _escenario(
            entidad: str,
            nivel: str | None = None,
            periodo: str | None = None,
            escenarios: tuple[str, ...] = ("OPERATIVO", "CONTABLE"),
        ) -> dict[str, dict[str, float]]:
            return escenario_mes(
                AnalisisRepository(db),
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
            return {"mensaje": str(salida.get("texto") or ""), "panel": None}
        return {"mensaje": str(salida.get("texto") or ""), "panel": {"datos": salida}}

    return _despachar


def main() -> int:
    preguntas = sys.argv[1:] or PREGUNTAS

    if not check_prod_connection():
        print("\n[ABORTA] db_prod no responde. Este script necesita VPN.")
        return 1

    fabrica = get_prod_session_factory()
    fallos = 0

    with fabrica() as db:

        def _detectar(texto: str) -> str | None:
            hit = resolver.buscar_en_texto(texto, db)
            return hit[0] if hit else None

        for pregunta in preguntas:
            print()
            print("=" * 74)
            print(f"  «{pregunta}»")
            print("=" * 74)
            try:
                r = maquina.clasificar(
                    pregunta,
                    detectar_entidad=_detectar,
                    despachar=_despachador(db),
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  [REVENTÓ] {exc}")
                traceback.print_exc()
                fallos += 1
                continue

            print(f"  grupo   : {r['grupo']} (capa: {r['capa_resolutora']})")
            print(f"  entidad : {r['entidad_cruda']}")
            print(f"  mensaje : {r['mensaje']}")

            panel = r.get("panel")
            if panel:
                datos = panel.get("datos", {})
                print(
                    f"  PANEL   : nivel={datos.get('nivel')} "
                    f"producto={datos.get('producto')}"
                )
                res = datos.get("resultado") or {}
                print(f"            valor={res.get('valor')} {datos.get('unidad')}")
                print(f"            cumplimiento={datos.get('cumplimiento_pct')}%")
            else:
                print("  PANEL   : NINGUNO  <-- el chat no daría ninguna cifra")
                fallos += 1

    print()
    print("=" * 74)
    print(f"  Preguntas sin panel: {fallos} de {len(preguntas)}")
    print("=" * 74)
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
