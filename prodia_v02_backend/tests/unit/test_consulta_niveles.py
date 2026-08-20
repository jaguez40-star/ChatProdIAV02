"""N2 acumulado, N3 serie y N4 variación.

El servicio de desempeño se INYECTA (H1/ADR-001), así que estos tests corren
sin BD y sin red: el doble devuelve payloads fijos.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.features.consulta.niveles import acumulado, serie, variacion

pytestmark = pytest.mark.unit


def _mes(
    numero: int,
    *,
    completo: bool = True,
    real: float = 100.0,
    ppto: float = 120.0,
    producto: str = "CRUDO",
) -> dict[str, Any]:
    return {
        "encontrada": True,
        "sin_datos": False,
        "sin_cierre": False,
        "mes": {
            "anio": 2026,
            "mes": numero,
            "nombre": "Mayo",
            "completo": completo,
            "dias_con_data": 31 if completo else 17,
            "dias_del_mes": 31,
        },
        "por_producto": [{"producto": producto, "real": real, "ppto": ppto}],
    }


_NUM_MES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5}


def _desempeno_falso(por_mes: dict[int | None, dict[str, Any]]):
    """Doble del servicio. La clave `None` es la consulta sin periodo."""

    def _fn(
        entidad: str | None = None,
        nivel: str | None = None,
        periodo: str | None = None,
    ) -> dict[str, Any]:
        clave = _NUM_MES.get(periodo) if periodo else None
        return por_mes.get(
            clave, {"encontrada": True, "sin_datos": True, "sin_cierre": False}
        )

    return _fn


_RESUELTA = {"valor": "CASTILLA", "nivel": "campo"}


# ── N2 acumulado ─────────────────────────────────────────────────────────────


def test_acumula_solo_los_meses_cerrados() -> None:
    """🔑 HE4: el mes en curso es una PROYECCIÓN y no se suma — inflaría el
    acumulado con un mes incompleto."""
    fn = _desempeno_falso(
        {
            None: _mes(3),
            1: _mes(1, real=100),
            2: _mes(2, real=200),
            3: _mes(3, completo=False, real=50),  # en curso
        }
    )

    resultado = acumulado(_RESUELTA, "CRUDO", fn)

    assert resultado["aplica"] is True
    assert resultado["real"] == 300  # 100 + 200, sin el mes en curso
    assert resultado["meses"] == ["enero", "febrero"]
    assert resultado["en_curso"] == {"nombre": "marzo", "real": 50}


def test_el_mes_en_curso_se_declara_aparte() -> None:
    """No se descarta en silencio: viaja en `en_curso` para que la respuesta
    pueda mencionarlo."""
    fn = _desempeno_falso({None: _mes(2), 1: _mes(1), 2: _mes(2, completo=False)})
    assert acumulado(_RESUELTA, "CRUDO", fn)["en_curso"] is not None


def test_sin_meses_cerrados_lo_dice() -> None:
    fn = _desempeno_falso({None: _mes(1), 1: _mes(1, completo=False)})
    resultado = acumulado(_RESUELTA, "CRUDO", fn)

    assert resultado["aplica"] is False
    assert "meses cerrados" in resultado["texto"]


def test_sin_datos_lo_dice_sin_lanzar() -> None:
    """La falta de datos es una respuesta legítima, no un error."""
    fn = _desempeno_falso({None: {"encontrada": False}})
    resultado = acumulado(_RESUELTA, "CRUDO", fn)

    assert resultado["aplica"] is False
    assert "CASTILLA" in resultado["texto"]


def test_ignora_los_meses_en_cero() -> None:
    """Real y presupuesto ambos en cero significa que no hay dato, no que la
    producción fuese nula."""
    fn = _desempeno_falso(
        {None: _mes(2), 1: _mes(1, real=0, ppto=0), 2: _mes(2, real=200)}
    )
    resultado = acumulado(_RESUELTA, "CRUDO", fn)

    assert resultado["meses"] == ["febrero"]


def test_el_producto_pedido_es_el_que_se_suma() -> None:
    fn = _desempeno_falso(
        {None: _mes(1, producto="GAS"), 1: _mes(1, producto="GAS", real=999)}
    )
    assert acumulado(_RESUELTA, "GAS", fn)["real"] == 999
    assert acumulado(_RESUELTA, "CRUDO", fn)["aplica"] is False


# ── N3 serie ─────────────────────────────────────────────────────────────────


def _con_ritmo(completo: bool = True) -> dict[str, Any]:
    base = _mes(3, completo=completo)
    base["ritmo_mensual"] = {
        "meses": ["Ene", "Feb", "Mar"],
        "series": {"CRUDO": [100, 200, 150]},
        "promedio_mes": {"CRUDO": 150},
    }
    return base


def test_la_serie_reusa_el_ritmo_del_panel() -> None:
    """Coherencia chat ↔ tablero: es la MISMA serie que pinta el panel."""
    fn = _desempeno_falso({None: _con_ritmo()})
    resultado = serie(_RESUELTA, "CRUDO", fn)

    assert resultado["aplica"] is True
    assert [p["mes"] for p in resultado["serie"]] == ["Ene", "Feb", "Mar"]
    assert resultado["promedio"] == 150


def test_la_serie_marca_el_mes_proyectado() -> None:
    """El último punto es proyección si el mes no está cerrado: pintarlo igual
    que los demás daría por cerrado lo que no lo está."""
    fn = _desempeno_falso({None: _con_ritmo(completo=False)})
    assert serie(_RESUELTA, "CRUDO", fn)["proyeccion_mes"] == "Mar"


def test_un_mes_cerrado_no_marca_proyeccion() -> None:
    fn = _desempeno_falso({None: _con_ritmo(completo=True)})
    assert serie(_RESUELTA, "CRUDO", fn)["proyeccion_mes"] is None


def test_sin_serie_lo_dice() -> None:
    fn = _desempeno_falso({None: _mes(1)})  # sin ritmo_mensual
    assert serie(_RESUELTA, "CRUDO", fn)["aplica"] is False


# ── N4 variación ─────────────────────────────────────────────────────────────


def test_la_variacion_calcula_los_deltas_y_su_porcentaje() -> None:
    fn = _desempeno_falso({None: _con_ritmo()})
    resultado = variacion(_RESUELTA, "CRUDO", fn)

    assert resultado["aplica"] is True
    assert len(resultado["deltas"]) == 2
    assert resultado["deltas"][0] == {
        "de": "Ene",
        "a": "Feb",
        "delta": 100,
        "pct": 100.0,
    }
    assert resultado["ultimo"]["delta"] == -50


def test_la_variacion_exige_al_menos_dos_puntos() -> None:
    """Con un solo mes no hay variación que calcular, y decirlo es más honesto
    que devolver un delta de cero."""
    base = _mes(1)
    base["ritmo_mensual"] = {
        "meses": ["Ene"],
        "series": {"CRUDO": [100]},
        "promedio_mes": {"CRUDO": 100},
    }
    fn = _desempeno_falso({None: base})

    resultado = variacion(_RESUELTA, "CRUDO", fn)
    assert resultado["aplica"] is False
    assert "suficientes meses" in resultado["texto"]


def test_una_division_por_cero_no_revienta() -> None:
    """Un mes anterior en cero deja el porcentaje en `None`, no lanza."""
    base = _mes(2)
    base["ritmo_mensual"] = {
        "meses": ["Ene", "Feb"],
        "series": {"CRUDO": [0, 100]},
        "promedio_mes": {"CRUDO": 50},
    }
    fn = _desempeno_falso({None: base})

    resultado = variacion(_RESUELTA, "CRUDO", fn)
    assert resultado["deltas"][0]["pct"] is None


# ── El servicio se inyecta ───────────────────────────────────────────────────


def test_acepta_un_modelo_pydantic_ademas_de_un_dict() -> None:
    """El servicio real devuelve un modelo; el motor razona con dicts. La
    conversión vive en un solo punto."""

    class _Modelo:
        def model_dump(self) -> dict[str, Any]:
            return _con_ritmo()

    def _fn(
        entidad: str | None = None,
        nivel: str | None = None,
        periodo: str | None = None,
    ) -> Any:
        return _Modelo()

    assert serie(_RESUELTA, "CRUDO", _fn)["aplica"] is True
