"""Desempeño del mes (ECP) — ámbito nivel+periodo aware, KPIs, curva y ritmo.

Portado de `INGESTA/Rep_Prod/backend/app/features/analisis/api.py:361-666`.

Cimiento compartido por `desempeno`, `desempeno_insight` y `ejecutivo`:

- **nivel-aware**: resuelve por la COLUMNA del nivel (campo ≠ área); sin nivel,
  OR-unión por compatibilidad.
- **periodo-aware** (v1 = solo MES): default último-con-dato · mes explícito ·
  mes+año · "mes pasado". Año/semana/trimestre NO están soportados y se
  declaran con `periodo_ok=False` en vez de servir otra cosa en silencio.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass

from src.features.analisis.repositories import NIVEL_A_COLUMNA, AnalisisRepository
from src.features.analisis.schemas import (
    CampoSinMetaOut,
    CurvaOut,
    DesempenoOut,
    MesInfoOut,
    ProductoDesempenoOut,
    RitmoMensualOut,
)
from src.features.analisis.services_catalogo import MESES_ES
from src.shared.catalogo_entidades import fuentes_de_activo

PRODUCTOS = ["CRUDO", "GAS", "BLANCOS"]

MESES_NUM = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

PERIODO_DEFAULT_TXT = {
    "este mes",
    "mes actual",
    "el mes",
    "mes en curso",
    "este mes en curso",
}

# Tolerancia de reconciliación entre la curva diaria y el fact mensual.
# BLANCOS no reconcilia (su curva diaria suma 4 conceptos-copia → ×4 vs el
# mensual), y por eso no se le entrega promedio diario.
_TOLERANCIA_RECONCILIA = 1.15


def periodo_es_default(texto: str | None) -> bool:
    return (not texto) or (texto.strip().lower() in PERIODO_DEFAULT_TXT)


def parse_periodo(
    texto: str | None, anio_ref: int, mes_ref: int
) -> tuple[int, int] | None:
    """Texto libre de periodo → (año, mes), o `None` si no se reconoce.

    v1 (D-C1): default, mes por nombre (+año opcional) y 'mes pasado'.
    Año/semana/trimestre devuelven `None` a propósito: el llamador lo declara
    con `periodo_ok=False` en vez de servir un periodo distinto al pedido.
    """
    if periodo_es_default(texto):
        return None

    normalizado = (texto or "").strip().lower()
    if "pasado" in normalizado or "anterior" in normalizado:
        anio, mes = anio_ref, mes_ref - 1
        if mes < 1:
            anio, mes = anio - 1, 12
        return (anio, mes)

    mes_encontrado = next(
        (num for nombre, num in MESES_NUM.items() if nombre in normalizado), None
    )
    if mes_encontrado is None:
        return None  # año/semana/trimestre no soportados en v1

    anio_explicito = re.search(r"(20\d\d)", normalizado)
    return (
        int(anio_explicito.group(1)) if anio_explicito else anio_ref,
        mes_encontrado,
    )


@dataclass
class Ambito:
    """Ámbito ECP resuelto: qué fuentes, qué mes y si hay grano diario."""

    ids: list[int]
    vice_id: int | None
    anio: int
    mes: int
    dias_del_mes: int
    ini: str
    fin: str
    aplica_diario: bool
    periodo_ok: bool


class SinDatosError(Exception):
    """La entidad existe pero no tiene ninguna fecha con dato."""


class NoEncontradaError(Exception):
    """La entidad no existe en el catálogo."""


class DesempenoService:
    """Desempeño del mes. Solo lectura, sin LLM."""

    def __init__(self, repo: AnalisisRepository) -> None:
        self._repo = repo

    # ── Ámbito ───────────────────────────────────────────────────────────────

    def resolver_ambito(
        self,
        entidad: str | None,
        nivel: str | None = None,
        periodo: str | None = None,
    ) -> Ambito:
        ids: list[int] = []
        vice_id: int | None = None

        if entidad:
            objetivo = entidad.strip().upper()
            nivel_norm = (nivel or "").lower()
            columna = NIVEL_A_COLUMNA.get(nivel_norm)

            if nivel_norm == "vicepresidencia":
                vice_id = self._repo.vice_id_de(objetivo)
            elif nivel_norm == "activo":
                # El activo se compone desde core.map_campo_activo — MISMA
                # fuente que el chat, para que no puedan divergir.
                ids = fuentes_de_activo(self._repo.db, objetivo)
            elif columna:
                ids = self._repo.fuentes_por_columna(columna, objetivo)
            else:
                # Sin nivel: OR-unión + activo + vicepresidencia (compat D-C3).
                ids = sorted(
                    set(self._repo.fuentes_union(objetivo))
                    | set(fuentes_de_activo(self._repo.db, objetivo))
                )
                vice_id = self._repo.vice_id_de(objetivo)

            if not ids and vice_id is None:
                raise NoEncontradaError(entidad)

        max_fecha = self._repo.max_fecha_diaria(ids, vice_id)
        aplica_diario = max_fecha is not None
        if max_fecha is None:
            max_fecha = self._repo.max_fecha_mensual_real(ids, vice_id)
        if max_fecha is None:
            raise SinDatosError(entidad or "global")

        pedido = parse_periodo(periodo, max_fecha.year, max_fecha.month)
        anio, mes = pedido if pedido else (max_fecha.year, max_fecha.month)
        # Honrado, o default explícito. False = el periodo pedido no se soporta.
        periodo_ok = bool(pedido) or periodo_es_default(periodo)
        dias_del_mes = calendar.monthrange(anio, mes)[1]

        return Ambito(
            ids=ids,
            vice_id=vice_id,
            anio=anio,
            mes=mes,
            dias_del_mes=dias_del_mes,
            ini=f"{anio:04d}-{mes:02d}-01",
            fin=f"{anio:04d}-{mes:02d}-{dias_del_mes:02d}",
            aplica_diario=aplica_diario,
            periodo_ok=periodo_ok,
        )

    # ── KPIs y curva (compartidos con el bloque ejecutivo) ───────────────────

    def kpis_por_producto(self, ambito: Ambito) -> dict[str, dict[str, float]]:
        """{producto: {REAL: x, PPTO: y}} del mes resuelto."""
        kpis: dict[str, dict[str, float]] = {}
        for fila in self._repo.kpis_mes(ambito.ids, ambito.vice_id, ambito.fin):
            kpis.setdefault(str(fila["prod"]), {})[str(fila["esc"])] = float(
                fila["vol"] or 0
            )
        return kpis

    def curva_diaria(self, ambito: Ambito) -> tuple[list[str], dict[str, list[float]]]:
        """(fechas, {producto: valores}) — solo forma, nunca alimenta KPIs (H2)."""
        if not ambito.aplica_diario:
            return [], {p: [] for p in PRODUCTOS}

        por_fecha: dict[str, dict[str, float]] = {}
        for fila in self._repo.curva_diaria(
            ambito.ids, ambito.vice_id, ambito.ini, ambito.fin
        ):
            iso = fila["fecha"].isoformat()
            por_fecha.setdefault(iso, {})[str(fila["prod"])] = float(fila["vol"] or 0)

        fechas = sorted(por_fecha.keys())
        series = {
            p: [por_fecha.get(f, {}).get(p, 0.0) for f in fechas] for p in PRODUCTOS
        }
        return fechas, series

    # ── Endpoint /desempeno ──────────────────────────────────────────────────

    def desempeno(
        self,
        entidad: str | None = None,
        nivel: str | None = None,
        periodo: str | None = None,
    ) -> DesempenoOut:
        try:
            ambito = self.resolver_ambito(entidad, nivel, periodo)
        except NoEncontradaError:
            return DesempenoOut(entidad=entidad, encontrada=False)
        except SinDatosError:
            return DesempenoOut(entidad=entidad, encontrada=True, sin_datos=True)

        kpis = self.kpis_por_producto(ambito)
        fechas, series = self.curva_diaria(ambito)
        dias_reportados = len(fechas)

        por_producto = []
        for producto in PRODUCTOS:
            real = kpis.get(producto, {}).get("REAL", 0.0)
            ppto = kpis.get(producto, {}).get("PPTO", 0.0)
            por_producto.append(
                ProductoDesempenoOut(
                    producto=producto,
                    real=real,
                    ppto=ppto,
                    # `None`, no 0: sin meta NO es 0 % de cumplimiento.
                    cumplimiento=round(real / ppto * 100.0, 1) if ppto else None,
                )
            )

        # H5: sin ninguna fila mensual REAL/PPTO para el mes.
        sin_cierre = not any(kpis.get(p) for p in PRODUCTOS)

        campos_sin_meta: list[CampoSinMetaOut] = []
        if ambito.ids and (nivel or "").lower() == "activo":
            # D-A4: solo aplica al nivel 'activo' — es el único que agrega
            # varios campos, y por tanto el único donde el REAL sumado puede
            # compararse contra un PPTO que no los cubre a todos.
            campos_sin_meta = [
                CampoSinMetaOut(
                    campo=str(fila["campo"]),
                    producto=str(fila["producto"]),
                    real=float(fila["real"] or 0),
                )
                for fila in self._repo.campos_sin_meta(ambito.ids, ambito.fin)
            ]

        return DesempenoOut(
            entidad=entidad,
            encontrada=True,
            aplica_diario=ambito.aplica_diario,
            sin_cierre=sin_cierre,
            periodo_ok=ambito.periodo_ok,
            mes=MesInfoOut(
                anio=ambito.anio,
                mes=ambito.mes,
                nombre=MESES_ES[ambito.mes],
                dias_con_data=dias_reportados,
                dias_del_mes=ambito.dias_del_mes,
                completo=dias_reportados >= ambito.dias_del_mes,
            ),
            por_producto=por_producto,
            campos_sin_meta=campos_sin_meta,
            curva=CurvaOut(fechas=fechas, series=series),
            ritmo_mensual=self._ritmo_mensual(ambito, kpis, series, dias_reportados),
        )

    def _ritmo_mensual(
        self,
        ambito: Ambito,
        kpis: dict[str, dict[str, float]],
        series: dict[str, list[float]],
        dias_reportados: int,
    ) -> RitmoMensualOut:
        """Producción mensual del año: barras = REAL de cada mes, línea =
        promedio de los meses CERRADOS.

        🔑 Sale del MISMO fact MENSUAL que la tarjeta, así que el mes en curso y
        el promedio reconcilian EXACTO. NO se usa el fact diario: para
        GAS/BLANCOS usa otra medida (H2).
        """
        real_por_mes: dict[int, dict[str, float]] = {}
        for fila in self._repo.real_mensual_del_anio(
            ambito.ids, ambito.vice_id, ambito.anio
        ):
            real_por_mes.setdefault(int(fila["mes"]), {})[str(fila["prod"])] = float(
                fila["vol"] or 0
            )

        meses_ordenados = sorted(real_por_mes.keys())
        series_mes: dict[str, list[float | None]] = {}
        promedio_mes: dict[str, float | None] = {}
        promedio_dia: dict[str, float | None] = {}

        for producto in PRODUCTOS:
            series_mes[producto] = [
                (
                    round(real_por_mes[m][producto])
                    if real_por_mes.get(m, {}).get(producto)
                    else None
                )
                for m in meses_ordenados
            ]

            # Promedio mensual = media de los meses CERRADOS (anteriores al
            # actual) = el `hist_prom` de la tarjeta.
            cerrados = [
                (m, real_por_mes[m][producto])
                for m in meses_ordenados
                if m < ambito.mes and real_por_mes.get(m, {}).get(producto)
            ]
            promedio_mes[producto] = (
                round(sum(v for _m, v in cerrados) / len(cerrados))
                if cerrados
                else None
            )

            # Promedio DIARIO del año = Σ REAL meses cerrados ÷ Σ días. Es la
            # referencia "vs 2026" de la curva diaria. SOLO se entrega si la
            # curva diaria de ESTE producto RECONCILIA con el mensual (GAS y
            # CRUDO sí; BLANCOS no — su curva suma 4 conceptos-copia → ×4 vs el
            # mensual). Cuando no reconcilia, el frontend cae a la media del mes
            # y su título NO dice "vs 2026".
            dias_cerrados = sum(
                calendar.monthrange(ambito.anio, m)[1] for m, _v in cerrados
            )
            acumulado_diario = sum(v for v in series.get(producto, []) if v)
            esperado = (
                kpis.get(producto, {}).get("REAL", 0.0)
                * (dias_reportados / ambito.dias_del_mes)
                if ambito.dias_del_mes
                else 0.0
            )
            reconcilia = (
                esperado > 0 and acumulado_diario <= esperado * _TOLERANCIA_RECONCILIA
            )
            promedio_dia[producto] = (
                round(sum(v for _m, v in cerrados) / dias_cerrados)
                if (dias_cerrados and reconcilia)
                else None
            )

        return RitmoMensualOut(
            meses=[MESES_ES[m][:3] for m in meses_ordenados],
            meses_num=meses_ordenados,
            series=series_mes,
            promedio_mes=promedio_mes,
            promedio_dia=promedio_dia,
            mes_actual=ambito.mes,
        )


def escenario_mes(
    repo: AnalisisRepository,
    entidad: str,
    nivel: str | None = None,
    periodo: str | None = None,
    escenarios: tuple[str, ...] = ("OPERATIVO", "CONTABLE"),
) -> dict[str, dict[str, float]]:
    """Valor por producto de escenarios de presupuesto en el mes resuelto.

    ⚠️ **NO es un endpoint, y no debe serlo** (AF-4.11 del origen). Lo consume
    el motor Q v2 de F4/Cuantificar llamándolo como función normal; exponerlo
    como ruta haría que sus parámetros llegaran como objetos `Query` de FastAPI
    en vez de valores. Hay un test que verifica que no aparece en el OpenAPI.

    Read-only y AISLADO: no toca `desempeno` ni su `sin_cierre` (AF-4.2).
    Devuelve `{PRODUCTO: {ESCENARIO: valor}}`, vacío si no hay ámbito ni datos.
    """
    servicio = DesempenoService(repo)
    try:
        ambito = servicio.resolver_ambito(entidad, nivel=nivel, periodo=periodo)
    except (NoEncontradaError, SinDatosError):
        return {}

    if not ambito.ids and ambito.vice_id is None:
        return {}

    salida: dict[str, dict[str, float]] = {}
    for fila in repo.escenarios_mes(
        ambito.ids, ambito.vice_id, ambito.fin, list(escenarios)
    ):
        salida.setdefault(str(fila["prod"]), {})[str(fila["esc"])] = float(
            fila["vol"] or 0
        )
    return salida


__all__ = [
    "Ambito",
    "DesempenoService",
    "NoEncontradaError",
    "SinDatosError",
    "escenario_mes",
    "parse_periodo",
    "periodo_es_default",
]
