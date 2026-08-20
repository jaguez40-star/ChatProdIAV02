"""Garantiza que importar la app NO abre conexiones (AP-2).

**Por qué este test existe.** `scripts/export_openapi.py` hace
`from src.main import app`, y ese script corre en dos sitios críticos:

1. el hook `gen-types-check` de pre-commit, en CADA cambio de
   `src/(main|features)/*.py` — es decir, en los commits de todo el equipo;
2. el job backend de CI.

Si un módulo abre su engine, parsea un `.xlsx` de 954 MB o contacta a Ollama en
tiempo de IMPORT en vez de bajo demanda, esos dos flujos intentarían alcanzar
recursos que no están disponibles (el Postgres del 139 exige VPN; Ollama vive
en otro host). El síntoma sería un commit colgado o un CI rojo, lejos de la
causa y difícil de atribuir.

F2 añade cinco módulos compartidos que son candidatos exactos a ese fallo, así
que la garantía se verifica, no se confía.
"""

from __future__ import annotations

import socket
from typing import Any

import pytest


@pytest.mark.integration
def test_importar_la_app_no_abre_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importar `src.main` no debe intentar ninguna conexión de red."""
    intentos: list[Any] = []
    connect_real = socket.socket.connect

    def _connect_espia(self: Any, direccion: Any) -> Any:
        intentos.append(direccion)
        return connect_real(self, direccion)

    monkeypatch.setattr(socket.socket, "connect", _connect_espia)

    import importlib

    import src.main

    importlib.reload(src.main)

    assert not intentos, (
        "importar src.main abrió conexiones de red: "
        f"{intentos}. Algún módulo hace I/O en tiempo de import (AP-2); "
        "muévelo dentro de una función."
    )


@pytest.mark.integration
def test_los_modulos_compartidos_de_f2_no_hacen_io_al_importarse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cada módulo nuevo de F2, importado en aislamiento, no toca la red."""
    intentos: list[Any] = []
    connect_real = socket.socket.connect

    def _connect_espia(self: Any, direccion: Any) -> Any:
        intentos.append(direccion)
        return connect_real(self, direccion)

    monkeypatch.setattr(socket.socket, "connect", _connect_espia)

    import importlib

    for modulo in (
        "src.shared.catalogo_entidades",
        "src.shared.cache_ttl",
        "src.shared.llm_client",
        "src.shared.db_ops",
        "src.shared.db_diferidas",
    ):
        importlib.reload(importlib.import_module(modulo))
        assert not intentos, f"{modulo} abrió una conexión al importarse: {intentos}"


@pytest.mark.integration
def test_el_engine_de_ops_no_se_crea_hasta_pedirlo() -> None:
    """`get_ops_engine` es `lru_cache`: la creación es perezosa por diseño.

    Con `OPS_DATABASE_URL` vacía debe lanzar `OpsNoConfiguradaError` —una excepción
    propia, NO un `SQLAlchemyError`—, porque falta configuración, no falla una
    base de datos. Sin ese tipo, el caso saldría como 500 genérico en vez del
    503 con mensaje accionable (AP-10).
    """
    from src.core.config import get_settings
    from src.shared.db_ops import (
        OpsNoConfiguradaError,
        check_ops_connection,
        get_ops_engine,
    )

    get_ops_engine.cache_clear()

    if not get_settings().ops_database_url:
        with pytest.raises(OpsNoConfiguradaError):
            get_ops_engine()
        # `check_ops_connection` nunca lanza: /health la usa para reportar.
        assert check_ops_connection() is False

    get_ops_engine.cache_clear()
