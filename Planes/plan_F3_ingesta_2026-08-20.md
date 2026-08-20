# Plan F3 — Ingesta (ETL de .xlsm, 17 extractores + progreso en vivo)

> Plan v2 auditado contra el código real del origen Y contra los pipelines del destino
> (2026-08-20). Formato según CLAUDE.md §0. Para el executor: seguir el **Orden de
> ejecución**, un artefacto por turno, verificación al cerrar cada bloque.

---

## 0. Hallazgos de la auditoría — LEER PRIMERO

F3 es la primera fase que **ESCRIBE** en PostgreSQL (F1 y F2 solo leen). Eso cambia el
perfil de riesgo por completo: un bug aquí no devuelve datos equivocados, los **destruye**.

| # | Hallazgo | Evidencia (origen) | Consecuencia | Acción en el plan |
|---|---|---|---|---|
| **G1** | **F3 escribe en la BD.** Toda fase anterior era de lectura. | `ingerir_archivo` hace UPSERT/DELETE+INSERT en 14 tablas de `core.*` y 4 de `bronze.*` | Un bug corrompe datos reales de producción. Un `DELETE WHERE reporte_id` mal parametrizado borra un reporte entero | **DA-1 bloqueante**: decidir contra qué BD se desarrolla. NUNCA desarrollar contra el 139 de producción |
| **G2** | **El SSE miente al frontend.** Toda la ingesta va en UNA transacción; los eventos `estado:"ok"` por hoja ya se emitieron cuando un fallo posterior hace ROLLBACK de todo. | `services.py:1734` abre `engine.begin()` y cierra en `:1852`; los `_emit("ok")` están dentro | El usuario ve 30 hojas en verde y luego un error, sin saber que **nada** se guardó. `ingesta_log` también se revierte: no queda rastro en BD | Emitir `"ok"` como **"procesada, pendiente de confirmar"** y un evento final que confirme el commit. Ver §5.3 |
| **G3** | **SSE artesanal sin heartbeat ni timeout.** `queue.Queue.get()` sin timeout, sin `event:`/`id:`/`retry:`, sin keep-alive. | `api.py:124-152`, `StreamingResponse` con generador síncrono | Si el hilo worker muere sin llegar al `finally`, el generador **cuelga para siempre**. Cualquier proxy con `proxy_read_timeout` corta durante `BDP_datos_mes` (minutos sin emitir) | Usar `sse-starlette` (no está en el destino, hay que añadirla) + heartbeat + timeout en la espera |
| **G4** | **Cero control de concurrencia.** No hay lock, semáforo ni cola. | Auditoría §7: `_engine` global sin lock; `DimCache` por invocación; nada más | Dos uploads simultáneos → **deadlock** en las `dim_*` (UPSERT en distinto orden) o bloqueo de minutos en `config_reporte`. Dos `.xlsm` de 125 MB en RAM a la vez | `pg_advisory_lock` por `fecha_reporte` (o cola con worker único). **No es opcional** si hay más de un usuario |
| **G5** | **Los extractores fallan en silencio.** Si no encuentran su ancla devuelven `{"rows": [], "tablas": DECLARED}` — 0 filas, sin error. | `_programa_extract` usa filas 6-312 y col 87 hard-codeadas; `_dpp_extract` filas 13-22 literales | Un cambio de layout del `.xlsm` produce una ingesta "exitosa" con tablas vacías. **Nadie se entera** | Emitir un evento `estado:"vacia"` distinguible de `"ok"`, y un resumen final que liste las tablas que salieron en 0 |
| **G6** | **`services.py` = 1.940 líneas** con 17 extractores + 10 loaders + orquestador + jobs. Sin `repositories.py` ni `models.py`. | Inventario §1 | Portarlo tal cual viola la arquitectura del destino (ADR-001, capas api/services/repositories). Refactorizarlo entero de golpe es inasumible | **DA-2**: separar por capas pero **un extractor por archivo NO** — ver §5.1 la estructura propuesta |
| **G7** | **El DDL requiere sus migraciones.** `fact_tabla_hoja.fecha` nace `NOT NULL` y la migración 004 lo hace NULLable — las tablas matriciales van con `fecha=NULL`. | `db/ddl_v2_postgres.sql` (648 líneas) + `db/migrations/001..010` | Portar solo el DDL base hace reventar la ingesta de toda tabla matricial | Verificar el esquema real del destino ANTES de escribir código (prerequisito P3) |
| **G8** | **Rendimiento: `executemany` + `ON CONFLICT` sobre ~315.000 filas** (`BDP_datos_mes`), en chunks de 10.000. Sin `COPY`. | `services.py:28` `CHUNK=10_000`; `load_fact_mes` | Es el cuello de botella real (minutos). Es también lo que obliga al heartbeat de G3 | **Fuera de alcance de F3**: portar la estrategia tal cual. Optimizar a `COPY` cambia la semántica de los eventos `avance`. Anotar como deuda |
| **G9** | **Los tests del origen son inservibles**: 34 líneas en total, y el único test sustantivo apunta a `c:\Users\user\Documents\...`, ruta que no existe → siempre `skipped`. Ningún extractor tiene test. | `tests/test_ingesta_api.py` (23 líneas), `test_transforms.py` (11) | No hay red de seguridad heredada. La suite de F3 se escribe **desde cero** | Tests con `.xlsm` de muestra reales (existen en `Rep_Prod/Doc_Desing/`). Ver §5.4 |
| **G10** | **No hay taxonomía de errores.** `except Exception as e: box["error"] = str(e)` es todo el manejo. El evento `hoja` solo tiene estados `"procesando"` y `"ok"` — **no existe `"error"`**. | `api.py:139`, `services.py:_emit` | El frontend no puede distinguir "archivo corrupto" de "Postgres caído" | Definir códigos de error de dominio (usa el campo `code` del contrato, C12/DT-4) |
| **G11** | **Validación de subida incompleta**: no valida tamaño máximo, ni MIME real, ni que el zip sea OOXML válido. `config_reporte.hash_archivo` existe en el DDL pero **nunca se escribe**. | `api.py:83-105` | Un archivo de 2 GB o un `.exe` renombrado llegan al ETL. Sin hash no hay deduplicación por contenido | Añadir límite de tamaño (no existe config de upload en el destino) + validar el zip antes de procesar |
| **G12** | **Destino: falta `sse-starlette`** y no hay ninguna configuración de subida de archivos. `openpyxl` y `python-multipart` **sí** están. | `pyproject.toml` del destino | Hay que añadir dependencia y settings nuevos | Bloque 0 del orden de ejecución |
| **G13** | **`get_settings()` del origen no tiene cache** — relee el `.env` del disco en cada llamada. | `core/config.py:77` del origen | No se porta: el destino ya usa `@lru_cache` (L3). Mencionado para que el executor **no copie ese patrón** | — |

