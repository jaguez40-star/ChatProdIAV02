"""Tests del cliente de Ollama — parseo tolerante y política de reintento.

Ningún test sale a la red: `_invocar_una_vez` se sustituye por un doble. Lo que
se protege son las 4 trampas del origen, cada una un fallo real ya diagnosticado.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.shared import llm_client
from src.shared.llm_client import extraer_json, invocar

# ── extraer_json: tolerancia a los defectos típicos de Gemma ────────────────


@pytest.mark.unit
def test_json_limpio() -> None:
    assert extraer_json('{"a": 1}') == {"a": 1}


@pytest.mark.unit
def test_quita_fences_de_markdown() -> None:
    assert extraer_json('```json\n{"a": 1}\n```') == {"a": 1}


@pytest.mark.unit
def test_ignora_prosa_alrededor() -> None:
    texto = 'Claro, aquí tienes:\n{"a": 1}\nEspero que sirva.'
    assert extraer_json(texto) == {"a": 1}


@pytest.mark.unit
def test_repara_comas_finales() -> None:
    assert extraer_json('{"a": 1, "b": [1, 2,],}') == {"a": 1, "b": [1, 2]}


@pytest.mark.unit
def test_normaliza_comillas_tipograficas() -> None:
    """Gemma las emite al redactar en español y rompen `json.loads`."""
    assert extraer_json("{“a”: “hola”}") == {"a": "hola"}


@pytest.mark.unit
def test_llave_dentro_de_cadena_no_cierra_el_objeto() -> None:
    """El balanceo respeta cadenas: un `}` dentro de un texto no es el cierre."""
    assert extraer_json('{"a": "cierra } aqui", "b": 2}') == {
        "a": "cierra } aqui",
        "b": 2,
    }


@pytest.mark.unit
def test_objeto_sin_cierre_reporta_el_motivo() -> None:
    diag: dict[str, Any] = {}
    assert extraer_json('{"a": 1', diag=diag) is None
    assert "sin cierre" in diag["parse_err"]


@pytest.mark.unit
def test_texto_vacio_o_sin_json() -> None:
    assert extraer_json("") is None
    assert extraer_json("no hay json aquí") is None


# ── Política de reintento (T4) ──────────────────────────────────────────────


def _stub(monkeypatch: pytest.MonkeyPatch, guion: list[Any]) -> list[int]:
    """Sustituye `_invocar_una_vez`. Un `str` en el guion = fallo con ese status."""
    llamadas = [0]
    pendientes = list(guion)

    def _falso(prompt: str, timeout: int, diag: dict[str, Any] | None) -> Any | None:
        llamadas[0] += 1
        valor = pendientes.pop(0) if len(pendientes) > 1 else pendientes[0]
        if isinstance(valor, str):
            if diag is not None:
                diag["status"] = valor
            return None
        return valor

    monkeypatch.setattr(llm_client, "_invocar_una_vez", _falso)
    return llamadas


@pytest.mark.unit
def test_exito_a_la_primera_no_reintenta(monkeypatch: pytest.MonkeyPatch) -> None:
    llamadas = _stub(monkeypatch, [{"ok": True}])
    assert invocar("p", diag={}) == {"ok": True}
    assert llamadas[0] == 1


@pytest.mark.unit
def test_reintenta_tras_aborto_y_acierta(monkeypatch: pytest.MonkeyPatch) -> None:
    """T4: el aborto es transitorio y no determinista — el mismo prompt
    completa unas veces y aborta otras. Reintentar es el arreglo."""
    llamadas = _stub(monkeypatch, ["generacion_abortada", {"ok": True}])
    assert invocar("p", diag={}) == {"ok": True}
    assert llamadas[0] == 2


@pytest.mark.unit
def test_no_reintenta_json_invalido(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con `temperature=0` repetir daría idéntico resultado: solo latencia."""
    llamadas = _stub(monkeypatch, ["json_invalido"])
    assert invocar("p", diag={}) is None
    assert llamadas[0] == 1


@pytest.mark.unit
def test_aborto_persistente_agota_los_intentos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas = _stub(monkeypatch, ["generacion_abortada"])
    assert invocar("p", diag={}, intentos=2) is None
    assert llamadas[0] == 2


@pytest.mark.unit
def test_fallo_de_red_no_reintenta(monkeypatch: pytest.MonkeyPatch) -> None:
    llamadas = _stub(monkeypatch, ["timeout_o_red:URLError"])
    assert invocar("p", diag={}) is None
    assert llamadas[0] == 1
