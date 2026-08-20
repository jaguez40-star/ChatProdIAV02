"""Tests de los loaders de las tablas estrella.

Usan hojas sintéticas reales de openpyxl y el doble de escrituras: nada de PostgreSQL.

Lo que se fija aquí son las reglas que deciden **qué dato entra y con qué clave**. Un
loader que resuelve mal una columna no da error: mete el valor en el campo equivocado, y
eso solo se descubre cuando alguien mira una cifra y no le cuadra.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from src.features.ingesta.loaders import (
    cargar_comentarios,
    cargar_filiales,
    cargar_pop,
    cargar_produccion_dia,
    cargar_produccion_mes,
    cargar_programa,
    cargar_promedios,
    completar_calendario,
    presembrar_fuentes_de_programa,
)
from src.features.ingesta.repositories import IngestaRepository
from tests.fakes.db_escritura_falsa import SesionEscrituraFalsa
from tests.fakes.hoja_sintetica import hoja_desde_filas

ENE = dt.date(2026, 1, 1)
FEB = dt.date(2026, 2, 1)


class DimensionFalsa:
    """Devuelve un id estable por nombre, sin tocar la base."""

    def __init__(self) -> None:
        self._ids: dict[str, int] = {}
        self.consultados: list[str | None] = []

    def get(self, nombre: str | None) -> int | None:
        self.consultados.append(nombre)
        if nombre is None:
            return None
        return self._ids.setdefault(nombre, len(self._ids) + 1)


def _entorno() -> tuple[IngestaRepository, SesionEscrituraFalsa, dict[str, Any]]:
    sesion = SesionEscrituraFalsa()
    dims = {
        clave: DimensionFalsa()
        for clave in (
            "vice", "socio", "concepto", "tipo_producto",
            "escenario", "proceso", "empresa", "tipo_registro",
        )
    }  # fmt: skip
    return IngestaRepository(sesion), sesion, dims  # type: ignore[arg-type]


# ── BDP_datos_dia ────────────────────────────────────────────────────────────

CABECERA_DIA = [
    "IDBDP", "FECHA", "FUENTE", "CONTRATO", "TIPOCONTRATO", "OPERADOR", "MODALIDAD",
    "OPERACION", "NACIONALIDAD", "GERENCIA", "GRUPO1", "GRUPO2", "GRUPO3", "ACTIVOS",
    "FUENTECONTRATO", "GRUPO1_SIGLA", "SOCIO", "CONCEPTO", "TIPOPRODUCTO", "PRODUCTO",
    "GRUPOPROD", "PROPIETARIO", "VOLUMEN", "PORCENTAJE", "VOLDISMEZ", "VOL_ESTIMADO",
    "PROMEDIO",
]  # fmt: skip


def _fila_dia(**valores: Any) -> list[Any]:
    fila: list[Any] = [None] * len(CABECERA_DIA)
    for nombre, valor in valores.items():
        fila[CABECERA_DIA.index(nombre.upper())] = valor
    return fila


@pytest.mark.unit
def test_produccion_dia_inserta_una_fila_completa() -> None:
    repo, sesion, dims = _entorno()
    hoja = hoja_desde_filas(
        [
            CABECERA_DIA,
            _fila_dia(idbdp=101, fecha=20260101, volumen=500.0, tipoproducto="CRUDO"),
        ]
    )

    resultado = cargar_produccion_dia(hoja, 1042, repo, dims)

    assert resultado.insertadas == 1
    escrita = sesion.inserciones_en("core.fact_produccion_dia_ecp")[0].parametros[0]
    assert escrita["fuente_id"] == 101
    assert escrita["fecha"] == ENE
    assert escrita["volumen"] == 500.0


@pytest.mark.unit
def test_produccion_dia_descarta_las_filas_sin_fecha() -> None:
    """Sin fecha no se puede colgar del modelo; se cuenta aparte para la bitácora."""
    repo, _, dims = _entorno()
    hoja = hoja_desde_filas(
        [CABECERA_DIA, _fila_dia(idbdp=101, fecha=None, volumen=1.0)]
    )

    resultado = cargar_produccion_dia(hoja, 1042, repo, dims)

    assert resultado.insertadas == 0
    # Tiene IDBDP, así que la fila SÍ se examina y se descarta por la fecha: eso es lo
    # que la hace visible en la bitácora, en vez de desaparecer sin dejar rastro.
    assert resultado.descartadas == 1


@pytest.mark.unit
def test_produccion_dia_ignora_las_filas_sin_idbdp_sin_contarlas() -> None:
    """Una fila sin IDBDP es relleno de la hoja, no un dato que se haya perdido."""
    repo, _, dims = _entorno()
    hoja = hoja_desde_filas([CABECERA_DIA, _fila_dia(volumen=1.0)])

    resultado = cargar_produccion_dia(hoja, 1042, repo, dims)

    assert resultado.insertadas == 0
    assert resultado.descartadas == 0


@pytest.mark.unit
def test_produccion_dia_cuenta_las_descartadas_por_fecha_invalida() -> None:
    repo, _, dims = _entorno()
    hoja = hoja_desde_filas(
        [CABECERA_DIA, _fila_dia(idbdp=101, fecha="no-es-fecha", volumen=1.0)]
    )

    resultado = cargar_produccion_dia(hoja, 1042, repo, dims)

    assert resultado.descartadas == 1
    assert resultado.leidas == 1


@pytest.mark.unit
def test_produccion_dia_resuelve_las_columnas_por_nombre_no_por_posicion() -> None:
    """El layout de esta hoja cambió entre versiones (30 → 32 columnas). Leer por
    posición habría metido los datos en campos equivocados sin dar error."""
    repo, sesion, dims = _entorno()
    cabecera_reordenada = ["VOLUMEN", "FECHA", "IDBDP"]
    hoja = hoja_desde_filas([cabecera_reordenada, [777.0, 20260101, 101]])

    cargar_produccion_dia(hoja, 1042, repo, dims)

    escrita = sesion.inserciones_en("core.fact_produccion_dia_ecp")[0].parametros[0]
    assert escrita["volumen"] == 777.0
    assert escrita["fuente_id"] == 101


@pytest.mark.unit
@pytest.mark.parametrize("columna", ["GRUPO1_SIGLA", "NIVEL1_SIGLA", "VICE"])
def test_produccion_dia_reconoce_los_tres_nombres_de_la_vicepresidencia(
    columna: str,
) -> None:
    """La vicepresidencia se ha llamado de tres formas distintas según el vintage del
    reporte, y `vice_id` es NOT NULL: si el loader solo conociera un nombre, el archivo
    de otro año reventaría al insertar —fue exactamente lo que pasó con el de 2024, que
    usa `VICE`."""
    repo, sesion, dims = _entorno()
    hoja = hoja_desde_filas(
        [["IDBDP", "FECHA", columna], [101, 20260101, "VRO"]],
    )

    cargar_produccion_dia(hoja, 1042, repo, dims)

    escrita = sesion.inserciones_en("core.fact_produccion_dia_ecp")[0].parametros[0]
    assert escrita["vice_id"] is not None


@pytest.mark.unit
def test_produccion_dia_siembra_fecha_y_fuente_antes_del_fact() -> None:
    """Las claves foráneas tienen que existir antes de insertar el fact."""
    repo, sesion, dims = _entorno()
    hoja = hoja_desde_filas(
        [CABECERA_DIA, _fila_dia(idbdp=101, fecha=20260101, volumen=1.0)]
    )

    cargar_produccion_dia(hoja, 1042, repo, dims)

    tablas = [e.tabla for e in sesion.escrituras]
    assert tablas.index("core.dim_fecha") < tablas.index("core.fact_produccion_dia_ecp")
    assert tablas.index("core.dim_fuente") < tablas.index(
        "core.fact_produccion_dia_ecp"
    )


# ── BDP_datos_mes ────────────────────────────────────────────────────────────

CABECERA_MES = [
    "IDBDP", "FECHA", "SOCIO", "CONCEPTO", "TIPOPRODUCTO", "ESCENARIO", "PROCESO",
    "GRUPOPROD", "VOLUMEN", "PORCENTAJE", "VOLDISMEZ", "BPD_M", "BPDA_AC", "BPD_A",
    "BPDEQ_M", "BLSEQ", "BPDEQ_A",
]  # fmt: skip


@pytest.mark.unit
def test_produccion_mes_tolera_una_columna_ausente() -> None:
    """En esta hoja algunas columnas faltan según el vintage: deben entrar como None,
    no reventar la ingesta entera."""
    repo, sesion, dims = _entorno()
    hoja = hoja_desde_filas(
        [CABECERA_MES, [101, 20260101, "S", "C", "CRUDO", "REAL", "P", "ECP",
                        1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]]
    )  # fmt: skip

    resultado = cargar_produccion_mes(hoja, 1042, repo, dims)

    assert resultado.insertadas == 1
    escrita = sesion.inserciones_en("core.fact_produccion_mes_ecp")[0].parametros[0]
    assert escrita["negocio"] is None  # la columna NEGOCIO no está en la hoja
    assert escrita["bpdeq_m"] == 7.0


@pytest.mark.unit
def test_produccion_mes_avisa_del_avance_en_hojas_largas() -> None:
    """Sin la señal de avance, el progreso se quedaría mudo minutos en esta hoja."""
    repo, _, dims = _entorno()
    filas = [
        [i, 20260101, "S", "C", "CRUDO", "REAL", "P", "ECP", 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
        for i in range(1, 10_002)
    ]  # fmt: skip
    hoja = hoja_desde_filas([CABECERA_MES, *filas])
    avisos: list[int] = []

    cargar_produccion_mes(hoja, 1042, repo, dims, avisos.append)

    assert avisos == [10_000]


# ── BDP_Programa ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_programa_lee_por_posicion_su_tabla_plana() -> None:
    repo, sesion, dims = _entorno()
    fila = [20260101, "VRO", "GER", "v1", 20251201, None, 100.0, "CASTILLA",
            "CRUDO", "ORIENTE", 101, "CT-1", 200.0, 0.5]  # fmt: skip
    hoja = hoja_desde_filas([["cabecera"], fila])

    resultado = cargar_programa(hoja, 1042, repo, dims)

    assert resultado.insertadas == 1
    escrita = sesion.inserciones_en("core.fact_programa_ecp")[0].parametros[0]
    assert escrita["campo"] == "CASTILLA"
    assert escrita["volumen"] == 100.0
    assert escrita["fuente_id"] == 101
    assert escrita["fecha_version"] == dt.date(2025, 12, 1)


@pytest.mark.unit
def test_programa_descarta_las_filas_sin_fecha() -> None:
    repo, _, dims = _entorno()
    hoja = hoja_desde_filas([["cabecera"], ["no-fecha", "VRO"]])

    resultado = cargar_programa(hoja, 1042, repo, dims)

    assert resultado.descartadas == 1


@pytest.mark.unit
def test_se_presiembran_las_fuentes_que_solo_estan_en_el_programa() -> None:
    """El programa puede referirse a fuentes que ningún fact diario trajo: sin
    presembrarlas, el INSERT violaría la clave foránea."""
    repo, sesion, _ = _entorno()
    fila = [20260101, "VRO", "GER", "v1", None, None, 1.0, "CASTILLA",
            "CRUDO", "ORIENTE", 999, "CT-9"]  # fmt: skip
    hoja = hoja_desde_filas([["cabecera"], fila])

    presembrar_fuentes_de_programa(hoja, 1042, repo)

    escrita = sesion.inserciones_en("core.dim_fuente")[0].parametros[0]
    assert escrita["fuente_id"] == 999
    assert escrita["campo"] == "CASTILLA"


# ── COMENTARIOS ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_comentarios_rellena_el_producto_hacia_abajo() -> None:
    repo, sesion, dims = _entorno()
    hoja = hoja_desde_filas(
        [
            ["PRODUCTO", "ACTIVOS", "AREA", "COMENTARIO"],
            ["CRUDO", "CASTILLA", "ORIENTE", "Sin novedad"],
            [None, "APIAY", "ORIENTE", "Otra cosa"],
        ]
    )

    resultado = cargar_comentarios(hoja, 1042, repo, dims)

    assert resultado.insertadas == 2
    # La segunda fila heredó el producto de la primera.
    assert dims["tipo_producto"].consultados == ["CRUDO", "CRUDO"]


@pytest.mark.unit
def test_comentarios_usa_la_cadena_de_respaldo() -> None:
    """`comentario` es NOT NULL: si D está vacío, se recurre a E y luego a G."""
    repo, sesion, dims = _entorno()
    hoja = hoja_desde_filas(
        [
            ["P", "A", "AR", "COM", "PROG", "X", "EXTRA"],
            ["CRUDO", "C", "O", None, "desde programa", None, None],
            ["GAS", "C", "O", None, None, None, "desde extra"],
        ]
    )

    cargar_comentarios(hoja, 1042, repo, dims)

    escritas = sesion.inserciones_en("core.fact_comentarios_produccion")[0].parametros
    assert escritas[0]["comentario"] == "desde programa"
    assert escritas[1]["comentario"] == "desde extra"


@pytest.mark.unit
def test_comentarios_trata_el_cero_como_vacio() -> None:
    """Corrige un bug del modelo previo: '0' es texto no vacío pero falsy al
    convertirlo, y cortocircuitaba la cadena de respaldo de forma incoherente."""
    repo, sesion, dims = _entorno()
    hoja = hoja_desde_filas(
        [
            ["P", "A", "AR", "COM", "PROG"],
            ["CRUDO", "C", "O", "0", "el verdadero"],
        ]
    )

    cargar_comentarios(hoja, 1042, repo, dims)

    escrita = sesion.inserciones_en("core.fact_comentarios_produccion")[0].parametros[0]
    assert escrita["comentario"] == "el verdadero"


@pytest.mark.unit
def test_comentarios_omite_las_filas_sin_ningun_texto() -> None:
    repo, _, dims = _entorno()
    hoja = hoja_desde_filas([["P", "A", "AR", "COM"], ["CRUDO", "C", "O", None]])

    resultado = cargar_comentarios(hoja, 1042, repo, dims)

    assert resultado.insertadas == 0


# ── Producción filiales ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_filiales_asigna_el_tipo_de_registro_del_bloque() -> None:
    repo, sesion, dims = _entorno()
    hoja = hoja_desde_filas(
        [
            ["REAL"],
            ["EMPRESA", ENE],
            ["Hocol (crudo)", 10.0],
            ["PROGRAMA"],
            ["EMPRESA", ENE],
            ["Hocol (crudo)", 20.0],
        ]
    )

    resultado = cargar_filiales(hoja, 1042, repo, dims)

    assert resultado.insertadas == 2
    assert dims["tipo_registro"].consultados == ["Real", "Programa"]


@pytest.mark.unit
def test_filiales_ignora_el_bloque_de_proyeccion() -> None:
    """La proyección no es producción registrada: no entra en el fact diario."""
    repo, _, dims = _entorno()
    hoja = hoja_desde_filas([["PROYECCIÓN"], ["EMPRESA", ENE], ["Hocol (crudo)", 99.0]])

    resultado = cargar_filiales(hoja, 1042, repo, dims)

    assert resultado.insertadas == 0


@pytest.mark.unit
def test_filiales_descarta_los_totales() -> None:
    repo, _, dims = _entorno()
    hoja = hoja_desde_filas(
        [["REAL"], ["EMPRESA", ENE], ["Hocol (crudo)", 10.0], ["TOTAL", 999.0]]
    )

    resultado = cargar_filiales(hoja, 1042, repo, dims)

    assert resultado.insertadas == 1


# ── POP ──────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_pop_convierte_barriles_a_kbd() -> None:
    """La hoja publica en barriles y el fact guarda kbd."""
    repo, sesion, dims = _entorno()
    hoja = hoja_desde_filas(
        [
            [None, "Producto", None, ENE],
            [None, "TOTAL Hocol", "Hocol", 5000.0],
        ]
    )

    cargar_pop(hoja, 1042, repo, dims)

    escrita = sesion.inserciones_en("core.fact_plan_mensual")[0].parametros[0]
    assert escrita["p"] == 5.0  # 5000 / 1000
    assert escrita["a"] == 2026
    assert escrita["m"] == 1


@pytest.mark.unit
def test_pop_solo_toma_los_totales_de_las_filiales_con_plan() -> None:
    repo, _, dims = _entorno()
    hoja = hoja_desde_filas(
        [
            [None, "Producto", None, ENE],
            [None, "TOTAL Otra", "OtraEmpresa", 1000.0],
            [None, "Detalle", "Hocol", 2000.0],
        ]
    )

    resultado = cargar_pop(hoja, 1042, repo, dims)

    assert resultado.insertadas == 0


# ── Promedios validados ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_promedios_solo_lee_dentro_de_su_seccion() -> None:
    repo, sesion, dims = _entorno()
    hoja = hoja_desde_filas(
        [
            ["Antes de la sección", "algo", 111.0],
            ["Producto", "Empresa", ENE],
            ["CRUDO", "Hocol", 42.0],
        ]
    )

    resultado = cargar_promedios(hoja, 1042, repo, dims)

    assert resultado.insertadas == 1
    escrita = sesion.inserciones_en("core.fact_promedio_validado")[0].parametros[0]
    assert escrita["v"] == 42.0


@pytest.mark.unit
def test_promedios_descarta_la_fila_de_total() -> None:
    repo, _, dims = _entorno()
    hoja = hoja_desde_filas([["Producto", "Empresa", ENE], ["TOTAL", "Hocol", 999.0]])

    resultado = cargar_promedios(hoja, 1042, repo, dims)

    assert resultado.insertadas == 0


# ── Calendario del reporte ───────────────────────────────────────────────────


@pytest.mark.unit
def test_el_calendario_se_localiza_por_etiqueta_no_por_fila() -> None:
    repo, sesion, _ = _entorno()
    hoja = hoja_desde_filas(
        [
            [None, "Ruido", "x"],
            [None, "Día de corte", dt.date(2026, 1, 15)],
            [None, "Version Semana", 3],
            [None, "Fecha inicial año", dt.date(2026, 1, 1)],
            [None, "Días del año", 365],
        ]
    )

    valores = completar_calendario(hoja, 1042, repo)

    assert valores["fc"] == dt.date(2026, 1, 15)
    assert valores["vs"] == 3
    assert valores["ai"] == 2026
    assert valores["da"] == 365
    assert sesion.escrituras_en("core.config_reporte")[0].verbo == "UPDATE"


@pytest.mark.unit
def test_el_calendario_tolera_las_etiquetas_ausentes() -> None:
    repo, _, _ = _entorno()
    hoja = hoja_desde_filas([[None, "Otra cosa", 1]])

    valores = completar_calendario(hoja, 1042, repo)

    assert all(valor is None for valor in valores.values())
