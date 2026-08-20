"""Control 3 — revisión por lotes de la libreta. CLI interactivo.

    uv run python scripts/revisar_lote.py [--lote 30]

**Por qué existe además de la pantalla de Test Clas.** Revisar 200 casos
seguidos en una tabla del navegador es incómodo; aquí el revisor no suelta el
teclado. La UI sirve para inspeccionar y corregir sobre la marcha; esto, para
sesiones largas de vaciado de cola.

**Por qué vive en `scripts/` y no en `src/`.** Es interactivo (`input()` en
bucle), así que bajo `src/` contaría como código sin cubrir y arrastraría el
umbral de cobertura hacia abajo sin significar nada. La lógica que sí se puede
probar —el orden de la cola y el mapeo de teclas— vive en `src/features/consulta`
y tiene sus tests. Mismo criterio que los `humo_*.py` de F3.

Teclas:
    1/2/3/4  corrige a jerarquizar/cuantificar/analizar/desconocido
    Enter    confirma la clasificación del motor
    n        añade una nota y vuelve a pedir veredicto
    s        salta el caso (lo deja pendiente)
    q        sale

La etiqueta de revisión es la **verdad final**: cierra el caso aunque hubiera
señales previas.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — en un CLI, no poder reconfigurar no es fatal
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.features.consulta import libreta, senales  # noqa: E402
from src.features.consulta.revision import (  # noqa: E402
    GRUPOS_POR_TECLA,
    cola_de_revision,
)
from src.shared.db_auth import SessionLocal  # noqa: E402


def _pedir(mensaje: str) -> str:
    try:
        return input(mensaje).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "q"


def main() -> int:
    parser = argparse.ArgumentParser(description="Revisión por lotes de la libreta")
    parser.add_argument("--lote", type=int, default=30, help="cuántos casos traer")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # Se escanea PRIMERO (P4: sin scheduler): así la cola llega ya
        # priorizada justo cuando alguien se sienta a revisarla.
        resultado = senales.escanear(db)
        print(
            f"Señales: {resultado['sospechas_nuevas']} sospecha(s) nueva(s) "
            f"sobre {resultado['filas_revisadas']} pendiente(s).\n"
        )

        filas = cola_de_revision(db, limite=args.lote)
        if not filas:
            print("Cola vacía: no hay casos pendientes de veredicto.")
            return 0

        print(
            f"{len(filas)} caso(s) en cola.  "
            "1=jerarquizar 2=cuantificar 3=analizar 4=desconocido · "
            "Enter=confirmar · n=nota · s=saltar · q=salir\n"
        )

        for fila in filas:
            diag = f" · diag={fila['llm_diag']}" if fila["llm_diag"] else ""
            print(
                f"[{fila['id']}] ({fila['veredicto']} · {fila['capa_resolutora']}{diag})"
            )
            print(f"    «{fila['texto_pregunta']}»  →  motor: {fila['grupo_asignado']}")

            nota: str | None = None
            while True:
                respuesta = _pedir("    veredicto> ")

                if respuesta == "q":
                    print("Fin de la sesión de revisión.")
                    return 0
                if respuesta == "s":
                    break
                if respuesta == "n":
                    nota = _pedir("    nota> ") or None
                    continue
                if respuesta == "":
                    ok = libreta.poner_veredicto(
                        db, fila["id"], "confirmado_revision",
                        fuente="revision", nota=nota,
                    )  # fmt: skip
                    print("    ✓ confirmado" if ok else "    ⚠ no se pudo escribir")
                    break
                if respuesta in GRUPOS_POR_TECLA:
                    grupo = GRUPOS_POR_TECLA[respuesta]
                    # Corregir al MISMO grupo es confirmar: el revisor tecleó el
                    # número en vez de Enter, y registrar una "corrección" a lo
                    # que el motor ya dijo ensuciaría el dato de entrenamiento.
                    if grupo == fila["grupo_asignado"]:
                        ok = libreta.poner_veredicto(
                            db, fila["id"], "confirmado_revision",
                            fuente="revision", nota=nota,
                        )  # fmt: skip
                        print("    ✓ confirmado (mismo grupo)" if ok else "    ⚠ error")
                    else:
                        ok = libreta.poner_veredicto(
                            db, fila["id"], "corregido_revision",
                            grupo_correcto=grupo, fuente="revision", nota=nota,
                        )  # fmt: skip
                        print(f"    ✓ corregido → {grupo}" if ok else "    ⚠ error")
                    break

                print("    (1/2/3/4, Enter, n, s o q)")
            print()

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
