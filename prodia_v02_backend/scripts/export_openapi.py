"""Vuelca el esquema OpenAPI de la app a un archivo JSON, SIN levantar un
servidor HTTP (N3/H5 — corrección sobre Robustez V02, cuyo `gen:types`
exige el backend corriendo en :6024 y por eso es un hook de pre-commit
frágil). `app.openapi()` construye el esquema en memoria; solo hace falta
poder IMPORTAR `src.main`, no tener el proceso escuchando en un puerto.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.main import app

OUT = Path(__file__).resolve().parent.parent / "openapi.json"


def main() -> None:
    schema = app.openapi()
    OUT.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OpenAPI exportado a {OUT} ({len(schema.get('paths', {}))} rutas)")


if __name__ == "__main__":
    main()
