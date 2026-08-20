"""Ejecutor de cuantificar — contrato, rechazos honestos y D1."""

from __future__ import annotations

from typing import Any

import pytest

from src.features.consulta.ejecutor import ejecutar, ejecutar_n1, ejecutar_n2
from src.features.consulta.slots import extraer_slots

pytestmark = pytest.mark.unit


def _desempeno(
    *,
    real: float = 1_000_000.0,
    ppto: float = 1_056_000.0,
    completo: bool = True,
    producto: str = "CRUDO",
    campos_sin_meta: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "encontrada": True,
        "sin_datos": False,
        "sin_cierre": False,
        "mes": {
            "anio": 2026,
            "mes": 5,
            "nombre": "Mayo",
            "completo": completo,
            "dias_con_data": 31 if completo else 17,
            "dias_del_mes": 31,
        },
        "por_producto": [{"producto": producto, "real": real, "ppto": ppto}],
        "campos_sin_meta": campos_sin_meta or [],
        "ritmo_mensual": {
            "meses": ["Ene", "Feb"],
            "series": {"CRUDO": [100, 200]},
            "promedio_mes": {"CRUDO": 150},
        },
    }


def _fn(payload: dict[str, Any]):
    def _inner(
        entidad: str | None = None,
        nivel: str | None = None,
        periodo: str | None = None,
    ) -> dict[str, Any]:
        return payload

    return _inner


_CAMPO = {"valor": "CASTILLA", "nivel": "campo", "rama": "A"}


# ── D1: el nivel se dice siempre ─────────────────────────────────────────────


def test_la_entidad_se_cualifica_con_su_nivel() -> None:
    """🔑 D1: "el Campo CASTILLA" y "el Activo CASTILLA" son cifras DISTINTAS
    y sin el rótulo son indistinguibles."""
    slots = extraer_slots("cuanto produjo CASTILLA")
    res = ejecutar_n1(_CAMPO, dict(slots), desempeno_fn=_fn(_desempeno()))

    assert res["entidad_cualificada"] == "el Campo CASTILLA"


def test_el_activo_se_rotula_distinto_del_campo() -> None:
    activo = {"valor": "CASTILLA", "nivel": "activo", "rama": "A"}
    slots = extraer_slots("cuanto produjo CASTILLA")
    res = ejecutar_n1(activo, dict(slots), desempeno_fn=_fn(_desempeno()))

    assert res["entidad_cualificada"] == "el Activo CASTILLA"


def test_el_puente_rotula_como_vicepresidencia() -> None:
    """R2: el nivel de consulta sigue siendo gerencia; solo cambia el rótulo."""
    gerencia = {"valor": "GOR", "nivel": "gerencia", "rama": "A", "puente": True}
    slots = extraer_slots("cuanto produjo GOR")
    res = ejecutar_n1(gerencia, dict(slots), desempeno_fn=_fn(_desempeno()))

    assert res["entidad_cualificada"] == "la Vicepresidencia GOR"
    assert res["entidad"]["nivel"] == "gerencia"


# ── N1 ───────────────────────────────────────────────────────────────────────


def test_n1_arma_el_contrato_completo() -> None:
    slots = extraer_slots("cuanto produjo CASTILLA en mayo")
    res = ejecutar_n1(_CAMPO, dict(slots), desempeno_fn=_fn(_desempeno()))

    assert res["aplica"] is True
    assert res["nivel"] == "N1"
    assert res["resultado"]["valor"] == 1_000_000
    assert res["cumplimiento_pct"] == 94.7
    assert res["estado"] == "Alineado"


def test_un_mes_incompleto_se_marca_como_proyeccion() -> None:
    slots = extraer_slots("cuanto produjo CASTILLA")
    res = ejecutar_n1(_CAMPO, dict(slots), desempeno_fn=_fn(_desempeno(completo=False)))

    assert res["huella"]["es_proyeccion"] is True


def test_el_cumplimiento_se_recalcula_contra_la_referencia_elegida() -> None:
    """Si se heredara del payload, "vs operativo" mostraría el % del PPTO."""

    def _escenario(
        entidad: str,
        nivel: str | None = None,
        periodo: str | None = None,
        escenarios: tuple[str, ...] = ("OPERATIVO", "CONTABLE"),
    ) -> dict[str, dict[str, float]]:
        return {"CRUDO": {"OPERATIVO": 2_000_000.0}}

    slots = extraer_slots("produccion de CASTILLA vs el operativo")
    res = ejecutar_n1(
        _CAMPO,
        dict(slots),
        desempeno_fn=_fn(_desempeno()),
        escenario_fn=_escenario,
    )

    assert res["referencia"] == "OPERATIVO"
    assert res["referencia_valor"] == 2_000_000
    assert res["cumplimiento_pct"] == 50.0  # contra el operativo, no el PPTO


def test_el_promedio_no_se_juzga_como_una_meta() -> None:
    """El promedio no es un compromiso: decir "Rezagado" contra él sería
    juzgar con una vara que nadie pactó."""
    slots = extraer_slots("produccion de CASTILLA vs el promedio del año")
    res = ejecutar_n1(_CAMPO, dict(slots), desempeno_fn=_fn(_desempeno()))

    assert res["referencia"] == "promedio_anio"
    assert res["estado"] in ("sobre el promedio", "bajo el promedio")


