"""Tests de la API de Ingesta: validación de subida y traducción de errores.

La validación es lo que protege la base: todo lo que se rechace aquí no llega a abrir una
transacción. El origen no comprobaba ni el tamaño ni que el zip fuera un Excel válido
(G11), así que un archivo de varios GB o un `.exe` renombrado entraban al ETL.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile

from src.features.ingesta.api import _guardar_y_validar, _validar_nombre
from src.features.ingesta.schemas import CodigoErrorIngesta, ResultadoIngesta
from src.features.ingesta.sse import _codigo_de, _EstadoDelTrabajo, _evento_final

_WORKBOOK = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="INICIO" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""


def _xlsm_valido() -> bytes:
    """Un .xlsm mínimo pero legible por el detector."""
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as archivo:
        archivo.writestr("xl/workbook.xml", _WORKBOOK)
    return memoria.getvalue()


def _subida(nombre: str, contenido: bytes) -> UploadFile:
    return UploadFile(filename=nombre, file=io.BytesIO(contenido))


@pytest.fixture(autouse=True)
def _subidas_en_carpeta_temporal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ningún test escribe en el directorio real de subidas."""
    import src.features.ingesta.api as modulo

    monkeypatch.setattr(modulo, "_directorio_de_subidas", lambda: tmp_path)


# ── Validación del nombre ────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "nombre", ["20260815_r.xlsm", "20260815_r.xlsx", "R_20260815.XLSM"]
)
def test_acepta_los_nombres_validos(nombre: str) -> None:
    _validar_nombre(nombre)  # no lanza


@pytest.mark.unit
def test_rechaza_una_extension_que_no_es_excel() -> None:
    with pytest.raises(HTTPException) as excinfo:
        _validar_nombre("20260815_reporte.pdf")

    assert excinfo.value.status_code == 400
    assert excinfo.value.headers["X-Codigo"] == CodigoErrorIngesta.ARCHIVO_INVALIDO


@pytest.mark.unit
def test_rechaza_un_archivo_sin_fecha_en_el_nombre() -> None:
    """La fecha es la clave única del reporte: sin ella no hay dónde colgarlo."""
    with pytest.raises(HTTPException) as excinfo:
        _validar_nombre("reporte_sin_fecha.xlsm")

    assert excinfo.value.status_code == 422
    assert excinfo.value.headers["X-Codigo"] == CodigoErrorIngesta.FECHA_AUSENTE
    assert "YYYYMMDD" in excinfo.value.detail


# ── Guardado y validación del contenido ──────────────────────────────────────


@pytest.mark.unit
def test_guarda_el_archivo_y_calcula_su_hash(tmp_path: Path) -> None:
    resultado = _guardar_y_validar(_subida("20260815_r.xlsm", _xlsm_valido()))

    assert resultado.ruta.exists()
    assert len(resultado.hash_contenido) == 64  # SHA-256 en hexadecimal


@pytest.mark.unit
def test_el_hash_distingue_contenidos_distintos() -> None:
    """Permite avisar de 'misma fecha, archivo distinto', que el origen no podía."""
    uno = _guardar_y_validar(_subida("20260815_r.xlsm", _xlsm_valido()))

    otro_contenido = io.BytesIO()
    with zipfile.ZipFile(otro_contenido, "w") as archivo:
        archivo.writestr("xl/workbook.xml", _WORKBOOK.replace("INICIO", "OTRA"))
    dos = _guardar_y_validar(_subida("20260815_r.xlsm", otro_contenido.getvalue()))

    assert uno.hash_contenido != dos.hash_contenido


@pytest.mark.unit
def test_rechaza_un_archivo_que_no_es_un_zip_valido(tmp_path: Path) -> None:
    """Un .exe renombrado no debe llegar al ETL."""
    with pytest.raises(HTTPException) as excinfo:
        _guardar_y_validar(_subida("20260815_r.xlsm", b"esto no es un zip"))

    assert excinfo.value.headers["X-Codigo"] == CodigoErrorIngesta.ARCHIVO_INVALIDO
    assert list(tmp_path.glob("*")) == []  # y no deja basura en disco


