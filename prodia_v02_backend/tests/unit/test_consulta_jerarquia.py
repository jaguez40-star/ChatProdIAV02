"""El despachador de `jerarquizar` — la pregunta más elemental del chat.

🔑 Por qué existe este archivo. «¿Qué campos tiene el activo Chichimene?» es la
pregunta más básica que admite el motor, y durante toda F4 el chat respondía
«[Jerarquizar] Entendí que preguntas por CHICHIMENE» sin decir un solo campo:
el grupo estaba clasificado pero sin redactor conectado.

Ningún test lo detectó porque todos probaban módulos aislados. Estos van por el
DESPACHADOR, que es la pieza que convierte «entendí» en una respuesta.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.features.consulta.api import _jerarquia
from src.shared import catalogo_entidades


@pytest.fixture
def db() -> MagicMock:
    return MagicMock()


def test_un_activo_devuelve_sus_campos(monkeypatch, db):
    monkeypatch.setattr(
        catalogo_entidades,
        "campos_de_activo",
        lambda _db, activo: (
            ["APIAY", "GUATIQUIA", "SURIA"] if activo == "APIAY" else []
        ),
    )

    salida = _jerarquia("apiay", db)

    assert salida is not None
    assert "3 campos" in salida["mensaje"]
    panel = salida["panel"]
    assert panel["tipo"] == "jerarq_arbol"
    assert panel["datos"]["nivel"] == "activo"
    assert panel["datos"]["hijos_grupos"][0]["items"] == [
        "APIAY",
        "GUATIQUIA",
        "SURIA",
    ]


def test_un_campo_devuelve_su_activo(monkeypatch, db):
    """La dirección inversa: pertenencia en vez de composición."""
    monkeypatch.setattr(catalogo_entidades, "campos_de_activo", lambda _db, a: [])
    monkeypatch.setattr(catalogo_entidades, "activo_de_campo", lambda _db, c: "CUSIANA")

    salida = _jerarquia("cupiagua", db)

    assert salida is not None
    assert "pertenece al activo CUSIANA" in salida["mensaje"]
    assert salida["panel"]["datos"]["nivel"] == "campo"
    assert salida["panel"]["datos"]["padres"] == [
        {"nivel": "activo", "items": ["CUSIANA"]}
    ]


def test_singular_cuando_hay_un_solo_campo(monkeypatch, db):
    """«1 campos» delata que nadie leyó la respuesta."""
    monkeypatch.setattr(catalogo_entidades, "campos_de_activo", lambda _db, a: ["SOLO"])

    salida = _jerarquia("x", db)

    assert salida is not None
    assert "1 campo." in salida["mensaje"]


def test_lo_desconocido_se_declara_sin_panel(monkeypatch, db):
    """🔑 No inventar. Un nombre que no está en el catálogo puede ser de un
    tercero o estar sin clasificar, y eso se dice — no se devuelve un árbol
    vacío que parezca un activo sin campos."""
    monkeypatch.setattr(catalogo_entidades, "campos_de_activo", lambda _db, a: [])
    monkeypatch.setattr(catalogo_entidades, "activo_de_campo", lambda _db, c: None)

    salida = _jerarquia("inventado", db)

    assert salida is not None
    assert salida["panel"] is None
    assert "no aparece en el catálogo" in salida["mensaje"]


def test_el_nombre_se_normaliza_a_mayusculas(monkeypatch, db):
    """El usuario escribe como quiere; el catálogo está en mayúsculas."""
    vistos: list[str] = []

    def _espia(_db, activo: str) -> list[str]:
        vistos.append(activo)
        return []

    monkeypatch.setattr(catalogo_entidades, "campos_de_activo", _espia)
    monkeypatch.setattr(catalogo_entidades, "activo_de_campo", lambda _db, c: None)

    _jerarquia("  chichimene  ", db)

    assert vistos == ["CHICHIMENE"]
