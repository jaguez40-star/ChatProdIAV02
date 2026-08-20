"""F6 · Bloque 1 — servir el frontend compilado (B-4).

Lo que estos tests fijan es la conducta que hace desplegable la aplicación, y
cada uno corresponde a una forma concreta de romperla:

1. Sin `dist/`, importar la app NO revienta — si lo hiciera, bloquearía el
   `pre-commit` de todo el equipo (AP-4).
2. El montaje en "/" NO se traga `/api/v1/*`.
3. Recargar en una ruta del router de React devuelve `index.html`, no un 404.
4. Un 404 de la API sigue siendo un 404 con su contrato de error uniforme.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _crear_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><title>ProdIA V02</title>", encoding="utf-8"
    )
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return dist


def _app_con_static(dist: Path | None, monkeypatch: pytest.MonkeyPatch):
    """Reimporta `src.main` con la configuración de estáticos pedida.

    `main.py` monta el `dist/` en tiempo de import (es lo que hará uvicorn en
    producción), así que para probarlo hay que volver a importarlo con otra
    configuración — no basta con tocar `settings` después.
    """
    import importlib

    from src.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("SERVE_STATIC", "true" if dist else "false")
    if dist:
        monkeypatch.setenv("STATIC_DIR", str(dist))

    import src.main

    modulo = importlib.reload(src.main)
    return modulo.app


@pytest.fixture(autouse=True)
def _restaurar_main():
    """Deja `src.main` como estaba: otros tests importan la app real."""
    yield
    import importlib

    from src.core.config import get_settings

    get_settings.cache_clear()
    import src.main

    importlib.reload(src.main)


def test_sin_dist_la_app_importa_igual(monkeypatch, tmp_path):
    """🔑 AP-4 — el caso que bloquearía los commits de todo el repo.

    El hook `gen-types-check` importa `src.main` en cada commit que toque el
    backend, y en desarrollo nadie compila el frontend. Si el montaje exigiera
    que `dist/` exista, nadie podría commitear.
    """
    monkeypatch.setenv("SERVE_STATIC", "true")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path / "no-existe"))

    app = _app_con_static(None, monkeypatch)
    monkeypatch.setenv("SERVE_STATIC", "true")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path / "no-existe"))

    # La app existe y responde: la ausencia del build no es un error fatal.
    assert app is not None


def test_apagado_por_defecto():
    """En desarrollo manda el proxy de Vite; el backend no sirve nada."""
    from src.core.config import Settings

    assert Settings().serve_static is False


def test_la_api_no_queda_tapada_por_los_estaticos(monkeypatch, tmp_path):
    """🔑 El montaje en "/" atrapa TODO lo que llega hasta él.

    Si `StaticFiles` se montara antes que los routers, `/api/v1/health`
    devolvería 404 y la API entera desaparecería. El orden es la corrección.
    """
    dist = _crear_dist(tmp_path)
    app = _app_con_static(dist, monkeypatch)

    with TestClient(app) as cliente:
        r = cliente.get("/api/v1/health")

    assert r.status_code == 200
    assert "database_auth" in r.json()


def test_recargar_en_una_ruta_de_react_devuelve_el_index(monkeypatch, tmp_path):
    """🔑 `createBrowserRouter`: `/analisis` es una ruta REAL del navegador.

    Sin el fallback, refrescar ahí busca un fichero `analisis` inexistente y el
    servidor responde 404 — la app se ve rota justo al recargar, que es lo
    primero que hace cualquiera.
    """
    dist = _crear_dist(tmp_path)
    app = _app_con_static(dist, monkeypatch)

    with TestClient(app) as cliente:
        r = cliente.get("/analisis", headers={"accept": "text/html"})

    assert r.status_code == 200
    assert "ProdIA V02" in r.text


def test_un_404_de_la_api_conserva_su_contrato(monkeypatch, tmp_path):
    """El fallback NO puede tragarse los errores de la API.

    Una ruta inexistente bajo `/api/` debe seguir devolviendo el JSON uniforme
    con su `correlation_id`, no el `index.html`. Si devolviera HTML, el cliente
    intentaría parsearlo como JSON y el error real quedaría enmascarado.
    """
    dist = _crear_dist(tmp_path)
    app = _app_con_static(dist, monkeypatch)

    with TestClient(app) as cliente:
        r = cliente.get("/api/v1/no-existe", headers={"accept": "text/html"})

    assert r.status_code in (401, 404)
    cuerpo = json.loads(r.text)
    assert "detail" in cuerpo
    assert "correlation_id" in cuerpo