**Cerradas antes de F3** (no repetir): DT-5, DT-6 y la ausencia de `pnpm build` en CI se
corrigieron el 2026-08-20. El CI está verde. La infraestructura de test sin Postgres
(`app.dependency_overrides[get_prod_db]` + `tests/fakes/prod_db_falsa.py`) ya existe de F1
y **se reutiliza**, no se reinventa.

---

## 1. Contexto

F3 porta la pestaña **Ingesta**: subir un archivo `.xlsm` de reporte diario de producción,
extraer ~74 tablas lógicas de sus hojas y volcarlas a PostgreSQL, mostrando el progreso en
vivo.

**Origen** (`12112025_prodIA/INGESTA/Rep_Prod/backend/app/features/ingesta/`) — **2.153
líneas** medidas (el CLAUDE.md §6 dice 2.195; la cifra correcta es 2.153):

| Archivo | Líneas | Contenido |
|---|---:|---|
| `services.py` | 1.940 | 17 extractores + 10 loaders + orquestador + jobs |
| `api.py` | 152 | 8 endpoints (incluye el SSE) |
| `schemas.py` | 38 | 6 modelos Pydantic |
| `transforms.py` | 43 | Constantes `BZ_DIA`/`BZ_MES`/`BZ_PRG` + normalizadores |
| `detector.py` | 22 | NEW vs STD leyendo `xl/workbook.xml` del zip |

