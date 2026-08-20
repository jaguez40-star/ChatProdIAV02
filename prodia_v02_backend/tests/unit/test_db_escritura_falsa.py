"""Tests del doble de escrituras — es infraestructura de test, y si falla en silencio
todos los tests del ETL de F3 mentirían.

El caso que más importa es `BorradoSinAcotarError`: la idempotencia del ETL se apoya en
`DELETE WHERE reporte_id=:r` antes de reinsertar. Un `WHERE` perdido en un refactor no
rompería ningún test convencional —el flujo seguiría "funcionando"— pero borraría la tabla
entera en producción. Estos tests garantizan que la red que lo detecta funciona de verdad.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from tests.fakes.db_escritura_falsa import BorradoSinAcotarError, SesionEscrituraFalsa


@pytest.mark.unit
def test_registra_un_insert_con_sus_filas() -> None:
    sesion = SesionEscrituraFalsa()

    sesion.execute(
        text("INSERT INTO core.fact_tabla_hoja (a, b) VALUES (:a, :b)"),
        [{"a": 1, "b": 2}, {"a": 3, "b": 4}],
    )

    inserciones = sesion.inserciones_en("core.fact_tabla_hoja")
    assert len(inserciones) == 1
    assert sesion.filas_escritas_en("core.fact_tabla_hoja") == 2


@pytest.mark.unit
def test_acepta_delete_acotado_por_reporte() -> None:
    sesion = SesionEscrituraFalsa()

    sesion.execute(
        text("DELETE FROM core.fact_tabla_hoja WHERE reporte_id=:r AND hoja=:h"),
        {"r": 1042, "h": "NEW MES-AÑO"},
    )

    assert len(sesion.borrados_en("core.fact_tabla_hoja")) == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM core.fact_tabla_hoja",
        "DELETE FROM core.fact_tabla_hoja WHERE hoja=:h",
        "DELETE FROM bronze.bdp_datos_mes WHERE 1=1",
    ],
)
def test_un_delete_sin_acotar_por_reporte_aborta_el_test(sql: str) -> None:
    """La red de seguridad: sin `reporte_id=:...` el borrado se lleva la tabla entera."""
    sesion = SesionEscrituraFalsa()

    with pytest.raises(BorradoSinAcotarError):
        sesion.execute(text(sql), {"h": "X"})


@pytest.mark.unit
def test_detecta_si_un_insert_es_idempotente() -> None:
    sesion = SesionEscrituraFalsa()

    sesion.execute(
        text(
            "INSERT INTO core.dim_fuente (fuente_id) VALUES (:f) "
            "ON CONFLICT (fuente_id) DO UPDATE SET fuente_id=EXCLUDED.fuente_id"
        ),
        {"f": 1},
    )
    sesion.execute(text("INSERT INTO core.ingesta_log (hoja) VALUES (:h)"), {"h": "X"})

    assert sesion.hubo_upsert_en("core.dim_fuente") is True
    assert sesion.hubo_upsert_en("core.ingesta_log") is False


@pytest.mark.unit
def test_registra_el_advisory_lock_sin_tratarlo_como_escritura() -> None:
    sesion = SesionEscrituraFalsa()

    sesion.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:clave))"), {"clave": "x"}
    )

    assert sesion.locks_tomados == [{"clave": "x"}]
    assert sesion.escrituras == []


@pytest.mark.unit
def test_puede_simular_un_fallo_a_mitad_del_etl() -> None:
    """Para verificar G2: un fallo tardío debe revertir y reportar `revertido`."""
    sesion = SesionEscrituraFalsa(fallar_en="fact_produccion_mes_ecp")

    sesion.execute(text("INSERT INTO core.config_reporte (a) VALUES (:a)"), {"a": 1})
    with pytest.raises(OperationalError):
        sesion.execute(
            text("INSERT INTO core.fact_produccion_mes_ecp (b) VALUES (:b)"), {"b": 2}
        )

    assert len(sesion.inserciones_en("core.config_reporte")) == 1


@pytest.mark.unit
def test_devuelve_las_respuestas_configuradas() -> None:
    """El ETL necesita el `reporte_id` que devuelve el UPSERT de config_reporte."""
    sesion = SesionEscrituraFalsa(respuestas={"RETURNING reporte_id": 1042})

    resultado = sesion.execute(
        text("INSERT INTO core.config_reporte (f) VALUES (:f) RETURNING reporte_id"),
        {"f": "2026-08-15"},
    )

    assert resultado.scalar() == 1042


@pytest.mark.unit
def test_cuenta_commits_y_rollbacks() -> None:
    sesion = SesionEscrituraFalsa()

    sesion.commit()
    sesion.rollback()
    sesion.commit()

    assert sesion.commits == 2
    assert sesion.rollbacks == 1
