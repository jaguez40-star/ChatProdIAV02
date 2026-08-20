"""Columnas de las tablas bronze y normalizadores de filiales — portado del sistema viejo.

`BZ_DIA`/`BZ_MES`/`BZ_PRG` son el **orden exacto** de columnas con que se aterrizan las
tres hojas crudas en `bronze.*`. No es una lista decorativa: el loader construye el INSERT
a partir de ella, así que reordenarla o renombrar un elemento desplaza los datos de columna
sin producir ningún error.

Los normalizadores existen porque las hojas escriben la misma entidad de varias formas
("EAI", "EA" y "AMERICA" son la misma filial). Sin ellos, la misma empresa entra como tres
filas distintas en las dimensiones.
"""

from __future__ import annotations

import re

# ── Columnas de las tablas bronze (orden significativo) ─────────────────────

BZ_DIA: list[str] = [
    "concepto", "socio", "operador", "tipocontrato", "contrato", "fuente", "idbdp",
    "fuentecontrato", "fecha", "mes", "anio", "escenario", "propietario", "grupoprod",
    "producto", "tipoproducto", "gerencia", "modalidad", "operacion", "nacionalidad",
    "grupo1", "grupo2", "grupo3", "volumen", "porcentaje", "vice", "activos",
    "voldismez", "vol_estimado", "promedio",
]  # fmt: skip

BZ_MES: list[str] = [
    "concepto", "socio", "ba_id", "operador", "grupooperador", "tipocontrato",
    "contrato", "fuente", "idbdp", "fuentecontratoplot", "fuentecontrato", "fecha",
    "mes", "anio", "escenario", "proceso", "row_changed_by", "propietario", "grupoprod",
    "producto", "tipoproducto", "negocio", "nuevagerencia", "superintendencia", "tag",
    "tipofuente", "tagdescripcion", "fechaefprop", "fechaexprop", "fechaefpden",
    "fechaexpden", "negociovpr", "gerencia", "modalidad", "operacion", "tipocrudo",
    "nacionalidad", "grupo1", "grupo2", "grupo3", "volumen", "porcentaje", "voldismez",
    "bpd_m", "bpda_ac", "bpdac_5", "bpd_a", "bpdeq_m", "blseq", "bpdeq_a", "nodo",
    "diluyente", "linea_estrategica", "mezcla_siv_gas", "producto_yacimiento",
    "proyeccion", "esc_proy", "vice", "activos",
]  # fmt: skip

BZ_PRG: list[str] = [
    "fecha", "vice", "gerencia", "version", "fecha_version", "estado", "volumen",
    "campo", "producto", "area", "idbdp", "contrato", "produccion_total", "part_ecp",
]  # fmt: skip

# ── Normalización de entidades de filiales ──────────────────────────────────

EMP_NORM: dict[str, str] = {
    "EAI": "America",
    "EA": "America",
    "AMERICA": "America",
    "HOCOL": "Hocol",
    "PERMIAN": "Permian",
}

PROD_NORM: dict[str, str] = {
    "CRUDO": "CRUDO",
    "GAS": "GAS",
    "BLANCOS": "BLANCOS",
    "BLANCO": "BLANCOS",
}

_ETIQUETA = re.compile(r"^\s*(.+?)\s*\(\s*([^)]+?)\s*\)?\s*$")


def norm_emp(empresa: str | None) -> str | None:
    """Nombre canónico de la filial. Si no está en el mapa, se conserva sin espacios."""
    if empresa is None:
        return None
    return EMP_NORM.get(empresa.strip().upper(), empresa.strip())


def norm_prod(producto: str | None) -> str | None:
    """Nombre canónico del producto. Devuelve `None` si no está en el mapa — a
    diferencia de `norm_emp`, aquí un valor desconocido NO se conserva: el producto
    decide la escala de la cifra (A5) y admitir uno arbitrario propagaría un error de
    unidades."""
    if producto is None:
        return None
    return PROD_NORM.get(producto.strip().upper())


def split_label(etiqueta: str) -> tuple[str | None, str | None]:
    """`'Hocol (crudo)'` → `('Hocol', 'crudo')`. `(None, None)` si no encaja."""
    coincidencia = _ETIQUETA.match(etiqueta)
    return (
        (coincidencia.group(1), coincidencia.group(2)) if coincidencia else (None, None)
    )