**Acoplados fuera de la carpeta** (hay que portar o reemplazar): `shared/utils.py`
(`NOISE`, `s()`, `num()`, `to_date()` — usados en **cada celda**), `core/db.py`,
`core/config.py`.

**Qué hace el ETL, en una línea:** `openpyxl` en modo `read_only`+`data_only` → 17
extractores que devuelven filas `{tabla_idx, tabla_label, dims, fecha, valor}` → `bronze.*`
(aterrizaje crudo) → `core.*` (14 tablas: dims, facts y el genérico `fact_tabla_hoja`).

**Bifurcación NEW/STD**: si el libro trae `{BDP_datos_dia, BDP_datos_mes, BDP_Programa}`
es **NEW** (`nivel_detalle='FULL'`); si no, **STD** (`'SIN_ECP'`) y se saltan los facts ECP.

---

## 2. Objetivo

Entregar una sección **Ingesta** en ProdIA V02 que:

1. Permita **subir** un `.xlsm` validado (extensión, tamaño, fecha `YYYYMMDD` en el nombre,
   zip OOXML íntegro).
2. Avise si esa fecha **ya fue ingerida** antes de procesar (`check_existing`).
3. Ejecute el ETL portado, con los **17 extractores** produciendo las mismas ~74 tablas.
4. Muestre **progreso en vivo** por hoja, con un estado final que diga la verdad sobre si
   los datos quedaron guardados (corrige G2).
5. Sea **idempotente**: reingerir el mismo archivo dos veces deja la BD igual.
6. Sea **seguro ante concurrencia**: dos subidas simultáneas no se corrompen ni bloquean
   indefinidamente (corrige G4).

Criterio de aceptación: lint + mypy strict + tests ≥ umbral, **paridad verificada** contra
las anclas conocidas (`DATOS_MES` = 7.776 filas, `TD_datos_dia` = 5.209 filas, ver §8) y
**verificación humana** subiendo un `.xlsm` real (R3).

---

## 3. Prerequisitos verificables

| # | Prerequisito | Cómo verificar | Estado |
|---|---|---|---|
| P1 | Infraestructura de test sin Postgres | `tests/fakes/prod_db_falsa.py` y el fixture `patch_prod_db` existen (de F1) | ✅ Existe — reutilizar |
| P2 | `openpyxl` y `python-multipart` disponibles | `grep openpyxl\|multipart prodia_v02_backend/pyproject.toml` | ✅ Ambos |
| P3 | **Esquema real del destino** | Contra la BD elegida en DA-1: ¿existen `bronze.*` y las 14 `core.*`? ¿`fact_tabla_hoja.fecha` es NULLable (G7)? | ⚠️ **VERIFICAR ANTES DE CODIFICAR** |
| P4 | `.xlsm` de muestra para tests | Existen en `12112025_prodIA/INGESTA/Rep_Prod/Doc_Desing/*.xlsm` | ⚠️ Confirmar que hay al menos uno NEW y uno STD |
| P5 | `sse-starlette` | No está en `pyproject.toml` del destino | ❌ **Añadir en Bloque 0** |
| P6 | Config de subida (ruta destino, tamaño máx.) | No existe nada de upload en `core/config.py` | ❌ **Añadir en Bloque 0** |
| P7 | CI verde | `gh run list --limit 1` | ✅ Verde desde el arreglo de DT-5/DT-6 |

---

## 4. Inventario de archivos

### Backend — nueva feature `ingesta`

