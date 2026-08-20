"""Gate de paridad de F6 — ¿puede ProdIA V02 reemplazar al sistema viejo?

    cd prodia_v02_backend
    uv run python scripts/humo_paridad.py

**Por qué existe.** El corte del sistema viejo (F6, Bloque 5) es la única
operación irreversible del proyecto: se borran ~10.700 líneas y se poda un
`routes/api.py` que el chatbot clásico comparte. Antes de eso hay que
demostrar —no suponer— que V02 devuelve los mismos números.

Las anclas son las de CLAUDE.md §6, y no son decorativas: cada una nació de un
bug real del sistema viejo. La de Castilla es la más importante porque es la
**única que nunca se ha comprobado** (DT-8) y la única que cruza `db_ops`.

**No es un test de pytest**, por la misma razón que `humo_tablas.py` y el
runner del golden: sale a la red (Postgres del 139, VPN) y CI no levanta
ninguna base de datos. Se ejecuta a mano, contra el entorno real.

Sale con **código 1 si alguna ancla no coincide**, para poder usarlo como
verificación automatizable y como criterio de "no cortar todavía".
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any

# La consola de Windows suele ser cp1252 y revienta al imprimir símbolos fuera
# de latin-1. Mismo arreglo que el runner del golden.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.shared.db_ops import (  # noqa: E402
    check_ops_connection,
    get_ops_session_factory,
)
from src.shared.db_prod import (  # noqa: E402
    check_prod_connection,
    get_prod_session_factory,
)

# ── Las anclas de CLAUDE.md §6 ────────────────────────────────────────────
#
# Castilla: 78.629 kUSD. Verificar el AÑO/MES contra el que se midió en el
# sistema viejo antes de darla por buena — el ancla es del valor, y el valor
# depende del periodo.
ANCLA_CASTILLA_KUSD = 78_629
ANCLA_DATOS_MES = 7_776
ANCLA_TD_DATOS_DIA = 5_209

# Tolerancia del EBITDA: es un cálculo en coma flotante sobre agregados, así
# que exigir igualdad exacta al peso sería frágil. 0,5 kUSD sobre 78.629 es
# ~0,0006 %: suficiente para detectar un error de fórmula o de unidad, que es
# lo que este gate busca, y no para fallar por redondeo.
TOLERANCIA_KUSD = 0.5


class Resultado:
    def __init__(self) -> None:
        self.fallos: list[str] = []
        self.omitidos: list[str] = []
        self.ok: list[str] = []

    def acierto(self, nombre: str, detalle: str) -> None:
        self.ok.append(f"{nombre}: {detalle}")
        print(f"  [OK]      {nombre} — {detalle}")

    def fallo(self, nombre: str, detalle: str) -> None:
        self.fallos.append(f"{nombre}: {detalle}")
        print(f"  [FALLO]   {nombre} — {detalle}")

    def omitido(self, nombre: str, motivo: str) -> None:
        self.omitidos.append(f"{nombre}: {motivo}")
        print(f"  [OMITIDO] {nombre} — {motivo}")


def _encabezado(texto: str) -> None:
    print()
    print("=" * 74)
    print(f"  {texto}")
    print("=" * 74)


def _conteo(sesion: Any, tabla: str) -> int:
    from sqlalchemy import text

    fila = sesion.execute(text(f"SELECT count(*) FROM {tabla}")).scalar()
    return int(fila or 0)


def verificar_anclas_de_ingesta(res: Resultado) -> None:
    """`DATOS_MES` = 7.776 filas · `TD_datos_dia` = 5.209 filas.

    Estas dos ya se verificaron en F3 contra un `.xlsm` real. Se repiten aquí
    porque el gate tiene que ser autosuficiente: quien lo ejecute antes de
    cortar no debería tener que confiar en una medición de otra fase.
    """
    _encabezado("Anclas de ingesta (F3)")

    if not check_prod_connection():
        res.omitido(
            "DATOS_MES / TD_datos_dia",
            "db_prod no responde — ¿VPN caída o PROD_DATABASE_URL sin configurar?",
        )
        return

    fabrica = get_prod_session_factory()
    with fabrica() as sesion:
        for tabla, esperado in (
            ("DATOS_MES", ANCLA_DATOS_MES),
            ("TD_datos_dia", ANCLA_TD_DATOS_DIA),
        ):
            try:
                obtenido = _conteo(sesion, f'"{tabla}"')
            except Exception as exc:  # noqa: BLE001
                res.fallo(tabla, f"la consulta reventó: {exc}")
                continue

            if obtenido == esperado:
                res.acierto(tabla, f"{obtenido:,} filas".replace(",", "."))
            else:
                res.fallo(
                    tabla,
                    f"esperado {esperado:,} filas, obtenido {obtenido:,}".replace(
                        ",", "."
                    ),
                )


def verificar_ancla_castilla(res: Resultado, anio: int, mes: int) -> None:
    """Castilla EBITDA = 78.629 kUSD — el ancla que nunca se ha comprobado.

    Es la única que cruza `db_ops` (base `robustez_v02`, esquema `ops`), y por
    eso es la que más riesgo cubre: valida a la vez la conexión, la jerarquía
    de entidades y la fórmula del waterfall.
    """
    _encabezado(f"Ancla de EBITDA — Castilla, {mes:02d}/{anio} (DT-8)")

    if not check_ops_connection():
        res.omitido(
            "Castilla EBITDA",
            "db_ops no responde — OPS_DATABASE_URL vacía o sin VPN. "
            "OJO: la clave lleva '£' y debe ir como %C2%A3",
        )
        return

    from src.features.ebitda.repositories import EbitdaRepository
    from src.features.ebitda.services import EbitdaService

    fabrica = get_ops_session_factory()
    try:
        with fabrica() as sesion:
            servicio = EbitdaService(EbitdaRepository(sesion))
            salida = servicio.waterfall(anio, mes, nivel="campo", entidad="CASTILLA")
    except Exception as exc:  # noqa: BLE001
        res.fallo("Castilla EBITDA", f"la consulta reventó: {exc}")
        traceback.print_exc()
        return

    # El EBITDA es el componente final del waterfall; el nombre exacto de la
    # clave se resuelve mirando la salida, no adivinando.
    valor = _extraer_ebitda(salida)
    if valor is None:
        res.fallo(
            "Castilla EBITDA",
            "la respuesta no trae ningún componente reconocible de EBITDA",
        )
        return

    delta = abs(valor - ANCLA_CASTILLA_KUSD)
    detalle = f"{valor:,.1f} kUSD (ancla {ANCLA_CASTILLA_KUSD:,})".replace(",", ".")
    if delta <= TOLERANCIA_KUSD:
        res.acierto("Castilla EBITDA", detalle)
    else:
        res.fallo("Castilla EBITDA", f"{detalle} — diferencia de {delta:,.1f} kUSD")


def _extraer_ebitda(salida: Any) -> float | None:
    """Saca el EBITDA de la respuesta del waterfall.

    Tolerante a la forma exacta del schema a propósito: si un día se renombra
    un campo, este script debe fallar diciendo "no lo encuentro", no callarse
    devolviendo cero — que es justo el fallo silencioso que el ancla busca
    evitar (A5: la conversión mal aplicada no dio error, dio un número mil
    veces menor).
    """
    for atributo in ("ebitda", "total", "valor_final"):
        valor = getattr(salida, atributo, None)
        if isinstance(valor, (int, float)):
            return float(valor)

    componentes = getattr(salida, "componentes", None) or []
    for comp in componentes:
        etiqueta = str(getattr(comp, "label", "") or "").strip().lower()
        if "ebitda" in etiqueta:
            valor = getattr(comp, "valor", None)
            if isinstance(valor, (int, float)):
                return float(valor)
    return None


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Gate de paridad de F6 — anclas de CLAUDE.md §6"
    )
    parser.add_argument("--anio", type=int, default=2026)
    parser.add_argument("--mes", type=int, default=5)
    args = parser.parse_args()

    print()
    print("GATE DE PARIDAD — ProdIA V02 vs. sistema viejo")
    print("Requiere VPN. No modifica nada: solo lee.")

    res = Resultado()
    verificar_anclas_de_ingesta(res)
    verificar_ancla_castilla(res, args.anio, args.mes)

    _encabezado("RESUMEN")
    print(f"  Coinciden : {len(res.ok)}")
    print(f"  Fallan    : {len(res.fallos)}")
    print(f"  Omitidas  : {len(res.omitidos)}")

    if res.omitidos:
        print()
        print("  ⚠️  Una ancla OMITIDA no es una ancla verificada. El corte del")
        print("      sistema viejo no debe ejecutarse hasta que las tres pasen.")

    if res.fallos:
        print()
        print("  ⛔ NO CORTAR. Hay anclas que no coinciden:")
        for f in res.fallos:
            print(f"      - {f}")
        return 1

    if res.omitidos:
        return 1

    print()
    print("  ✅ Las tres anclas coinciden. La paridad está demostrada.")
    print("     Falta la verificación en navegador (R3) antes del Bloque 5.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
