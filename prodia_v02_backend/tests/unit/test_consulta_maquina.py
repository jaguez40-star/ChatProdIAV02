"""Orquestador del Motor Q — el flujo de capas y D4/D6.

El detector de entidad y el LLM se inyectan o se doblan, así que ningún test
sale a la red.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.features.consulta.maquina import clasificar, clasificar_nucleo
from src.features.consulta.memoria import ContextoCuantificar
from src.shared import llm_client

pytestmark = pytest.mark.unit


def _sin_entidad(_texto: str) -> str | None:
    return None


def _con_entidad(nombre: str):
    def _detectar(_texto: str) -> str | None:
        return nombre

    return _detectar


def _doblar_llm(monkeypatch: pytest.MonkeyPatch, respuesta: Any) -> None:
    def _falso(prompt: str, timeout: int, diag: dict[str, Any] | None) -> Any:
        return respuesta

    monkeypatch.setattr(llm_client, "_invocar_una_vez", _falso)


# ── Capa 1 resuelve sola ─────────────────────────────────────────────────────


def test_la_regex_con_entidad_no_gasta_una_llamada_al_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si la regex atrapó y hay entidad del catálogo, no hace falta el modelo."""
    llamadas: list[str] = []

    def _falso(prompt: str, timeout: int, diag: dict[str, Any] | None) -> Any:
        llamadas.append(prompt)
        return {"grupo": "analizar", "entidad": None}

    monkeypatch.setattr(llm_client, "_invocar_una_vez", _falso)

    res = clasificar_nucleo(
        "cuanto produjo CASTILLA", detectar_entidad=_con_entidad("CASTILLA")
    )

    assert res["grupo"] == "cuantificar"
    assert res["capa_resolutora"] == "regex"
    assert llamadas == []


def test_un_patron_anclado_se_salta_el_filtro_de_dominio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Los anclados YA son señal de dominio: no hace falta confirmarlos."""
    _doblar_llm(monkeypatch, {"grupo": "desconocido", "entidad": None})

    res = clasificar_nucleo("cual es el P50 de este mes", detectar_entidad=_sin_entidad)

    assert res["grupo"] == "analizar"
    assert res["capa_resolutora"] == "regex"


# ── Filtro de dominio ────────────────────────────────────────────────────────


def test_sin_entidad_ni_vocabulario_cae_fuera_de_dominio() -> None:
    """La regex vio la FORMA, pero el TEMA no es de producción."""
    res = clasificar_nucleo(
        "cuánto es la raíz cuadrada de 2", detectar_entidad=_sin_entidad
    )

    assert res["grupo"] == "desconocido"
    assert res["capa_resolutora"] == "regex+filtro"
    # Se conservan los patrones para poder trazar POR QUÉ disparó la regex.
    assert res["patrones"]


def test_la_evidencia_estructural_la_confirma_el_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ "campos de la dieta mediterránea" y "campos bajo la meta" traen la
    misma palabra; la regex no ve el contexto gramatical."""
    _doblar_llm(monkeypatch, {"grupo": "desconocido", "entidad": None})

    res = clasificar_nucleo(
        "cuántos campos hay en el formulario", detectar_entidad=_sin_entidad
    )

    assert res["capa_resolutora"] == "regex+llm"
    assert res["grupo"] == "desconocido"


# ── D4: fallback obligatorio ─────────────────────────────────────────────────


def test_si_el_llm_falla_se_conserva_el_grupo_de_la_regex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔑 D4. Una caída del modelo degrada al comportamiento previo; jamás se
    traga una pregunta legítima."""
    _doblar_llm(monkeypatch, None)  # timeout / conexión / JSON malo

    res = clasificar_nucleo(
        "cuántos campos hay en el formulario", detectar_entidad=_sin_entidad
    )

    assert res["capa_resolutora"] == "regex+llm_fallo"
    # El grupo de la regex SOBREVIVE.
    assert res["grupo"] in ("jerarquizar", "cuantificar", "analizar")


# ── Capa 2 pura ──────────────────────────────────────────────────────────────


def test_sin_regex_decide_el_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    _doblar_llm(monkeypatch, {"grupo": "jerarquizar", "entidad": "INVENTADO"})

    res = clasificar_nucleo("CASTILLA", detectar_entidad=_sin_entidad)

    assert res["grupo"] == "jerarquizar"
    assert res["capa_resolutora"] == "llm"


def test_la_entidad_del_llm_no_se_usa_para_consultar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔑 D6: se escaló porque el catálogo no encontró ninguna. Si el modelo la
    inventa, mentiría."""
    _doblar_llm(monkeypatch, {"grupo": "jerarquizar", "entidad": "CAMPO FANTASMA"})

    res = clasificar_nucleo("texto raro", detectar_entidad=_sin_entidad)

    assert res["entidad_cruda"] != "CAMPO FANTASMA"


def test_si_el_llm_no_responde_el_grupo_es_desconocido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _doblar_llm(monkeypatch, None)
    res = clasificar_nucleo("texto raro", detectar_entidad=_sin_entidad)

    assert res["grupo"] == "desconocido"


# ── Envoltura: memoria y libreta ─────────────────────────────────────────────


def test_la_reescritura_conserva_el_texto_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El usuario debe ver lo que escribió, no la reescritura interna."""
    _doblar_llm(monkeypatch, {"grupo": "cuantificar", "entidad": None})
    ctx = ContextoCuantificar(entidad="CASTILLA", producto="crudo")

    res = clasificar("¿y el acumulado?", detectar_entidad=_sin_entidad, contexto=ctx)

    assert res["texto_original"] == "¿y el acumulado?"
    assert res["continuacion"] is True
    assert "CASTILLA" in res["texto_efectivo"]


def test_sin_contexto_no_hay_reescritura(monkeypatch: pytest.MonkeyPatch) -> None:
    _doblar_llm(monkeypatch, {"grupo": "desconocido", "entidad": None})
    res = clasificar("¿y el acumulado?", detectar_entidad=_sin_entidad)

    assert "continuacion" not in res


def test_la_libreta_nunca_tumba_la_respuesta() -> None:
    """🔑 Regla madre: si registrar falla, se responde igual."""

    def _registrar_roto(**_kwargs: Any) -> int | None:
        raise RuntimeError("la BD no está disponible")

    res = clasificar(
        "cuanto produjo CASTILLA",
        detectar_entidad=_con_entidad("CASTILLA"),
        registrar=_registrar_roto,
    )

    assert res["grupo"] == "cuantificar"
    assert res["log_id"] is None


def test_sin_registrador_no_se_escribe_pero_se_responde() -> None:
    """Permite que el golden ejercite EL MISMO camino que producción, a
    diferencia del origen, donde `log=False` cambiaba el flujo."""
    res = clasificar(
        "cuanto produjo CASTILLA", detectar_entidad=_con_entidad("CASTILLA")
    )

    assert res["log_id"] is None
    assert res["grupo"] == "cuantificar"


def test_el_contrato_trae_las_claves_que_el_frontend_espera() -> None:
    res = clasificar(
        "cuanto produjo CASTILLA", detectar_entidad=_con_entidad("CASTILLA")
    )

    for clave in (
        "log_id",
        "texto_original",
        "grupo",
        "grupo_label",
        "capa_resolutora",
        "entidad_cruda",
        "patrones",
        "llm_diag",
        "timestamp",
        "mensaje",
        "panel",
        "vp_ofrecida",
    ):
        assert clave in res