```
src/features/ingesta/
├── __init__.py
├── api.py               router: subir, check-existing, progreso SSE, jobs
├── schemas.py           DTOs + eventos SSE tipados + códigos de error (G10)
├── services.py          orquestador `ingerir_archivo` (SOLO el flujo, no los extractores)
├── repositories.py      TODOS los INSERT/UPSERT/DELETE — capa que el origen no tiene (G6)
├── detector.py          NEW vs STD (portado, 22 líneas)
├── transforms.py        BZ_DIA/BZ_MES/BZ_PRG + normalizadores (portado, 43 líneas)
├── celdas.py            NOISE, s(), num(), to_date() — de `shared/utils.py` del origen
└── extractores/
    ├── __init__.py      el REGISTRY (lista de (regex, función)) y el despachador
    ├── comunes.py       _grid(), _p50_contig_months(), helpers compartidos
    ├── p50.py           extractores 1 y 4
    ├── filiales.py      extractores 2, 10, 12
    ├── reportes.py      extractores 3, 5, 6, 7, 9, 11
    ├── mesano.py        extractor 8 (13 tablas)
    └── raw.py           extractores 13-17 (TD_datos_dia, DATOS_MES, BDP_*)
```

> **Por qué agrupar y no un archivo por extractor**: 17 archivos de ~60 líneas fragmentan
> helpers compartidos (`_grid`, `_p50_contig_months`) y hacen ilegible el registry. El
> agrupamiento es por **familia de hoja**, que es como el negocio las nombra.

**Modificar:** `src/main.py` (router + tag), `src/core/config.py` (settings de subida),
`pyproject.toml` (`sse-starlette`).

**Migración Alembic:** si P3 revela que el esquema del destino no tiene `bronze.*` /
`core.*` completos, F3 necesita su propia migración. **Ojo**: `db_auth` (SQLite) y
`db_prod` (PostgreSQL) usan mecanismos distintos — Alembic hoy solo gestiona `db_auth`.

### Frontend — nueva feature `ingesta`

```
src/features/ingesta/
├── pages/IngestaPage.tsx
├── components/
│   ├── ZonaSubida/          drag & drop + validación en cliente
│   ├── AvisoReingesta/      "esta fecha ya fue ingerida" (check_existing)
│   └── ProgresoIngesta/     lista de hojas con su estado, en vivo
├── hooks/
│   ├── useCheckExisting.ts
│   └── useSubidaConProgreso.ts   EventSource / fetch-stream
├── services/ingestaService.ts
├── mappers/ingestaMappers.ts
└── types/ingestaTypes.ts
```

**Modificar:** `src/app/router.tsx` (ruta `/ingesta`).

---

## 5. Especificación

### 5.1 Portado de los extractores — regla de oro

**El código de cada extractor se porta LITERALMENTE.** Son posiciones de celda pactadas con
un `.xlsm` real; "mejorarlas" es inventar. Solo cambian tres cosas:

1. **Tipos** (mypy strict): firma `(ws: Worksheet) -> ResultadoExtractor`.
2. **Ubicación**: del monolito al archivo de su familia.
3. **Imports**: `celdas.py` en vez de `app.shared.utils`.

Se preservan íntegros los comentarios que explican el porqué (p. ej. la nota de auditoría
A4 en `_p50_contig_months` sobre no cruzar a la tabla VR/GER, o el truncado de Excel a 31
caracteres que obliga a que las regex matcheen por prefijo).

**El contrato dual se unifica**: el origen tiene extractores que devuelven `list[dict]` y
otros que devuelven `{"rows": [...], "tablas": DECLARED}`, y el despachador hace
`isinstance(res, dict)`. En el destino **todos** devuelven la forma extendida (un
`TypedDict`/dataclass), y los dos simples (`p50`, `filiales`) se adaptan. Con mypy strict,
el `isinstance` deja de ser necesario.

### 5.2 Capa de repositorio (la que el origen no tiene)

Todo `INSERT`/`UPSERT`/`DELETE` baja a `repositories.py`, con el SQL **idéntico** al origen.
Es donde vive la doctrina de idempotencia, que **se conserva tal cual**:

