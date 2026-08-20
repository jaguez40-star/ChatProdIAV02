"""Settings — patrón Robustez V02 (L3): env_file con ruta ABSOLUTA (funciona
con cualquier CWD), listas como CSV + property (evita el parser JSON de
pydantic-settings), y `SECRET_KEY` obligatoria con longitud mínima.

Corrección C15/H6 sobre el original: Robustez V02 solo rechazaba `*` en
LOCAL_LOGIN_ALLOWED_IPS cuando APP_ENV=production. Aquí se rechaza SIEMPRE —
en dev basta con `127.0.0.1,::1`; el comodín es una puerta trasera que su
propio código fuente marca como "usar solo temporalmente" (services.py:150-179
de la plantilla) y que aquí simplemente no existe como opción válida.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Aplicación ────────────────────────────────────────────────────────
    app_env: Literal["development", "production"] = "development"
    app_port: int = 6034
    log_level: str = "INFO"

    # ── Base de datos de autenticación (SQLite, motor db_auth) ─────────────
    database_url: str = "sqlite:///./data/prodia_v02_auth.db"

    # ── Base de datos operacional (PostgreSQL, motor db_prod) ──────────────
    # OPCIONAL en F0 (H4/P-6): el backend arranca sin Postgres disponible.
    # Pasa a CRÍTICA en F1 cuando la feature `tablas` dependa de ella.
    # TODO[F1]: reclasificar como crítica cuando exista una feature que la use.
    prod_database_url: str = ""

    # BD operacional de ROBUSTEZ (schema `ops.*`) — usada desde F2 (EBITDA).
    ops_database_url: str = ""

    # ── Fuentes de datos de F2 (Análisis) ───────────────────────────────────
    # Rutas a ficheros de datos operativos. Viven FUERA del repo (.gitignore) y
    # se copian al desplegar. Default vacío a propósito: un campo obligatorio
    # rompería `scripts/export_openapi.py` —y con él el pre-commit y CI— en
    # cualquier máquina que no tenga los ficheros. Ausente = la feature degrada
    # con `sin_datos` + `motivo`, nunca un 500.
    #
    # ECP_DIFERIDAS.db (954 MB): se abre SOLO LECTURA. Su tabla de respaldo
    # `AVM_DATADIF_BACK` y los índices `ix_dd_event`/`ix_dd_cover` están
    # corruptos (verificado 2026-08-20), pero `AVM_DATADIF` —la única que se
    # consulta— está sana con 1.142.599 filas. Por eso NUNCA se debe hacer
    # `SELECT count(*)` a secas sobre ella: SQLite lo resolvería con el índice
    # corrupto y fallaría. Filtrar por columna fuerza escaneo de tabla y
    # funciona; contar filas se hace en Python tras el GROUP BY, como el origen.
    diferidas_db_path: str = ""
    eventos_ow_path: str = ""

    # ── LLM (Ollama) — F2 usa el pulido de prosa del Análisis Ejecutivo ──────
    consulta_ollama_url: str = "http://localhost:11434/api/generate"
    consulta_llm_model: str = "qwen2.5:3b"
    # Cuánto queda residente el modelo tras cada petición. "-1" = indefinido.
    # Una petición SIN keep_alive resetea el de Ollama a 5 min y el modelo se
    # descarga en el primer hueco de inactividad; la siguiente llamada vuelve a
    # pagar el arranque en frío (~342 s > timeout → fallback sin prosa).
    consulta_keep_alive: str = "-1"

    @property
    def keep_alive_ollama(self) -> int | str:
        """Valor para el body de Ollama: entero si es numérico, si no la cadena
        de duración tal cual ("5m"). Ollama exige el ENTERO -1 como número JSON
        — la cadena "-1" la interpretaría como duración Go inválida y fallaría.
        """
        valor = self.consulta_keep_alive.strip()
        try:
            return int(valor)
        except ValueError:
            return valor

    # ── Análisis Ejecutivo (F2) ─────────────────────────────────────────────
    # En desarrollo se sirve el composer determinista: es superior al qwen
    # local, que confunde cifras, y el gate solo valida estructura, no
    # grounding. En producción (gemma4) se activa para el pulido de prosa.
    ejecutivo_usar_llm: bool = False
    # En pruebas, `false` evita tapar un fallo de Gemma con el texto base:
    # devuelve generado_por="error" + el diagnóstico crudo para poder validarlo.
    ejecutivo_fallback: bool = True
    # Banda ámbar de las tarjetas de cierre: alineado (>=meta) / ajustado
    # (>=meta*0.93) / actuar (por debajo). Eje de estado PROPIO, independiente
    # de los umbrales 90/75 de los chips — son dos ejes distintos a propósito.
    # Calibrado contra mayo-2026 (Rubiales 95,6% → ajustado; APIAY 50,7% →
    # actuar). Recalibrar aquí, nunca en el código.
    kpi_cierre_ambar_pct: float = 0.93
    # Caché TTL de los paneles caros (A4). 15 min: el reporte cambia 1 vez/día.
    # Sin ella, cada login dispara una generación de LLM y Ollama las serializa.
    analisis_cache_ttl_s: int = 900

    # ── F3 · Ingesta de archivos .xlsm ──────────────────────────────────────
    # Dónde aterrizan los archivos subidos. Se conservan tras ingerir: son la
    # única evidencia de qué se cargó si hay que auditar un reporte. Ruta
    # relativa al backend por defecto, y FUERA del repo (.gitignore).
    ingesta_upload_dir: str = "./data/uploads"
    # Tope de tamaño. Los .xlsm NEW reales rondan los 125 MB; 200 deja margen
    # sin permitir que una subida accidental de varios GB tumbe el proceso.
    # El origen NO validaba tamaño (G11): cualquier archivo llegaba al ETL.
    ingesta_max_upload_mb: int = 200
    # Latido del progreso en vivo. Una hoja pesada (BDP_datos_mes, ~315.000
    # filas) puede tardar minutos SIN emitir nada, y cualquier proxy con
    # `proxy_read_timeout` cortaría la conexión a mitad de la ingesta (G3).
    ingesta_sse_heartbeat_s: int = 15

    # ── Seguridad — cookie firmada (itsdangerous) ───────────────────────────
    secret_key: str

    @field_validator("secret_key")
    @classmethod
    def secret_key_not_empty(cls, v: str) -> str:
        if len(v.strip()) < 16:
            raise ValueError("SECRET_KEY debe tener al menos 16 caracteres")
        return v

    # ── LDAP / Active Directory ──────────────────────────────────────────────
    auth_ad_domain: str = "red.ecopetrol.com.co"
    auth_ad_server: str = ""
    auth_ad_timeout_sec: int = 10

    # ── Sesión ────────────────────────────────────────────────────────────
    session_timeout_minutes: int = 30

    # ── Login local de desarrollo auditado (D3) ──────────────────────────────
    enable_local_login: bool = False
    local_login_username: str = ""
    local_login_password: str = ""
    local_login_extra_users: str = ""
    local_login_allowed_ips: str = "127.0.0.1,::1"

    @field_validator("local_login_allowed_ips")
    @classmethod
    def local_login_ips_no_wildcard(cls, v: str) -> str:
        # C15/H6: "*" desactiva el filtro de IP — es la puerta trasera que
        # el código fuente de Robustez V02 marca como temporal. Aquí se
        # rechaza SIEMPRE, sin excepción por entorno.
        if "*" in {p.strip() for p in v.split(",")}:
            raise ValueError(
                "LOCAL_LOGIN_ALLOWED_IPS no admite '*' (D3) — enumera IPs concretas"
            )
        return v

    # ── Seed del padrón (D2, migración 0003) ────────────────────────────────
    seed_source_auth_db: str = ""
    seed_admin_usernames: str = ""

    # ── CORS ──────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:6033"

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def local_login_allowed_ips_list(self) -> set[str]:
        return {p.strip() for p in self.local_login_allowed_ips.split(",") if p.strip()}

    @property
    def local_login_users(self) -> dict[str, str]:
        """Combina LOCAL_LOGIN_USERNAME/PASSWORD + LOCAL_LOGIN_EXTRA_USERS.

        Formato de EXTRA_USERS: "user1:pass1,user2:pass2". Username normalizado
        a lowercase (patrón de Robustez V02, services.py:150-179).
        """
        users: dict[str, str] = {}
        if self.local_login_username and self.local_login_password:
            users[self.local_login_username.strip().lower()] = self.local_login_password
        for pair in self.local_login_extra_users.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            u, p = pair.split(":", 1)
            users[u.strip().lower()] = p
        return users

    @property
    def seed_admin_usernames_list(self) -> list[str]:
        return [
            u.strip().lower() for u in self.seed_admin_usernames.split(",") if u.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
