"""Capa 1 del clasificador + filtro de dominio (Bloque 1 de F4).

Tests PORTADOS de `tests/test_consulta_v2_clasificador.py` del sistema de
origen. Se conservan sus casos y sus comentarios de motivo: cada uno documenta
una decisión que ya costó una corrección allí, y que pasen contra el código
reescrito es la validación más fuerte de que el portado conserva la conducta.

Cambios respecto al original: rutas de import y el acceso a la caché interna
(`_compilar()` en vez de `_get()`).
"""

from __future__ import annotations

import pytest

from src.features.consulta import patrones as modulo_patrones
from src.features.consulta.dominio import hay_palabra_dominio, nivel_dominio
from src.features.consulta.patrones import clasificar_capa1, es_anclado

pytestmark = pytest.mark.unit


# ── Capa 1: regex ────────────────────────────────────────────────────────────


def test_capa1_jerarquizar_pertenencia() -> None:
    grupo, patrones = clasificar_capa1("¿A qué activo pertenece Cajúa?")
    assert grupo == "jerarquizar"
    assert patrones


def test_capa1_cuantificar_directo() -> None:
    grupo, _ = clasificar_capa1("¿Cuánto crudo produjo Castilla?")
    assert grupo == "cuantificar"


def test_capa1_analizar_porque() -> None:
    grupo, _ = clasificar_capa1("¿Por qué está mal Castilla?")
    assert grupo == "analizar"


def test_capa1_precedencia_analizar_gana_a_cuantificar() -> None:
    """ "cuánto" (cuantificar) + "meta" (analizar) → analizar."""
    grupo, _ = clasificar_capa1("¿Cuánto nos falta para la meta?")
    assert grupo == "analizar"


def test_capa1_huella_gana_a_cuantos() -> None:
    """Trampa conocida: pregunta por DISPONIBILIDAD, no por cifra.

    Es lo que justifica que `precedencia_maxima` se evalúe ANTES que los
    grupos: "cuántos" apunta a cuantificar, pero la pregunta real es si hay
    datos.
    """
    grupo, patrones = clasificar_capa1("¿Cuántos días con reporte hay de Rubiales?")
    assert grupo == "jerarquizar"
    assert any("REPORTE" in p or "DIAS" in p for p in patrones)


def test_capa1_huella_que_informacion() -> None:
    grupo, _ = clasificar_capa1("¿Qué información hay de Rubiales?")
    assert grupo == "jerarquizar"


def test_capa1_sin_senales_baja_a_capa2() -> None:
    """Un nombre a secas no lo decide la regex: baja al LLM."""
    grupo, patrones = clasificar_capa1("Castilla")
    assert grupo is None
    assert patrones == []


def test_capa1_texto_vacio() -> None:
    grupo, patrones = clasificar_capa1("")
    assert grupo is None
    assert patrones == []


def test_capa1_conteo_jerarquia_es_jerarquizar() -> None:
    """ "cuántos X tiene Y" es ESTRUCTURA, no producción.

    Antes de la corrección R1 del origen (2026-08-03) este caso clasificaba
    'cuantificar' — ese era el defecto, no el contrato.
    """
    grupo, _ = clasificar_capa1("¿Cuántos pozos tiene Apiay?")
    assert grupo == "jerarquizar"


def test_capa1_acentos_normalizados() -> None:
    """`norm()` pliega acentos: "producción" debe calzar 'PRODUCCION DE'."""
    grupo, _ = clasificar_capa1("producción de Rubiales")
    assert grupo == "cuantificar"


# ── Filtro de dominio ────────────────────────────────────────────────────────


def test_vocabulario_detecta_crudo() -> None:
    assert hay_palabra_dominio("¿cuánto crudo se perdió?") is True


def test_vocabulario_ignora_offtopic() -> None:
    assert hay_palabra_dominio("¿cuánto es la raíz cuadrada de 2?") is False


def test_nivel_dominio_fuerte() -> None:
    assert nivel_dominio("¿cuánto crudo produjo?") == "fuerte"


def test_nivel_dominio_estructural() -> None:
    assert nivel_dominio("¿cuántos campos hay?") == "estructural"


def test_nivel_dominio_ninguno() -> None:
    assert nivel_dominio("¿cuánto es 2 + 2?") is None


def test_nivel_dominio_fuerte_gana_a_estructural() -> None:
    """D3: con ambas presentes gana 'fuerte' — de ahí el orden de los `if`."""
    assert nivel_dominio("¿qué campos producen crudo?") == "fuerte"


# ── Patrones anclados: se saltan el filtro de dominio ─────────────────────────


def test_anclado_p50() -> None:
    grupo, patrones = clasificar_capa1("¿cuál es el P50 de este mes?")
    assert grupo == "analizar"
    assert es_anclado(patrones) is True


def test_no_anclado_cuantos_generico() -> None:
    grupo, patrones = clasificar_capa1("¿cuánto es la raíz cuadrada de 2?")
    assert grupo == "cuantificar"
    assert es_anclado(patrones) is False


def test_no_anclado_detractores_ahora_generico() -> None:
    """DETRACTORES pasó a genérico en el origen (2026-08-02): la palabra sola
    ya no basta, necesita entidad o vocabulario. Verificado allí en vivo con
    "detractores del rendimiento académico"."""
    grupo, patrones = clasificar_capa1(
        "¿cuáles son los detractores del rendimiento académico?"
    )
    assert grupo == "analizar"
    assert es_anclado(patrones) is False


def test_anclados_existen_en_patrones() -> None:
    """Guarda de deriva: cada cadena de `patrones_anclados` debe existir entre
    los patrones reales. Si alguien renombra un patrón y olvida la lista de
    anclados, el ancla deja de aplicarse en silencio."""
    compilados = modulo_patrones._compilar()
    reales = {p for _, _, p in compilados.maximos}
    for pares in compilados.grupos.values():
        reales |= {p for _, p in pares}
    faltan = compilados.anclados - reales
    assert not faltan, f"patrones_anclados no presentes entre los patrones: {faltan}"


def test_es_anclado_con_lista_vacia() -> None:
    assert es_anclado([]) is False
    assert es_anclado(None) is False