def test_avisa_de_los_campos_que_producen_sin_meta() -> None:
    slots = extraer_slots("cuanto produjo APIAY")
    res = ejecutar_n1(
        {"valor": "APIAY", "nivel": "activo", "rama": "A"},
        dict(slots),
        desempeno_fn=_fn(
            _desempeno(
                campos_sin_meta=[
                    {"campo": "SURIA", "producto": "CRUDO", "real": 500_000}
                ]
            )
        ),
    )

    assert any("SURIA" in a for a in res["avisos"])


# ── Rechazos honestos ────────────────────────────────────────────────────────


def test_el_p50_se_declina_explicando_por_que() -> None:
    """El P50 vive en otra escala y a otro nivel: compararlo contra un campo
    daría un número sin significado. Se declina nombrando alternativas."""
    slots = extraer_slots("cual es el P50 de CASTILLA")
    res = ejecutar_n1(_CAMPO, dict(slots), desempeno_fn=_fn(_desempeno()))

    assert res["aplica"] is False
    assert "P50" in res["texto"]
    assert "presupuesto" in res["texto"]  # ofrece qué SÍ puede


def test_una_filial_se_declina_sin_inventar() -> None:
    filial = {"valor": "HOCOL", "nivel": "filial", "rama": "B"}
    slots = extraer_slots("cuanto produjo HOCOL")
    res = ejecutar_n1(filial, dict(slots), desempeno_fn=_fn(_desempeno()))

    assert res["aplica"] is False
    assert "filial" in res["texto"]


def test_sin_datos_lo_dice() -> None:
    slots = extraer_slots("cuanto produjo CASTILLA")
    res = ejecutar_n1(_CAMPO, dict(slots), desempeno_fn=_fn({"encontrada": False}))

    assert res["aplica"] is False
    assert "CASTILLA" in res["texto"]


def test_sin_cierre_se_distingue_de_sin_datos() -> None:
    """Son cosas distintas: una es que no hay entidad, otra que aún no cerró
    el mes. Confundirlas daría un mensaje engañoso."""
    slots = extraer_slots("cuanto produjo CASTILLA")
    res = ejecutar_n1(
        _CAMPO,
        dict(slots),
        desempeno_fn=_fn({"encontrada": True, "sin_datos": False, "sin_cierre": True}),
    )

    assert res["aplica"] is False
    assert "cierre" in res["texto"]


def test_un_producto_que_no_reporta_lo_dice() -> None:
    slots = extraer_slots("cuanto gas produjo CASTILLA")
    res = ejecutar_n1(
        _CAMPO,
        dict(slots),
        desempeno_fn=_fn(_desempeno(producto="GAS", real=0, ppto=0)),
    )

    assert res["aplica"] is False
    assert "no reporta" in res["texto"]


# ── N2 ───────────────────────────────────────────────────────────────────────


def _fn_por_mes():
    def _inner(
        entidad: str | None = None,
        nivel: str | None = None,
        periodo: str | None = None,
    ) -> dict[str, Any]:
        if periodo in ("enero", "febrero", None):
            return _desempeno(real=500_000, ppto=500_000)
        return {"encontrada": True, "sin_datos": True}

    return _inner


def test_n2_no_fabrica_un_mes_sintetico() -> None:
    """🔑 HE6: un acumulado no es un mes. Trae sus propias claves."""
    slots = extraer_slots("acumulado de CASTILLA")
    res = ejecutar_n2(_CAMPO, dict(slots), desempeno_fn=_fn_por_mes())

    assert res["aplica"] is True
    assert res["nivel"] == "N2"
    assert "mes" not in res
    assert res["meses_cerrados"] >= 1
    assert res["periodo_label"]


def test_n2_declara_que_la_referencia_alterna_no_aplica() -> None:
    """AF-4.7: se dice, en vez de aplicar en silencio una referencia que no
    corresponde al acumulado."""
    slots = dict(extraer_slots("acumulado de CASTILLA"))
    slots["referencia"] = "OPERATIVO"
    res = ejecutar_n2(_CAMPO, slots, desempeno_fn=_fn_por_mes())

    assert any("solo aplican al dato puntual" in a for a in res["avisos"])


# ── Despacho ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("texto", "nivel_esperado"),
    [
        ("cuanto produjo CASTILLA", "N1"),
        ("acumulado de CASTILLA", "N2"),
        ("produccion de CASTILLA mes a mes", "N3"),
        ("como vario la produccion de CASTILLA", "N4"),
    ],
)
def test_el_despacho_respeta_el_nivel_temporal(texto: str, nivel_esperado: str) -> None:
    slots = extraer_slots(texto)
    res = ejecutar(_CAMPO, dict(slots), desempeno_fn=_fn_por_mes())

    # N3/N4 pueden no aplicar con este doble, pero el despacho debe ser el
    # correcto: si aplica, el nivel coincide; si no, es un rechazo con texto.
    assert res.get("nivel") == nivel_esperado or res["aplica"] is False
