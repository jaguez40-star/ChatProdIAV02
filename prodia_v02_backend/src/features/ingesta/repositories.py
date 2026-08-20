"""Acceso a datos del ETL de Ingesta — el SQL portado del sistema viejo.

**Todo el SQL se conserva idéntico** (U3: se reescribe la capa de acceso, no el esquema ni
las consultas). Lo único que cambia es que aquí vive en una capa propia, con tipos, en vez
de estar mezclado con la lógica de extracción como en el monolito de origen.

## La doctrina de idempotencia

Reingerir el mismo archivo dos veces debe dejar la base igual. Se logra de dos formas,
según lo que la tabla permita:

| Patrón | Cuándo | Tablas |
|---|---|---|
| `UPSERT ON CONFLICT` | hay una clave única natural | `config_reporte`, `dim_*`, los `fact_*` de ECP y filiales |
| `DELETE WHERE reporte_id` + `INSERT` | no hay clave única | `bronze.*`, `fact_comentarios_produccion`, `fact_tabla_hoja` |

⚠️ **Los DELETE son la operación más peligrosa de F3.** Cada uno lleva su
`WHERE reporte_id=:r` (y `AND hoja=:h` donde aplica). Perder ese `WHERE` en un refactor no
rompería ningún test convencional —el flujo seguiría funcionando— pero borraría la tabla
entera. El doble de test (`tests/fakes/db_escritura_falsa.py`) aborta si detecta uno sin
acotar.

## Chunking

Los INSERT masivos van en lotes de `TAMANO_LOTE` filas. `BDP_datos_mes` aporta ~315.000
filas por reporte: en una sola sentencia, el driver construiría un statement gigantesco.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.features.ingesta.celdas import to_date
from src.features.ingesta.extractores.comunes import FilaExtraida

# Filas por lote en los INSERT masivos. Heredado del origen.
TAMANO_LOTE = 10_000

# Columnas descriptivas de `dim_fuente` que se actualizan preservando lo no nulo.
COLUMNAS_FUENTE = [
    "nombre", "campo", "contrato", "tipo_contrato", "operador", "modalidad",
    "operacion", "nacionalidad", "gerencia", "grupo1", "grupo2", "grupo3",
    "activos", "fuente_contrato",
]  # fmt: skip

_FECHA_EN_NOMBRE = re.compile(r"(\d{8})")


class CacheDimension:
    """Resuelve nombre → id de una dimensión pequeña, creándola si falta.

    Carga la dimensión entera en memoria al construirse: son catálogos de decenas de
    filas que se consultan una vez por cada fila del fact, así que sin caché el ETL haría
    cientos de miles de SELECT.

    El `INSERT ... ON CONFLICT DO UPDATE SET <col>=EXCLUDED.<col> RETURNING <id>` es un
    truco deliberado del origen: el `DO UPDATE` aparentemente inútil —asigna la columna a
    sí misma— es lo que hace que PostgreSQL devuelva el id **también cuando la fila ya
    existía**. Con `DO NOTHING`, el RETURNING vendría vacío en ese caso.
    """

    def __init__(
        self, db: Session, tabla: str, columna_id: str, columna_nombre: str
    ) -> None:
        self._db = db
        self._tabla = tabla
        self._columna_id = columna_id
        self._columna_nombre = columna_nombre
        self._cache: dict[str, int] = {}
        for fila in self._db.execute(
            text(f"SELECT {columna_id}, {columna_nombre} FROM {tabla}")
        ):
            self._cache[fila[1]] = fila[0]

    def get(self, nombre: str | None) -> int | None:
        if nombre is None:
            return None
        if nombre in self._cache:
            return self._cache[nombre]
        identificador = self._db.execute(
            text(
                f"INSERT INTO {self._tabla} ({self._columna_nombre}) VALUES (:n) "
                f"ON CONFLICT ({self._columna_nombre}) DO UPDATE "
                f"SET {self._columna_nombre}=EXCLUDED.{self._columna_nombre} "
                f"RETURNING {self._columna_id}"
            ),
            {"n": nombre},
        ).scalar()
        if identificador is None:
            return None
        self._cache[nombre] = int(identificador)
        return int(identificador)


class IngestaRepository:
    """Escrituras del ETL. Recibe la sesión transaccional; no abre ni cierra nada."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Bloqueo de concurrencia ─────────────────────────────────────────────

    def tomar_bloqueo_de_reporte(self, fecha_reporte: dt.date | None) -> None:
        """Serializa las ingestas de la MISMA fecha; las de fechas distintas corren en
        paralelo (G4 — el origen no tenía nada de esto).

        Es `xact`: el bloqueo se libera solo al terminar la transacción, sin que nadie
        tenga que acordarse de soltarlo, ni siquiera si el ETL revienta.
        """
        clave = fecha_reporte.isoformat() if fecha_reporte else "sin-fecha"
        self._db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:clave))"), {"clave": clave}
        )

    # ── config_reporte ──────────────────────────────────────────────────────

    def upsert_reporte(
        self, ruta: Path, tiene_hojas_raw: bool
    ) -> tuple[int, dt.date | None]:
        """Crea o actualiza la fila del reporte y devuelve `(reporte_id, fecha)`.

        La fecha sale del nombre del archivo (`YYYYMMDD`), que es obligatorio: es la clave
        única de `config_reporte` y el linaje temporal de todo lo que se ingiere.
        """
        coincidencia = _FECHA_EN_NOMBRE.search(ruta.name)
        fecha_reporte = to_date(coincidencia.group(1)) if coincidencia else None
        tipo = "NEW" if tiene_hojas_raw else "STD"
        nivel = "FULL" if tiene_hojas_raw else "SIN_ECP"

        identificador = self._db.execute(
            text("""
        INSERT INTO core.config_reporte
            (fecha_reporte, archivo_nombre, tipo_archivo, tiene_raw, nivel_detalle)
        VALUES (:fr, :an, :tp, :raw, :nv)
        ON CONFLICT (fecha_reporte) DO UPDATE SET
            archivo_nombre=EXCLUDED.archivo_nombre, tipo_archivo=EXCLUDED.tipo_archivo,
            tiene_raw=EXCLUDED.tiene_raw, nivel_detalle=EXCLUDED.nivel_detalle,
            ingested_at=now()
        RETURNING reporte_id"""),
            {
                "fr": fecha_reporte,
                "an": ruta.name,
                "tp": tipo,
                "raw": tiene_hojas_raw,
                "nv": nivel,
            },
        ).scalar()
        if identificador is None:
            # El UPSERT siempre devuelve el id: si no lo hace, el esquema no es el
            # esperado y seguir escribiría facts huérfanos sin reporte al que colgarse.
            raise RuntimeError(
                "core.config_reporte no devolvió reporte_id: el esquema de la base "
                "no coincide con el que espera la ingesta."
            )
        return int(identificador), fecha_reporte

    def registrar_en_bitacora(
        self,
        reporte_id: int,
        hoja: str,
        destino: str,
        filas_leidas: int,
        filas_insertadas: int,
        estado: str = "OK",
        mensaje: str | None = None,
    ) -> None:
        """Anota una hoja en `core.ingesta_log`.

        Ojo: esta bitácora vive DENTRO de la transacción del ETL, así que un fallo
        posterior también la revierte. No sirve para diagnosticar una ingesta fallida —
        para eso está el log estructurado del backend.
        """
        self._db.execute(
            text("""
        INSERT INTO core.ingesta_log
            (reporte_id, hoja, tabla_destino, filas_leidas, filas_insertadas, estado, mensaje)
        VALUES (:r, :h, :d, :l, :i, :e, :m)"""),
            {
                "r": reporte_id,
                "h": hoja,
                "d": destino,
                "l": filas_leidas,
                "i": filas_insertadas,
                "e": estado,
                "m": mensaje,
            },
        )

    # ── Dimensiones compartidas ─────────────────────────────────────────────

    def asegurar_fechas(self, fechas: set[dt.date]) -> None:
        """Siembra `dim_fecha` con los atributos derivados de cada fecha."""
        filas = [
            {
                "f": fecha,
                "a": fecha.year,
                "m": fecha.month,
                "d": fecha.day,
                "t": (fecha.month - 1) // 3 + 1,
                "dw": fecha.isoweekday(),
                "sm": (fecha.day - 1) // 7 + 1,
            }
            for fecha in fechas
            if fecha is not None
        ]
        if not filas:
            return
        self._db.execute(
            text("""
            INSERT INTO core.dim_fecha (fecha, anio, mes, dia, trimestre, dia_semana, semana_mes)
            VALUES (:f, :a, :m, :d, :t, :dw, :sm) ON CONFLICT (fecha) DO NOTHING"""),
            filas,
        )

    def upsert_fuentes(
        self, fuentes: dict[int, dict[str, Any]], reporte_id: int
    ) -> None:
        """Actualiza `dim_fuente` preservando los valores no nulos ya guardados.

        El `COALESCE(EXCLUDED.col, dim_fuente.col)` es lo que evita que un reporte que
        trae una columna vacía borre el dato que otro reporte sí aportó: la dimensión
        acumula lo mejor de cada archivo en vez de quedarse con lo último.
        """
        if not fuentes:
            return
        asignaciones = ", ".join(
            f"{c}=COALESCE(EXCLUDED.{c}, core.dim_fuente.{c})" for c in COLUMNAS_FUENTE
        )
        columnas = ", ".join(COLUMNAS_FUENTE)
        parametros = ", ".join(f":{c}" for c in COLUMNAS_FUENTE)
        sentencia = text(f"""
        INSERT INTO core.dim_fuente (fuente_id, {columnas}, reporte_id_origen)
        VALUES (:fuente_id, {parametros}, :rep)
        ON CONFLICT (fuente_id) DO UPDATE SET {asignaciones},
            reporte_id_origen = EXCLUDED.reporte_id_origen, updated_at = now()""")
        filas = [
            {
                "fuente_id": identificador,
                "rep": reporte_id,
                **{c: atributos.get(c) for c in COLUMNAS_FUENTE},
            }
            for identificador, atributos in fuentes.items()
        ]
        self._db.execute(sentencia, filas)

    def crear_caches_de_dimension(self) -> dict[str, CacheDimension]:
        """Las ocho dimensiones pequeñas que consultan los loaders de facts."""
        definiciones = [
            ("vice", "core.dim_vicepresidencia", "vice_id", "sigla"),
            ("socio", "core.dim_socio", "socio_id", "nombre"),
            ("concepto", "core.dim_concepto", "concepto_id", "nombre"),
            ("tipo_producto", "core.dim_tipo_producto", "tipo_producto_id", "nombre"),
            ("escenario", "core.dim_escenario", "escenario_id", "nombre"),
            ("proceso", "core.dim_proceso", "proceso_id", "nombre"),
            ("empresa", "core.dim_empresa", "empresa_id", "nombre"),
            ("tipo_registro", "core.dim_tipo_registro", "tipo_id", "nombre"),
        ]
        return {
            alias: CacheDimension(self._db, tabla, columna_id, columna_nombre)
            for alias, tabla, columna_id, columna_nombre in definiciones
        }

    # ── Capa bronze ─────────────────────────────────────────────────────────

    def aterrizar_hoja_tipada(
        self,
        tabla: str,
        columnas: list[str],
        reporte_id: int,
        filas_hoja: list[tuple[Any, ...]],
    ) -> int:
        """Vuelca una hoja plana RAW en su tabla `bronze.*`, todo como TEXT.

        Bronze conserva el dato **tal como venía**, sin interpretar: es la copia de
        seguridad de la que se puede reprocesar si la lógica de `core` cambia.
        """
        self._db.execute(
            text(f"DELETE FROM bronze.{tabla} WHERE reporte_id=:r"), {"r": reporte_id}
        )
        parametros = ", ".join(f":{c}" for c in columnas)
        sentencia = text(
            f"INSERT INTO bronze.{tabla} (reporte_id, fila_origen, {', '.join(columnas)}) "
            f"VALUES (:_rep, :_fila, {parametros})"
        )

        lote: list[dict[str, Any]] = []
        total = 0
        for numero_fila, fila in enumerate(filas_hoja, start=2):
            if fila is None or all(celda is None for celda in fila):
                continue
            registro: dict[str, Any] = {"_rep": reporte_id, "_fila": numero_fila}
            for posicion, columna in enumerate(columnas):
                registro[columna] = (
                    None
                    if posicion >= len(fila) or fila[posicion] is None
                    else str(fila[posicion])
                )
            lote.append(registro)
            total += 1
            if len(lote) >= TAMANO_LOTE:
                self._db.execute(sentencia, lote)
                lote.clear()
        if lote:
            self._db.execute(sentencia, lote)
        return total

    def aterrizar_hoja_generica(
        self, hoja: str, reporte_id: int, filas_hoja: list[tuple[Any, ...]]
    ) -> int:
        """Vuelca cualquier otra hoja en `bronze.hoja_landing` como JSONB.

        Las claves salen del encabezado; una columna sin nombre se guarda como `colN`
        para no perderla.
        """
        self._db.execute(
            text("DELETE FROM bronze.hoja_landing WHERE reporte_id=:r AND hoja=:h"),
            {"r": reporte_id, "h": hoja},
        )
        if not filas_hoja:
            return 0

        encabezado = filas_hoja[0]
        claves = [
            str(nombre) if nombre is not None else f"col{posicion}"
            for posicion, nombre in enumerate(encabezado)
        ]
        sentencia = text(
            """INSERT INTO bronze.hoja_landing (reporte_id, hoja, fila_origen, payload)
               VALUES (:r, :h, :f, CAST(:p AS jsonb))"""
        )

        lote: list[dict[str, Any]] = []
        total = 0
        for numero_fila, fila in enumerate(filas_hoja[1:], start=2):
            if fila is None or all(celda is None for celda in fila):
                continue
            contenido = {
                (claves[posicion] if posicion < len(claves) else f"col{posicion}"): (
                    None if celda is None else str(celda)
                )
                for posicion, celda in enumerate(fila)
            }
            lote.append(
                {
                    "r": reporte_id,
                    "h": hoja,
                    "f": numero_fila,
                    "p": json.dumps(contenido, ensure_ascii=False),
                }
            )
            total += 1
            if len(lote) >= TAMANO_LOTE:
                self._db.execute(sentencia, lote)
                lote.clear()
        if lote:
            self._db.execute(sentencia, lote)
        return total

    # ── fact_tabla_hoja (lo que producen los 17 extractores) ────────────────

    def reemplazar_tablas_de_hoja(
        self, reporte_id: int, hoja: str, filas: list[FilaExtraida]
    ) -> list[FilaExtraida]:
        """Sustituye las filas de una hoja en `core.fact_tabla_hoja`.

        Deduplica antes de insertar por `(tabla_idx, dims, fecha)` con **last-wins**: esa
        tabla no tiene clave única, así que dos filas con la misma combinación entrarían
        ambas y el visor mostraría un duplicado. Gana la última, igual que en el origen.

        Devuelve las filas realmente insertadas, para que el servicio pueda contar por
        tabla sin recalcular la deduplicación.
        """
        self._db.execute(
            text("DELETE FROM core.fact_tabla_hoja WHERE reporte_id=:r AND hoja=:h"),
            {"r": reporte_id, "h": hoja},
        )

        unicas: dict[tuple[int, str, dt.date | None], FilaExtraida] = {}
        for fila in filas:
            clave = (
                fila.tabla_idx,
                json.dumps(fila.dims, sort_keys=True, ensure_ascii=False, default=str),
                fila.fecha,
            )
            unicas[clave] = fila
        deduplicadas = list(unicas.values())
        if not deduplicadas:
            return []

        sentencia = text("""
        INSERT INTO core.fact_tabla_hoja
            (reporte_id, hoja, tabla_idx, tabla_label, dims, fecha, valor)
        VALUES (:r, :h, :idx, :label, CAST(:dims AS jsonb), :fecha, :valor)""")
        for inicio in range(0, len(deduplicadas), TAMANO_LOTE):
            self._db.execute(
                sentencia,
                [
                    {
                        "r": reporte_id,
                        "h": hoja,
                        "idx": fila.tabla_idx,
                        "label": fila.tabla_label,
                        "dims": json.dumps(fila.dims, ensure_ascii=False, default=str),
                        "fecha": fila.fecha,
                        "valor": fila.valor,
                    }
                    for fila in deduplicadas[inicio : inicio + TAMANO_LOTE]
                ],
            )
        return deduplicadas

    # ── Comentarios ─────────────────────────────────────────────────────────

    def reemplazar_comentarios(
        self, reporte_id: int, filas: list[dict[str, Any]]
    ) -> int:
        """Sustituye los comentarios del reporte. No hay clave única: DELETE + INSERT."""
        self._db.execute(
            text("DELETE FROM core.fact_comentarios_produccion WHERE reporte_id=:r"),
            {"r": reporte_id},
        )
        if not filas:
            return 0
        self._db.execute(
            text("""
        INSERT INTO core.fact_comentarios_produccion
            (reporte_id, tipo_producto_id, activos, area, comentario,
             comentario_programa, comentario_extra)
        VALUES (:rep, :tipo, :activos, :area, :comentario, :programa, :extra)"""),
            filas,
        )
        return len(filas)
