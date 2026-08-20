"""Prueba de humo de los 17 extractores contra un .xlsm REAL.

Para qué sirve: el Bloque 2 de F3 no tiene interfaz todavía —los extractores leen el
Excel y devuelven filas en memoria, sin API ni pantalla—, así que esta es la forma de ver
con datos propios que el portado funciona antes de que exista la página de Ingesta.

Qué muestra: por cada hoja modelada, cuántas tablas declara, cuántas filas produjo cada
una y cuáles salieron VACÍAS. Las vacías son la señal que importa (hallazgo G5): un
extractor cuyo layout cambió no da error, simplemente devuelve cero filas, y en el sistema
viejo eso pasaba inadvertido.

No escribe nada: solo lee el archivo. La BD no se toca en este bloque.

Uso:
    cd prodia_v02_backend
    uv run python scripts/humo_extractores.py "<ruta al .xlsm>"
    uv run python scripts/humo_extractores.py          # usa el NEW de Doc_Desing
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from openpyxl import load_workbook

from src.features.ingesta.detector import nombres_de_hojas, tiene_raw
from src.features.ingesta.extractores import extractores_aplicables

MUESTRAS_POR_DEFECTO = Path(
    r"C:\APLICACIONES\ProdIA\12112025_prodIA\12112025_prodIA\INGESTA\Rep_Prod\Doc_Desing"
)


def _resolver_archivo() -> Path | None:
    if len(sys.argv) > 1:
        ruta = Path(sys.argv[1])
        return ruta if ruta.exists() else None
    candidatos = sorted(MUESTRAS_POR_DEFECTO.glob("*New*.xlsm"))
    return candidatos[0] if candidatos else None


def main() -> int:
    archivo = _resolver_archivo()
    if archivo is None:
        print("No se encontró ningún .xlsm.")
        print(f"Pasa la ruta como argumento, o deja uno en {MUESTRAS_POR_DEFECTO}")
        return 1

    mb = archivo.stat().st_size // 1048576
    hojas = nombres_de_hojas(archivo)
    tipo = "NEW" if tiene_raw(hojas) else "STD"

    print("=" * 82)
    print(f"Archivo : {archivo.name}")
    print(f"Tamaño  : {mb} MB    Tipo: {tipo}    Hojas en el libro: {len(hojas)}")
    print("=" * 82)

    aplicables = extractores_aplicables(sorted(hojas))
    print(f"Hojas modeladas que este archivo trae: {len(aplicables)} de 17")
    if tipo == "STD":
        print("  (un reporte STD no trae las tres hojas BDP_*: es su naturaleza)")
    print()

    inicio_total = time.perf_counter()
    libro = load_workbook(archivo, read_only=True, data_only=True, keep_links=False)

    print(f"  {'HOJA':<34}{'TABLAS':>7}{'FILAS':>10}{'VACÍAS':>8}{'SEG':>7}")
    print(f"  {'-' * 34}{'-' * 7:>7}{'-' * 10:>10}{'-' * 8:>8}{'-' * 7:>7}")

    total_filas = 0
    total_tablas = 0
    hojas_sin_filas: list[str] = []
    tablas_vacias: list[str] = []
    fallos: list[str] = []

    for nombre_hoja, extractor in aplicables:
        inicio = time.perf_counter()
        try:
            resultado = extractor(libro[nombre_hoja])
        except Exception as exc:  # noqa: BLE001 — el objetivo es reportar, no propagar
            print(f"  {nombre_hoja[:34]:<34}  *** {type(exc).__name__} ***")
            print(f"      -> {str(exc)[:200]}")
            fallos.append(f"{nombre_hoja}: {type(exc).__name__}: {str(exc)[:120]}")
            continue
        segundos = time.perf_counter() - inicio

        vacias = resultado.tablas_vacias()
        total_filas += len(resultado.filas)
        total_tablas += len(resultado.tablas_declaradas)
        if not resultado.filas:
            hojas_sin_filas.append(nombre_hoja)
        for _, etiqueta in vacias:
            tablas_vacias.append(f"{nombre_hoja} → {etiqueta}")

        print(
            f"  {nombre_hoja[:34]:<34}{len(resultado.tablas_declaradas):>7}"
            f"{len(resultado.filas):>10,}{len(vacias):>8}{segundos:>7.2f}"
        )

    libro.close()
    segundos_total = time.perf_counter() - inicio_total

    print()
    print("=" * 82)
    print("RESUMEN")
    print("=" * 82)
    print(f"  Hojas procesadas   : {len(aplicables)}")
    print(f"  Tablas declaradas  : {total_tablas}")
    print(f"  Filas extraídas    : {total_filas:,}")
    print(f"  Tiempo total       : {segundos_total:.1f} s")

    if fallos:
        print()
        print(f"  FALLOS ({len(fallos)}) — copia esto y pásalo para corregirlo:")
        for fallo in fallos:
            print(f"    - {fallo}")

    if hojas_sin_filas:
        print()
        print(f"  HOJAS SIN NINGUNA FILA ({len(hojas_sin_filas)}):")
        for hoja in hojas_sin_filas:
            print(f"    - {hoja}")
        print("    Puede ser normal (la hoja viene vacía en este archivo) o indicar")
        print("    que su layout cambió y el extractor ya no la reconoce.")

    if tablas_vacias:
        print()
        print(f"  TABLAS DECLARADAS SIN FILAS ({len(tablas_vacias)}):")
        for tabla in tablas_vacias[:25]:
            print(f"    - {tabla}")
        if len(tablas_vacias) > 25:
            print(f"    ... y {len(tablas_vacias) - 25} más")
        print("    Se declaran a propósito para que el visor las liste (G5): una tabla")
        print("    vacía debe verse, no desaparecer en silencio.")

    print()
    if fallos:
        print("  Resultado: HAY FALLOS que corregir.")
        return 1
    print("  Resultado: los 17 extractores corrieron sin reventar.")
    print("  NOTA: esto verifica que extraen y que la forma es coherente. Que las")
    print(
        "  CIFRAS sean las correctas se comprueba comparando contra el sistema viejo."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
