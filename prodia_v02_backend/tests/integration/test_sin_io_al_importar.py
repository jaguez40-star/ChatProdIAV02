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

**F4 amplía la vigilancia a FICHEROS**, no solo a sockets: la feature trae
cuatro `config/*.yaml` y el sistema de origen los carga en tiempo de import
(`respuesta_cuantificar.py:27`). Un espía de sockets no habría visto ese fallo.
"""

from __future__ import annotations

import builtins
import socket
from pathlib import Path
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


# Extensiones de datos que NINGÚN módulo debe leer en tiempo de import. Se
# vigilan por extensión y no por ruta porque lo que importa no es dónde está el
# fichero, sino que abrirlo cueste I/O de disco al arrancar.
_EXTENSIONES_DE_DATOS = (".yaml", ".yml", ".json", ".csv", ".xlsx", ".xlsm", ".db")


@pytest.mark.integration
def test_importar_la_app_no_lee_ficheros_de_datos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Importar `src.main` no debe leer YAML, CSV ni bases de datos.

    **Por qué se amplía el guardián en F4.** El test hermano de arriba espía
    *sockets*, que bastaba hasta F3. F4 trae cuatro `config/*.yaml` (442
    líneas) y el sistema de origen los carga MAL: `respuesta_cuantificar.py:27`
    ejecuta `_catalogo.get()` a nivel de módulo, así que allí importar la app
    lee disco. Fue deliberado ("arranque ruidoso si el YAML está mal"), pero
    aquí el momento es inaceptable: el hook `gen-types-check` de pre-commit se
    dispara con TODO fichero de `src/features/**` e importa la app entera en
    cada `git commit` del equipo.

    La validación ruidosa sigue existiendo, pero vive en el `lifespan`: se
    conserva el beneficio sin pagar el I/O al importar.
    """
    leidos: list[str] = []
    open_real = builtins.open

    def _open_espia(archivo: Any, *args: Any, **kwargs: Any) -> Any:
        nombre = str(archivo)
        if nombre.lower().endswith(_EXTENSIONES_DE_DATOS):
            leidos.append(nombre)
        return open_real(archivo, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _open_espia)

    # `Path.read_text`/`read_bytes` NO pasan por `builtins.open` en CPython:
    # usan `io.open` a través del propio objeto. El origen carga sus YAML
    # justamente con `_CFG_PATH.read_text(...)`, así que sin espiar también
    # estos dos métodos el test daría verde en falso.
    leidos_por_path: list[str] = []
    read_text_real = Path.read_text
    read_bytes_real = Path.read_bytes

    def _read_text_espia(self: Path, *args: Any, **kwargs: Any) -> Any:
        if str(self).lower().endswith(_EXTENSIONES_DE_DATOS):
            leidos_por_path.append(str(self))
        return read_text_real(self, *args, **kwargs)

    def _read_bytes_espia(self: Path, *args: Any, **kwargs: Any) -> Any:
        if str(self).lower().endswith(_EXTENSIONES_DE_DATOS):
            leidos_por_path.append(str(self))
        return read_bytes_real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _read_text_espia)
    monkeypatch.setattr(Path, "read_bytes", _read_bytes_espia)

    import importlib

    import src.main

    importlib.reload(src.main)

    todos = leidos + leidos_por_path
    assert not todos, (
        "importar src.main leyó ficheros de datos: "
        f"{todos}. Algún módulo carga su configuración en tiempo de import "
        "(H4/AP-2); hazlo perezoso y valida en el lifespan."
    )


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
