"""Los drills de reescritura conversacional — y su ORDEN (Q3).

El test central de este archivo es
`test_promedio_del_anio_es_referencia_no_acumulado`: fija el bug real que el
origen documenta con fecha (2026-08-02) y que cualquier reordenación de los
drills reintroduciría en silencio.
"""

from __future__ import annotations

import pytest

from src.features.consulta.drills import reescribir
from src.features.consulta.memoria import (
    ContextoAnalizar,
    ContextoCuantificar,
    ContextoJerarquizar,
    ContextoRanking,
)

pytestmark = pytest.mark.unit


def _sin_entidad(_texto: str) -> str | None:
    """Detector que nunca encuentra entidad: aísla los drills que dependen del
    contexto, sin arrastrar la BD de `respuesta_jerarquizar`."""
    return None


def _con_entidad(nombre: str):
    def _detectar(_texto: str) -> str | None:
        return nombre

    return _detectar


# ═════════════════════════════════════════════════════════════════════════════
# Q3 — el orden ES la corrección
# ═════════════════════════════════════════════════════════════════════════════


def test_promedio_del_anio_es_referencia_no_acumulado() -> None:
    """🔑 Q3, el bug que da nombre a la regla (origen, 2026-08-02).

    "promedio del año" contiene la substring "DEL ANO", que es palabra clave
    de acumulado. Si el drill de ACUMULADO corriera antes que el de
    REFERENCIA, esta frase devolvería el acumulado contra PPTO: una cifra
    DISTINTA a la pedida, servida con la misma confianza.
    """
    ctx = ContextoCuantificar(entidad="CASTILLA", producto="crudo")
    resultado = reescribir("¿y el promedio del año?", ctx, _sin_entidad)

    assert resultado is not None
    # La referencia viaja VERBATIM para que `slots` la detecte aguas abajo.
    assert "promedio del año" in resultado
    # Y NO se convirtió en un acumulado.
    assert not resultado.startswith("acumulado")


@pytest.mark.parametrize("palabra", ["operativo", "contable", "P50", "promedio"])
def test_las_cuatro_palabras_de_referencia_ganan_al_acumulado(palabra: str) -> None:
    ctx = ContextoCuantificar(entidad="APIAY", producto="crudo")
    resultado = reescribir(f"¿contra el {palabra}?", ctx, _sin_entidad)
    assert resultado is not None
    assert not resultado.startswith("acumulado")


def test_acumulado_sin_palabra_de_referencia_si_va_a_n2() -> None:
    """El drill 6 sigue funcionando cuando el 5 no aplica."""
    ctx = ContextoCuantificar(entidad="CASTILLA", producto="crudo")
    assert reescribir("¿y el acumulado?", ctx, _sin_entidad) == "acumulado de CASTILLA"


def test_el_acumulado_preserva_el_producto() -> None:
    """AF9: sin esto, "acumulado" tras un N1 de gas volvería a crudo."""
    ctx = ContextoCuantificar(entidad="CUSIANA", producto="gas")
    assert reescribir("acumulado", ctx, _sin_entidad) == "acumulado de gas de CUSIANA"


def test_un_si_pelado_tras_una_cifra_va_al_acumulado() -> None:
    ctx = ContextoCuantificar(entidad="CASTILLA", producto="crudo")
    assert reescribir("sí", ctx, _sin_entidad) == "acumulado de CASTILLA"


# ═════════════════════════════════════════════════════════════════════════════
# Longitud y entidad nombrada
# ═════════════════════════════════════════════════════════════════════════════


def test_una_frase_larga_es_intencion_propia() -> None:
    ctx = ContextoCuantificar(entidad="CASTILLA")
    largo = "quiero saber cuanto crudo produjo el campo el mes pasado"
    assert reescribir(largo, ctx, _sin_entidad) is None


def test_la_continuacion_temporal_es_la_excepcion_a_la_longitud() -> None:
    """Drill 0: "muéstrame la producción mes a mes" son 6 tokens, pero es
    continuación porque no nombra entidad nueva."""
    ctx = ContextoCuantificar(entidad="RUBIALES", producto="crudo")
    resultado = reescribir("muéstrame la produccion mes a mes", ctx, _sin_entidad)
    assert resultado is not None
    assert "RUBIALES" in resultado
    assert "mes a mes" in resultado


def test_una_frase_corta_con_entidad_y_verbo_no_se_reescribe() -> None:
    """🔑 Bug real (2026-08-02): "cuántos blancos produjo Cupiagua" son 4
    tokens, entraba al reescritor, y la plantilla "produccion de {ent}"
    borraba el producto — respondía CRUDO a una pregunta de BLANCOS."""
    ctx = ContextoCuantificar(entidad="CASTILLA", producto="crudo")
    assert (
        reescribir("cuántos blancos produjo Cupiagua", ctx, _con_entidad("CUPIAGUA"))
        is None
    )


def test_una_entidad_sola_se_lee_como_pregunta_estructural() -> None:
    ctx = ContextoCuantificar(entidad="CASTILLA")
    assert reescribir("CUPIAGUA", ctx, _con_entidad("CUPIAGUA")) == "que es CUPIAGUA"


def test_sin_contexto_no_hay_reescritura() -> None:
    assert reescribir("sí", None, _sin_entidad) is None


def test_texto_vacio() -> None:
    ctx = ContextoCuantificar(entidad="CASTILLA")
    assert reescribir("   ", ctx, _sin_entidad) is None


# ═════════════════════════════════════════════════════════════════════════════
# Drill de ranking (corta siempre)
# ═════════════════════════════════════════════════════════════════════════════


