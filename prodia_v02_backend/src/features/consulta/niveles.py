"""N2 acumulado, N3 serie y N4 variación.

Portado de `consulta_v2/cuantificar/niveles.py` (85 líneas).

═══════════════════════════════════════════════════════════════════════════════
🔑 **H1 / ADR-001 — cómo se rompe el ciclo de dependencias.**
═══════════════════════════════════════════════════════════════════════════════

El origen importa el endpoint de análisis y lo llama como función:
`fn = _desempeno_fn or _desempeno_ep`. El parámetro existe para poder testear,
pero el *default* crea una dependencia `consulta → analisis` que aquí violaría
ADR-001.

En F4 se invierte: **el parámetro es obligatorio y no hay default**. Quien
compone la petición —`api.py`, el único módulo que conoce ambas features—
inyecta el servicio. Este módulo no importa nada de `analisis`, y como efecto
lateral se vuelve testeable sin BD.

**Coherencia chat ↔ tablero**: se reusa el MISMO servicio de desempeño que
alimenta la sección de Análisis. Si el chat calculara por su cuenta, las dos
pantallas podrían dar cifras distintas para la misma entidad.

🔑 **HE4 — el mes en curso NO se suma.** Es una proyección, no un cierre. Se
declara aparte en `en_curso` para que la respuesta pueda decirlo, en vez de
inflar el acumulado con un mes incompleto.
"""

from __future__ import annotations

from typing import Any, Protocol


class DesempenoFn(Protocol):
    """Firma del servicio de desempeño que F4 consume.

    Se declara como Protocol en vez de importar el tipo real: así este módulo
    no depende de `features/analisis` ni siquiera para tipar.
    """

    def __call__(
        self,
        entidad: str | None = None,
        nivel: str | None = None,
        periodo: str | None = None,
    ) -> Any: ...