| Patrón | Tablas |
|---|---|
| `UPSERT ON CONFLICT` (hay UNIQUE natural) | `config_reporte`, `dim_*`, `fact_produccion_dia_ecp`, `fact_produccion_mes_ecp`, `fact_programa_ecp`, `fact_produccion_diaria`, `fact_plan_mensual`, `fact_promedio_validado` |
| `DELETE WHERE reporte_id` + `INSERT` | `bronze.*`, `fact_comentarios_produccion`, `fact_tabla_hoja` |

⚠️ **Los `DELETE` son la operación más peligrosa de F3.** Cada uno lleva su `WHERE
reporte_id=:r` (y `AND hoja=:h` donde aplica). Un test debe verificar que **nunca** se
ejecuta un DELETE sin parámetros de acotación.

`fact_tabla_hoja` conserva su dedup previo en Python (`by_key[(tabla_idx, dims_json,
fecha)] = fila`, **last-wins**) porque esa tabla no tiene UNIQUE.

### 5.3 Progreso en vivo — corregir la mentira (G2)

El problema: los eventos `ok` se emiten dentro de la transacción; si algo falla después,
todo se revierte y el usuario ya vio verde.

**Diseño para F3:**

- Los eventos por hoja pasan a `estado: "procesada"` (no `"ok"`) — significa "leída e
  insertada, **pendiente de confirmación**".
- Se añade `estado: "vacia"` cuando un extractor devuelve 0 filas (corrige G5, el fallo
  silencioso), y `estado: "error"` que hoy no existe (G10).
- El evento final `fin` distingue explícitamente:
  - `{"tipo":"fin","estado":"confirmado","resultado":{...}}` — commit hecho, los datos
    están en la BD.
  - `{"tipo":"fin","estado":"revertido","code":"...","detalle":"..."}` — rollback, **nada**
    se guardó, y dice en qué hoja falló.
- El resumen final incluye la lista de tablas que quedaron en 0 filas, para que un cambio
  de layout sea visible (G5).

**Transporte:** `sse-starlette` con `EventSourceResponse`, heartbeat de ~15 s (G3) y
timeout en la espera de la cola. El generador debe detectar la **desconexión del cliente**
y cancelar, en vez de dejar el hilo trabajando en el vacío como hace el origen.

> **Nota sobre compatibilidad**: el origen es consumido por un proxy Flask que reenvía a
> SocketIO. ProdIA V02 es autónomo (§1 del CLAUDE.md) y su frontend consume el SSE
> directamente, así que **no hay que preservar el formato byte a byte**. Si en F6 se
> despliega en paralelo, el proxy viejo seguirá apuntando al backend viejo.

### 5.4 Concurrencia (G4)

Antes de abrir la transacción, tomar `pg_advisory_xact_lock(hashtext(:fecha_reporte))`. Dos
ingestas de **fechas distintas** corren en paralelo; dos de la **misma fecha** se serializan
sin deadlock. El lock se libera solo al terminar la transacción (`_xact_`).

Además: límite de subidas concurrentes (semáforo) para no tener dos `.xlsm` de 125 MB en
RAM a la vez.

### 5.5 Validación de subida (G11)

En orden, antes de tocar el ETL: extensión → tamaño máximo (nuevo setting) → nombre con
`YYYYMMDD` (422, mensaje del origen) → zip OOXML válido y con hojas legibles → hash SHA-256
del contenido, que **sí se escribe** en `config_reporte.hash_archivo` (el origen lo dejó
sin usar). Con el hash, `check_existing` puede distinguir "misma fecha, mismo archivo" de
"misma fecha, archivo distinto".

### 5.6 Tests (G9 — se escriben desde cero)