def test_el_ranking_cambia_de_producto() -> None:
    ctx = ContextoRanking(
        nivel_ranking="campo", metrica="real", direccion="top", producto="crudo"
    )
    resultado = reescribir("para gas", ctx, _sin_entidad)
    assert resultado == "cuales campos son los mayores productores de gas"


def test_el_ranking_invierte_el_orden() -> None:
    ctx = ContextoRanking(
        nivel_ranking="campo", metrica="real", direccion="top", producto="crudo"
    )
    resultado = reescribir("al revés", ctx, _sin_entidad)
    assert resultado == "cuales campos son los menores productores de crudo"


def test_el_ranking_de_gap_usa_su_propio_lenguaje() -> None:
    """D3: el gap no se dice "mayores/menores" sino "excedente / más cortos"."""
    ctx = ContextoRanking(
        nivel_ranking="activo", metrica="gap", direccion="bottom", producto="crudo"
    )
    resultado = reescribir("al revés", ctx, _sin_entidad)
    assert (
        resultado == "cuales activos con mayor excedente frente al presupuesto de crudo"
    )


def test_el_ranking_corta_siempre() -> None:
    """Sin producto ni inversión no aplica, y NO cae a los drills de abajo:
    el contexto de ranking no tiene entidad que heredar."""
    ctx = ContextoRanking()
    assert reescribir("gracias", ctx, _sin_entidad) is None


# ═════════════════════════════════════════════════════════════════════════════
# Drill de analizar (corta siempre)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("frase", "esperado"),
    [
        ("el ebitda", "ebitda de la produccion de CASTILLA"),
        ("las diferidas", "diferidas de la produccion de CASTILLA"),
        (
            "la proyección",
            "cual es la proyeccion de cierre de la produccion de CASTILLA",
        ),
        ("qué campos", "por que la produccion de CASTILLA esta corta"),
    ],
)
def test_los_destinos_de_analizar(frase: str, esperado: str) -> None:
    ctx = ContextoAnalizar(entidad="CASTILLA", sub="causal")
    assert reescribir(frase, ctx, _sin_entidad) == esperado


def test_un_si_tras_proyeccion_va_al_causal() -> None:
    """El cierre de proyección ofrece "qué campos explican el faltante"."""
    ctx = ContextoAnalizar(entidad="CASTILLA", sub="proyeccion")
    resultado = reescribir("sí", ctx, _sin_entidad)
    assert resultado == "por que la produccion de CASTILLA esta corta"


def test_un_si_tras_causal_va_a_la_proyeccion() -> None:
    """El detalle por campo ya venía en el bloque que el usuario acaba de leer."""
    ctx = ContextoAnalizar(entidad="CASTILLA", sub="causal")
    resultado = reescribir("sí", ctx, _sin_entidad)
    assert resultado == "cual es la proyeccion de cierre de la produccion de CASTILLA"


def test_la_vicepresidencia_ofrecida_gana_al_campo_del_contexto() -> None:
    """🔑 Sin esto la reescritura repetía el CAMPO, volvía a declinar y
    entraba en BUCLE (bug reproducido en la verificación del origen)."""
    ctx = ContextoAnalizar(entidad="CASTILLA", sub="referencia", vp="GOR")
    resultado = reescribir("la vicepresidencia", ctx, _sin_entidad)
    assert resultado is not None
    assert "GOR" in resultado
    assert "CASTILLA" not in resultado


def test_analizar_global_sin_entidad_no_revienta() -> None:
    """El contexto de analizar puede no llevar entidad (análisis global ECP).

    En el origen esta era la razón de que el drill cortara siempre: los de
    abajo hacían `ctx['entidad']` y lanzaban KeyError.
    """
    ctx = ContextoAnalizar(entidad=None, sub="causal")
    resultado = reescribir("el ebitda", ctx, _sin_entidad)
    assert resultado == "ebitda de la produccion"


def test_analizar_corta_siempre() -> None:
    ctx = ContextoAnalizar(entidad="CASTILLA")
    assert reescribir("gracias", ctx, _sin_entidad) is None


# ═════════════════════════════════════════════════════════════════════════════
# Drills de jerarquizar
# ═════════════════════════════════════════════════════════════════════════════


def test_un_si_tras_ofrecer_produccion_pide_la_cifra() -> None:
    ctx = ContextoJerarquizar(entidad="RUBIALES", ofrece_produccion=True)
    assert reescribir("sí", ctx, _sin_entidad) == "produccion de RUBIALES"


def test_pregunta_estructural_con_pronombre_elidido() -> None:
    ctx = ContextoJerarquizar(entidad="CAJUA", ofrece_produccion=False)
    assert reescribir("¿a qué activo pertenece?", ctx, _sin_entidad) == "que es CAJUA"


def test_jerarquizar_sin_oferta_ignora_el_si() -> None:
    ctx = ContextoJerarquizar(entidad="CAJUA", ofrece_produccion=False)
    assert reescribir("sí", ctx, _sin_entidad) is None


# ═════════════════════════════════════════════════════════════════════════════
# Drill N1 genérico
# ═════════════════════════════════════════════════════════════════════════════


def test_cambiar_de_mes_sin_repetir_la_entidad() -> None:
    """Bug real (2026-08-02): sin esta rama la memoria perdía el hilo apenas
    el usuario cambiaba de mes sin repetir el nombre — caía a Desconocido a
    mitad de una conversación."""
    ctx = ContextoCuantificar(entidad="RUBIALES", producto="crudo")
    resultado = reescribir("¿y en abril?", ctx, _sin_entidad)
    assert resultado is None or "RUBIALES" in resultado

    resultado2 = reescribir("cuánto en abril", ctx, _sin_entidad)
    assert resultado2 is not None
    assert "RUBIALES" in resultado2
    # El texto ORIGINAL viaja completo: es donde `slots` encuentra el mes.
    assert "abril" in resultado2
