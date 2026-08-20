"""Tests del orquestador del ETL — sin PostgreSQL y sin archivos reales.

Lo que se verifica aquí es el **flujo y lo que promete al usuario**: el orden de las
escrituras, que el bloqueo se tome antes de escribir, y sobre todo que los eventos de
progreso digan la verdad (G2) y hagan visible una tabla vacía (G5).

El libro de Excel se sustituye por un doble mínimo: construir uno real para cada caso
haría los tests lentos y frágiles, y lo que se prueba es la orquestación, no la
extracción —eso ya lo cubren los tests de extractores.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from src.features.ingesta.extractores.comunes import FilaExtraida, ResultadoExtractor
from src.features.ingesta.repositories import IngestaRepository
from src.features.ingesta.schemas import EventoIngesta
from src.features.ingesta.services import IngestaService
from tests.fakes.db_escritura_falsa import SesionEscrituraFalsa

ENE = dt.date(2026, 1, 1)

HOJAS_STD = ["INICIO", "COMENTARIOS", "Otra hoja"]
HOJAS_NEW = ["BDP_datos_dia", "BDP_datos_mes", "BDP_Programa", "INICIO"]


class LibroFalso:
    """Doble mínimo de un `Workbook` de openpyxl."""

    def __init__(
        self, nombres: list[str], filas_por_hoja: dict[str, list[Any]] | None = None
    ):
        self.sheetnames = nombres
        self._filas = filas_por_hoja or {}
        self.cerrado = False

    def __getitem__(self, nombre: str) -> HojaFalsa:
        return HojaFalsa(self._filas.get(nombre, [("A", "B"), (1, 2)]))

    def close(self) -> None:
        self.cerrado = True


class HojaFalsa:
    """Doble de una hoja. Acepta los mismos argumentos que `openpyxl`, porque los
    loaders acotan la lectura con `min_row`/`max_row` cuando solo les interesa la
    cabecera de la hoja."""

    def __init__(self, filas: list[Any]) -> None:
        self._filas = filas

    def iter_rows(
        self,
        min_row: int | None = None,
        max_row: int | None = None,
        max_col: int | None = None,
        values_only: bool = True,
    ) -> Iterator[Any]:
        # Devuelve un ITERADOR, no una lista: openpyxl también lo hace, y los loaders
        # consumen la fila de encabezado con `next()`. Un doble que devolviera una lista
        # daría verde aquí y fallaría contra el archivo real.
        desde = (min_row - 1) if min_row else 0
        return iter(self._filas[desde:max_row])


def _servicio(
    nombres: list[str],
    extractores: list[tuple[str, Any]] | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> tuple[IngestaService, SesionEscrituraFalsa, list[EventoIngesta]]:
    sesion = SesionEscrituraFalsa(respuestas={"RETURNING reporte_id": 1042})
    eventos: list[EventoIngesta] = []
    servicio = IngestaService(
        IngestaRepository(sesion),  # type: ignore[arg-type]
        observador=eventos.append,
    )
    if monkeypatch is not None:
        import src.features.ingesta.services as modulo

        monkeypatch.setattr(
            modulo, "extractores_aplicables", lambda _: (extractores or [])
        )
    return servicio, sesion, eventos


def _ingerir(
    servicio: IngestaService,
    nombres: list[str],
    nombre_archivo: str = "20260101_r.xlsm",
) -> Any:
    return servicio._ingerir_libro(LibroFalso(nombres), Path(nombre_archivo))


# ── Flujo básico ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_el_bloqueo_se_toma_antes_de_escribir_nada_mas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si se tomara después, dos ingestas simultáneas ya habrían empezado a pisarse."""
    servicio, sesion, _ = _servicio(HOJAS_STD, monkeypatch=monkeypatch)

    _ingerir(servicio, HOJAS_STD)

    posicion_lock = next(
        i for i, sql in enumerate(sesion.sentencias) if "pg_advisory" in sql
    )
    primera_escritura_de_datos = next(
        i for i, sql in enumerate(sesion.sentencias) if "bronze." in sql
    )
    assert posicion_lock < primera_escritura_de_datos


@pytest.mark.unit
def test_un_archivo_std_no_toca_las_tablas_bronze_tipadas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    servicio, sesion, _ = _servicio(HOJAS_STD, monkeypatch=monkeypatch)

    resultado = _ingerir(servicio, HOJAS_STD)

    assert resultado.tipo_archivo == "STD"
    assert sesion.escrituras_en("bronze.bdp_datos_dia") == []


