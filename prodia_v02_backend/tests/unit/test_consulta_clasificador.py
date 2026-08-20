"""Capa 2 del clasificador — el LLM.

**Ningún test sale a la red**: se sustituye `_invocar_una_vez` de
`shared/llm_client`, el mismo patrón que ya usan los tests de F2. CI no levanta
Ollama, así que una llamada real colgaría 30 s y luego fallaría.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.features.consulta.clasificador import clasificar_capa2, parsear
from src.features.consulta.prompts import PROMPT_CLASIFICADOR
from src.shared import llm_client

pytestmark = pytest.mark.unit


def _doblar_llm(monkeypatch: pytest.MonkeyPatch, respuesta: Any) -> list[str]:
    """Sustituye la llamada real y captura los prompts enviados."""
    prompts: list[str] = []

    def _falso(prompt: str, timeout: int, diag: dict[str, Any] | None) -> Any:
        prompts.append(prompt)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    monkeypatch.setattr(llm_client, "_invocar_una_vez", _falso)
    return prompts


# ── parsear ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "grupo", ["jerarquizar", "cuantificar", "analizar", "desconocido"]
)
def test_acepta_los_cuatro_grupos_validos(grupo: str) -> None:
    assert parsear({"grupo": grupo, "entidad": None}) == grupo


def test_rechaza_un_grupo_inventado() -> None:
    """El modelo puede devolver cualquier cosa; solo los 4 grupos valen."""
    diag: dict[str, Any] = {}
    assert parsear({"grupo": "produccion", "entidad": None}, diag) is None
    assert diag["llm_diag"] == "grupo_invalido"


def test_rechaza_una_respuesta_que_no_es_objeto() -> None:
    diag: dict[str, Any] = {}
    assert parsear(["jerarquizar"], diag) is None
    assert diag["llm_diag"] == "json_invalido"


def test_rechaza_none() -> None:
    diag: dict[str, Any] = {}
    assert parsear(None, diag) is None
    assert diag["llm_diag"] == "json_invalido"


def test_la_entidad_del_llm_se_guarda_pero_no_decide() -> None:
    """🔑 D6: el modelo alucina nombres de campo con facilidad. La entidad la
    resuelve el catálogo, que es cerrado y verificable; esta solo se conserva
    para poder auditar qué dijo."""
    diag: dict[str, Any] = {}
    grupo = parsear({"grupo": "cuantificar", "entidad": "CAMPO INVENTADO"}, diag)

    assert grupo == "cuantificar"
    assert diag["entidad_llm"] == "CAMPO INVENTADO"


def test_una_entidad_no_textual_no_rompe_el_parseo() -> None:
    assert parsear({"grupo": "analizar", "entidad": 42}) == "analizar"


# ── clasificar_capa2 ─────────────────────────────────────────────────────────


def test_clasifica_con_el_prompt_esperado(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts = _doblar_llm(monkeypatch, {"grupo": "analizar", "entidad": None})

    assert clasificar_capa2("¿por qué bajó Castilla?") == "analizar"
    assert len(prompts) == 1
    # La pregunta viaja dentro del molde, no suelta.
    assert "¿por qué bajó Castilla?" in prompts[0]
    assert prompts[0].startswith(PROMPT_CLASIFICADOR[:40])


def test_un_fallo_del_llm_devuelve_none_con_su_motivo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`None` no es un error para el llamador: significa "usa tu camino
    determinista". Pero el motivo queda registrado para la libreta."""
    _doblar_llm(monkeypatch, None)
    diag: dict[str, Any] = {}

    assert clasificar_capa2("cualquier cosa", diag) is None
    assert diag.get("llm_diag")


def test_una_respuesta_invalida_deja_el_diagnostico(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _doblar_llm(monkeypatch, {"grupo": "otra_cosa"})
    diag: dict[str, Any] = {}

    assert clasificar_capa2("cualquier cosa", diag) is None
    assert diag["llm_diag"] == "grupo_invalido"


def test_el_diagnostico_del_cliente_se_propaga(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Modelo y host viajan al diagnóstico: sin ellos, un timeout por arranque
    en frío parecería un error del clasificador al revisar la libreta."""

    def _falso(prompt: str, timeout: int, diag: dict[str, Any] | None) -> Any:
        if diag is not None:
            diag["model"] = "qwen2.5:3b"
            diag["host"] = "http://localhost:11434/api/generate"
        return {"grupo": "jerarquizar", "entidad": None}

    monkeypatch.setattr(llm_client, "_invocar_una_vez", _falso)
    diag: dict[str, Any] = {}

    assert clasificar_capa2("¿qué es Castilla?", diag) == "jerarquizar"
    assert diag["model"] == "qwen2.5:3b"
    assert "11434" in diag["host"]
