"""AuthService — autenticación LDAP + cookie firmada + auditoría.

Copiado de Robustez V02 (L5) preservando sus 3 trampas ya pagadas:
1. Resolver DNS FRESCO por intento (`_resolve_ldap_server`) — si el backend
   arranca antes que la VPN, un resolver con config cacheada hace fallar
   todo login hasta reiniciar el proceso.
2. `answers.nameserver` (IP del DNS resolver), NO `answers[0].target`
   (hostname del DC — da timeout por firewall).
3. `self._db.commit()` ANTES de cada `raise` — si no, el rollback del
   exception handler global borraría el registro de auditoría recién creado.

Corrección C15 sobre el original: `_is_local_login_allowed` comparaba
contraseñas con `==` (no es tiempo-constante, filtra por timing) y admitía
"*" como allowlist de IP. Aquí se usa `secrets.compare_digest` y el propio
`Settings.local_login_ips_no_wildcard` (core/config.py) ya rechaza "*" antes
de que este código se ejecute — el chequeo de `allowed_ips` de abajo nunca
puede ver un comodín porque Settings no lo permite construir.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.logger import get_logger
from src.features.audit.services import AuditService
from src.features.auth.models import User
from src.features.auth.repositories import UserRepository
from src.shared.app_settings import get_session_timeout_minutes

logger = get_logger("auth.service")


class LDAPError(Exception):
    """LDAP no disponible (503)."""


class AuthService:
    """Lógica de autenticación: LDAP bind + cookie firmada + audit trail."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = UserRepository(db)
        self._audit = AuditService(db)
        self._settings = get_settings()
        self._serializer = URLSafeTimedSerializer(self._settings.secret_key)

    # ── LDAP ────────────────────────────────────────────────────────────

    def _resolve_ldap_server(self) -> str:
        """Resuelve servidor LDAP via DNS SRV o config."""
        if self._settings.auth_ad_server:
            return f"ldap://{self._settings.auth_ad_server}"

        import dns.resolver

        domain = self._settings.auth_ad_domain
        try:
            # Resolver fresco por intento: dnspython cachea la config DNS del
            # sistema en el primer uso del resolver por defecto. Si el backend
            # arranca antes de conectar la VPN, ese cache queda sin el DNS
            # corporativo y todos los logins fallan hasta reiniciar el proceso.
            resolver = dns.resolver.Resolver(configure=True)
            answers = resolver.resolve(f"_ldap._tcp.{domain}", "SRV")
            # Usar nameserver (IP del DNS resolver) — tiene conectividad real.
            # answers[0].target es el hostname del DC específico y da timeout
            # por firewall.
            host = str(answers.nameserver)
            port = answers[0].port
            return f"ldap://{host}:{port}"
        except Exception as exc:
            logger.error("ldap_srv_resolution_failed", domain=domain, error=str(exc))
            raise LDAPError(f"No se pudo resolver servidor LDAP para {domain}") from exc

    def authenticate_ldap(
        self,
        username: str,
        password: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> User:
        """Autentica usuario contra LDAP y registra evento.

        Returns:
            User ORM si autenticación exitosa.

        Raises:
            LDAPError: servidor LDAP no disponible (→ 503).
            PermissionError: credenciales inválidas o usuario inactivo/no registrado (→ 401).
        """
        # LDAP acepta UPN (user@domain); BD almacena solo el username
        ldap_user = username
        if "@" in username:
            username = username.split("@")[0]
        else:
            ldap_user = f"{username}@{self._settings.auth_ad_domain}"
        username = username.lower()

        audit_kwargs: dict[str, Any] = {
            "username": username,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "correlation_id": correlation_id,
        }

        # 1. Verificar que el usuario existe en app_users
        db_user = self._repo.get_by_username(username)
        if db_user is None:
            self._audit.log_login_failure(**audit_kwargs, reason="not_in_app_users")
            self._db.commit()
            logger.warning("login_rejected_not_registered", username=username)
            raise PermissionError("Usuario no registrado en la aplicación")

        # 2. Verificar que está activo
        if not db_user.is_active:
            self._audit.log_login_failure(**audit_kwargs, reason="inactive_user")
            self._db.commit()
            logger.warning("login_rejected_inactive", username=username)
            raise PermissionError("Usuario desactivado")

        # 3. Login local auditado para desarrollo/control de contingencia local.
        if self._is_local_login_allowed(username, password, ip_address):
            now = datetime.now(timezone.utc).isoformat()
            self._audit.log_login_success(
                **audit_kwargs,
                user_id=db_user.id,
                timestamp=now,
                reason="local_login_dev",
            )
            self._db.commit()
            logger.warning("local_login_success", username=username)
            return db_user

        # 4. Bind LDAP
        try:
            ldap_url = self._resolve_ldap_server()
            if not self._ldap_bind(ldap_url, ldap_user, password):
                self._audit.log_login_failure(
                    **audit_kwargs, reason="invalid_credentials"
                )
                self._db.commit()
                logger.warning("login_failed_invalid_credentials", username=username)
                raise PermissionError("Credenciales inválidas")
        except LDAPError:
            self._audit.log_login_failure(**audit_kwargs, reason="ldap_unreachable")
            self._db.commit()
            raise

        # 5. Login exitoso — registrar evento + actualizar last_login
        now = datetime.now(timezone.utc).isoformat()
        self._audit.log_login_success(
            **audit_kwargs,
            user_id=db_user.id,
            timestamp=now,
        )
        self._db.commit()

        logger.info("login_success", username=username)
        return db_user

    def _is_local_login_allowed(
        self,
        username: str,
        password: str,
        ip_address: str | None,
    ) -> bool:
        """Valida login local auditado, restringido por flag e IP. Soporta varias
        credenciales de prueba activas a la vez (Settings.local_login_users).

        C15: comparación en TIEMPO CONSTANTE con secrets.compare_digest — una
        comparación `==` de string filtra cuánto del prefijo coincide vía
        temporización, medible en teoría incluso en localhost. El comodín "*"
        en la allowlist de IP NO es una rama posible aquí: Settings lo rechaza
        en la validación de config (core/config.py) antes de que la app arranque.
        """
        if not self._settings.enable_local_login:
            return False

        users = self._settings.local_login_users
        if not users:
            return False

        allowed_ips = self._settings.local_login_allowed_ips_list
        if ip_address not in allowed_ips:
            logger.warning(
                "local_login_rejected_ip",
                username=username,
                ip_address=ip_address,
            )
            return False

        expected = users.get(username)
        if expected is None:
            return False
        return secrets.compare_digest(expected, password)

    def _ldap_bind(self, ldap_url: str, username: str, password: str) -> bool:
        """Intenta bind LDAP. Retorna True si exitoso."""
        from ldap3 import Connection, Server

        timeout = self._settings.auth_ad_timeout_sec
        try:
            server = Server(
                ldap_url,
                use_ssl=ldap_url.startswith("ldaps://"),
                get_info="ALL",
                connect_timeout=timeout,
            )
            conn = Connection(
                server,
                user=username,
                password=password,
                auto_bind=False,
                receive_timeout=timeout,
            )
            bound = conn.bind()
            if bound:
                conn.unbind()
            return bound  # type: ignore[no-any-return]
        except Exception as exc:
            logger.error("ldap_bind_error", ldap_url=ldap_url, error=str(exc))
            raise LDAPError(f"Error de conexión LDAP: {exc}") from exc

    # ── Cookie firmada (itsdangerous) ───────────────────────────────────

    def create_session_token(self, user_id: int) -> str:
        """Crea token firmado con user_id."""
        return self._serializer.dumps({"uid": user_id})

    def validate_session_token(self, token: str) -> int | None:
        """Valida token y retorna user_id si vigente, None si expirado/inválido.

        El max_age se resuelve en cada llamada (tabla app_settings, con .env de
        fallback): así un cambio del timeout aplica también a las sesiones que
        ya estaban abiertas, sin reemitir cookies.
        """
        max_age = get_session_timeout_minutes(self._db) * 60
        try:
            data: dict[str, Any] = self._serializer.loads(token, max_age=max_age)
            return data.get("uid")
        except SignatureExpired:
            logger.info("session_token_expired")
            return None
        except BadSignature:
            logger.warning("session_token_invalid")
            return None

    # ── Logout ──────────────────────────────────────────────────────────

    def logout(
        self,
        username: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Registra evento de logout."""
        self._audit.log_logout(
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )
        self._db.commit()
        logger.info("logout", username=username)
