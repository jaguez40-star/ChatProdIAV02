"""Núcleo determinista de F4: normaliza, no_soportado, catálogo y cargador YAML.

Todos son módulos PUROS o de solo lectura de fichero: ninguno toca BD ni LLM.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from src.features.consulta import catalogo, config_yaml, no_soportado
from src.features.consulta.normaliza import norm

pytestmark = pytest.mark.unit


# ── normaliza ────────────────────────────────────────────────────────────────


def test_norm_mayusculas_y_espacios() -> None:
    assert norm("  producción   diaria  ") == "PRODUCCION DIARIA"


def test_norm_pliega_acentos() -> None:
    assert norm("Cajúa") == "CAJUA"


def test_norm_pliega_la_enie() -> None:
    """La Ñ se pliega a N.

    No es un detalle cosmético: obliga a que todo patrón escrito contra texto
    normalizado use N. Un patrón con "AÑO" nunca casaría, porque el texto
    normalizado dice "ANO".
    """
    assert norm("año") == "ANO"
    assert norm("PEQUEÑOS") == "PEQUENOS"


def test_norm_conserva_signos_de_interrogacion() -> None:
    """`norm` NO retira puntuación: quien necesite tokens limpios la recorta."""
    assert norm("¿cuánto?") == "¿CUANTO?"


def test_norm_tolera_vacio() -> None:
    assert norm("") == ""


# ── no_soportado ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("texto", "codigo"),
    [
        ("¿cuánto produjo entre el 5 y el 10?", "rango_dias"),
        ("¿cuánto produjo del 1 al 15?", "rango_dias"),
        ("dame el primer trimestre", "trimestre"),
        ("producción trimestral", "trimestre"),
        ("¿cuánto produjo durante 2026?", "anio"),
        ("dame la cifra anual", "anio"),
        ("¿cuánto produjo esta semana?", "semana"),
        ("producción semanal", "semana"),
    ],
)
def test_detecta_las_formas_fuera_de_capacidad(texto: str, codigo: str) -> None:
    assert no_soportado.detectar(texto) == codigo


def test_promedio_del_anio_no_es_forma_no_soportada() -> None:
    """H2: "promedio del año" es la referencia SOPORTADA `promedio_anio`.

    Sin esta guarda, el detector la rechazaría por traer "ANO" cuando en
    realidad el motor sí sabe responderla.
    """
    assert no_soportado.detectar("dame el promedio del año") is None
    assert no_soportado.detectar("¿cuál es el promedio anual?") is None


def test_texto_soportado_no_detecta_nada() -> None:
    assert no_soportado.detectar("¿cuánto produjo Castilla en mayo?") is None
    assert no_soportado.detectar("") is None


def test_el_mensaje_nombra_entidad_y_no_termina_en_pregunta_si_no() -> None:
    """H1: si terminara en pregunta sí/no, un "sí" del usuario caería en el
    drill de afirmación y devolvería un acumulado en vez de lo ofrecido."""
    msg = no_soportado.mensaje("trimestre", "CASTILLA")
    assert "CASTILLA" in msg
    assert "trimestre" in msg
    assert not msg.rstrip().endswith("?")


def test_el_mensaje_de_un_codigo_desconocido_degrada_con_gracia() -> None:
    msg = no_soportado.mensaje("inexistente", "APIAY")
    assert "APIAY" in msg
    assert msg


# ── catálogo ─────────────────────────────────────────────────────────────────


def test_el_catalogo_carga_y_trae_sus_secciones() -> None:
    cfg = catalogo.get()
    assert "productos" in cfg
    assert "produccion_crudo" in cfg["productos"]
    assert "PPTO" in cfg["referencias"]


def test_validar_no_lanza_con_el_yaml_real() -> None:
    """Es lo que corre el `lifespan` para conservar el arranque ruidoso."""
    catalogo.validar()


def test_el_catalogo_falla_ruidoso_si_le_falta_una_seccion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un catálogo corrupto en silencio sería peor que un arranque roto:
    `cuantificar` respondería con datos a medias sin avisar."""
    monkeypatch.setattr(config_yaml, "cargar", lambda _n: {"meta": {}})
    with pytest.raises(ValueError, match="faltan secciones"):
        catalogo.get()


def test_el_catalogo_exige_produccion_crudo(monkeypatch: pytest.MonkeyPatch) -> None:
    completo = {s: {} for s in catalogo._SECCIONES_REQUERIDAS}
    completo["referencias"] = {"PPTO": {}}
    monkeypatch.setattr(config_yaml, "cargar", lambda _n: completo)
    with pytest.raises(ValueError, match="produccion_crudo"):
        catalogo.get()


def test_el_catalogo_exige_la_referencia_ppto(monkeypatch: pytest.MonkeyPatch) -> None:
    completo: dict[str, Any] = {s: {} for s in catalogo._SECCIONES_REQUERIDAS}
    completo["productos"] = {
        "produccion_crudo": {
            "unidad": "bbl",
            "fuente": "x",
            "referencias": [],
            "granos": [],
        }
    }
    completo["referencias"] = {}
    monkeypatch.setattr(config_yaml, "cargar", lambda _n: completo)
    with pytest.raises(ValueError, match="PPTO"):
        catalogo.get()


# ── cargador YAML ────────────────────────────────────────────────────────────


def test_el_cargador_cachea_entre_llamadas() -> None:
    config_yaml.reset_cache()
    primero = config_yaml.cargar("vocabulario_dominio.yaml")
    segundo = config_yaml.cargar("vocabulario_dominio.yaml")
    assert primero is segundo  # misma instancia: no se releyó el disco


def test_el_cargador_es_seguro_bajo_concurrencia() -> None:
    """A1: sin lock, N hilos parsearían el mismo YAML N veces. El doble
    chequeo garantiza además que todos ven EL MISMO objeto."""
    config_yaml.reset_cache()
    resultados: list[Any] = []
    barrera = threading.Barrier(8)

    def _cargar() -> None:
        barrera.wait()  # maximiza la colisión
        resultados.append(config_yaml.cargar("patrones_grupo.yaml"))

    hilos = [threading.Thread(target=_cargar) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert len(resultados) == 8
    assert all(r is resultados[0] for r in resultados)


def test_el_cargador_falla_si_el_yaml_no_existe() -> None:
    with pytest.raises(FileNotFoundError):
        config_yaml.cargar("no_existe.yaml")
