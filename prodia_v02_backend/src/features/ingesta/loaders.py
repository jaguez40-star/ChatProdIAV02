"""Loaders de las tablas estrella — leen una hoja y la vuelcan a su fact.

Se separan de los extractores (`extractores/`) porque hacen algo distinto: aquellos
producen filas genéricas para el visor (`fact_tabla_hoja`), estos alimentan el **modelo
dimensional** con sus claves foráneas resueltas contra las dimensiones.

## Por qué las columnas se resuelven por NOMBRE

`_indice_de_encabezado` construye un mapa `NOMBRE → posición` en vez de leer por posición
fija. No es una preferencia de estilo: el layout de `BDP_datos_dia` y `BDP_datos_mes` ha
cambiado entre versiones del reporte (hallazgo del 2026-07-06 — el diario pasó de 30 a 32
columnas, y el mensual de 59 a 31 con reordenación completa). Leer por posición habría
metido los datos en las columnas equivocadas **sin dar ningún error**.

`load_fact_mes` va un paso más allá y usa `.get()` para las columnas que pueden faltar en
un vintage concreto: así una columna ausente entra como `None` en vez de reventar. En
cambio `load_fact_dia` las exige todas, porque ahí sí son obligatorias.

## Filas descartadas

Una fila sin `FECHA` o sin `IDBDP` no se puede colgar del modelo, así que se descarta y se
cuenta aparte. Ese conteo llega a la bitácora: `filas_leidas` incluye las descartadas y
`filas_insertadas` no, de modo que la diferencia queda registrada.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Any

from src.features.ingesta.celdas import num, s, to_date
from src.features.ingesta.repositories import CacheDimension, IngestaRepository
from src.features.ingesta.transforms import norm_emp, norm_prod, split_label

# Filas acumuladas antes de volcar un lote a la base.
TAMANO_LOTE_LOADER = 10_000

# Empresas cuyo total mensual se ingiere como plan (POP).
EMPRESAS_CON_PLAN = ("Hocol", "America", "Permian")


class ResultadoLoader:
    """Cuántas filas se insertaron y cuántas se descartaron por falta de clave."""

    def __init__(self, insertadas: int = 0, descartadas: int = 0) -> None:
        self.insertadas = insertadas
        self.descartadas = descartadas

    @property
    def leidas(self) -> int:
        return self.insertadas + self.descartadas


def _indice_de_encabezado(filas: Iterator[tuple[Any, ...]]) -> dict[str, int]:
    """Mapa `NOMBRE_COLUMNA → posición` desde la primera fila (que consume del iterador)."""
    encabezado = next(filas, ())
    return {
        str(nombre).strip().upper(): posicion
        for posicion, nombre in enumerate(encabezado)
        if nombre is not None
    }


def _celda(fila: tuple[Any, ...], posicion: int | None) -> Any:
    """Valor de una columna que puede no existir en este vintage de la hoja."""
    if posicion is None or posicion >= len(fila):
        return None
    return fila[posicion]


def _primera_presente(indice: dict[str, int], *nombres: str) -> int | None:
    """Posición de la primera columna que exista, entre varios nombres posibles.

    La vicepresidencia es el caso que obliga a esto: se ha llamado `GRUPO1_SIGLA`,
    `NIVEL1_SIGLA` y `VICE` en distintos vintages del reporte (el archivo de 2024 usa
    `VICE`). Fijar un solo nombre deja `vice_id` en nulo, y como esa columna es NOT NULL
    en el fact, la ingesta entera revienta contra la base — no en la lectura, donde sería
    evidente, sino al insertar.
    """
    for nombre in nombres:
        posicion = indice.get(nombre)
        if posicion is not None:
            return posicion
    return None


def cargar_produccion_dia(
    hoja: Any,
    reporte_id: int,
    repositorio: IngestaRepository,
    dims: dict[str, CacheDimension],
) -> ResultadoLoader:
    """`BDP_datos_dia` → `core.fact_produccion_dia_ecp`.

    Va sembrando `dim_fecha` y `dim_fuente` lote a lote: las claves foráneas deben existir
    antes de insertar el fact, y acumularlas todas hasta el final gastaría memoria sin
    ganar nada.
    """
    filas_hoja = hoja.iter_rows(values_only=True)
    indice = _indice_de_encabezado(filas_hoja)
    resultado = ResultadoLoader()

    lote: list[dict[str, Any]] = []
    fuentes: dict[int, dict[str, Any]] = {}
    fechas: set[dt.date] = set()

    def volcar() -> None:
        repositorio.asegurar_fechas(fechas)
        repositorio.upsert_fuentes(fuentes, reporte_id)
        repositorio.insertar_produccion_dia(lote)
        lote.clear()
        fuentes.clear()
        fechas.clear()

    for fila in filas_hoja:
        if fila is None or _celda(fila, indice.get("IDBDP")) is None:
            continue
        fecha = to_date(_celda(fila, indice.get("FECHA")))
        identificador = num(_celda(fila, indice.get("IDBDP")))
        if fecha is None or identificador is None:
            resultado.descartadas += 1
            continue

        fuente_id = int(identificador)
        fuentes[fuente_id] = {
            "nombre": s(_celda(fila, indice.get("FUENTE"))),
            "contrato": s(_celda(fila, indice.get("CONTRATO"))),
            "tipo_contrato": s(_celda(fila, indice.get("TIPOCONTRATO"))),
            "operador": s(_celda(fila, indice.get("OPERADOR"))),
            "modalidad": s(_celda(fila, indice.get("MODALIDAD"))),
            "operacion": s(_celda(fila, indice.get("OPERACION"))),
            "nacionalidad": s(_celda(fila, indice.get("NACIONALIDAD"))),
            "gerencia": s(_celda(fila, indice.get("GERENCIA"))),
            "grupo1": s(_celda(fila, indice.get("GRUPO1"))),
            "grupo2": s(_celda(fila, indice.get("GRUPO2"))),
            "grupo3": s(_celda(fila, indice.get("GRUPO3"))),
            "activos": s(_celda(fila, indice.get("ACTIVOS"))),
            "fuente_contrato": s(_celda(fila, indice.get("FUENTECONTRATO"))),
        }
        fechas.add(fecha)
        lote.append(
            {
                "fecha": fecha,
                "fuente_id": fuente_id,
                "vice_id": dims["vice"].get(
                    s(
                        _celda(
                            fila,
                            _primera_presente(
                                indice, "GRUPO1_SIGLA", "NIVEL1_SIGLA", "VICE"
                            ),
                        )
                    )
                ),
                "socio_id": dims["socio"].get(s(_celda(fila, indice.get("SOCIO")))),
                "concepto_id": dims["concepto"].get(
                    s(_celda(fila, indice.get("CONCEPTO")))
                ),
                "tipo_producto_id": dims["tipo_producto"].get(
                    s(_celda(fila, indice.get("TIPOPRODUCTO")))
                ),
                "producto": s(_celda(fila, indice.get("PRODUCTO"))) or "",
                "grupo_prod": s(_celda(fila, indice.get("GRUPOPROD"))) or "",
                "propietario": s(_celda(fila, indice.get("PROPIETARIO"))) or "",
                "volumen": num(_celda(fila, indice.get("VOLUMEN"))),
                "porcentaje": num(_celda(fila, indice.get("PORCENTAJE"))),
                "voldismez": num(_celda(fila, indice.get("VOLDISMEZ"))),
                "vol_estimado": num(_celda(fila, indice.get("VOL_ESTIMADO"))),
                "promedio": num(_celda(fila, indice.get("PROMEDIO"))),
                "rep": reporte_id,
            }
        )
        resultado.insertadas += 1
        if len(lote) >= TAMANO_LOTE_LOADER:
            volcar()

    if lote:
        volcar()
    return resultado


def cargar_produccion_mes(
    hoja: Any,
    reporte_id: int,
    repositorio: IngestaRepository,
    dims: dict[str, CacheDimension],
    al_avanzar: Any = None,
) -> ResultadoLoader:
    """`BDP_datos_mes` → `core.fact_produccion_mes_ecp`.

    Es la hoja más pesada (~315.000 filas). `al_avanzar` recibe el total acumulado en
    cada lote: sin esa señal, el progreso se quedaría mudo varios minutos y cualquier
    proxy daría la conexión por muerta.
    """
    filas_hoja = hoja.iter_rows(values_only=True)
    indice = _indice_de_encabezado(filas_hoja)
    resultado = ResultadoLoader()

    lote: list[dict[str, Any]] = []
    fuentes: dict[int, dict[str, Any]] = {}
    fechas: set[dt.date] = set()

    def volcar() -> None:
        repositorio.asegurar_fechas(fechas)
        repositorio.upsert_fuentes(fuentes, reporte_id)
        repositorio.insertar_produccion_mes(lote)
        lote.clear()
        fuentes.clear()
        fechas.clear()

    for fila in filas_hoja:
        if fila is None or _celda(fila, indice.get("IDBDP")) is None:
            continue
        fecha = to_date(_celda(fila, indice.get("FECHA")))
        identificador = num(_celda(fila, indice.get("IDBDP")))
        if fecha is None or identificador is None:
            resultado.descartadas += 1
            continue

        fuente_id = int(identificador)
        fuentes[fuente_id] = {
            "nombre": s(_celda(fila, indice.get("FUENTE"))),
            "contrato": s(_celda(fila, indice.get("CONTRATO"))),
            "operador": s(_celda(fila, indice.get("OPERADOR"))),
            "gerencia": s(_celda(fila, indice.get("GERENCIA"))),
            "grupo1": s(_celda(fila, indice.get("GRUPO1"))),
            "grupo2": s(_celda(fila, indice.get("GRUPO2"))),
            "activos": s(_celda(fila, indice.get("ACTIVOS"))),
            "fuente_contrato": s(_celda(fila, indice.get("FUENTECONTRATO"))),
        }
        fechas.add(fecha)
        lote.append(
            {
                "fecha": fecha,
                "fuente_id": fuente_id,
                "vice_id": dims["vice"].get(
                    s(
                        _celda(
                            fila,
                            _primera_presente(
                                indice, "NIVEL1_SIGLA", "GRUPO1_SIGLA", "VICE"
                            ),
                        )
                    )
                ),
                "socio_id": dims["socio"].get(s(_celda(fila, indice.get("SOCIO")))),
                "concepto_id": dims["concepto"].get(
                    s(_celda(fila, indice.get("CONCEPTO")))
                ),
                "tipo_producto_id": dims["tipo_producto"].get(
                    s(_celda(fila, indice.get("TIPOPRODUCTO")))
                ),
                "producto": s(_celda(fila, indice.get("PRODUCTO"))) or "",
                "escenario_id": dims["escenario"].get(
                    s(_celda(fila, indice.get("ESCENARIO")))
                ),
                "proceso_id": dims["proceso"].get(
                    s(_celda(fila, indice.get("PROCESO")))
                ),
                "grupo_prod": s(_celda(fila, indice.get("GRUPOPROD"))) or "",
                "negocio": s(_celda(fila, indice.get("NEGOCIO"))),
                "volumen": num(_celda(fila, indice.get("VOLUMEN"))),
                "porcentaje": num(_celda(fila, indice.get("PORCENTAJE"))),
                "voldismez": num(_celda(fila, indice.get("VOLDISMEZ"))),
                "bpd_m": num(_celda(fila, indice.get("BPD_M"))),
                "bpda_ac": num(_celda(fila, indice.get("BPDA_AC"))),
                "bpd_a": num(_celda(fila, indice.get("BPD_A"))),
                "bpdeq_m": num(_celda(fila, indice.get("BPDEQ_M"))),
                "blseq": num(_celda(fila, indice.get("BLSEQ"))),
                "bpdeq_a": num(_celda(fila, indice.get("BPDEQ_A"))),
                "rep": reporte_id,
            }
        )
        resultado.insertadas += 1
        if len(lote) >= TAMANO_LOTE_LOADER:
            volcar()
            if al_avanzar is not None:
                al_avanzar(resultado.insertadas)

    if lote:
        volcar()
    return resultado


def cargar_programa(
    hoja: Any,
    reporte_id: int,
    repositorio: IngestaRepository,
    dims: dict[str, CacheDimension],
) -> ResultadoLoader:
    """`BDP_Programa` → `core.fact_programa_ecp`.

    Esta hoja sí se lee por posición: es una tabla plana estable de 14 columnas, no un
    export cuyo layout cambie entre versiones.
    """
    filas_hoja = hoja.iter_rows(values_only=True)
    next(filas_hoja, None)  # encabezado
    resultado = ResultadoLoader()

    lote: list[dict[str, Any]] = []
    fechas: set[dt.date] = set()

    def volcar() -> None:
        repositorio.asegurar_fechas(fechas)
        repositorio.insertar_programa(lote)
        lote.clear()
        fechas.clear()

    for fila in filas_hoja:
        if fila is None or _celda(fila, 0) is None:
            continue
        fecha = to_date(fila[0])
        if fecha is None:
            resultado.descartadas += 1
            continue
        identificador = num(_celda(fila, 10))
        fechas.add(fecha)
        lote.append(
            {
                "fecha": fecha,
                "vice_id": dims["vice"].get(s(_celda(fila, 1))),
                "tipo_producto_id": dims["tipo_producto"].get(s(_celda(fila, 8))),
                "fuente_id": int(identificador) if identificador is not None else None,
                "area": s(_celda(fila, 9)) or "",
                "campo": s(_celda(fila, 7)) or "",
                "version": s(_celda(fila, 3)) or "",
                "fecha_version": to_date(_celda(fila, 4)),
                "volumen": num(_celda(fila, 6)),
                "produccion_total": num(_celda(fila, 12)),
                "part_ecp": num(_celda(fila, 13)),
                "rep": reporte_id,
            }
        )
        resultado.insertadas += 1
        if len(lote) >= TAMANO_LOTE_LOADER:
            volcar()

    if lote:
        volcar()
    return resultado


def presembrar_fuentes_de_programa(
    hoja: Any, reporte_id: int, repositorio: IngestaRepository
) -> None:
    """Crea en `dim_fuente` los IDBDP que solo aparecen en el programa.

    Sin esto, `fact_programa_ecp` violaría la clave foránea: el programa puede referirse
    a fuentes que aún no produjeron nada y por tanto no llegaron por los facts diarios.
    """
    filas_hoja = hoja.iter_rows(values_only=True)
    next(filas_hoja, None)
    nuevas: dict[int, dict[str, Any]] = {}
    for fila in filas_hoja:
        identificador = num(_celda(fila, 10)) if fila else None
        if identificador is None:
            continue
        nuevas[int(identificador)] = {
            "campo": s(_celda(fila, 7)),
            "grupo1": s(_celda(fila, 9)),
            "gerencia": s(_celda(fila, 2)),
            "contrato": s(_celda(fila, 11)),
        }
    repositorio.upsert_fuentes(nuevas, reporte_id)


# ── Comentarios ──────────────────────────────────────────────────────────────


def _celda_de_comentario(fila: tuple[Any, ...], posicion: int) -> str | None:
    """Comentario limpio; trata el `'0'` como vacío.

    Ese caso concreto corrige un bug del modelo anterior: la cadena de respaldo usaba
    `or`, y un `'0'` —que es texto no vacío pero falsy al convertirlo— cortocircuitaba de
    forma incoherente. Aquí se normaliza a `None` antes de encadenar.
    """
    valor = s(_celda(fila, posicion))
    return None if valor == "0" else valor


def cargar_comentarios(
    hoja: Any,
    reporte_id: int,
    repositorio: IngestaRepository,
    dims: dict[str, CacheDimension],
) -> ResultadoLoader:
    """`COMENTARIOS` → `core.fact_comentarios_produccion`.

    Tres campos de texto por fila: D = comentario real, E = comentario de programa,
    G = comentario extra. Como `comentario` es NOT NULL, se usa la cadena de respaldo
    D → E → G: si los tres están vacíos, la fila no aporta nada y se salta.

    El producto se rellena hacia abajo porque la columna A viene dispersa.
    """
    filas_hoja = hoja.iter_rows(values_only=True)
    next(filas_hoja, None)  # encabezado
    resultado = ResultadoLoader()
    lote: list[dict[str, Any]] = []
    producto: str | None = None

    for fila in filas_hoja:
        if fila is None or len(fila) < 4:
            continue
        etiqueta = s(_celda(fila, 0))
        if etiqueta:
            producto = etiqueta  # forward-fill

        comentario = _celda_de_comentario(fila, 3)
        programa = _celda_de_comentario(fila, 4)
        extra = _celda_de_comentario(fila, 6)
        principal = comentario or programa or extra
        if not principal:
            continue

        lote.append(
            {
                "tipo": dims["tipo_producto"].get(producto),
                "activos": s(_celda(fila, 1)),
                "area": s(_celda(fila, 2)),
                "comentario": principal,
                "programa": programa,
                "extra": extra,
                "rep": reporte_id,
            }
        )
        resultado.insertadas += 1

    repositorio.reemplazar_comentarios(reporte_id, lote)
    return resultado


# ── Filiales, POP y promedios ────────────────────────────────────────────────


def cargar_filiales(
    hoja: Any,
    reporte_id: int,
    repositorio: IngestaRepository,
    dims: dict[str, CacheDimension],
) -> ResultadoLoader:
    """`Producción filiales` → `core.fact_produccion_diaria`.

    Recorre la hoja por bloques: los títulos REAL y PROGRAMA cambian el tipo de registro
    vigente, la fila 'EMPRESA' aporta las fechas, y las siguientes son datos hasta el
    próximo título. El bloque PROYECCIÓN se ignora: no es producción registrada.
    """
    resultado = ResultadoLoader()
    tipo_vigente: str | None = None
    fechas_bloque: list[dt.date | None] = []
    lote: list[dict[str, Any]] = []
    fechas: set[dt.date] = set()

    for fila in hoja.iter_rows(values_only=True):
        etiqueta = s(_celda(fila, 0)) if fila else None
        if etiqueta is None:
            continue
        mayus = etiqueta.upper()

        if mayus == "REAL":
            tipo_vigente, fechas_bloque = "Real", []
            continue
        if mayus == "PROGRAMA":
            tipo_vigente, fechas_bloque = "Programa", []
            continue
        if mayus.startswith("PROYEC"):
            tipo_vigente, fechas_bloque = None, []
            continue
        if mayus == "EMPRESA":
            fechas_bloque = [to_date(v) for v in fila[1:]]
            continue
        if tipo_vigente is None or mayus.startswith("TOTAL"):
            continue

        empresa_cruda, producto_crudo = split_label(etiqueta)
        empresa_id = dims["empresa"].get(norm_emp(empresa_cruda))
        producto_id = dims["tipo_producto"].get(norm_prod(producto_crudo))
        tipo_id = dims["tipo_registro"].get(tipo_vigente)
        if not (empresa_id and producto_id and tipo_id):
            continue

        for posicion, valor_celda in enumerate(fila[1:]):
            fecha = fechas_bloque[posicion] if posicion < len(fechas_bloque) else None
            valor = num(valor_celda)
            if fecha is None or valor is None:
                continue
            fechas.add(fecha)
            lote.append(
                {
                    "e": empresa_id,
                    "p": producto_id,
                    "t": tipo_id,
                    "f": fecha,
                    "v": valor,
                    "r": reporte_id,
                }
            )

    repositorio.asegurar_fechas(fechas)
    repositorio.insertar_produccion_filiales(lote)
    resultado.insertadas = len(lote)
    return resultado


def cargar_pop(
    hoja: Any,
    reporte_id: int,
    repositorio: IngestaRepository,
    dims: dict[str, CacheDimension],
) -> ResultadoLoader:
    """`POP Filiales y Exploración` → `core.fact_plan_mensual`.

    Solo se toman las filas 'TOTAL <empresa>' de las tres filiales con plan. El valor se
    divide entre 1.000 porque la hoja publica en barriles y el fact guarda kbd.
    """
    resultado = ResultadoLoader()
    fechas_columna: list[dt.date | None] = []
    lote: list[dict[str, Any]] = []

    for fila in hoja.iter_rows(values_only=True):
        if fila is None:
            continue
        if s(_celda(fila, 1)) == "Producto":
            fechas_columna = [to_date(v) for v in fila]
            continue

        etiqueta = s(_celda(fila, 1))
        empresa = norm_emp(s(_celda(fila, 2)))
        if not (
            etiqueta
            and etiqueta.upper().startswith("TOTAL")
            and empresa in EMPRESAS_CON_PLAN
        ):
            continue

        empresa_id = dims["empresa"].get(empresa)
        for posicion, valor_celda in enumerate(fila):
            fecha = fechas_columna[posicion] if posicion < len(fechas_columna) else None
            valor = num(valor_celda)
            if fecha is None or valor is None:
                continue
            lote.append(
                {
                    "e": empresa_id,
                    "a": fecha.year,
                    "m": fecha.month,
                    "p": valor / 1000.0,
                    "r": reporte_id,
                }
            )

    repositorio.insertar_plan_mensual(lote)
    resultado.insertadas = len(lote)
    return resultado


def cargar_promedios(
    hoja: Any,
    reporte_id: int,
    repositorio: IngestaRepository,
    dims: dict[str, CacheDimension],
) -> ResultadoLoader:
    """Sección 'REAL PROMEDIO MES (YTD)' de `INICIO` → `core.fact_promedio_validado`."""
    resultado = ResultadoLoader()
    fechas_columna: list[dt.date | None] = []
    lote: list[dict[str, Any]] = []
    dentro_de_la_seccion = False

    for fila in hoja.iter_rows(values_only=True):
        etiqueta = s(_celda(fila, 0)) if fila else None
        if etiqueta == "Producto" and s(_celda(fila, 1)) == "Empresa":
            fechas_columna = [to_date(v) for v in fila]
            dentro_de_la_seccion = True
            continue
        if not dentro_de_la_seccion:
            continue
        if etiqueta is None or etiqueta.upper() == "TOTAL":
            continue

        producto_id = dims["tipo_producto"].get(norm_prod(etiqueta))
        empresa_id = dims["empresa"].get(norm_emp(s(_celda(fila, 1))))
        if not (producto_id and empresa_id):
            continue

        for posicion, valor_celda in enumerate(fila):
            fecha = fechas_columna[posicion] if posicion < len(fechas_columna) else None
            valor = num(valor_celda)
            if fecha is None or valor is None:
                continue
            lote.append(
                {
                    "e": empresa_id,
                    "p": producto_id,
                    "a": fecha.year,
                    "m": fecha.month,
                    "v": valor,
                    "r": reporte_id,
                }
            )

    repositorio.insertar_promedios_validados(lote)
    resultado.insertadas = len(lote)
    return resultado


def completar_calendario(
    hoja: Any, reporte_id: int, repositorio: IngestaRepository
) -> dict[str, Any]:
    """Completa los campos de calendario de `config_reporte` desde `INICIO`.

    Los valores se localizan por su etiqueta en la columna B, no por fila fija.
    """
    etiquetas: dict[str, Any] = {}
    for fila in hoja.iter_rows(min_row=1, max_row=40, max_col=4, values_only=True):
        nombre = s(_celda(fila, 1))
        if nombre:
            etiquetas[nombre] = _celda(fila, 2)

    def entero(valor: Any) -> int | None:
        numero = num(valor)
        return int(numero) if numero is not None else None

    inicio_de_anio = to_date(etiquetas.get("Fecha inicial año"))
    valores = {
        "fc": to_date(etiquetas.get("Día de corte")),
        "mi": to_date(etiquetas.get("1er dia del mes")),
        "mf": to_date(etiquetas.get("MES CORTE")),
        "vs": entero(etiquetas.get("Version Semana")),
        "ai": inicio_de_anio.year if inicio_de_anio else None,
        "da": entero(etiquetas.get("Días del año")),
    }
    repositorio.completar_calendario_del_reporte(reporte_id, valores)
    return valores
