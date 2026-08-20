"""Control 2 — señales indirectas.

`similitud()` se prueba pura, sin BD. `escanear()` se prueba contra SQLite real
con **fechas inyectadas**: es lo que permite verificar las ventanas de 120 s y
600 s sin esperarlas ni depender del reloj. En el origen esta función no tiene
ni un test, precisamente porque su aritmética de fechas vivía dentro del SQL.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.features.consulta import libreta, senales

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

AHORA = dt.datetime(2026, 8, 20, 12, 0, 0)


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    with engine.begin() as conexion:
        conexion.execute(text(_DDL))
    sesion = sessionmaker(bind=engine)()
    yield sesion
    sesion.close()


def _insertar(
    db: Session,
    texto: str,
    *,
    ts: dt.datetime,
    usuario: str | None = "javier",
    grupo: str = "cuantificar",
    capa: str = "regex",
) -> int:
    """Inserta con `ts` explícito — el DEFAULT no sirve para probar ventanas."""
    fila = db.execute(
        text("""
            INSERT INTO clasificacion_log
                (ts, usuario, texto_pregunta, grupo_asignado, capa_resolutora)
            VALUES (:ts, :usuario, :texto, :grupo, :capa)
            RETURNING id
            """),
        {"ts": ts, "usuario": usuario, "texto": texto, "grupo": grupo, "capa": capa},
    ).scalar()
    db.commit()
    return int(fila)  # type: ignore[arg-type]


def _veredicto_de(db: Session, log_id: int) -> str:
    return str(
        db.execute(
            text("SELECT veredicto FROM clasificacion_log WHERE id = :id"),
            {"id": log_id},
        ).scalar()
    )


# ── similitud: pura, sin BD ──────────────────────────────────────────────────


def test_dos_textos_identicos_son_uno() -> None:
    assert (
        senales.similitud("cuánto produjo Castilla", "cuánto produjo Castilla") == 1.0
    )


def test_dos_textos_sin_nada_en_comun_son_cero() -> None:
    assert senales.similitud("cuánto produjo Castilla", "quién ganó el partido") == 0.0


def test_el_texto_vacio_no_se_parece_a_nada() -> None:
    """Sin esta guarda, un `set()` vacío dividiría por cero."""
    assert senales.similitud("", "lo que sea") == 0.0
    assert senales.similitud("lo que sea", "") == 0.0


def test_los_acentos_no_cuentan_como_diferencia() -> None:
    """`norm()` pliega acentos: escribir sin tilde no debe bajar la similitud."""
    assert (
        senales.similitud("cuánto produjo Rubiales", "cuanto produjo rubiales") == 1.0
    )


def test_la_puntuacion_no_cuenta_como_diferencia() -> None:
    """`norm()` NO retira puntuación (lo dice su docstring), así que «RUBIALES?»
    y «RUBIALES» serían tokens distintos si no se recortara aquí."""
    assert (
        senales.similitud("¿cuánto produjo Rubiales?", "cuanto produjo Rubiales") == 1.0
    )


def test_una_reformulacion_parcial_queda_por_encima_del_umbral() -> None:
    """El caso real que la señal 1 busca: la misma pregunta, dicha distinto."""
    valor = senales.similitud(
        "cuánto produjo Castilla en mayo", "cuánto produjo Castilla mayo"
    )
    assert valor >= 0.70


# ── escanear: señal 1, reformulación ─────────────────────────────────────────


def test_una_reformulacion_dentro_de_la_ventana_marca_sospecha(db: Session) -> None:
    primera = _insertar(db, "cuánto produjo Castilla en mayo", ts=AHORA)
    _insertar(db, "cuánto produjo Castilla mayo", ts=AHORA + dt.timedelta(seconds=30))

    resultado = senales.escanear(db, ahora=AHORA + dt.timedelta(minutes=30))

    assert resultado["sospechas_nuevas"] == 1
    assert _veredicto_de(db, primera) == "sospecha"


def test_una_reformulacion_fuera_de_la_ventana_no_cuenta(db: Session) -> None:
    """121 s después ya no es una reformulación: es otra consulta."""
    primera = _insertar(db, "cuánto produjo Castilla en mayo", ts=AHORA)
    _insertar(db, "cuánto produjo Castilla mayo", ts=AHORA + dt.timedelta(seconds=200))

    senales.escanear(db, ahora=AHORA + dt.timedelta(minutes=30))

    assert _veredicto_de(db, primera) == "pendiente"


def test_una_pregunta_distinta_del_mismo_usuario_no_es_reformulacion(
    db: Session,
) -> None:
    primera = _insertar(db, "cuánto produjo Castilla", ts=AHORA)
    _insertar(
        db,
        "qué campos tiene la vicepresidencia GOR",
        ts=AHORA + dt.timedelta(seconds=30),
    )

    senales.escanear(db, ahora=AHORA + dt.timedelta(minutes=30))

    assert _veredicto_de(db, primera) == "pendiente"


def test_la_reformulacion_se_empareja_por_usuario_no_por_conversacion(
    db: Session,
) -> None:
    """H2 del origen: el flujo real cruza chats con IDs distintos —se prueba en
    Test Clas y se repite en Consulta—, así que emparejar por conversación no
    casaría jamás. Pero OTRO usuario preguntando lo mismo no es una señal."""
    mia = _insertar(db, "cuánto produjo Castilla en mayo", ts=AHORA, usuario="javier")
    _insertar(
        db,
        "cuánto produjo Castilla mayo",
        ts=AHORA + dt.timedelta(seconds=30),
        usuario="otra.persona",
    )

    senales.escanear(db, ahora=AHORA + dt.timedelta(minutes=30))

    assert _veredicto_de(db, mia) == "pendiente"


# ── escanear: señal 3, abandono ──────────────────────────────────────────────


def test_el_abandono_tras_un_desconocido_del_llm_marca_sospecha(db: Session) -> None:
    huerfana = _insertar(db, "algo raro", ts=AHORA, grupo="desconocido", capa="llm")

    resultado = senales.escanear(db, ahora=AHORA + dt.timedelta(seconds=700))

    assert resultado["sospechas_nuevas"] == 1
    assert _veredicto_de(db, huerfana) == "sospecha"


def test_el_out_por_filtro_no_cuenta_como_abandono(db: Session) -> None:
    """H-B del origen: `regex+filtro` es una salida CONFIADA ante algo fuera de
    dominio. Que el usuario no insista tras un off-topic es lo esperado."""
    fuera = _insertar(
        db,
        "cuántos pozos tiene el ajedrez",
        ts=AHORA,
        grupo="desconocido",
        capa="regex+filtro",
    )

    senales.escanear(db, ahora=AHORA + dt.timedelta(seconds=700))

    assert _veredicto_de(db, fuera) == "pendiente"


def test_sin_cumplirse_la_ventana_el_abandono_no_se_declara(db: Session) -> None:
    """A los 300 s el usuario todavía puede estar leyendo."""
    reciente = _insertar(db, "algo raro", ts=AHORA, grupo="desconocido", capa="llm")

    senales.escanear(db, ahora=AHORA + dt.timedelta(seconds=300))

    assert _veredicto_de(db, reciente) == "pendiente"


def test_si_el_usuario_siguio_preguntando_no_hubo_abandono(db: Session) -> None:
    primera = _insertar(db, "algo raro", ts=AHORA, grupo="desconocido", capa="llm")
    _insertar(db, "cuánto produjo Castilla", ts=AHORA + dt.timedelta(seconds=400))

    senales.escanear(db, ahora=AHORA + dt.timedelta(seconds=900))

    assert _veredicto_de(db, primera) == "pendiente"


# ── escanear: acotado y respeto al juicio humano ─────────────────────────────


def test_el_escaneo_no_mira_mas_alla_de_la_ventana_de_dias(db: Session) -> None:
    """H7 del origen: escanear la libreta entera crecería sin límite."""
    vieja = _insertar(
        db,
        "algo raro",
        ts=AHORA - dt.timedelta(days=30),
        grupo="desconocido",
        capa="llm",
    )

    resultado = senales.escanear(db, ahora=AHORA)

    assert resultado["filas_revisadas"] == 0
    assert _veredicto_de(db, vieja) == "pendiente"


def test_el_escaneo_jamas_pisa_un_veredicto_humano(db: Session) -> None:
    """La guarda vive en `marcar_sospecha`, pero se verifica desde aquí: es la
    regla que separa una señal débil de un juez."""
    juzgada = _insertar(db, "algo raro", ts=AHORA, grupo="desconocido", capa="llm")
    libreta.poner_veredicto(db, juzgada, "confirmado_usuario")

    senales.escanear(db, ahora=AHORA + dt.timedelta(seconds=700))

    assert _veredicto_de(db, juzgada) == "confirmado_usuario"


def test_el_escaneo_reporta_lo_que_hizo(db: Session) -> None:
    """El origen lo envolvía en `except: pass` y no devolvía nada: un escaneo
    que fallaba siempre era indistinguible de uno que no encontraba nada."""
    _insertar(db, "una", ts=AHORA)
    _insertar(db, "dos", ts=AHORA)

    resultado = senales.escanear(db, ahora=AHORA + dt.timedelta(minutes=1))

    assert resultado == {"sospechas_nuevas": 0, "filas_revisadas": 2}


def test_los_umbrales_salen_del_yaml() -> None:
    """Si el fichero dejara de leerse, las ventanas cambiarían en silencio."""
    cfg = senales._cfg()

    assert cfg["similitud_reformulacion"] == 0.70
    assert cfg["ventana_reformulacion_seg"] == 120
    assert cfg["ventana_abandono_seg"] == 600
    assert cfg["escaneo_dias"] == 7
