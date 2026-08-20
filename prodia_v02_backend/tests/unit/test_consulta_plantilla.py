"""Plantilla de análisis — Q2 (REGLA CERO) y Q4 (cobertura en cabecera).

Los dos tests que dan sentido al archivo son
`test_sin_rezago_se_declara_no_se_fabrica` y
`test_sin_meta_no_es_lo_mismo_que_ir_al_cero_por_ciento`: fijan las tres ramas
de Q2, que es la regla que nació de una alucinación real del LLM.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.features.consulta.plantilla import (
    causal,
    diferidas,
    economia,
    proyeccion,
    rezagados,
)
from src.features.consulta.subrouter import sub_intencion

pytestmark = pytest.mark.unit


def _datos(titular: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "meta": {"scope": "el Campo CASTILLA", "periodo": "Mayo 2026"},
        "titular": titular,
        "tarjetas": [],
        "causas": {},
    }
    base.update(extra)
    return base


# ═════════════════════════════════════════════════════════════════════════════
# Q2 — REGLA CERO
# ═════════════════════════════════════════════════════════════════════════════


def test_sin_rezago_se_declara_no_se_fabrica() -> None:
    """🔑 Q2. Un LLM alucinó un déficit inexistente con Castilla al 102,7 % de
    cumplimiento; de ahí nace esta regla. Aquí es código, no una instrucción."""
    datos = _datos([{"producto": "CRUDO", "valor_pct": 102.7, "texto": "—"}])
    texto = causal(datos, "CASTILLA")

    assert "no hay rezago" in texto
    assert "102.7%" in texto or "102.7" in texto
    # Y no aparece nada que suene a faltante inventado.
    assert "faltante" not in texto.lower() or "no hay faltante" in texto.lower()


def test_sin_meta_no_es_lo_mismo_que_ir_al_cero_por_ciento() -> None:
    """🔑 Q2, tercer estado. `valor_pct is None` significa que no hay meta, no
    que el cumplimiento sea cero. Confundirlos inventaría un incumplimiento."""
    datos = _datos([{"producto": "CRUDO", "valor_pct": None}])
    texto = causal(datos, "CASTILLA")

    assert "ningún producto tiene meta definida" in texto
    assert "no hay cumplimiento que evaluar" in texto


def test_con_rezago_si_se_explica() -> None:
    datos = _datos(
        [{"producto": "CRUDO", "valor_pct": 87.0, "faltante_abs": -500_000}],
        causas={"CRUDO": ["falla eléctrica en la estación"]},
    )
    texto = causal(datos, "CASTILLA")

    assert "87.0%" in texto
    assert "falla eléctrica" in texto


def test_rezagados_exige_meta_y_estar_por_debajo() -> None:
    """La condición es doble: sin meta no hay rezago, solo ausencia de vara."""
    datos = _datos(
        [
            {"producto": "CRUDO", "valor_pct": 87.0},  # rezagado
            {"producto": "GAS", "valor_pct": 105.0},  # cumple
            {"producto": "BLANCOS", "valor_pct": None},  # sin meta
        ]
    )
    assert [t["producto"] for t in rezagados(datos)] == ["CRUDO"]


def test_acotado_a_un_producto_sin_rezago_no_lista_los_otros() -> None:
    """Si el usuario preguntó por el gas, no se le responde sobre el crudo."""
    datos = _datos(
        [
            {"producto": "CRUDO", "valor_pct": 80.0},
            {"producto": "GAS", "valor_pct": 110.0, "texto": "—"},
        ]
    )
    texto = causal(datos, "CASTILLA", producto="GAS")

    assert "gas" in texto
    assert "no hay rezago" in texto
    assert "crudo" not in texto


def test_el_delta_aporta_contexto_aunque_no_haya_rezago() -> None:
    """Ir al 101 % de una meta baja no es lo mismo que ir al 101 % estando
    por encima del histórico."""
    datos = _datos(
        [{"producto": "CRUDO", "valor_pct": 101.0}],
        tarjetas=[
            {
                "producto": "CRUDO",
                "proyectado_cierre": 1_200_000,
                "hist_prom": 1_000_000,
            }
        ],
    )
    texto = causal(datos, "CASTILLA")

    assert "DELTA" in texto
    assert "por encima de" in texto


# ═════════════════════════════════════════════════════════════════════════════
# Q4 — cobertura parcial en cabecera
# ═════════════════════════════════════════════════════════════════════════════


def test_la_cobertura_parcial_va_primera_y_nombra_los_campos() -> None:
    """🔑 Q4. Medido en el origen: NARE tiene 1 de 8 campos. Servir el EBITDA
    de un campo como "el EBITDA de NARE" sería mentir por omisión."""
    datos = {"components": [{"key": "ebitda", "label": "EBITDA", "valueKusd": 1000}]}
    texto = economia(datos, "NARE", nivel="activo", incluidos=["NARE"], total=8)

    lineas = texto.split("\n")
    # La salvedad es la PRIMERA línea del cuerpo, no una nota al pie.
    assert "COBERTURA PARCIAL" in lineas[1]
    assert "1 de 8 campos" in lineas[1]
    assert "NARE" in lineas[1]


def test_la_cobertura_parcial_cambia_el_sujeto_de_las_cifras() -> None:
    """No es solo un banner: las cifras dejan de ser "de esta entidad"."""
    datos = {"components": [{"key": "ebitda", "label": "EBITDA", "valueKusd": 1000}]}
    texto = economia(datos, "NARE", nivel="activo", incluidos=["NARE"], total=8)

    assert "de esos 1 campos" in texto
    assert "de esta entidad" not in texto


def test_con_cobertura_completa_no_hay_salvedad() -> None:
    datos = {"components": [{"key": "ebitda", "label": "EBITDA", "valueKusd": 1000}]}
    texto = economia(datos, "CASTILLA", nivel="campo", incluidos=["CASTILLA"], total=1)

    assert "COBERTURA PARCIAL" not in texto
    assert "de esta entidad" in texto


def test_sin_cifras_economicas_lo_dice() -> None:
    texto = economia({"components": []}, "CASTILLA", nivel="campo")
    assert "no hay cifras económicas" in texto


# ═════════════════════════════════════════════════════════════════════════════
# Proyección y diferidas
# ═════════════════════════════════════════════════════════════════════════════


def test_la_proyeccion_compara_contra_la_meta() -> None:
    datos = _datos(
        [],
        tarjetas=[
            {"producto": "CRUDO", "proyectado_cierre": 900_000, "meta_mes": 1_000_000}
        ],
    )
    texto = proyeccion(datos, "CASTILLA")

    assert "90.0% de su meta" in texto


def test_la_proyeccion_sin_meta_lo_declara() -> None:
    """Sin meta no se inventa un porcentaje."""
    datos = _datos(
        [],
        tarjetas=[
            {"producto": "CRUDO", "proyectado_cierre": 900_000, "meta_mes": None}
        ],
    )
    texto = proyeccion(datos, "CASTILLA")

    assert "sin meta definida" in texto


def test_sin_tarjetas_no_se_fabrica_una_proyeccion() -> None:
    texto = proyeccion(_datos([]), "CASTILLA")
    assert "no hay proyección" in texto


def test_las_diferidas_rotulan_que_son_historicas() -> None:
    """La fuente termina antes del mes en curso; presentarla como actual sería
    engañoso."""
    datos = {
        "sin_datos": False,
        "pareto": [{"grupo": "Operacional", "pct": 60.0}],
    }
    texto = diferidas(datos, "CASTILLA", nivel="campo")

    assert "NO refleja el mes en curso" in texto
    assert "Operacional" in texto


def test_las_diferidas_sin_datos_dan_su_motivo() -> None:
    datos = {"sin_datos": True, "motivo": "el histórico no cubre este activo"}
    texto = diferidas(datos, "NARE", nivel="activo")

    assert "el histórico no cubre este activo" in texto


# ═════════════════════════════════════════════════════════════════════════════
# Sub-router: la precedencia es significativa
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("cuál es el ebitda de Castilla", "economia"),
        ("qué diferidas tuvo Castilla", "diferidas"),
        ("cómo vamos a cerrar el mes", "proyeccion"),
        ("cuál es el P50 de la vicepresidencia", "referencia"),
        ("por qué bajó Castilla", "causal"),
    ],
)
def test_las_cinco_sub_intenciones(texto: str, esperada: str) -> None:
    assert sub_intencion(texto) == esperada


def test_vamos_a_llegar_al_p50_sigue_siendo_proyeccion() -> None:
    """🔑 `referencia` va DEBAJO de `proyeccion` a propósito: preguntar si se
    va a llegar al P50 es preguntar por el cierre, no por la cifra."""
    assert sub_intencion("¿vamos a llegar al P50?") == "proyeccion"


def test_por_que_no_llegamos_al_p50_es_causal() -> None:
    """Con señal causal explícita, el P50 no convierte la pregunta en
    referencia: se pregunta por la causa, no por el número."""
    assert sub_intencion("por qué no llegamos al P50") == "causal"


def test_economia_gana_sobre_todo() -> None:
    """EBITDA lee otra fuente: si la pregunta lo nombra, ninguna otra ruta
    puede responderla."""
    assert sub_intencion("por qué el ebitda bajó tanto") == "economia"
