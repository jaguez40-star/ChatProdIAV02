"""Segmento FILIALES — focos y excedentes sobre la base de las tarjetas.

Portado de `INGESTA/Rep_Prod/backend/app/features/analisis/api.py:1592-1657`.

⚠️ **La base de comparación NO es el programa: es el promedio 2026.**

Las filiales (Hocol · America · Permian) no tienen PPTO, así que la meta es su
PROMEDIO MENSUAL del año y el mes en curso se lleva a PROYECCIÓN DE CIERRE
(decisión del usuario "Opción B", 2026-07-21). Comparar 17 días contra un mes
entero daría ~55 % siempre.

**El bug que estas funciones corrigen**: el bloque central usaba el `focos` de
ECP, que mide REAL vs PROGRAMA misma-ventana, y contradecía a las tarjetas —
Permian aparecía como "excedente en crudo" mientras su propia tarjeta lo
marcaba 148k por DEBAJO de su promedio 2026. Aquí la descomposición usa la
MISMA base que las tarjetas y el desglose por filial, así que no pueden
divergir.
"""

from __future__ import annotations

from typing import Any

# ±5 % alrededor del promedio = "en línea": ni por encima ni por debajo.
BANDA_EN_LINEA_PCT = 5.0

_MAX_FOCOS = 5
_MAX_ENTIDADES_NOMBRADAS = 2
_MAX_EXCEDENTES = 3


def _formato(numero: float) -> str:
    return f"{abs(float(numero)):,.0f}".replace(",", ".")


def diferencias_por_producto(
    producto: str, por_filial_raw: list[dict[str, Any]]
) -> list[tuple[str, float, float, float]]:
    """[(empresa, proyección, promedio_2026, faltante)] para un producto.

    Solo entran las filiales que REPORTAN ese producto y tienen promedio: sin
    base de comparación no hay faltante que calcular.
    """
    diferencias: list[tuple[str, float, float, float]] = []
    for filial in por_filial_raw:
        for producto_filial in filial["t"].get("por_producto") or []:
            if (
                producto_filial.get("producto") == producto
                and producto_filial.get("reporta")
                and producto_filial.get("promedio_2026")
            ):
                proyeccion = float(producto_filial["proyeccion"])
                promedio = float(producto_filial["promedio_2026"])
                diferencias.append(
                    (filial["empresa"], proyeccion, promedio, proyeccion - promedio)
                )
    return diferencias


def focos_filiales(
    titular_cards: list[dict[str, Any]], por_filial_raw: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Un foco por producto cuyo GRUPO proyecta bajo su promedio 2026.

    Se atribuye a las filiales que quedan por debajo, sobre la misma base.
    """
    focos: list[dict[str, Any]] = []

    for tarjeta in titular_cards:
        producto = tarjeta["producto"]
        proyectado = float(tarjeta.get("real") or 0)
        meta = float(tarjeta.get("ppto") or 0)

        # El grupo está en o por encima de su promedio: no hay foco.
        if not meta or proyectado >= meta:
            continue

        faltante_grupo = proyectado - meta
        diferencias = diferencias_por_producto(producto, por_filial_raw)
        detractores = sorted(
            [d for d in diferencias if d[3] < 0], key=lambda x: x[3]
        )  # más negativa primero
        compensadores = sorted(
            [d for d in diferencias if d[3] > 0], key=lambda x: -x[3]
        )

        entidades = [d[0] for d in detractores[:_MAX_ENTIDADES_NOMBRADAS]]
        total_negativo = sum(-d[3] for d in detractores) or 1.0
        concentracion = (
            round(
                sum(-d[3] for d in detractores[:_MAX_ENTIDADES_NOMBRADAS])
                / total_negativo
                * 100
            )
            if detractores
            else None
        )

        # El frontend antepone `entidades` → el título NO las repite (evitaría
        # "Permian + Hocol Permian…").
        if not entidades:
            titulo = f"{round((1 - proyectado / meta) * 100)}% por debajo de su promedio 2026"
        elif len(entidades) == 1 or concentracion is None:
            titulo = "concentra el rezago del producto"
        else:
            titulo = (
                f"{concentracion}% del faltante en "
                f"{min(len(detractores), _MAX_ENTIDADES_NOMBRADAS)} filiales"
            )

        amortiguador = compensadores[0] if compensadores else None
        accion = (
            f"sostener {amortiguador[0]} (+{_formato(amortiguador[3])}) como amortiguador"
            if amortiguador
            else "plan de recuperación en las filiales rezagadas"
        )

        focos.append(
            {
                "producto": producto,
                "entidades": entidades,
                "faltante_abs": round(faltante_grupo),
                "magnitud_txt": None,
                "peso_relativo_pct": concentracion,
                "titulo": titulo,
                "causa": {
                    "texto": (
                        "proyecta por debajo de su promedio 2026 — sin meta "
                        "presupuestal en filiales"
                    ),
                    "cobertura": "sin_meta",
                    "detalle": [
                        f"{d[0]}: faltante {_formato(d[3])} "
                        f"(proy {_formato(d[1])} vs prom {_formato(d[2])})"
                        for d in detractores
                    ],
                },
                "accion": accion,
                "tipo": "promedio",
                "score": round(abs(faltante_grupo)),
            }
        )

    focos.sort(key=lambda f: f["score"], reverse=True)
    for indice, foco in enumerate(focos, 1):
        foco["rank"] = indice
    return focos[:_MAX_FOCOS]


def sin_foco_filiales(
    titular_cards: list[dict[str, Any]], por_filial_raw: list[dict[str, Any]]
) -> str:
    """Excedentes reales, sobre la base promedio 2026.

    Solo filiales POR ENCIMA en cada producto: así Permian NUNCA aparece como
    excedente en crudo si su tarjeta lo marca por debajo. Fin de la
    contradicción entre el bloque central y las tarjetas.
    """
    positivos: list[tuple[float, str]] = []
    for tarjeta in titular_cards:
        producto = tarjeta["producto"]
        for empresa, _proy, _prom, excedente in diferencias_por_producto(
            producto, por_filial_raw
        ):
            if excedente > 0:
                positivos.append(
                    (
                        excedente,
                        f"{empresa} en {producto.lower()} (+{_formato(excedente)})",
                    )
                )

    positivos.sort(key=lambda x: -x[0])
    if not positivos:
        return "Sin elementos adicionales."
    return "con excedentes: " + ", ".join(
        texto for _valor, texto in positivos[:_MAX_EXCEDENTES]
    )