| Nivel | Qué cubre |
|---|---|
| Unitario, sin BD | `celdas.py` (`NOISE`, `s`, `num`, `to_date`), `detector` (NEW/STD), `transforms` |
| Unitario, con `.xlsm` de muestra | **Cada uno de los 17 extractores**: número de tablas declaradas, filas > 0, forma de `dims`. Es lo que evita G5 |
| Repositorio | Que cada DELETE lleve su `WHERE reporte_id`; que los UPSERT tengan el `ON CONFLICT` correcto |
| Servicio | Orquestación con repositorio falso: orden de loaders, bifurcación NEW/STD, eventos emitidos |
| SSE | Formato y **orden** de eventos; que `fin` diga `revertido` cuando el ETL lanza |
| Idempotencia | Ingerir dos veces el mismo archivo produce el mismo estado |

Usar el patrón de F1: doble de sesión con `app.dependency_overrides`, **cero Postgres en CI**.

---

## 6. Orden de ejecución

**Bloque 0 — Prerequisitos y andamiaje**
1. Resolver **DA-1** (¿contra qué BD se desarrolla?) — bloqueante, ver §10.
2. Verificar P3 contra esa BD: existencia de `bronze.*` y `core.*`, y que
   `fact_tabla_hoja.fecha` sea NULLable (G7).
3. Confirmar P4: `.xlsm` de muestra NEW y STD disponibles para los tests.
4. Añadir `sse-starlette` a `pyproject.toml` + `uv sync`.
5. Añadir settings de subida a `core/config.py` (directorio destino, tamaño máximo).

**Bloque 1 — Base del ETL (sin BD todavía)**
6. `celdas.py` (portar `shared/utils.py`) + sus tests.
7. `detector.py` y `transforms.py` (portados) + tests NEW/STD.
8. `schemas.py`: DTOs, eventos SSE tipados y códigos de error (G10).
9. **Verificar**: `ruff`, `black`, `mypy src`, `pytest --cov=src --cov-fail-under=75`.

**Bloque 2 — Los 17 extractores** (el grueso; varios turnos)
10. `extractores/comunes.py` (helpers `_grid`, `_p50_contig_months`, …).
11. `extractores/{p50,filiales,reportes,mesano,raw}.py` — portado literal + tipos.
12. `extractores/__init__.py`: el registry y el despachador (contrato unificado, §5.1).
13. **Un test por extractor** contra el `.xlsm` de muestra (G5/G9).
14. **Verificar** con los comandos de CI.

**Bloque 3 — Repositorio y orquestador**
15. `repositories.py`: SQL idéntico, con el test que prohíbe DELETE sin `WHERE reporte_id`.
16. `services.py`: `ingerir_archivo` — flujo, bifurcación NEW/STD, `pg_advisory_xact_lock`.
17. Tests de servicio con repositorio falso (orden, bifurcación, eventos).
18. **Verificar**.

**Bloque 4 — API y SSE**
19. `api.py`: subir, `check-existing`, progreso SSE, jobs. Validación completa (§5.5).
20. Registrar router en `main.py` + tag.
21. Tests de contrato: 401 sin sesión, 400/422 de validación, formato y orden de eventos,
    `fin: revertido` ante fallo.
22. **Verificar** + `export_openapi.py` + `pnpm gen:types`.

**Bloque 5 — Frontend**
23. `types/` + `mappers/` + `services/`.
24. `hooks/useSubidaConProgreso.ts` (consumo del SSE, con reconexión y cancelación).
25. Componentes: `ZonaSubida`, `AvisoReingesta`, `ProgresoIngesta`.
26. `IngestaPage.tsx` + ruta `/ingesta`.
27. Tests (umbral 80 %×4).
28. **Verificar**: `pnpm lint`, `typecheck`, `build`, `test:front`.

**Bloque 6 — Paridad y verificación humana (R3)**
29. Ingerir un `.xlsm` real y comparar contra las anclas: `DATOS_MES` = 7.776 filas,
    `TD_datos_dia` = 5.209 filas.
30. Reingerir el mismo archivo: la BD debe quedar idéntica (idempotencia).
31. Provocar un fallo a mitad y comprobar que `fin` dice `revertido` y que **nada** quedó
    guardado (la corrección de G2).