@pytest.mark.unit
def test_rechaza_un_archivo_que_supera_el_tope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import src.features.ingesta.api as modulo

    class AjustesFalsos:
        ingesta_max_upload_mb = 0  # cualquier byte supera el tope
        ingesta_upload_dir = str(tmp_path)

    monkeypatch.setattr(modulo, "get_settings", lambda: AjustesFalsos())

    with pytest.raises(HTTPException) as excinfo:
        _guardar_y_validar(_subida("20260815_r.xlsm", _xlsm_valido()))

    assert excinfo.value.status_code == 413
    assert (
        excinfo.value.headers["X-Codigo"] == CodigoErrorIngesta.ARCHIVO_DEMASIADO_GRANDE
    )
    assert list(tmp_path.glob("*")) == []


@pytest.mark.unit
def test_descarta_la_ruta_del_nombre_recibido(tmp_path: Path) -> None:
    """Un nombre con directorios no debe poder escribir fuera de la carpeta de subidas."""
    resultado = _guardar_y_validar(_subida("../../20260815_r.xlsm", _xlsm_valido()))

    assert resultado.ruta.parent == tmp_path


# ── Traducción de errores del ETL ────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    ("excepcion", "codigo"),
    [
        (ValueError("layout"), CodigoErrorIngesta.HOJA_ILEGIBLE),
        (KeyError("columna"), CodigoErrorIngesta.HOJA_ILEGIBLE),
        (OSError("disco"), CodigoErrorIngesta.ARCHIVO_INVALIDO),
        (RuntimeError("otra cosa"), CodigoErrorIngesta.ERROR_INTERNO),
    ],
)
def test_cada_fallo_recibe_su_codigo(
    excepcion: Exception, codigo: CodigoErrorIngesta
) -> None:
    """G10: el frontend tiene que poder distinguir 'archivo corrupto' de 'BD caída',
    porque la acción del usuario es distinta en cada caso."""
    assert _codigo_de(excepcion) == codigo


@pytest.mark.unit
def test_un_fallo_de_base_de_datos_se_marca_como_tal() -> None:
    from sqlalchemy.exc import OperationalError

    excepcion = OperationalError("SELECT 1", {}, Exception("caída"))

    assert _codigo_de(excepcion) == CodigoErrorIngesta.BD_NO_DISPONIBLE


# ── El evento final: la única promesa fiable (G2) ────────────────────────────


@pytest.mark.unit
def test_el_evento_final_confirma_cuando_hubo_commit() -> None:
    estado = _EstadoDelTrabajo()
    estado.resultado = ResultadoIngesta(
        archivo="r.xlsm", reporte_id=1, tipo_archivo="STD", tiene_raw=False
    )

    final = _evento_final(estado)

    assert final.estado == "confirmado"
    assert final.resultado is not None
    assert final.code is None


@pytest.mark.unit
def test_el_evento_final_avisa_de_que_no_se_guardo_nada() -> None:
    """Lo importante no es que falló: es que las hojas vistas en verde se revirtieron."""
    estado = _EstadoDelTrabajo()
    estado.error = ValueError("la hoja 30 cambió")
    estado.hoja_del_error = "PROGRAMA"

    final = _evento_final(estado)

    assert final.estado == "revertido"
    assert final.hoja == "PROGRAMA"
    assert final.code == CodigoErrorIngesta.HOJA_ILEGIBLE
    assert "no se guardó ningún dato" in (final.detalle or "")
    assert final.resultado is None


@pytest.mark.unit
def test_un_final_sin_resultado_ni_error_tambien_se_reporta_como_revertido() -> None:
    """Nunca se afirma que hubo commit sin tener el resultado que lo demuestra."""
    final = _evento_final(_EstadoDelTrabajo())

    assert final.estado == "revertido"