_MESES = (
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def _como_dict(payload: Any) -> dict[str, Any]:
    """El servicio devuelve un modelo Pydantic; el motor razona con dicts.

    Se convierte en un solo punto para no salpicar `model_dump()` por todo el
    módulo ni acoplarse a la forma exacta del modelo.
    """
    if isinstance(payload, dict):
        return payload
    volcado = getattr(payload, "model_dump", None)
    if callable(volcado):
        resultado: dict[str, Any] = volcado()
        return resultado
    return dict(payload)


def _sin_datos(d: dict[str, Any]) -> bool:
    """Las tres formas en que el desempeño dice "no puedo responder"."""
    return (
        not d.get("encontrada") or bool(d.get("sin_datos")) or bool(d.get("sin_cierre"))
    )


def acumulado(
    resuelta: dict[str, Any],
    dim_producto: str,
    desempeno_fn: DesempenoFn,
) -> dict[str, Any]:
    """Σ del REAL de los meses CERRADOS del año.

    `dim_producto` es el nombre del producto en el payload de desempeño
    (`CRUDO` | `GAS` | `BLANCOS`).

    Devuelve `{aplica: True, ...}` o `{aplica: False, texto}` — nunca lanza:
    la falta de datos es una respuesta legítima que hay que saber decir.
    """
    entidad = resuelta["valor"]
    nivel = resuelta.get("nivel")

    base = _como_dict(desempeno_fn(entidad=entidad, nivel=nivel, periodo=None))
    if _sin_datos(base):
        return {
            "aplica": False,
            "texto": f"No tengo datos de producción para «{entidad}».",
        }

    anio = base["mes"]["anio"]
    ultimo_mes = base["mes"]["mes"]

    total_real = 0.0
    total_ppto = 0.0
    meses_cerrados: list[str] = []
    en_curso: dict[str, Any] | None = None

    for m in range(1, ultimo_mes + 1):
        mes = _como_dict(desempeno_fn(entidad=entidad, nivel=nivel, periodo=_MESES[m]))
        if _sin_datos(mes):
            continue

        fila = next(
            (p for p in mes["por_producto"] if p["producto"] == dim_producto), None
        )
        if not fila or (fila["real"] == 0 and fila["ppto"] == 0):
            continue

        if mes["mes"]["completo"]:
            total_real += fila["real"]
            total_ppto += fila["ppto"] or 0
            meses_cerrados.append(_MESES[m])
        else:
            # HE4: proyección, NO se suma.
            en_curso = {"nombre": _MESES[m], "real": fila["real"]}

    if not meses_cerrados:
        return {
            "aplica": False,
            "texto": (
                f"«{entidad}» aún no tiene meses cerrados en {anio} para acumular."
            ),
        }

    return {
        "aplica": True,
        "real": total_real,
        "ppto": total_ppto,
        "meses": meses_cerrados,
        "en_curso": en_curso,
        "anio": anio,
    }


def _serie_puntos(
    resuelta: dict[str, Any],
    dim_producto: str,
    desempeno_fn: DesempenoFn,
) -> tuple[list[dict[str, Any]] | None, float | None, int | None, str | None]:
    """Puntos de la serie mensual, su promedio, el año y el mes proyectado.

    Reusa `ritmo_mensual` del desempeño: es la MISMA serie que pinta el panel,
    así que el chat y el tablero no pueden divergir.
    """
    base = _como_dict(
        desempeno_fn(
            entidad=resuelta["valor"], nivel=resuelta.get("nivel"), periodo=None
        )
    )
    if _sin_datos(base):
        return None, None, None, None

    ritmo = base.get("ritmo_mensual") or {}
    meses = ritmo.get("meses") or []
    valores = (ritmo.get("series") or {}).get(dim_producto) or []

    puntos = [
        {"mes": meses[i], "valor": valores[i]}
        for i in range(min(len(meses), len(valores)))
        if valores[i] is not None
    ]
    promedio = (ritmo.get("promedio_mes") or {}).get(dim_producto)

    # El último punto es PROYECCIÓN si el mes más reciente no está cerrado.
    proyeccion_mes = (
        puntos[-1]["mes"] if (puntos and not base["mes"]["completo"]) else None
    )

    return puntos, promedio, base["mes"]["anio"], proyeccion_mes


def serie(
    resuelta: dict[str, Any],
    dim_producto: str,
    desempeno_fn: DesempenoFn,
) -> dict[str, Any]:
    """N3: la serie mensual del año."""
    puntos, promedio, anio, proyeccion_mes = _serie_puntos(
        resuelta, dim_producto, desempeno_fn
    )
    if not puntos:
        return {
            "aplica": False,
            "texto": f"No tengo serie mensual para «{resuelta['valor']}».",
        }
    return {
        "aplica": True,
        "serie": puntos,
        "promedio": promedio,
        "anio": anio,
        "proyeccion_mes": proyeccion_mes,
    }


def variacion(
    resuelta: dict[str, Any],
    dim_producto: str,
    desempeno_fn: DesempenoFn,
) -> dict[str, Any]:
    """N4: los cambios mes a mes.

    Exige al menos DOS puntos: con uno solo no hay variación que calcular, y
    decirlo es más honesto que devolver un delta de cero.
    """
    puntos, _promedio, anio, proyeccion_mes = _serie_puntos(
        resuelta, dim_producto, desempeno_fn
    )
    if not puntos or len(puntos) < 2:
        return {
            "aplica": False,
            "texto": (
                f"«{resuelta['valor']}» no tiene suficientes meses para comparar."
            ),
        }

    deltas: list[dict[str, Any]] = []
    for anterior, actual in zip(puntos, puntos[1:], strict=False):
        delta = actual["valor"] - anterior["valor"]
        pct = round(delta / anterior["valor"] * 100, 1) if anterior["valor"] else None
        deltas.append(
            {
                "de": anterior["mes"],
                "a": actual["mes"],
                "delta": delta,
                "pct": pct,
            }
        )

    return {
        "aplica": True,
        "deltas": deltas,
        "ultimo": deltas[-1],
        "anio": anio,
        "proyeccion_mes": proyeccion_mes,
    }
