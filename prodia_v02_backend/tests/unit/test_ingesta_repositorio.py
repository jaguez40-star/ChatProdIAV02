"""Tests del repositorio del ETL — con el doble de escrituras, sin tocar PostgreSQL.

El test que más importa es el de los DELETE acotados. La idempotencia del ETL se apoya en
`DELETE WHERE reporte_id=:r` antes de reinsertar; si ese `WHERE` se perdiera en un
refactor, el flujo seguiría "funcionando" —ninguna aserción de comportamiento fallaría—
pero cada ingesta borraría la tabla entera. El doble aborta en cuanto detecta uno sin
acotar, así que basta con ejercitar cada método que borra.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from src.features.ingesta.extractores.comunes import FilaExtraida
from src.features.ingesta.repositories import (
    TAMANO_LOTE,
    CacheDimension,
    IngestaRepository,
)
from tests.fakes.db_escritura_falsa import SesionEscrituraFalsa

ENE = dt.date(2026, 1, 1)
FEB = dt.date(2026, 2, 1)


def _repo(
    respuestas: dict[str, Any] | None = None,
) -> tuple[IngestaRepository, SesionEscrituraFalsa]:
    sesion = SesionEscrituraFalsa(respuestas=respuestas)
    return IngestaRepository(sesion), sesion  # type: ignore[arg-type]


# ── La red de seguridad: ningún DELETE sin acotar ────────────────────────────


@pytest.mark.unit
def test_todos_los_borrados_van_acotados_por_reporte() -> None:
    """Si alguno perdiera su WHERE, el doble abortaría este test."""
    repo, sesion = _repo()

    repo.aterrizar_hoja_tipada("bdp_datos_dia", ["campo"], 1042, [])
    repo.aterrizar_hoja_generica("INICIO", 1042, [])
    repo.reemplazar_tablas_de_hoja(1042, "NEW MES-AÑO", [])
    repo.reemplazar_comentarios(1042, [])

    borrados = [e for e in sesion.escrituras if e.verbo == "DELETE"]
    assert len(borrados) == 4
    assert all("reporte_id=:r" in e.sql for e in borrados)


@pytest.mark.unit
def test_el_borrado_de_una_hoja_se_acota_tambien_por_hoja() -> None:
    """Reingerir una hoja no debe llevarse por delante las demás del mismo reporte."""
    repo, sesion = _repo()

    repo.reemplazar_tablas_de_hoja(1042, "PROGRAMA", [])

    borrado = sesion.borrados_en("core.fact_tabla_hoja")[0]
    assert "hoja=:h" in borrado.sql


# ── config_reporte ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_el_reporte_se_identifica_por_la_fecha_del_nombre_del_archivo() -> None:
    repo, _ = _repo(respuestas={"RETURNING reporte_id": 1042})

    reporte_id, fecha = repo.upsert_reporte(
        Path("20260815_Reporte Diario.xlsm"), tiene_hojas_raw=True
    )

    assert reporte_id == 1042
    assert fecha == dt.date(2026, 8, 15)


@pytest.mark.unit
def test_el_upsert_de_reporte_es_idempotente() -> None:
    """`ON CONFLICT (fecha_reporte)` es lo que hace segura la reingesta."""
    repo, sesion = _repo(respuestas={"RETURNING reporte_id": 1})

    repo.upsert_reporte(Path("20260815_x.xlsm"), tiene_hojas_raw=True)

    assert sesion.hubo_upsert_en("core.config_reporte")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tiene_raw", "tipo", "nivel"),
    [(True, "NEW", "FULL"), (False, "STD", "SIN_ECP")],
)
def test_el_tipo_de_reporte_se_deriva_de_las_hojas_raw(
    tiene_raw: bool, tipo: str, nivel: str
) -> None:
    repo, sesion = _repo(respuestas={"RETURNING reporte_id": 1})

    repo.upsert_reporte(Path("20260815_x.xlsm"), tiene_hojas_raw=tiene_raw)

    parametros = sesion.inserciones_en("core.config_reporte")[0].parametros
    assert parametros["tp"] == tipo
    assert parametros["nv"] == nivel


@pytest.mark.unit
def test_un_archivo_sin_fecha_en_el_nombre_deja_la_fecha_en_none() -> None:
    repo, _ = _repo(respuestas={"RETURNING reporte_id": 1})

    _, fecha = repo.upsert_reporte(Path("sin_fecha.xlsm"), tiene_hojas_raw=False)

    assert fecha is None


@pytest.mark.unit
def test_si_el_upsert_no_devuelve_id_se_falla_ruidosamente() -> None:
    """Seguir sin reporte_id escribiría facts huérfanos que nadie podría rastrear."""
    repo, _ = _repo()  # sin respuesta configurada → scalar() devuelve None

    with pytest.raises(RuntimeError, match="no devolvió reporte_id"):
        repo.upsert_reporte(Path("20260815_x.xlsm"), tiene_hojas_raw=True)


# ── Bloqueo de concurrencia ──────────────────────────────────────────────────


@pytest.mark.unit
def test_el_bloqueo_se_toma_por_fecha_de_reporte() -> None:
    """Dos ingestas de fechas distintas no deben bloquearse entre sí."""
    repo, sesion = _repo()

    repo.tomar_bloqueo_de_reporte(ENE)

    assert sesion.locks_tomados == [{"clave": "2026-01-01"}]
    assert "pg_advisory_xact_lock" in sesion.sentencias[0]


@pytest.mark.unit
def test_un_reporte_sin_fecha_usa_una_clave_de_bloqueo_propia() -> None:
    repo, sesion = _repo()

    repo.tomar_bloqueo_de_reporte(None)

    assert sesion.locks_tomados == [{"clave": "sin-fecha"}]


# ── Dimensiones ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_la_cache_de_dimension_no_consulta_dos_veces_el_mismo_nombre() -> None:
    sesion = SesionEscrituraFalsa(respuestas={"RETURNING vice_id": 7})
    cache = CacheDimension(sesion, "core.dim_vicepresidencia", "vice_id", "sigla")  # type: ignore[arg-type]

    primero = cache.get("VRO")
    segundo = cache.get("VRO")

    assert primero == segundo == 7
    inserciones = [s for s in sesion.sentencias if "INSERT" in s]
    assert len(inserciones) == 1  # la segunda salió de la caché


@pytest.mark.unit
def test_la_dimension_devuelve_none_ante_un_nombre_nulo() -> None:
    sesion = SesionEscrituraFalsa()
    cache = CacheDimension(sesion, "core.dim_socio", "socio_id", "nombre")  # type: ignore[arg-type]

    assert cache.get(None) is None


@pytest.mark.unit
def test_las_fechas_se_siembran_con_sus_atributos_derivados() -> None:
    repo, sesion = _repo()

    repo.asegurar_fechas({dt.date(2026, 8, 15)})

    parametros = sesion.inserciones_en("core.dim_fecha")[0].parametros[0]
    assert parametros["a"] == 2026
    assert parametros["t"] == 3  # agosto es tercer trimestre
    assert parametros["dw"] == 6  # sábado
    assert parametros["sm"] == 3  # tercera semana del mes


@pytest.mark.unit
def test_sembrar_fechas_vacias_no_escribe_nada() -> None:
    repo, sesion = _repo()

    repo.asegurar_fechas(set())

    assert sesion.escrituras == []


@pytest.mark.unit
def test_las_fuentes_preservan_los_valores_no_nulos_ya_guardados() -> None:
    """Un reporte con una columna vacía no debe borrar lo que otro sí aportó."""
    repo, sesion = _repo()

    repo.upsert_fuentes({101: {"nombre": "CASTILLA", "campo": None}}, 1042)

    sql = sesion.inserciones_en("core.dim_fuente")[0].sql
    assert "COALESCE(EXCLUDED.nombre, core.dim_fuente.nombre)" in sql


# ── Capa bronze ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_bronze_guarda_todo_como_texto_saltando_el_encabezado() -> None:
    repo, sesion = _repo()
    filas = [("CAMPO", "VOLUMEN"), ("CASTILLA", 100), ("APIAY", 200)]

    total = repo.aterrizar_hoja_tipada(
        "bdp_datos_dia", ["campo", "volumen"], 1042, filas
    )

    assert total == 3  # el helper no descarta el encabezado: lo hace quien lo llama
    escritas = sesion.inserciones_en("bronze.bdp_datos_dia")[0].parametros
    assert escritas[1]["volumen"] == "100"  # convertido a texto


@pytest.mark.unit
def test_bronze_omite_las_filas_completamente_vacias() -> None:
    repo, _ = _repo()

    total = repo.aterrizar_hoja_tipada(
        "bdp_datos_dia", ["campo"], 1042, [("CASTILLA",), (None,), ("APIAY",)]
    )

    assert total == 2


@pytest.mark.unit
def test_la_hoja_generica_usa_el_encabezado_como_claves_del_json() -> None:
    repo, sesion = _repo()
    filas = [("CAMPO", "VOL"), ("CASTILLA", 10)]

    total = repo.aterrizar_hoja_generica("INICIO", 1042, filas)

    assert total == 1  # el encabezado no cuenta como dato
    contenido = json.loads(
        sesion.inserciones_en("bronze.hoja_landing")[0].parametros[0]["p"]
    )
    assert contenido == {"CAMPO": "CASTILLA", "VOL": "10"}


@pytest.mark.unit
def test_una_columna_sin_nombre_no_se_pierde() -> None:
    repo, sesion = _repo()
    filas = [("CAMPO", None), ("CASTILLA", "algo")]

    repo.aterrizar_hoja_generica("INICIO", 1042, filas)

    contenido = json.loads(
        sesion.inserciones_en("bronze.hoja_landing")[0].parametros[0]["p"]
    )
    assert contenido["col1"] == "algo"


@pytest.mark.unit
def test_una_hoja_generica_vacia_solo_borra() -> None:
    repo, sesion = _repo()

    total = repo.aterrizar_hoja_generica("INICIO", 1042, [])

    assert total == 0
    assert sesion.inserciones_en("bronze.hoja_landing") == []
    assert len(sesion.borrados_en("bronze.hoja_landing")) == 1


# ── fact_tabla_hoja ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_las_filas_duplicadas_se_deduplican_con_last_wins() -> None:
    """`fact_tabla_hoja` no tiene clave única: sin deduplicar, el visor mostraría la
    misma celda dos veces."""
    repo, _ = _repo()
    filas = [
        FilaExtraida(1, "T1", {"campo": "CASTILLA"}, ENE, 100.0),
        FilaExtraida(1, "T1", {"campo": "CASTILLA"}, ENE, 200.0),  # misma clave
        FilaExtraida(1, "T1", {"campo": "APIAY"}, ENE, 300.0),
    ]

    insertadas = repo.reemplazar_tablas_de_hoja(1042, "H", filas)

    assert len(insertadas) == 2
    assert 200.0 in [f.valor for f in insertadas]  # gana la última
    assert 100.0 not in [f.valor for f in insertadas]


@pytest.mark.unit
def test_la_fecha_forma_parte_de_la_clave_de_deduplicacion() -> None:
    repo, _ = _repo()
    filas = [
        FilaExtraida(1, "T1", {"campo": "CASTILLA"}, ENE, 10.0),
        FilaExtraida(1, "T1", {"campo": "CASTILLA"}, FEB, 20.0),
    ]

    insertadas = repo.reemplazar_tablas_de_hoja(1042, "H", filas)

    assert len(insertadas) == 2  # distinta fecha, no son duplicados


@pytest.mark.unit
def test_las_dims_se_guardan_como_json_ordenado() -> None:
    """El orden estable de las claves es lo que hace comparable la clave de dedup."""
    repo, sesion = _repo()
    filas = [FilaExtraida(1, "T1", {"b": "2", "a": "1"}, ENE, 10.0)]

    repo.reemplazar_tablas_de_hoja(1042, "H", filas)

    escrito = sesion.inserciones_en("core.fact_tabla_hoja")[0].parametros[0]
    assert json.loads(escrito["dims"]) == {"a": "1", "b": "2"}


@pytest.mark.unit
def test_las_dims_no_textuales_se_serializan_sin_reventar() -> None:
    """`dims` es JSONB y los extractores meten números y fechas, no solo texto."""
    repo, sesion = _repo()
    filas = [FilaExtraida(1, "T1", {"anio": 2026, "desde": ENE}, None, 10.0)]

    repo.reemplazar_tablas_de_hoja(1042, "H", filas)

    escrito = sesion.inserciones_en("core.fact_tabla_hoja")[0].parametros[0]
    assert json.loads(escrito["dims"]) == {"anio": 2026, "desde": "2026-01-01"}


@pytest.mark.unit
def test_una_hoja_sin_filas_solo_borra_lo_anterior() -> None:
    repo, sesion = _repo()

    insertadas = repo.reemplazar_tablas_de_hoja(1042, "H", [])

    assert insertadas == []
    assert sesion.inserciones_en("core.fact_tabla_hoja") == []
    assert len(sesion.borrados_en("core.fact_tabla_hoja")) == 1


@pytest.mark.unit
def test_los_insert_masivos_se_parten_en_lotes() -> None:
    """Sin lotes, BDP_datos_mes (~315.000 filas) armaría un statement gigantesco."""
    repo, sesion = _repo()
    filas = [
        FilaExtraida(1, "T1", {"n": str(i)}, ENE, float(i))
        for i in range(TAMANO_LOTE + 500)
    ]

    repo.reemplazar_tablas_de_hoja(1042, "H", filas)

    inserciones = sesion.inserciones_en("core.fact_tabla_hoja")
    assert len(inserciones) == 2
    assert inserciones[0].filas == TAMANO_LOTE
    assert inserciones[1].filas == 500


# ── Comentarios ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_los_comentarios_se_reemplazan_enteros() -> None:
    repo, sesion = _repo()
    filas = [
        {
            "rep": 1042,
            "tipo": 1,
            "activos": "CASTILLA",
            "area": "ORIENTE",
            "comentario": "Sin novedad",
            "programa": None,
            "extra": None,
        }
    ]

    total = repo.reemplazar_comentarios(1042, filas)

    assert total == 1
    assert len(sesion.borrados_en("core.fact_comentarios_produccion")) == 1