@pytest.mark.unit
def test_un_archivo_new_aterriza_las_tres_hojas_crudas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    servicio, sesion, _ = _servicio(HOJAS_NEW, monkeypatch=monkeypatch)

    resultado = _ingerir(servicio, HOJAS_NEW)

    assert resultado.tipo_archivo == "NEW"
    for tabla in (
        "bronze.bdp_datos_dia",
        "bronze.bdp_datos_mes",
        "bronze.bdp_programa",
    ):
        assert sesion.inserciones_en(tabla), f"{tabla} sin escribir"


@pytest.mark.unit
def test_las_hojas_crudas_no_se_aterrizan_dos_veces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ya van a su tabla tipada: repetirlas en hoja_landing duplicaría el volumen."""
    servicio, sesion, _ = _servicio(HOJAS_NEW, monkeypatch=monkeypatch)

    _ingerir(servicio, HOJAS_NEW)

    hojas_landing = [
        e.parametros[0]["h"]
        for e in sesion.inserciones_en("bronze.hoja_landing")
        if e.parametros
    ]
    assert "BDP_datos_dia" not in hojas_landing


@pytest.mark.unit
def test_toda_hoja_no_cruda_se_preserva_en_bronze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bronze es la copia fiel del archivo: incluso una hoja que nadie modela."""
    servicio, sesion, _ = _servicio(HOJAS_STD, monkeypatch=monkeypatch)

    _ingerir(servicio, HOJAS_STD)

    borrados = sesion.borrados_en("bronze.hoja_landing")
    assert len(borrados) == len(HOJAS_STD)


# ── Eventos de progreso (G2) ─────────────────────────────────────────────────


@pytest.mark.unit
def test_el_primer_evento_anuncia_el_archivo(monkeypatch: pytest.MonkeyPatch) -> None:
    servicio, _, eventos = _servicio(HOJAS_STD, monkeypatch=monkeypatch)

    _ingerir(servicio, HOJAS_STD)

    assert eventos[0].tipo == "inicio"
    assert eventos[0].total == len(HOJAS_STD)
    assert eventos[0].tipo_archivo == "STD"


@pytest.mark.unit
def test_las_hojas_se_reportan_como_procesada_no_como_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G2: 'ok' prometía que el dato estaba guardado, y la transacción aún podía
    revertirse. 'procesada' dice la verdad: insertada, pendiente de confirmar."""
    servicio, _, eventos = _servicio(HOJAS_STD, monkeypatch=monkeypatch)

    _ingerir(servicio, HOJAS_STD)

    estados = {e.estado for e in eventos if e.tipo == "hoja"}
    assert "ok" not in estados
    assert estados <= {"procesando", "procesada", "vacia", "error"}


@pytest.mark.unit
def test_cada_hoja_emite_procesando_antes_que_su_resultado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    servicio, _, eventos = _servicio(HOJAS_STD, monkeypatch=monkeypatch)

    _ingerir(servicio, HOJAS_STD)

    de_inicio = [e for e in eventos if e.tipo == "hoja" and e.hoja == "INICIO"]
    assert de_inicio[0].estado == "procesando"
    assert de_inicio[-1].estado in {"procesada", "vacia"}


@pytest.mark.unit
def test_un_observador_que_falla_no_tumba_la_ingesta() -> None:
    """El progreso es informativo: el dato es lo que importa."""
    sesion = SesionEscrituraFalsa(respuestas={"RETURNING reporte_id": 1042})

    def observador_roto(_: EventoIngesta) -> None:
        raise RuntimeError("el cliente se desconectó")

    servicio = IngestaService(IngestaRepository(sesion), observador=observador_roto)  # type: ignore[arg-type]

    resultado = servicio._ingerir_libro(LibroFalso(HOJAS_STD), Path("20260101_r.xlsm"))

    assert resultado.reporte_id == 1042


# ── Hojas modeladas y tablas vacías (G5) ─────────────────────────────────────


@pytest.mark.unit
def test_una_tabla_declarada_sin_filas_queda_registrada_como_vacia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G5: si solo se contaran las tablas con filas, un cambio de layout se vería como
    una tabla que desapareció, sin que nadie lo note."""

    def extractor(_: Any) -> ResultadoExtractor:
        return ResultadoExtractor(
            filas=[FilaExtraida(1, "T1", {"a": "x"}, ENE, 10.0)],
            tablas_declaradas=[(1, "T1"), (2, "T2 vacía")],
        )

    servicio, _, eventos = _servicio(
        HOJAS_STD, extractores=[("INICIO", extractor)], monkeypatch=monkeypatch
    )

    resultado = _ingerir(servicio, HOJAS_STD)

    assert resultado.tablas_vacias == ["INICIO → T2 vacía"]
    evento = next(
        e for e in eventos if e.tipo == "hoja" and e.tablas and e.hoja == "INICIO"
    )
    assert [t.filas for t in evento.tablas] == [1, 0]