32. El **usuario** marca F3 como verificada.

---

## 7. Reglas no negociables

- **Los extractores se portan literalmente.** Son posiciones pactadas con un Excel real.
- **La doctrina de idempotencia se conserva** (UPSERT vs DELETE+INSERT por tabla).
- **Ningún DELETE sin `WHERE reporte_id`.** Con test que lo verifique.
- **Nunca desarrollar contra la BD de producción** (G1/DA-1).
- **Cero imports cross-feature** (ADR-001).
- **Los tests no tocan Postgres** — reutilizar el doble de F1.
- **mypy strict** sobre todo el código nuevo (H3 de F1 sigue vigente).
- **R3**: build verde ≠ verificada. La verificación la hace el usuario subiendo un archivo.
- **R1**: no tocar configuración de pnpm sin aprobación.

---

## 8. Validaciones

```powershell
# backend (comandos EXACTOS de CI — no variantes)
uv run ruff check . ; uv run black --check . ; uv run mypy src
uv run pytest --cov=src --cov-fail-under=75

# tipos
uv run python scripts/export_openapi.py ; cd ../prodia_v02_frontend ; pnpm gen:types

# frontend
pnpm lint ; pnpm typecheck ; pnpm build ; cd .. ; pnpm test:front
```

Anclas de paridad: `DATOS_MES` = **7.776** filas · `TD_datos_dia` = **5.209** filas
(CLAUDE.md §6). Si no cuadran, el portado tiene un bug — no ajustar el ancla.

---

## 9. Fuera de alcance

- **Optimizar el ETL a `COPY`** (G8). Se porta `executemany`+chunks tal cual; cambiar la
  estrategia altera los eventos `avance`. Anotar como deuda técnica.
- **Reescribir los extractores** o hacerlos tolerantes a cambios de layout. F3 los porta;
  hacerlos robustos es otro trabajo.
- **Cola de trabajos con worker dedicado**. F3 usa `BackgroundTasks` + advisory lock. Si
  hace falta un worker real (Celery/RQ), es una fase aparte.
- **Menú de navegación** entre secciones (sigue diferido desde F1).
- **`reingesta_hojas_nuevas.py`** (183 líneas, re-ingesta targeteada de 2 hojas): duplica
  lógica de `load_tablas_hoja`. No se porta; si hace falta, se resuelve reingiriendo.
- **Deduplicación por hash entre reportes distintos**: F3 escribe el hash y lo usa para
  avisar, no para bloquear.

---

## 10. Decisiones abiertas — resolver ANTES de codificar

### Cerradas (2026-08-20)

| # | Decisión | Consecuencia para el executor |
|---|---|---|
| **DA-1** | ✅ **Postgres LOCAL con un dump restaurado.** F3 NO se desarrolla contra el 139. | El Bloque 0 incluye montar el Postgres local y restaurar el dump. `PROD_DATABASE_URL` apunta a `localhost` durante F3 — **el `.env` actual apunta al 139 y hay que cambiarlo**. Los dumps disponibles se vieron en `C:\APLICACIONES\ProdIA\ProdIA_V02\` (`dump-robustez_v02-*.zip`); hace falta uno de `daily_report_prod` |
| **DA-3** | ✅ **`pg_advisory_xact_lock` incluido en F3** (§5.4). | El servicio toma el lock por `fecha_reporte` antes de abrir la transacción. Va con su test |

### Abiertas (no bloquean el arranque)

| # | Pregunta | Cuándo decidir |
|---|---|---|
| **DA-2** | ¿Se acepta la estructura de `extractores/` por familias (§4)? | Al empezar el Bloque 2 |
| **DA-4** | ¿La subida es siempre asíncrona con SSE, o se mantienen también los endpoints síncronos (`/archivo`, `/jobs`)? | Al empezar el Bloque 4 |
| **DA-5** | ¿Dónde se guardan los `.xlsm` subidos y se conservan tras ingerir? | En el Bloque 0, al crear el setting de P6 |
