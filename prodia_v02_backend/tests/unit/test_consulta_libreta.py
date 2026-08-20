"""La libreta de clasificación, contra SQLite real en memoria.

Se usa una BD de verdad —no un doble— porque lo que hay que verificar es SQL:
que el `WHERE veredicto = 'pendiente'` protege el juicio humano, que una
corrección exige grupo, y que el orden pone las sospechas primero. Un doble que
reconociera cadenas no probaría nada de eso.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.features.consulta import libreta

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


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    with engine.begin() as conexion:
        conexion.execute(text(_DDL))
    sesion = sessionmaker(bind=engine)()
    yield sesion
    sesion.close()


def _registrar(db: Session, **kwargs: object) -> int:
    base = {
        "texto": "cuanto produjo CASTILLA",
        "grupo": "cuantificar",
        "capa": "regex",
    }
    base.update(kwargs)
    log_id = libreta.registrar(db, **base)  # type: ignore[arg-type]
    assert log_id is not None
    return log_id


def test_registrar_devuelve_el_id_y_arranca_pendiente(db: Session) -> None:
    """Sin veredicto todavía: nadie lo ha juzgado."""
    log_id = _registrar(db, usuario="javier", entidad="CASTILLA")

    fila = (
        db.execute(
            text(
                "SELECT veredicto, usuario, entidad_cruda FROM clasificacion_log WHERE id = :i"
            ),
            {"i": log_id},
        )
        .mappings()
        .one()
    )

    assert fila["veredicto"] == "pendiente"
    assert fila["usuario"] == "javier"
    assert fila["entidad_cruda"] == "CASTILLA"


def test_los_patrones_se_guardan_como_json(db: Session) -> None:
    """Permiten trazar POR QUÉ la regex disparó, al revisar semanas después."""
    log_id = _registrar(db, patrones=["PRODUCCION DE", "CUANTO"])

    guardado = db.execute(
        text("SELECT patrones_atrapados FROM clasificacion_log WHERE id = :i"),
        {"i": log_id},
    ).scalar()

    assert guardado is not None
    assert "PRODUCCION DE" in guardado


def test_el_diagnostico_del_llm_se_conserva(db: Session) -> None:
    """🔑 Sin `llm_diag`, un timeout por arranque en frío del modelo y un
    error del clasificador parecen lo mismo al revisar la libreta."""
    log_id = _registrar(db, capa="llm", llm_diag="timeout")

    assert (
        db.execute(
            text("SELECT llm_diag FROM clasificacion_log WHERE id = :i"), {"i": log_id}
        ).scalar()
        == "timeout"
    )


# ── Veredictos ───────────────────────────────────────────────────────────────


def test_confirmar_no_duplica_el_grupo(db: Session) -> None:
    """Una confirmación fuerza `grupo_correcto` a NULL: el grupo correcto ya
    es el asignado, y duplicarlo invitaría a que diverjan."""
    log_id = _registrar(db)

    assert libreta.poner_veredicto(
        db, log_id, "confirmado_usuario", grupo_correcto="analizar"
    )

    fila = (
        db.execute(
            text(
                "SELECT veredicto, grupo_correcto FROM clasificacion_log WHERE id = :i"
            ),
            {"i": log_id},
        )
        .mappings()
        .one()
    )

    assert fila["veredicto"] == "confirmado_usuario"
    assert fila["grupo_correcto"] is None


def test_corregir_exige_decir_cual_era_el_grupo(db: Session) -> None:
    """Una corrección sin grupo no enseña nada: no puede alimentar el golden."""
    log_id = _registrar(db)

    assert libreta.poner_veredicto(db, log_id, "corregido_usuario") is False
    assert (
        libreta.poner_veredicto(
            db, log_id, "corregido_usuario", grupo_correcto="ficticio"
        )
        is False
    )
    assert libreta.poner_veredicto(
        db, log_id, "corregido_usuario", grupo_correcto="analizar"
    )


def test_un_veredicto_inventado_se_rechaza(db: Session) -> None:
    log_id = _registrar(db)
    assert libreta.poner_veredicto(db, log_id, "me_gusta") is False


def test_un_id_inexistente_devuelve_false(db: Session) -> None:
    assert libreta.poner_veredicto(db, 9999, "confirmado_usuario") is False


# ── Sospecha: bandera, no veredicto ──────────────────────────────────────────


def test_la_sospecha_marca_una_fila_pendiente(db: Session) -> None:
    log_id = _registrar(db)

    assert libreta.marcar_sospecha(db, log_id, nota="reformuló a los 30 s")

    fila = (
        db.execute(
            text(
                "SELECT veredicto, fuente_veredicto FROM clasificacion_log WHERE id = :i"
            ),
            {"i": log_id},
        )
        .mappings()
        .one()
    )

    assert fila["veredicto"] == "sospecha"
    assert fila["fuente_veredicto"] == "indirecta"


def test_la_sospecha_jamas_pisa_el_juicio_de_una_persona(db: Session) -> None:
    """🔑 `WHERE veredicto = 'pendiente'`. Una señal automática no puede
    sobrescribir lo que un humano ya decidió."""
    log_id = _registrar(db)
    libreta.poner_veredicto(db, log_id, "confirmado_usuario")

    assert libreta.marcar_sospecha(db, log_id) is False

    assert (
        db.execute(
            text("SELECT veredicto FROM clasificacion_log WHERE id = :i"), {"i": log_id}
        ).scalar()
        == "confirmado_usuario"
    )


# ── Listado ──────────────────────────────────────────────────────────────────


def test_las_sospechas_van_primero(db: Session) -> None:
    """El orden no es cosmético: son las que más valor tienen para revisar."""
    _registrar(db, texto="primera")
    sospechosa = _registrar(db, texto="sospechosa")
    _registrar(db, texto="tercera")
    libreta.marcar_sospecha(db, sospechosa)

    filas = libreta.listar(db)["filas"]

    assert filas[0]["texto_pregunta"] == "sospechosa"


@pytest.mark.parametrize(
    ("filtro", "esperadas"), [("pendientes", 2), ("sospecha", 1), ("todas", 3)]
)
def test_los_filtros(db: Session, filtro: str, esperadas: int) -> None:
    _registrar(db, texto="a")
    b = _registrar(db, texto="b")
    _registrar(db, texto="c")
    libreta.marcar_sospecha(db, b)

    assert len(libreta.listar(db, filtro=filtro)["filas"]) == esperadas


def test_el_limite_se_acota(db: Session) -> None:
    """Un límite enorme vaciaría la memoria del servidor."""
    for i in range(5):
        _registrar(db, texto=f"p{i}")

    assert len(libreta.listar(db, limite=2)["filas"]) == 2
    assert len(libreta.listar(db, limite=0)["filas"]) == 1  # se sube a 1
    assert len(libreta.listar(db, limite=99999)["filas"]) == 5  # se baja a 500


def test_un_filtro_desconocido_no_rompe(db: Session) -> None:
    """Degrada a "todas" en vez de lanzar: es un parámetro de consulta."""
    _registrar(db, texto="a")
    assert len(libreta.listar(db, filtro="inventado")["filas"]) == 1
