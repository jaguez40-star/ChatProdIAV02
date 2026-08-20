"""Atribución del diagnóstico del valle: QUIÉN reportó el comentario.

Portado de `INGESTA/Rep_Prod/backend/tests/test_analisis_valle_atribucion.py`.

Origen del bug (usuario, 2026-07-16): el panel decía «Lo que reportó LORITO el
2026-05-06: "…descargas atmosféricas sobre la línea 115 kV Ocoa-Catama…
apagado de los pozos AK107 y Guamal Profundo-1"». El usuario no encontraba ese
comentario buscando LORITO — porque está registrado bajo **CPO-09**, y AK107 es
un pozo de AKACIAS.

Causa: `nombres_entidad` incluye `grupo1`/`activos` de `dim_fuente`, o sea el
GRUPO con el que el reporte agrupa a la entidad. LORITO trae
`{LORITO, CPO-09}`, así que el comentario del área CPO-09 calza. El dato es
relevante (el evento afecta al área que contiene a LORITO), pero la frase se
componía con `entidad` —lo que el usuario pidió— e ignoraba `campo` —quien lo
reportó de verdad—, que la consulta ya traía.

Estos tests fijan la parte pura: el orden de preferencia y la atribución. El
SQL se verifica contra la BD real, no aquí.
"""

from __future__ import annotations

import pytest

from src.features.analisis.services_ejecutivo import elegir_comentario_del_valle


@pytest.mark.unit
def test_comentario_propio_gana_al_del_grupo() -> None:
    """Si la entidad reportó algo ella misma, ESE es el diagnóstico."""
    comentarios = [
        {"campo": "CPO-09", "texto": "evento del área"},
        {"campo": "LORITO", "texto": "lo mío"},
    ]
    quien, es_ajeno = elegir_comentario_del_valle(comentarios, "LORITO")
    assert quien == "LORITO"
    assert es_ajeno is False


@pytest.mark.unit
def test_sin_comentario_propio_se_declara_el_grupo() -> None:
    """Caso LORITO real: solo hay comentario de CPO-09 → se muestra, pero
    declarando quién lo reportó. Atribución honesta."""
    comentarios = [{"campo": "CPO-09", "texto": "evento eléctrico Ocoa-Catama"}]
    quien, es_ajeno = elegir_comentario_del_valle(comentarios, "LORITO")
    assert quien == "CPO-09"
    assert es_ajeno is True


@pytest.mark.unit
def test_castilla_reporta_lo_suyo_sin_salvedad() -> None:
    """No regresión: CASTILLA sí tiene comentario propio → frase directa."""
    comentarios = [{"campo": "CASTILLA", "texto": "Desplazamiento de existencias…"}]
    quien, es_ajeno = elegir_comentario_del_valle(comentarios, "CASTILLA")
    assert quien == "CASTILLA"
    assert es_ajeno is False


@pytest.mark.unit
def test_atribucion_ignora_acentos_y_mayusculas() -> None:
    """La comparación pasa por `norm()`: 'Caño Sur' en la hoja y 'CANO SUR'
    pedido son la misma entidad."""
    comentarios = [{"campo": "Caño Sur", "texto": "x"}]
    _quien, es_ajeno = elegir_comentario_del_valle(comentarios, "CAÑO SUR")
    assert es_ajeno is False


@pytest.mark.unit
def test_el_producto_como_sufijo_no_vuelve_ajeno_el_comentario() -> None:
    """`CUPIAGUA (CRUDO)` es la MISMA entidad con el producto como sufijo.

    Comparar en crudo la declaraba ajena ("el grupo con el que el reporte
    agrupa a CUPIAGUA") cuando es su propio comentario. Se compara la BASE.
    """
    comentarios = [{"campo": "CUPIAGUA (CRUDO)", "texto": "x"}]
    _quien, es_ajeno = elegir_comentario_del_valle(comentarios, "CUPIAGUA")
    assert es_ajeno is False


@pytest.mark.unit
def test_orden_estable_con_varios_del_grupo() -> None:
    """Con varios ajenos y ninguno propio no debe romperse: gana el primero,
    declarado como ajeno."""
    comentarios = [
        {"campo": "CPO-09", "texto": "a"},
        {"campo": "CHICHIMENE", "texto": "b"},
    ]
    quien, es_ajeno = elegir_comentario_del_valle(comentarios, "LORITO")
    assert quien == "CPO-09"
    assert es_ajeno is True


@pytest.mark.unit
def test_sin_comentarios_no_hay_atribucion() -> None:
    quien, es_ajeno = elegir_comentario_del_valle([], "LORITO")
    assert quien == ""
    assert es_ajeno is False
