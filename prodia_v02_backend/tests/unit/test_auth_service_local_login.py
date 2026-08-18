"""Tests unitarios de AuthService._is_local_login_allowed (C15).

Verifica la corrección sobre Robustez V02: comparación en tiempo constante
(secrets.compare_digest) y ausencia total del comodín "*" como vía de escape
del filtro de IP (Settings ya lo rechaza antes de construir el objeto).
"""

from __future__ import annotations

import pytest

from src.core.config import Settings
from src.features.auth.services import AuthService


def _settings(**overrides: object) -> Settings:
    base = {
        "secret_key": "x" * 32,
        "enable_local_login": True,
        "local_login_username": "test.user",
        "local_login_password": "clave-correcta",
        "local_login_allowed_ips": "127.0.0.1,::1",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.mark.unit
def test_local_login_password_correcta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.features.auth.services.get_settings", lambda: _settings())
    service = AuthService.__new__(AuthService)
    service._settings = _settings()  # type: ignore[attr-defined]
    assert (
        service._is_local_login_allowed("test.user", "clave-correcta", "127.0.0.1")
        is True
    )


@pytest.mark.unit
def test_local_login_password_incorrecta(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AuthService.__new__(AuthService)
    service._settings = _settings()  # type: ignore[attr-defined]
    assert (
        service._is_local_login_allowed("test.user", "clave-mala", "127.0.0.1") is False
    )


@pytest.mark.unit
def test_local_login_ip_no_permitida(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AuthService.__new__(AuthService)
    service._settings = _settings()  # type: ignore[attr-defined]
    assert (
        service._is_local_login_allowed("test.user", "clave-correcta", "10.0.0.99")
        is False
    )


@pytest.mark.unit
def test_local_login_desactivado(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AuthService.__new__(AuthService)
    service._settings = _settings(enable_local_login=False)  # type: ignore[attr-defined]
    assert (
        service._is_local_login_allowed("test.user", "clave-correcta", "127.0.0.1")
        is False
    )


@pytest.mark.unit
def test_local_login_usuario_desconocido(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AuthService.__new__(AuthService)
    service._settings = _settings()  # type: ignore[attr-defined]
    assert (
        service._is_local_login_allowed("otro.usuario", "clave-correcta", "127.0.0.1")
        is False
    )


@pytest.mark.unit
def test_wildcard_rechazado_en_settings() -> None:
    """C15/H6: '*' en LOCAL_LOGIN_ALLOWED_IPS nunca llega a construirse — el
    propio validador de Settings lo rechaza, sin excepción por entorno."""
    with pytest.raises(ValueError, match=r"no admite '\*'"):
        _settings(local_login_allowed_ips="*")


@pytest.mark.unit
def test_secret_key_corta_rechazada() -> None:
    with pytest.raises(ValueError, match="al menos 16 caracteres"):
        Settings(secret_key="corta")  # type: ignore[arg-type]
