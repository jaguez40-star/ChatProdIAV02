"""La cola del Control 3 — el orden ES la funcionalidad.

Lo que se prueba aquí no es que devuelva filas, sino que las devuelva en el
orden que hace productiva una sesión de revisión: sospechas primero, luego lo
que decidió el LLM, y dentro de cada escalón lo más antiguo antes.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.features.consulta import libreta
from src.features.consulta.revision import GRUPOS_POR_TECLA, cola_de_revision

pytestmark = pytest.mark.unit

_DDL = """
CREATE TABLE clasificacion_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario VARCHAR(120),
    conversacion_id VARCHAR(64),
    texto_pregunta TEXT NOT NULL,
    grupo_asignado VARCHAR(20) NOT NULL,
    capa_resolutora VARCHAR(20) NOT NULL,
    patrones_atrapados TEXT,
    entidad_cruda VARCHAR(200),
    llm_diag VARCHAR(40),
    veredicto VARCHAR(30) NOT NULL DEFAULT 'pendiente',
    grupo_correcto VARCHAR(20),
    fuente_veredicto VARCHAR(20),
    ts_veredicto TIMESTAMP,
    nota_revision TEXT
)
"""

BASE = dt.datetime(2026, 8, 20, 9, 0, 0)


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    with engine.begin() as conexion:
        conexion.execute(text(_DDL))
    sesion = sessionmaker(bind=engine)()
    yield sesion
    sesion.close()


def _insertar(db: Session, texto: str, *, capa: str = "regex", minutos: int = 0) -> int:
    fila = db.execute(
        text("""
            INSERT INTO clasificacion_log
                (ts, texto_pregunta, grupo_asignado, capa_resolutora)
            VALUES (:ts, :texto, 'cuantificar', :capa)
            RETURNING id
            """),
        {"ts": BASE + dt.timedelta(minutes=minutos), "texto": texto, "capa": capa},
    ).scalar()
    db.commit()
    return int(fila)  # type: ignore[arg-type]


def _textos(db: Session) -> list[str]:
    return [f["texto_pregunta"] for f in cola_de_revision(db)]


def test_las_sospechas_van_primero(db: Session) -> None:
    """Son las que una señal marcó como probablemente mal clasificadas."""
    _insertar(db, "normal", minutos=0)
    sospechosa = _insertar(db, "sospechosa", minutos=10)
    libreta.marcar_sospecha(db, sospechosa)

    assert _textos(db)[0] == "sospechosa"


def test_lo_que_resolvio_el_llm_va_antes_que_lo_que_resolvio_la_regex(
    db: Session,
) -> None:
    """Si la Capa 1 atrapó la pregunta, la decisión es determinista y auditable;
    donde puede haber deriva es en lo que decidió el modelo."""
    _insertar(db, "por regex", capa="regex", minutos=0)
    _insertar(db, "por llm", capa="llm", minutos=10)

    assert _textos(db) == ["por llm", "por regex"]


def test_dentro_del_mismo_escalon_lo_mas_antiguo_primero(db: Session) -> None:
    """Una cola que se revisa por lo más reciente deja un fondo que nadie mira."""
    _insertar(db, "vieja", capa="llm", minutos=0)
    _insertar(db, "nueva", capa="llm", minutos=60)

    assert _textos(db) == ["vieja", "nueva"]


def test_lo_ya_juzgado_no_vuelve_a_la_cola(db: Session) -> None:
    juzgada = _insertar(db, "ya vista")
    libreta.poner_veredicto(db, juzgada, "confirmado_revision", fuente="revision")
    _insertar(db, "sin ver", minutos=5)

    assert _textos(db) == ["sin ver"]


def test_el_limite_se_acota(db: Session) -> None:
    for i in range(6):
        _insertar(db, f"p{i}", minutos=i)

    assert len(cola_de_revision(db, limite=3)) == 3
    assert len(cola_de_revision(db, limite=0)) == 1  # se sube a 1
    assert len(cola_de_revision(db, limite=99_999)) == 6  # se baja a 500


def test_una_cola_vacia_no_es_un_error(db: Session) -> None:
    assert cola_de_revision(db) == []


def test_las_teclas_cubren_los_cuatro_grupos() -> None:
    """El revisor tiene estas cuatro en los dedos desde el sistema viejo."""
    assert set(GRUPOS_POR_TECLA) == {"1", "2", "3", "4"}
    assert set(GRUPOS_POR_TECLA.values()) == {
        "jerarquizar",
        "cuantificar",
        "analizar",
        "desconocido",
    }
