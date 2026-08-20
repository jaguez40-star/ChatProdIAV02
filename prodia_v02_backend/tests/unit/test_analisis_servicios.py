"""Servicios de Análisis contra un doble de repositorio.

Cubren la lógica que NO es SQL: composición del catálogo, huecos y rachas de
densidad, categorización de cobertura, y el armado del desempeño (KPIs, curva y
ritmo). El SQL en sí se valida contra el Postgres real, no aquí.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from src.features.analisis.services_catalogo import CatalogoService, severidad
from src.features.analisis.services_desempeno import (
    Ambito,
    DesempenoService,
    NoEncontradaError,
    SinDatosError,
)


class RepoCatalogoFalso:
    """Doble del repositorio de catálogo: devuelve filas fijas, sin BD."""

    def __init__(self, **datos: Any) -> None:
        self._datos = datos
        self.timeouts: list[str] = []

    def cardinalidad(self) -> list[dict[str, Any]]:
        return self._datos.get(
            "cardinalidad",
            [
                {"nivel": "gerencia", "n": 8},
                {"nivel": "activo", "n": 18},
                {"nivel": "area", "n": 62},
                {"nivel": "campo", "n": 128},
                {"nivel": "fuente", "n": 900},
            ],
        )

    def total_vicepresidencias(self) -> int:
        return self._datos.get("vices", 5)

    def colisiones(self) -> list[dict[str, Any]]:
        return self._datos.get("colisiones", [])

    def filiales(self) -> list[str]:
        return self._datos.get("filiales", ["Hocol", "America", "Permian"])

    def entidades_por_nivel(self) -> dict[str, list[str]]:
        return self._datos.get("entidades", {"campo": ["CASTILLA"]})

    def fuentes_de_entidad(self, entidad: str) -> list[int]:
        return self._datos.get("ids", [])

    def vice_id_de(self, entidad: str) -> int | None:
        return self._datos.get("vice_id")

    def densidad_global(self) -> list[dict[str, Any]]:
        return self._datos.get("densidad", [])

    def densidad_de_entidad(
        self, ids: list[int], vice_id: int | None
    ) -> list[dict[str, Any]]:
        return self._datos.get("densidad", [])

    def fijar_timeout(self, segundos: str) -> None:
        self.timeouts.append(segundos)

    def fuentes_para_huella(self, entidad: str) -> list[int]:
        return self._datos.get("ids", [])

    def contar_dia_ecp(self, ids: list[int] | None = None) -> int:
        return self._datos.get("n_dia", 100)

    def mes_ecp_por_escenario(
        self, ids: list[int] | None = None
    ) -> list[dict[str, Any]]:
        return self._datos.get("escenarios", [{"nombre": "REAL", "filas": 50}])

    def contar_programa(self, ids: list[int] | None = None, entidad: str = "") -> int:
        return self._datos.get("n_programa", 10)

    def hojas_de_ingesta(self) -> list[dict[str, Any]]:
        return self._datos.get("hojas", [])

    def presencia_en_facts(self, *args: Any, **kwargs: Any) -> int:
        return self._datos.get("presencia_fact", 0)

    def presencia_en_landing(self, patron: str) -> list[dict[str, Any]]:
        return self._datos.get("presencia_landing", [])


# ── Severidad de colisiones ─────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    ("niveles", "esperado"),
    [
        (["activo", "campo"], "dura"),
        (["gerencia", "fuente"], "dura"),  # gerencia agrega tanto como activo
        (["area", "campo"], "media"),
        (["campo", "fuente"], "blanda"),
    ],
)
def test_severidad_de_colision(niveles: list[str], esperado: str) -> None:
    """Decide si el chat contrapregunta: dura/media sí, blanda usa el default."""
    assert severidad(niveles) == esperado


# ── Catálogo ────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_catalogo_ordena_los_niveles_de_mayor_a_menor_agregacion() -> None:
    servicio = CatalogoService(RepoCatalogoFalso())  # type: ignore[arg-type]
    resultado = servicio.catalogo()
    assert [c.nivel for c in resultado.cardinalidad] == [
        "vicepresidencia",
        "gerencia",
        "activo",
        "area",
        "campo",
        "fuente",
    ]


@pytest.mark.unit
def test_catalogo_no_ofrece_agua_como_producto() -> None:
    """`agua` no existe en `dim_tipo_producto`: ofrecerla haría que el
    slot-filling aceptara una consulta irresoluble."""
    servicio = CatalogoService(RepoCatalogoFalso())  # type: ignore[arg-type]
    terminos = {p.termino for p in servicio.catalogo().productos_validos}
    assert terminos == {"aceite", "gas", "blancos"}


@pytest.mark.unit
def test_catalogo_resume_las_colisiones_por_severidad() -> None:
    repo = RepoCatalogoFalso(
        colisiones=[
            {
                "nombre": "RUBIALES",
                "n_niveles": 3,
                "niveles": ["activo", "campo", "fuente"],
            },
            {"nombre": "APIAY", "n_niveles": 2, "niveles": ["area", "campo"]},
            {"nombre": "LORITO", "n_niveles": 2, "niveles": ["campo", "fuente"]},
        ]
    )
    resumen = CatalogoService(repo).catalogo().resumen_colisiones  # type: ignore[arg-type]
    assert (resumen.dura, resumen.media, resumen.blanda, resumen.total) == (1, 1, 1, 3)


# ── Densidad ────────────────────────────────────────────────────────────────


def _dia(iso: str, filas: int = 10, fuentes: int = 3) -> dict[str, Any]:
    anio, mes, dia = (int(p) for p in iso.split("-"))
    return {"fecha": date(anio, mes, dia), "filas": filas, "fuentes": fuentes}


@pytest.mark.unit
def test_densidad_cuenta_huecos_del_mes() -> None:
    """Mayo tiene 31 días; con 3 con dato, 28 son huecos."""
    repo = RepoCatalogoFalso(
        densidad=[_dia("2026-05-01"), _dia("2026-05-02"), _dia("2026-05-03")]
    )
    resultado = CatalogoService(repo).densidad()  # type: ignore[arg-type]
    assert resultado.resumen.total_dias == 3
    assert resultado.resumen.huecos_totales == 28
    assert resultado.por_mes[0].dias_del_mes == 31


@pytest.mark.unit
def test_racha_maxima_cuenta_dias_consecutivos() -> None:
    """La racha es lo que habilita tendencias: días CONTINUOS, no totales."""
    repo = RepoCatalogoFalso(
        densidad=[
            _dia("2026-05-01"),
            _dia("2026-05-02"),
            _dia("2026-05-03"),
            _dia("2026-05-10"),  # corta la racha
        ]
    )
    assert CatalogoService(repo).densidad().resumen.racha_maxima == 3  # type: ignore[arg-type]


@pytest.mark.unit
def test_semaforo_marca_rojo_sin_continuidad() -> None:
    """Con pocos días continuos, las familias que necesitan continuidad van en
    rojo; las otras tres siguen en verde: el dato SÍ sirve para totales."""
    repo = RepoCatalogoFalso(densidad=[_dia("2026-05-01"), _dia("2026-05-05")])
    semaforo = CatalogoService(repo).densidad().semaforo  # type: ignore[arg-type]

    con_continuidad = [f for f in semaforo if f.necesita_continuidad]
    sin_continuidad = [f for f in semaforo if not f.necesita_continuidad]
    assert len(semaforo) == 5
    assert all(f.nivel == "rojo" for f in con_continuidad)
    assert all(f.nivel == "verde" for f in sin_continuidad)


@pytest.mark.unit
def test_entidad_desconocida_declara_que_no_aplica_ecp() -> None:
    """No es un error: vicepresidencias y filiales no tienen grano diario."""
    repo = RepoCatalogoFalso(ids=[], vice_id=None, densidad=[])
    resultado = CatalogoService(repo).densidad("HOCOL")  # type: ignore[arg-type]
    assert resultado.aplica_ecp is False
    assert resultado.dias == []


# ── Huella y cobertura ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_huella_de_entidad_inexistente() -> None:
    repo = RepoCatalogoFalso(ids=[])
    resultado = CatalogoService(repo).huella("NO EXISTE")  # type: ignore[arg-type]
    assert resultado.encontrada is False
    assert resultado.series == []


@pytest.mark.unit
def test_huella_global_trae_las_tres_series() -> None:
    resultado = CatalogoService(RepoCatalogoFalso()).huella()  # type: ignore[arg-type]
    assert [s.grupo for s in resultado.series] == ["dia", "mes", "programa"]


@pytest.mark.unit
def test_cobertura_agrupa_por_categoria_y_prioriza_la_mas_especifica() -> None:
    repo = RepoCatalogoFalso(
        hojas=[
            {
                "hoja": "BDP_datos_dia",
                "tabla_destino": "core.fact_produccion_dia_ecp",
                "reps": 100,
            },
            {"hoja": "RAW_x", "tabla_destino": "bronze.hoja_landing", "reps": 40},
        ]
    )
    resultado = CatalogoService(repo).cobertura()  # type: ignore[arg-type]
    categorias = {c.categoria for c in resultado.categorias}
    assert categorias == {"Producción ECP", "Preservada en crudo (Bronze)"}
    assert resultado.total_hojas == 2


@pytest.mark.unit
def test_cobertura_fija_timeout_de_60s() -> None:
    """El origen lo fija porque estas consultas tocan facts grandes."""
    repo = RepoCatalogoFalso(hojas=[])
    CatalogoService(repo).cobertura()  # type: ignore[arg-type]
    assert repo.timeouts == ["60s"]


# ── Desempeño ───────────────────────────────────────────────────────────────


class RepoDesempenoFalso:
    """Doble del repositorio de desempeño."""

    db = None

    def __init__(self, **datos: Any) -> None:
        self._datos = datos

    def fuentes_por_columna(self, columna: str, entidad: str) -> list[int]:
        return self._datos.get("ids", [])

    def fuentes_union(self, entidad: str) -> list[int]:
        return self._datos.get("ids", [])

    def vice_id_de(self, entidad: str) -> int | None:
        return self._datos.get("vice_id")

    def max_fecha_diaria(self, ids: list[int], vice_id: int | None) -> Any:
        return self._datos.get("max_dia")

    def max_fecha_mensual_real(self, ids: list[int], vice_id: int | None) -> Any:
        return self._datos.get("max_mes")

    def kpis_mes(self, *args: Any) -> list[dict[str, Any]]:
        return self._datos.get("kpis", [])

    def curva_diaria(self, *args: Any) -> list[dict[str, Any]]:
        return self._datos.get("curva", [])

    def real_mensual_del_anio(self, *args: Any) -> list[dict[str, Any]]:
        return self._datos.get("mensual", [])

    def campos_sin_meta(self, *args: Any) -> list[dict[str, Any]]:
        return self._datos.get("sin_meta", [])


@pytest.mark.unit
def test_entidad_inexistente_devuelve_no_encontrada() -> None:
    servicio = DesempenoService(RepoDesempenoFalso(ids=[], vice_id=None))  # type: ignore[arg-type]
    resultado = servicio.desempeno("NO EXISTE", nivel="campo")
    assert resultado.encontrada is False


@pytest.mark.unit
def test_entidad_sin_ninguna_fecha_devuelve_sin_datos() -> None:
    servicio = DesempenoService(
        RepoDesempenoFalso(ids=[1], max_dia=None, max_mes=None)  # type: ignore[arg-type]
    )
    resultado = servicio.desempeno("CASTILLA", nivel="campo")
    assert resultado.sin_datos is True


@pytest.mark.unit
def test_sin_grano_diario_cae_al_ultimo_mes_con_real() -> None:
    """El fallback existe porque hay entidades que solo tienen fact mensual."""
    servicio = DesempenoService(
        RepoDesempenoFalso(ids=[1], max_dia=None, max_mes=date(2026, 5, 31))  # type: ignore[arg-type]
    )
    resultado = servicio.desempeno("CASTILLA", nivel="campo")
    assert resultado.aplica_diario is False
    assert resultado.mes is not None
    assert (resultado.mes.anio, resultado.mes.mes) == (2026, 5)


@pytest.mark.unit
def test_cumplimiento_es_none_sin_meta_no_cero() -> None:
    """Un producto sin PPTO NO cumple el 0 %: no hay con qué compararlo."""
    repo = RepoDesempenoFalso(
        ids=[1],
        max_dia=date(2026, 5, 17),
        kpis=[{"prod": "CRUDO", "esc": "REAL", "vol": 1000}],
    )
    resultado = DesempenoService(repo).desempeno("CASTILLA", nivel="campo")  # type: ignore[arg-type]
    crudo = [p for p in resultado.por_producto if p.producto == "CRUDO"][0]
    assert crudo.real == 1000
    assert crudo.cumplimiento is None


@pytest.mark.unit
def test_cumplimiento_se_calcula_con_meta() -> None:
    repo = RepoDesempenoFalso(
        ids=[1],
        max_dia=date(2026, 5, 17),
        kpis=[
            {"prod": "CRUDO", "esc": "REAL", "vol": 950},
            {"prod": "CRUDO", "esc": "PPTO", "vol": 1000},
        ],
    )
    resultado = DesempenoService(repo).desempeno("CASTILLA", nivel="campo")  # type: ignore[arg-type]
    crudo = [p for p in resultado.por_producto if p.producto == "CRUDO"][0]
    assert crudo.cumplimiento == 95.0


@pytest.mark.unit
def test_sin_cierre_cuando_no_hay_fila_mensual() -> None:
    repo = RepoDesempenoFalso(ids=[1], max_dia=date(2026, 5, 17), kpis=[])
    resultado = DesempenoService(repo).desempeno("CASTILLA", nivel="campo")  # type: ignore[arg-type]
    assert resultado.sin_cierre is True


@pytest.mark.unit
def test_periodo_no_soportado_se_declara() -> None:
    """Pedir 'el año' sirve el último mes con dato, pero `periodo_ok=False` lo
    DECLARA en vez de fingir que se honró la petición."""
    repo = RepoDesempenoFalso(ids=[1], max_dia=date(2026, 5, 17))
    resultado = DesempenoService(repo).desempeno(  # type: ignore[arg-type]
        "CASTILLA", nivel="campo", periodo="el año"
    )
    assert resultado.periodo_ok is False


@pytest.mark.unit
def test_los_tres_productos_salen_siempre() -> None:
    """Orden fijo Crudo→Gas→Blancos aunque no haya dato de alguno."""
    repo = RepoDesempenoFalso(ids=[1], max_dia=date(2026, 5, 17))
    resultado = DesempenoService(repo).desempeno("CASTILLA", nivel="campo")  # type: ignore[arg-type]
    assert [p.producto for p in resultado.por_producto] == ["CRUDO", "GAS", "BLANCOS"]


@pytest.mark.unit
def test_ambito_es_un_dataclass_con_el_mes_resuelto() -> None:
    repo = RepoDesempenoFalso(ids=[1, 2], max_dia=date(2026, 5, 17))
    ambito = DesempenoService(repo).resolver_ambito("CASTILLA", nivel="campo")  # type: ignore[arg-type]
    assert isinstance(ambito, Ambito)
    assert ambito.ini == "2026-05-01"
    assert ambito.fin == "2026-05-31"
    assert ambito.dias_del_mes == 31


@pytest.mark.unit
def test_las_excepciones_de_ambito_son_tipos_propios() -> None:
    """`NoEncontradaError` y `SinDatosError` distinguen 'no existe' de 'existe
    pero sin dato' — dos mensajes distintos para el usuario."""
    assert issubclass(NoEncontradaError, Exception)
    assert issubclass(SinDatosError, Exception)