@pytest.mark.unit
def test_una_hoja_sin_ninguna_fila_se_marca_vacia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def extractor_vacio(_: Any) -> ResultadoExtractor:
        return ResultadoExtractor(filas=[], tablas_declaradas=[(1, "T1")])

    servicio, _, eventos = _servicio(
        HOJAS_STD, extractores=[("INICIO", extractor_vacio)], monkeypatch=monkeypatch
    )

    _ingerir(servicio, HOJAS_STD)

    de_tabla_hoja = [
        e for e in eventos if e.tipo == "hoja" and e.destino == "core.fact_tabla_hoja"
    ]
    assert de_tabla_hoja[-1].estado == "vacia"


@pytest.mark.unit
def test_un_extractor_que_revienta_no_aborta_las_demas_hojas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Perder una hoja por un cambio de layout no debería costar las otras dieciséis."""

    def extractor_roto(_: Any) -> ResultadoExtractor:
        raise ValueError("la fila 37 ya no existe")

    def extractor_sano(_: Any) -> ResultadoExtractor:
        return ResultadoExtractor(
            filas=[FilaExtraida(1, "T1", {"a": "x"}, ENE, 1.0)],
            tablas_declaradas=[(1, "T1")],
        )

    servicio, sesion, eventos = _servicio(
        HOJAS_STD,
        extractores=[("INICIO", extractor_roto), ("COMENTARIOS", extractor_sano)],
        monkeypatch=monkeypatch,
    )

    resultado = _ingerir(servicio, HOJAS_STD)

    errores = [e for e in eventos if e.tipo == "hoja" and e.estado == "error"]
    assert len(errores) == 1
    assert errores[0].hoja == "INICIO"
    # La hoja sana se procesó igualmente.
    assert any(h.hoja == "COMENTARIOS" for h in resultado.hojas)


@pytest.mark.unit
def test_el_fallo_de_un_extractor_queda_en_la_bitacora(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def extractor_roto(_: Any) -> ResultadoExtractor:
        raise ValueError("layout cambiado")

    servicio, sesion, _ = _servicio(
        HOJAS_STD, extractores=[("INICIO", extractor_roto)], monkeypatch=monkeypatch
    )

    _ingerir(servicio, HOJAS_STD)

    registros = sesion.inserciones_en("core.ingesta_log")
    con_error = [r for r in registros if r.parametros.get("e") == "ERROR"]
    assert con_error
    assert "layout cambiado" in con_error[0].parametros["m"]


# ── Resultado ────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_el_resultado_resume_lo_escrito(monkeypatch: pytest.MonkeyPatch) -> None:
    def extractor(_: Any) -> ResultadoExtractor:
        return ResultadoExtractor(
            filas=[
                FilaExtraida(1, "T1", {"a": "x"}, ENE, 1.0),
                FilaExtraida(1, "T1", {"a": "y"}, ENE, 2.0),
            ],
            tablas_declaradas=[(1, "T1")],
        )

    servicio, _, _ = _servicio(
        HOJAS_STD, extractores=[("INICIO", extractor)], monkeypatch=monkeypatch
    )

    resultado = _ingerir(servicio, HOJAS_STD)

    assert resultado.reporte_id == 1042
    assert resultado.fecha_reporte == ENE
    assert resultado.filas_por_destino["fact_tabla_hoja::INICIO"] == 2
    assert resultado.total_filas > 0


@pytest.mark.unit
def test_el_servicio_no_confirma_la_transaccion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confirmar es responsabilidad de `get_prod_tx`: si el servicio hiciera commit,
    podría dejar la ingesta a medias sin que nadie lo pidiera."""
    servicio, sesion, _ = _servicio(HOJAS_STD, monkeypatch=monkeypatch)

    _ingerir(servicio, HOJAS_STD)

    assert sesion.commits == 0
    assert sesion.rollbacks == 0
