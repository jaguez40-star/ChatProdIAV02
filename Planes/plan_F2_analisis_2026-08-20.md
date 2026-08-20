# Plan F2 — Análisis (ECP + Filiales + EBITDA + Diferidas + Mantenimientos)

> **Plan v2 — auditado contra el código real Y contra los pipelines configurados** el
> **2026-08-20** (Modo Planner, CLAUDE.md §0: Mapeo → Auditoría → Diagnóstico antes de escribir).
> La v1 se auditó contra el código de origen/destino; la **v2 añade la auditoría de pipelines**
> (`ci.yml`, `.pre-commit-config.yaml`, `pyproject.toml`, `vitest.config.ts`, `vite.config.ts`,
> `.gitignore`, `conftest.py`) **ejecutando sondas reales**, no leyendo configuración.
>
> Los hallazgos marcados 🔬 se **verificaron ejecutando código** en esta máquina hoy. Los marcados
> 🔄 **invalidan o corrigen algo que decía la v1**.
>
> **Para el executor:** seguir §6 bloque por bloque, **un artefacto por turno**, con la verificación
> del bloque en verde antes de continuar. El prompt de arranque está en §13.

---

## 0. Hallazgos de la auditoría — LEER PRIMERO

### 0.1 Qué cambió en el repo desde la v1 de este plan (mismo día)

🔄 **F1 backend se cerró y commiteó** (`3dda27c feat(F1): feature 'tablas' del backend`). Esto
**invalida el H1 de la v1** ("F1 a medio ejecutar"). El estado real ahora:

| Pieza | Estado | Qué significa para F2 |
|---|---|---|
| `src/features/tablas/{__init__,api,schemas,services,repositories}.py` | ✅ commiteado | **Existe el patrón canónico de feature V02.** F2 lo copia, no lo inventa (§5.0) |
| `src/main.py` | ✅ monta `tablas_router`, `db_prod` documentada como crítica-para-la-feature **sin fail-fast** | F2 añade 4 routers siguiendo el mismo bloque |
| `tests/conftest.py:161-196` → `patch_prod_db` | ✅ existe (usa `app.dependency_overrides`) | **La v1 pedía crearlo. Ya está.** F2 solo añade los hermanos (`ops`, `diferidas`, `llm`) |
| `src/core/exceptions.py` → `database_exception_handler` | ⚠️ **en vuelo, sin commitear** | Convierte cualquier `SQLAlchemyError` en **503 + `code="DB_UNAVAILABLE"`** de forma global. F2 hereda ese 503 gratis (§5.0) |
| `src/features/control/` (frontend F1) | ❌ no existe | F1 **frontend sigue pendiente**. Ver AP-1 |
| `.github/workflows/ci.yml` | ❌ **sin tocar desde el commit inicial** (`git log -1 -- ci.yml` → `83cab78`) | **DT-5 y DT-6 siguen abiertas.** F1 no ejecutó su Bloque 4 |

### 0.2 🔬 Hallazgos de pipeline (nuevos en la v2) — cada uno con su sonda ejecutada

| # | Hallazgo | Evidencia ejecutada hoy | Consecuencia si se ignora | Acción |
|---|---|---|---|---|
| **AP-1** | **F1 frontend está pendiente y hay 4 archivos sin commitear.** `git status` → `M exceptions.py`, `M tablas/schemas.py`, `M test_tablas_flow.py`, `M test_tablas_service.py`. | `git log --oneline -5`, `git status --short` | Empezar F2 encima de un working tree sucio mezcla dos fases en el mismo diff; el hook `gen-types-check` recalcula `api.d.ts` con features a medias. | **Bloque 0 paso 1:** commitear o revertir lo en vuelo. F2 arranca con `git status` limpio. F1-frontend puede ir en paralelo (no comparte archivos con F2 salvo `router.tsx`). |
| **AP-2** | 🔴 **El pre-commit ejecuta `gen:types` en CADA cambio de `src/(main\|features)/*.py`**, y `gen:types` **importa `src.main`**. | `.pre-commit-config.yaml` hook `gen-types-check`; `scripts/export_openapi.py:13` (`from src.main import app`) | Si cualquier módulo nuevo hace **I/O al importarse** (construir el índice del catálogo, crear el engine de `ops`, parsear `Eventos_OW.xlsx`), **cada commit intentará conectar al Postgres del 139 o leer 192 MB** → el hook cuelga o falla, en toda máquina y en CI. | **Regla dura nueva (§5.1): CERO I/O en tiempo de import.** Todo lazy, todo detrás de función. Y **toda Settings nueva lleva default** — un campo requerido rompe `gen:types` en cualquier máquina sin esa variable. |
| **AP-3** | 🔬 🔴 **`ruff` con `select=["N"]` rechaza el idiom del origen.** Sonda: 14 líneas de código estilo-origen → **6 errores** (`N806` sobre `E`, `P`, `RD`, `TOP_N`, `CATS` + `I001`). `mypy --strict` sobre la misma sonda → **2 errores** (`no-untyped-def`, `no-untyped-call`). `black --check` → "1 file would be reformatted". | Sonda `src/_sonda_tmp.py` ejecutada y borrada. Ocurrencias reales en el origen: **14 en `analisis/api.py`** (`E`,`P`,`RD`,`I`,`TOP_N`,`CATS`,`PRIOR`,`NIVELES_SQL`) + `ANIOS`,`TOP_G`,`TOP_I`,`TOP` en las rutas Flask. | `uv run ruff check .` y `uv run mypy src` fallan → **CI rojo y pre-commit bloqueado**. El executor descubre esto tras portar 2.600 líneas. | **§5.2 Normalización de estilo obligatoria**, con la tabla de renombres. Se hace **al portar**, no después. `black .` (no `--check`) antes de cada verificación. **Buena noticia:** los 5 archivos de test a portar tienen **0 mayúsculas locales** (medido) — se portan sin fricción. |
| **AP-4** | 🔬 🔴 **Plotly NO renderiza en jsdom: rompe la SUITE, no un test.** `render(<Plot .../>)` → `TypeError: window.URL.createObjectURL is not a function` → **`Failed Suites 1 · Tests: no tests`**. | Sonda `src/_sonda/Sonda.test.tsx` con `react-plotly.js` → FAIL en 17,5 s. | Los 5 gráficos de F2 harían fallar **cada archivo de test que importe su componente**, incluido el de la página que los contiene. `pnpm test:front` rojo. La cobertura ni se calcula. | 🔬 **Fix verificado:** polyfill de `URL.createObjectURL`/`revokeObjectURL` en `tests/setup/vitest.setup.ts` → **`1 passed (142 ms)`**. Va en el **Bloque 0**, antes de escribir un solo gráfico. Los `Not implemented: HTMLCanvasElement.getContext` que quedan son **ruido de jsdom, no fallo**. |
| **AP-5** | 🔬 **Hay DOS Plotly instalados y el import obvio usa el peor.** `plotly.js-dist-min@2.35.3` = **4,3 MB** (el declarado, el que dice CLAUDE.md §2) y `plotly.js@3.7.0` = **10,7 MB**, auto-instalado como *peer* de `react-plotly.js@2.6.0`, que arrastra `mapbox-gl@1.13.3` + `@plotly/mapbox-gl@1.13.4` (**marcado `deprecated` en el propio lock**). `import Plot from 'react-plotly.js'` usa el de 10,7 MB. | `ls node_modules/.pnpm \| grep plotly`; `pnpm-lock.yaml:46,794`; tamaños medidos con `ls -la`. | Bundle inflado con una librería de mapas que ProdIA no usa, y arranque de entorno de test de **17,5 s vs 1,8 s** (medido con ambas variantes). | **§5.3:** usar `createPlotlyComponent(Plotly)` de `react-plotly.js/factory` con `plotly.js-dist-min`. Un único wrapper `shared/components/Grafico/` centraliza el import — **ningún componente importa Plotly directamente**. |
| **AP-6** | 🔬 **Los tipos instalados son de Plotly 3.x y el runtime declarado es 2.35.** `@types/plotly.js@3.0.13`. El idiom v2 `layout={{ title: 'x' }}` **falla `tsc`**: `TS2769 … Type 'string' has no properties in common with type 'Partial<{ text: string; … }>'`. | `pnpm build` sobre la sonda → error TS2769; corregido con `title: { text: 'x' }` compila. | `pnpm build` corre `tsc -b` → **el build falla**, no es solo un aviso del editor. Cada ejemplo de Plotly de internet usa el idiom v2. | **§5.3 regla:** `title` siempre como objeto `{ text }`. El wrapper `Grafico` expone un tipo propio para que el error salga una vez, no cinco. |
| **AP-7** | 🔄 **`openapi.json` está en `.gitignore`.** La v1 decía "commitear `openapi.json` + `api.d.ts`". | `.gitignore` línea `prodia_v02_backend/openapi.json` | Un `git add` forzado ensucia el repo; el executor pierde tiempo buscando por qué no aparece en el diff. | **Solo se commitea `api.d.ts`.** El hook `gen-types-check` valida exactamente eso (`git diff --exit-code … api.d.ts`). |
| **AP-8** | **`.gitignore` cubre `data/*.db` pero NO `*.xlsx`.** | `.gitignore` sección "Datos y secretos" | `Eventos_OW.xlsx` (259 kB) se commitearía por accidente al copiarlo a `prodia_v02_backend/data/`. | **DA-8 (§10).** Recomendación: añadir `prodia_v02_backend/data/*.xlsx` al `.gitignore` y documentar la copia en el despliegue; los tests usan un `.xlsx` sintético de 3 filas. |
| **AP-9** | 🔴 **F1 declara sus endpoints `async def` con SQLAlchemy SÍNCRONA.** | `tablas/api.py:77,96,119,145,166,182,201` | En F1 (consultas rápidas) es tolerable. En F2 es **inaceptable**: un `async def` que hace la llamada bloqueante a Ollama (`urllib`, `timeout=180`) **congela el event loop y con él TODA la app** — login incluido — durante 3 minutos. | **F2 declara sus endpoints `def` (sync)**, que Starlette manda al threadpool. Es una **desviación deliberada del precedente de F1**, documentada en el código. Y es una **mejora que F1 debería adoptar** (§11). |
| **AP-10** | **`database_exception_handler` (en vuelo) ya da el 503 global.** | `git diff src/core/exceptions.py` | Duplicar `try/except SQLAlchemyError` en los 12 endpoints de F2 es ruido… pero **`RuntimeError("OPS_DATABASE_URL no configurada")` NO es un `SQLAlchemyError`** y saldría como **500**. | F2 mantiene el `_error_db()` por endpoint (coherencia con F1) **y** añade el caso "ops no configurada" como 503 explícito. Test de regresión para ambos. |
| **AP-11** | 🔄 **`patch_prod_db` ya existe** (`conftest.py:161-196`), y `test_tablas_flow.py` ya tiene el test que garantiza que la suite **jamás** alcanza el Postgres real. | lectura directa | La v1 planificaba crearlo (su "Bloque 1b"). | F2 **reutiliza** el patrón y añade `patch_ops_db`, `patch_diferidas_db`, `stub_llm`, `eventos_ow_fake` con el mismo estilo documentado. |
| **AP-12** | **`vitest` corre `pool:'forks', singleFork:true` con `--max-old-space-size=8192`.** | `vitest.config.ts` | Todos los archivos comparten proceso: el módulo Plotly se carga **una vez** (bien), pero un `Failed Suite` por Plotly (AP-4) contamina toda la corrida. | Refuerza que AP-4 se arregla en el Bloque 0. La elección de `dist-min` (AP-5) ahorra ~15 s por corrida de CI. |
| **AP-13** | **`ci.yml` sigue roto: no lo tocó nadie.** `cache-dependency-path: prodia_v02_frontend/pnpm-lock.yaml` (archivo inexistente), `pnpm install --frozen-lockfile` en el subdirectorio, `pnpm test -- --coverage` (pnpm se come el `--`), **sin `pnpm build`**. | `git log -1 -- .github/workflows/ci.yml` → `83cab78` (commit inicial) | El job frontend de CI **falla en el paso install**; el umbral de cobertura del 80 % **no se ha evaluado nunca**; y `pnpm build` (el único que atrapa AP-6) no corre. **F2 no se validaría en CI.** | **DA-5.** Corrección propuesta con diff exacto en §11. Requiere aprobación (tocar infraestructura). |

### 0.3 Hallazgos de dominio y portado (v1, vigentes)

| # | Hallazgo | Evidencia | Acción |
|---|---|---|---|
| **H2** | **El origen viola ADR-001**: `analisis/api.py:4` importa `consulta.resolver`, que importa `consulta.normaliza`. | `api.py:4`, `resolver.py:1-3,138-152` | Módulo compartido `src/shared/catalogo_entidades.py` (§5.1). F2 y F4 lo consumen; ninguna feature importa a otra. |
| **H3** | El índice del resolver es **estado global mutable sin lock** (`_INDEX`, `_FUENTE_SETS`). | `resolver.py:27,100,103-135` | **Lock + doble chequeo** (mismo patrón que A1). |
| **H4** | **La caché TTL + single-flight vive en el proxy Flask que NO se migra.** Su propio comentario: *"/analisis/ejecutivo NO tiene caché en FastAPI (verificado)"*. | `routes/api.py:153-228` | `src/shared/cache_ttl.py` en el backend — **es la regla A4** del CLAUDE.md §7. |
| **H8** | 🔴 **La BD de diferidas de 954 MB está CORRUPTA** (`quick_check` → `Tree 1389 page 120706: btreeInitPage() returns error code 11`; todo `SELECT count(*)` → `database disk image is malformed`). La alternativa **`ECP_DIFERIDAS_slim.db` (192 MB, 1.142.599 filas) está sana pero NO tiene `ACEITE_PERDIDO`/`GAS_PERDIDO`** (solo 8 columnas). | Inspección directa de ambos archivos | El bloque `impacto` **no se puede calcular con ninguna de las dos**. **DA-4 (§10)**; tres vías en §5.7. |
| **H9** | **`OPS_DATABASE_URL` está VACÍA** en el `.env` de destino. | `.env`; el valor está en `Des_robustez_2.0/robustez_v02_backend/.env` | Prerequisito P6. `config.py:47` ya declara el campo con default `""` (correcto por AP-2). |
| **H10** | 🔬 **Sin VPN el Postgres 139 no responde** (`timeout expired` medido hoy). | sonda de conexión | Bloqueo de la verificación R3, no del desarrollo. |
| **H11** | **Dos fuentes distintas para "campos de un activo"**: `core.map_campo_activo` (backend) vs `data/Activo_campo.csv` (rutas Flask). | `resolver.py:106-142` vs `routes/api.py:393,399-411` | **Una sola fuente**: `catalogo_entidades.campos_de_activo()`. El CSV **no se porta**. |
| **H12** | El LLM se llama con **`urllib` bloqueante** y `timeout=180`. | `api.py:1110-1160,1957,2368` | Ver AP-9: endpoints `def` sync + caché obligatoria. |
| **H13** | **`_estado()` (90/75) y `_estado_cierre()` (ámbar 93 %) son dos ejes distintos a propósito.** | `api.py:676-701`, comentario *"Eje de estado PROPIO … NO SE TOCA"* | Se portan **los dos**, con su comentario. Unificarlos descalibra tarjetas validadas. |
| **H15** | **`escenario_mes()` es un helper SIN `@router.get` a propósito** (lo consume F4/Cuantificar). | `api.py:628-666` (`AF-4.11`) | Función pública de `services_desempeno.py`, **no ruta**. Test de que no aparece en el OpenAPI. |
| **H16** | `president` lee `core.fact_tabla_hoja` — la **misma tabla** que la feature `tablas` de F1. | `api.py:2562-2619` vs `tablas/repositories.py:89-118` | Solape de tabla, **no** de código: cada feature con su consulta (ADR-001). |
| **H17** | En el sistema viejo **los paneles de análisis se pintan dentro del chat** (`cn-*`); la pestaña "Análisis" solo tiene Fundación de datos. | `multitab_shell.js:663-681` vs `1388-2530, 3400-3900` | **F2 entrega sección propia `/analisis`** (precedente de `/control`). F4 decidirá si promueve componentes. |

---

## 1. Contexto

### 1.1 Inventario de origen — medido

| Archivo origen | Líneas | Aporta |
|---|---:|---|
| `INGESTA/Rep_Prod/backend/app/features/analisis/api.py` | **2.619** | 9 endpoints + 30 funciones auxiliares |
| `…/features/ebitda/api.py` | **123** | waterfall Ingresos→NOPAT sobre `ops.*` |
| `routes/api.py:381-700` | **320** | `/diferidas/frecuencia` + `/mantenimientos/eventos` |
| `routes/api.py:153-228` | **76** | caché TTL + single-flight (A4) |
| `…/consulta/resolver.py:91-181` + `normaliza.py` | **~97** | `norm`, `fuentes_de_activo`, `campos_de_activo` |
| **Backend total** | **~3.235** | |
| `tests/test_analisis_{ejecutivo_tesis,tarjetas_kpi,focos_gap,focos_filiales,valle_atribucion}.py` | **482** (~42 tests) | **Puros — no tocan BD. 0 mayúsculas locales (medido)** |

`multitab_shell.js` **no se porta**: se lee como especificación visual.

### 1.2 Los 12 endpoints

| # | Endpoint | Motor | LLM | Caché | Feature V02 |
|---|---|---|---|---|---|
| 1-4 | `/analisis/{catalogo,densidad,huella,cobertura}` | `db_prod` | no | no | `analisis` |
| 5 | `/analisis/desempeno` | `db_prod` mes+día | no | **900 s** | `analisis` |
| 6 | `/analisis/desempeno_insight` | `db_prod`+comentarios | sí (60 s) | **900 s** (nuevo) | `analisis` |
| 7 | `/analisis/ejecutivo` | `db_prod` completo | sí (180 s) | **900 s** | `analisis` |
| 8 | `/analisis/tendencia_filial` | `fact_produccion_diaria` | no | no | `analisis` |
| 9 | `/analisis/president` | `fact_tabla_hoja` | no | **900 s** | `analisis` |
| 10 | `/ebitda/unificado-waterfall` | **`db_ops`** | no | no | `ebitda` |
| 11 | `/diferidas/frecuencia` | **SQLite** | no | in-proc | `diferidas` |
| 12 | `/mantenimientos/eventos` | **`Eventos_OW.xlsx`** | no | singleton | `mantenimientos` |

Los endpoints 5-9 aceptan `segmento=filiales`, que **cambia fuente y reglas por completo**.

---

## 2. Objetivo

Sección **`/analisis`** con datos reales del 139:

1. **Fundación de datos** — catálogo (cardinalidad + colisiones + explorador), densidad (heatmap +
   semáforo por familia estadística), huella y cobertura por hoja.
2. **Desempeño del mes** — KPIs REAL vs PPTO, curva diaria, producción mensual del año, campos sin
   meta **declarados** (nunca inventados).
3. **Análisis ejecutivo** — tarjetas de cierre con proyección, focos por producto (orden fijo
   Crudo→Gas→Blancos), valle de crudo con atribución honesta, pace, y las 4 secciones generadas por
   el **composer determinista** (LLM = pulido opcional).
4. **Acordeón de foco** — 4 pills: Comportamiento diario · Diferidas · Mantenimientos · EBITDA-NOPAT.
5. **Segmento Filiales** + **tarjeta P50**.

**Aceptación:** build verde + cobertura sobre umbral (L7) + **verificación humana en navegador**
(R3). Ancla de paridad: **Castilla EBITDA = 78.629 kUSD**.

---

## 3. Prerequisitos verificables

| # | Prerequisito | Cómo verificar | Estado (2026-08-20) |
|---|---|---|---|
| P1 | Working tree limpio | `git status --short` vacío | 🔴 4 archivos en vuelo (AP-1) |
| P2 | `db_prod` accesible con VPN | `uv run python -c "from src.shared.db_prod import check_prod_connection; print(check_prod_connection())"` | ⚠️ hoy `timeout expired` sin VPN (H10) |
| P3 | Tablas ECP con datos | `SELECT count(*)` sobre las 14 tablas de §12 | ⚠️ bloqueado por P2 |
| P4 | Hoja `REPORTE_PRESIDENT` | `… WHERE hoja='REPORTE_PRESIDENT'` > 0 | ⚠️ pendiente |
| P5 | `core.map_campo_activo` poblada (52 activos) | `SELECT count(DISTINCT activo) …` | ⚠️ pendiente |
| P6 | `OPS_DATABASE_URL` configurada | leer `.env` | 🔴 vacía (H9) |
| P7 | `ops.*` con el mes objetivo | `SELECT count(*) FROM ops.financial_results WHERE year=:y AND month=:m` | ⚠️ bloqueado por P6 |
| P8 | Fuente de diferidas utilizable | `PRAGMA quick_check` | 🔴 954 MB corrupta / slim sin columnas de volumen (H8) |
| P9 | `Eventos_OW.xlsx` | `ls data/Eventos_OW.xlsx` | ✅ en origen (259.577 bytes) |
| P10 | Molde de feature | `src/features/tablas/*` + `src/features/auth/*` | ✅ **F1 lo dejó listo** |
| P11 | CI capaz de validar F2 | `ci.yml` corregido | 🔴 sin tocar desde el commit inicial (AP-13) |
| P12 | Polyfill de Plotly en jsdom | grep `createObjectURL` en `tests/setup/vitest.setup.ts` | 🔴 no existe (AP-4) |

**Bloqueantes duros:** P1 (antes de empezar) · P2/P3 (antes de dar por verificado) · P6 (bloque
EBITDA) · P8 (bloque Diferidas) · **P12 (antes de escribir el primer gráfico)**.

---

## 4. Inventario de archivos

### 4.1 Backend

**CREAR — infraestructura compartida:**

```
src/shared/catalogo_entidades.py   norm, fuentes_de_activo, campos_de_activo, activo_de_campo
                                   índice con lock + doble chequeo · CERO I/O al importar (AP-2)
src/shared/db_ops.py               engine PostgreSQL robustez_v02 (ops.*), lazy, solo lectura (L4)
src/shared/db_diferidas.py         engine SQLite, lazy, read-only (`file:…?mode=ro`)
src/shared/cache_ttl.py            TTL + single-flight en el BACKEND (A4/H4)
src/shared/llm_client.py           Ollama: extraer_json, invocar, reintento solo ante aborto (H12)
```

**CREAR — feature `analisis`** (split por sufijo, CLAUDE.md §6):

```
src/features/analisis/__init__.py
                      api.py                    los 9 endpoints — `def` sync (AP-9)
                      schemas.py                DTOs Pydantic de salida
                      repositories.py           SQL ECP (ámbito, mes, día, comentarios)
                      repositories_catalogo.py  SQL catálogo/densidad/huella/cobertura
                      repositories_filiales.py  SQL sobre core.fact_produccion_diaria
                      services_catalogo.py      severidad, semáforo, por_mes, rachas
                      services_desempeno.py     ámbito+periodo, KPIs, curva, ritmo,
                                                campos_sin_meta, escenario_mes() (NO ruta — H15)
                      services_ejecutivo.py     valle, gap reconciliado, flags, tarjetas, focos,
                                                síntesis, composer determinista
                      services_filiales.py      intermedios, tendencia, serie mensual, focos
                      prompts.py                los 4 prompts + reglas_tesis
```

**CREAR — features auxiliares:**
`src/features/{ebitda,diferidas,mantenimientos}/{__init__,api,schemas,services,repositories}.py`

**CREAR — tests:**

```
tests/unit/test_analisis_tesis.py             ← port (adaptar monkeypatch a shared.llm_client)
tests/unit/test_analisis_tarjetas_kpi.py      ← port
tests/unit/test_analisis_focos_gap.py         ← port
tests/unit/test_analisis_focos_filiales.py    ← port
tests/unit/test_analisis_valle_atribucion.py  ← port
tests/unit/test_cache_ttl.py                  NUEVO (TTL, single-flight, no cachear errores)
tests/unit/test_llm_client.py                 NUEVO (extraer_json + política de reintento)
tests/unit/test_catalogo_entidades.py         NUEVO (norm, lock, composición de activo)
tests/unit/test_mantenimientos_service.py     NUEVO (A2 abierto, A3 solape)
tests/integration/test_analisis_flow.py       NUEVO (401 deny-by-default + overrides)
tests/integration/test_ebitda_flow.py         NUEVO (503 con ops caída Y con ops sin configurar)
tests/integration/test_diferidas_flow.py      NUEVO (degradación SIEMPRE 200)
tests/integration/test_sin_io_al_importar.py  NUEVO (AP-2: importar src.main no abre conexiones)
```

**MODIFICAR:**

```
src/main.py                       + 4 routers + OPENAPI_TAGS + estado de db_ops en /health
src/core/config.py                + 9 settings, TODAS con default (AP-2)
.env / .env.example               + OPS_DATABASE_URL, EJECUTIVO_USAR_LLM=false, CONSULTA_OLLAMA_URL,
                                    CONSULTA_LLM_MODEL, CONSULTA_KEEP_ALIVE, EJECUTIVO_FALLBACK,
                                    KPI_CIERRE_AMBAR_PCT, ANALISIS_CACHE_TTL, DIFERIDAS_DB_PATH,
                                    EVENTOS_OW_PATH
tests/conftest.py                 + patch_ops_db, patch_diferidas_db, stub_llm, eventos_ow_fake
.gitignore                        + prodia_v02_backend/data/*.xlsx (AP-8, según DA-8)
```

> `openpyxl>=3.1` **ya está** en `pyproject.toml`. El cliente LLM usa `urllib` de stdlib —
> **no se añade `requests`**.

### 4.2 Frontend

**CREAR — wrapper compartido (AP-5/AP-6):**

```
src/shared/components/Grafico/{Grafico.tsx,Grafico.module.scss,index.ts,Grafico.test.tsx}
   ÚNICO punto que importa Plotly (dist-min vía react-plotly.js/factory).
   Expone tipos propios para que el desajuste v2/v3 se resuelva una vez.
```

**CREAR — feature `analisis`:**

```
src/features/analisis/pages/AnalisisPage.tsx (+ .module.scss, .test.tsx)   default export (lazy)
src/features/analisis/components/
  ├─ SelectorAmbito/            entidad · nivel · periodo · segmento
  ├─ PanelFundacion/            {TarjetasCardinalidad, TablaColisiones, HeatmapDensidad, MapaCobertura}
  ├─ PanelDesempeno/            {KpisPorProducto, CurvaDiaria, RitmoMensual}
  ├─ PanelEjecutivo/            {TarjetaKpiCierre, TarjetaP50, FocosProducto, SeccionesEjecutivas,
  │                              AcordeonFoco → PillComportamiento|PillDiferidas|PillMantenimientos|PillEbitda}
  └─ PanelFiliales/
src/features/analisis/services/{analisis,ebitda,diferidas,mantenimientos}Service.ts
src/features/analisis/hooks/                 un hook React Query por endpoint (con `enabled`)
src/features/analisis/mappers/analisisMappers.ts
src/features/analisis/types/analisisTypes.ts
```

**MODIFICAR:**

```
src/app/router.tsx                    + { path: '/analisis', element: withSuspense(AnalisisPage) }
tests/setup/vitest.setup.ts           + polyfill URL.createObjectURL/revokeObjectURL (AP-4) 🔴
src/shared/types/api.d.ts             regenerar con gen:types (SOLO este se commitea — AP-7)
src/shared/utils/format.ts            + formatBopd, formatKbpe (A5/C3)
```

---

## 5. Especificación

### 5.0 Contrato heredado de F1 — copiar, no inventar

F1 ya fijó el patrón. F2 lo sigue **literalmente**, con **una desviación declarada**:

| Pieza | Referencia | F2 |
|---|---|---|
| Dependencia de feature | `tablas/api.py:46-49` (`get_service()` arma repo+service sobre la sesión inyectada) | idéntico, uno por feature |
| Traducción de error de BD | `tablas/api.py:52-59` (`_error_db` → 503, detalle al log, nunca al cliente) | idéntico |
| Documentación OpenAPI | `tablas/api.py:40-43` (`RESPUESTAS_COMUNES` 401/503) | idéntico + 503 de `ops` |
| Handler global | `exceptions.py::database_exception_handler` (503 + `code="DB_UNAVAILABLE"`) | se hereda; **añadir** el caso `RuntimeError` de ops sin configurar (AP-10) |
| Aislamiento en tests | `conftest.py:161-196` + `test_tablas_flow.py` | mismo patrón para ops/diferidas/llm |
| Sanitización A6 | `tablas/services.py:44,230,285,318` (`_sanitize_col`) | igual en toda response numérica |
| **`async def`** | `tablas/api.py` usa `async def` con SQLAlchemy síncrona | 🔴 **F2 usa `def` (sync)** — AP-9. Comentario obligatorio explicando por qué |

### 5.1 `shared/catalogo_entidades.py` — resuelve H2/H3/AP-2

Porta `resolver.py:91-181` + `normaliza.py`. **No** porta lo conversacional (`resolver()`,
`buscar_en_texto`, `termino_candidato`, `_STOP`, `clave_fisica`) — eso es **F4**.

```python
def norm(s: str) -> str
def fuentes_de_activo(db: Session, activo: str) -> list[int]
def campos_de_activo(db: Session, activo: str) -> list[str]
def activo_de_campo(db: Session, campo: str) -> str | None
def reset_cache() -> None            # solo tests
```

1. **CERO I/O al importar (AP-2).** El índice se construye en la primera llamada, nunca a nivel de
   módulo. Test dedicado: `test_sin_io_al_importar.py`.
2. **Lock + doble chequeo** (H3, patrón A1), con el comentario que explica por qué.
3. **D-A3 preservada:** no se rescatan fuentes con `campo` NULL usando `nombre` (Chichimene sumaba
   +56.003 bl al colar 3 filas NULL homónimas).
4. Copiar íntegro el bloque `resolver.py:7-16`: explica por qué el activo **no** sale de
   `dim_fuente.activos` (bucket de portafolio, APIAY agrupaba 13 campos en vez de 4) ni de `grupo1`.
5. Recibe la sesión inyectada; no la crea (igual que `tablas/repositories.py`).

### 5.2 Normalización de estilo obligatoria — resuelve AP-3

**El SQL se copia idéntico (U3). El estilo Python NO.** Al portar cada función:

| Idiom del origen | Falla | Se escribe |
|---|---|---|
| `E = entidad.strip().upper()` | N806 | `entidad_norm = …` |
| `P = {"ini": ini, "fin": fin}` | N806 | `params = {…}` |
| `RD = "WITH rd AS (…) "` | N806 | `cte_rd = "…"` |
| `I = _fil_intermedios(c)` | N806 | `intermedios = …` |
| `TOP_N = 12` (dentro de función) | N806 | constante **a nivel de módulo** `TOP_EVENTOS_VALLE = 12` |
| `CATS`, `PRIOR`, `NIVELES_SQL`, `ANIOS`, `TOP_G`, `TOP_I` | N806 | constantes de módulo en MAYÚSCULAS |
| `import calendar` dentro de la función | I001 | import al tope del módulo |
| `_base = lambda s: …` | estilo | `def _base(s: str) -> str:` |
| `def desempeno(entidad=None, …):` | mypy `no-untyped-def` | firma completamente anotada |
| filas como `dict` sueltos | mypy strict | `Mapping[str, Any]` en el repo → DTO tipado en el service |

**Buena noticia medida:** los 5 archivos de test a portar tienen **0 mayúsculas locales** → se
portan sin renombres (solo cambian los imports y el objetivo del `monkeypatch`).

**Orden de verificación por archivo:** `uv run black .` → `uv run ruff check . --fix` →
`uv run mypy src`. Nunca `black --check` primero: reformatea y ahorra una vuelta.

### 5.3 Plotly: decisión de arquitectura — resuelve AP-4/AP-5/AP-6 + R2

1. **Un solo wrapper.** `shared/components/Grafico/` es el **único** archivo del repo que importa
   Plotly:

   ```tsx
   // @ts-expect-error — plotly.js-dist-min no publica tipos propios
   import Plotly from 'plotly.js-dist-min';
   import createPlotlyComponent from 'react-plotly.js/factory';
   const Plot = createPlotlyComponent(Plotly);
   ```

   Motivo (AP-5): `import Plot from 'react-plotly.js'` arrastra `plotly.js@3.7.0` (10,7 MB) +
   `mapbox-gl` **deprecado**; el factory con `dist-min` usa 4,3 MB y arranca el entorno de test en
   1,8 s en vez de 17,5 s (medido).
2. **`title` siempre objeto** (AP-6): `layout={{ title: { text: '…' } }}`. Los tipos instalados son
   de Plotly 3.x; el idiom v2 (`title: 'x'`) **rompe `tsc -b`** y por tanto `pnpm build`.
3. **Polyfill en el setup de vitest** (AP-4) — sin él, cada suite con un gráfico falla entera:

   ```ts
   // jsdom no implementa URL.createObjectURL; Plotly lo llama al cargarse.
   // Sin esto la SUITE entera falla ("Failed Suites 1 · no tests"), no un test.
   if (!window.URL.createObjectURL) {
     window.URL.createObjectURL = (() => 'blob:test') as unknown as typeof window.URL.createObjectURL;
     window.URL.revokeObjectURL = (() => {}) as unknown as typeof window.URL.revokeObjectURL;
   }
   ```

   Los `Not implemented: HTMLCanvasElement.getContext` que siguen apareciendo son **ruido de jsdom,
   no fallo** (verificado: `1 passed`).
4. **R2, regla no negociable.** El `data` memoizado **jamás** depende de estado de selección/hover.
   Cada `useMemo` lleva un comentario declarando sus dependencias reales. La selección se pinta con
   `layout`/`style`, nunca recreando `data`.
5. `Grafico` carga con `React.lazy` desde cada panel: los 4,3 MB no entran en el bundle inicial
   (hoy `index.js` = 331 kB / 106 kB gzip — ese es el baseline a no arruinar).

### 5.4 `shared/cache_ttl.py` — resuelve H4/A4

Porta `routes/api.py:153-228`:

- TTL configurable (`ANALISIS_CACHE_TTL`, default **900 s**; el reporte cambia 1 vez/día).
- **Single-flight**: un `Lock` por clave + **double-check** tras adquirirlo.
- **Criterio de cacheabilidad portado tal cual**: nunca cachear `encontrada is False`, `sin_datos`,
  error, `meta.generado_por == "error"`, ni un `president` con `productos == []`.
- Clave = ruta + params ordenados.
- Test: hit/miss, expiración, single-flight con 2 hilos, y que un error **no** se cachea.

### 5.5 `shared/llm_client.py` — resuelve H12/AP-9

Porta `_extraer_json`, `_llm_insight`, `_llm_insight_once`. Las 4 trampas se preservan **con su
comentario**:

| # | Regla |
|---|---|
| T1 | `format="json"` en el body — elimina fences/prosa/comas rotas de raíz |
| T2 | `num_ctx=8192` **explícito** — el default (2048) corta el objeto a media llave y produce un falso `json_invalido` |
| T3 | `resp["done"] is False` = **generación abortada** → `None` sin parsear el fragmento |
| T4 | Reintento **solo** ante aborto. Un `json_invalido` con `temperature=0` daría lo mismo |

`extraer_json` conserva la tolerancia a fences, comillas tipográficas (`“ ” ‘ ’`), comas finales y
el balanceo de llaves respetando strings/escapes. El `diag` (status, model, host, raw truncado,
done_reason, tokens) se expone en `meta.llm_diag` — es lo que distingue "Gemma se cayó" de "el
prompt está mal" (C2/N6).

**El módulo no abre nada al importarse** (AP-2) y **ningún test sale a la red** (`stub_llm`).

### 5.6 Reglas de dominio (CLAUDE.md §7) → dónde aterrizan

| Regla | Implementación | Verificación |
|---|---|---|
| **A1** singleton bajo lock con doble chequeo | `mantenimientos/repositories.py` (xlsx, ~1,53 s) **y** `catalogo_entidades` (H3) | 2 hilos → 1 solo parseo |
| **A2** `FinalizaEvento` vacío = **ABIERTO** (3.305/6.850 = 48 %) | `mantenimientos/services.py`; los 5 años mal tecleados (2526/2626/3026/2016) también abiertos | test con fila sin fin y con año absurdo |
| **A3** filtro por **solape con el mes**, nunca contra `now()` | `inicio < fin_mes AND (fin IS NULL OR fin >= ini_mes)` | test: contra `now()` quedan 3 eventos; contra el mes, 2.741 |
| **A4** caché TTL + single-flight en el backend | `shared/cache_ttl.py` | `test_cache_ttl.py` |
| **A5** cada producto con SU escala | back: `{CRUDO:"bbl", BLANCOS:"bbl", GAS:"MSCF"}`; front: `formatBl`/`formatMscf`/`formatKbpe`/`formatBopd` | test de unidades (ya en el port) |
| **A6** `_sanitize_col` antes de toda response numérica | todos los `services_*` + `ebitda` | `test_utils.py` + uso por service |
| **Q2** REGLA CERO | `services_ejecutivo.situacion_general()` + `prompts.reglas_tesis()` | los 9 tests de `test_analisis_tesis.py` |

### 5.7 Comentarios del origen que NO pueden perderse

Cada uno es un bug ya pagado. Se traducen, **no se resumen**:

| Ancla | Qué explica |
|---|---|
| `api.py:525-529` (H1) | El `volumen` de cada producto vive en UN SOLO proceso → `SUM` sobre todos **no** doble-cuenta. **No filtrar por proceso.** |
| `api.py:541-543` (H2) | Día y mes usan **medidas distintas** (BLANCOS: día ≈1,9M vs mes ≈0,9M). KPIs 100 % de `mes`; `día` solo para la curva. |
| `api.py:594-606` | El promedio diario del año solo se entrega si la curva diaria **reconcilia** (`mtd ≤ esperado×1,15`). Si no, el título NO dice "vs 2026". |
| `api.py:608-613` (D-A4) | Campos que producen **sin PPTO** se **declaran**. Se descartó `PPTO=1,25×REAL`: hundía APIAY de 108,8 % a 63,0 % con 385.409 bl fabricados. |
| `api.py:324-326` (F1) | Cobertura = `COUNT(DISTINCT reporte_id)`, **no** `SUM(filas_insertadas)` (sobre-cuenta ~26×: 11,2M vs 435K). |
| `api.py:794-800` | El área trae el producto como sufijo (`CUPIAGUA (CRUDO)`) en 144/648 comentarios → `SPLIT_PART`. Sin esto el panel decía "sin evento asociado" con 18 comentarios disponibles. |
| `api.py:804-812` (INS-A) | Solo el **onset** del valle da eventos limpios; el rango completo repite el mismo evento cada día. |
| `api.py:919-948` | **Atribución honesta**: si el comentario es del grupo y no de la entidad, se dice. Comparar por **base**, o el propio se degrada a ajeno. |
| `api.py:1754-1758` | Ritmo diario solo si `mtd ≤ real×1,05`. Mayo-2026: CRUDO 54,6 % y GAS 55,2 % reconcilian; **BLANCOS 183,7 % no**. |
| `api.py:1816-1820` | Concentración = `|top3| / |Σ detractores brutos|`, no sobre el neto (daría >100 % con compensadores grandes). |
| `api.py:1836-1840` | `faltante_bruto + excedente_bruto = gap_total_campos`. Sin esto el panel mostraba −10.813.358 con un detalle que sumaba 19.814.696. |
| `api.py:2579-2584` | `reporte_id` es serial **por orden de ingesta, no cronológico** → ordenar por `fecha_reporte DESC`. |
| `api.py:1505-1510` | La concentración del foco se calcula sobre **los campos nombrados** (2 campos: 88,2 %, no 90,6 %). |
| `api.py:2284-2288` | Filiales sin PPTO → meta = **promedio mensual 2026**, mes en curso a **proyección de cierre**. |
| `api.py:2546-2547` | `_fil_serie_mensual` excluye meses con <60 % de días (Nov-2025 = 1 día distorsionaba). |

**Constantes con su valor exacto:** `MESES_ES` · `PRODUCTOS_VALIDOS` (aceite→CRUDO, gas→GAS,
blancos→BLANCOS; **agua no existe**) · valle: media×**0,997**, run ≥**3** días, serie ≥**5** ·
`_estado` 90/75 · `kpi_cierre_ambar_pct` **0,93** · top eventos valle **12** · flags: crítico <60 %,
gap concentrado ≥70 %, pace exigente ≥10 %, reconciliado ≤2 % · detractores **3** / compensadores
**2** · `_FIL_BANDA_PCT` **5,0** · diferidas: años 2023/2024/2025, top **8** grupos + Otros, top **6**
causas, tendencia solo `empeora` (|Δ|>0,5 pp) · mantenimientos top **8** · EBITDA 18 componentes
(`pos/negabs/neg/asis`) · `statement_timeout` 40 s (huella) / 60 s (cobertura).

### 5.8 Diferidas — las tres vías ante H8

| Vía | Qué implica | Riesgo |
|---|---|---|
| **V1 recuperar** | `sqlite3 ECP_DIFERIDAS.db ".recover" \| sqlite3 recuperada.db`, regenerar slim **con** `ACEITE_PERDIDO`/`GAS_PERDIDO` | El `.recover` puede perder filas de las páginas dañadas. Reconciliar contra 1.142.599 (slim sana) |
| **V2 regenerar** | Re-exportar `AVM_DATADIF` desde la fuente original con las 18 columnas | La fuente puede no estar accesible |
| **V3 sin `impacto`** | 3 bloques contra la slim; `impacto` degrada con `motivo` declarado | Se pierde el "volumen perdido por causa" |

**Recomendación:** **V3 ahora + V1 en paralelo**. Contrato del origen: `sin_datos` + `motivo` con
**HTTP 200 siempre**. El código se escribe para las 18 columnas: encender `impacto` será cambiar
`DIFERIDAS_DB_PATH`, sin tocar código. Los campos del activo salen de `catalogo_entidades` (H11).

### 5.9 Frontend — reglas

1. `multitab_shell.js` **no se reutiliza**; se lee como especificación.
2. **N1/C1** — todo service por `apiClient`. Cero `fetch` desnudo.
3. **C5** — cada fetch en `QueryState` (loading/error/vacío **con `correlation_id`**).
4. **C3/A5** — formateo por producto; el gas llega ya convertido del backend.
5. **R2** — §5.3 punto 4.
6. **Carga perezosa** del acordeón: cada pill dispara su query solo al mostrarse (`enabled`).
7. **Scope por props, nunca global** — bug real del origen (`multitab_shell.js:3617-3619`): las
   pills leían estado global y "Rubiales" mostraba las diferidas de "Castilla".
8. Anillo KPI: el arco topa en 100 %, el texto muestra el % real (108 % se ve).
9. El **estado** lo decide el backend, no el frontend (derivarlo de `mes < histórico` marcaría un
   94 % ajustado como rojo).
10. Ruta `/analisis` por URL, **sin menú** (precedente `/control`).

---

## 6. Orden de ejecución (reformulado según la auditoría v2)

Un artefacto por turno. **Los bloques 0 y 1 son endurecimiento de pipeline: sin ellos, todo lo
demás falla al final en vez de al principio.**

### Bloque 0 — Higiene y endurecimiento de pipeline (antes de una sola línea de F2)

| # | Paso | Resuelve |
|---|---|---|
| 0.1 | Dejar `git status` limpio: commitear o revertir los 4 archivos en vuelo | AP-1 |
| 0.2 | **Polyfill de `URL.createObjectURL`** en `tests/setup/vitest.setup.ts` + test de humo de `Grafico` | AP-4 |
| 0.3 | Crear `shared/components/Grafico/` (dist-min vía factory, `title` como objeto, tipos propios) | AP-5/AP-6 |
| 0.4 | Verificar: `pnpm typecheck && pnpm build && pnpm test:front` en verde **con el gráfico de humo** | AP-4/6 |
| 0.5 | Añadir `prodia_v02_backend/data/*.xlsx` al `.gitignore` (según DA-8) | AP-8 |
| 0.6 | Corregir `ci.yml` (§11) — **requiere aprobación DA-5** | AP-13 |
| 0.7 | Con VPN: verificar P2/P3/P4/P5. Configurar `OPS_DATABASE_URL` (P6) y verificar P7 | H9/H10 |
| 0.8 | Decidir DA-4; copiar el `.db` elegido y `Eventos_OW.xlsx` a `prodia_v02_backend/data/` | H8 |
| 0.9 | Añadir las 9 settings a `config.py` + `.env` + `.env.example`, **todas con default** | AP-2 |

> **Puerta de salida del Bloque 0:** `pnpm build` verde con un gráfico Plotly real renderizado en un
> test. Si esto no pasa, no se escribe backend de F2.

### Bloque 1 — Infraestructura compartida del backend

1.1 `shared/catalogo_entidades.py` + `test_catalogo_entidades.py`
1.2 `shared/cache_ttl.py` + `test_cache_ttl.py`
1.3 `shared/llm_client.py` + `test_llm_client.py`
1.4 `shared/db_ops.py` + `shared/db_diferidas.py` (**lazy, cero I/O al importar**)
1.5 `tests/integration/test_sin_io_al_importar.py` — **importar `src.main` no abre conexiones** (AP-2)
1.6 Ampliar `conftest.py` con `patch_ops_db`, `patch_diferidas_db`, `stub_llm`, `eventos_ow_fake`
1.7 **Verificar:** `uv run black . && uv run ruff check . && uv run mypy src && uv run pytest --cov=src --cov-fail-under=75` — verde **sin red**, y `pnpm gen:types` sin colgarse (prueba viva de AP-2)

### Bloque 2 — Port de los tests puros (son la especificación)

2.1 Portar los 5 archivos a `tests/unit/`, con `@pytest.mark.unit` y el `monkeypatch` apuntando a
`shared.llm_client` (antes era `api._llm_insight_once`). Quedan **rojos** a propósito.

### Bloque 3 — `analisis` · Fundación de datos (sin LLM, sin filiales)

3.1 `schemas.py` (catálogo/densidad/huella/cobertura) · 3.2 `repositories_catalogo.py` ·
3.3 `services_catalogo.py` · 3.4 `api.py` endpoints 1-4 + `main.py` + `OPENAPI_TAGS` ·
3.5 tests de integración con `patch_prod_db` · 3.6 **verificar**

### Bloque 4 — `analisis` · Desempeño ECP

4.1 ampliar `schemas.py` · 4.2 `repositories.py` · 4.3 `services_desempeno.py` (incluye
`escenario_mes()` **como función, no ruta** — H15) · 4.4 endpoint `/desempeno` + caché ·
4.5 tests (uno verifica que `escenario_mes` **no** está en el OpenAPI) · 4.6 **verificar**

### Bloque 5 — `analisis` · Ejecutivo ECP (el más denso: 4 turnos)

5.1 `services_ejecutivo` I: `detectar_valle`, `eventos_valle`, `comentarios_campo_mes`,
`valle_diagnostico_entidad`, `nombres_entidad`
5.2 `services_ejecutivo` II: `gap_campo` reconciliado, `flags`, `tarjetas_kpi`, `estado_cierre`,
`focos`, `sin_foco`
5.3 `services_ejecutivo` III + `prompts.py`: `situacion_general`, `sintesis`, `ejec_fallback`,
`reglas_tesis`
5.4 endpoints `/desempeno_insight` y `/ejecutivo` (**`def` sync** — AP-9) + caché + `llm_diag`
5.5 **los 5 archivos del Bloque 2 pasan a verde aquí** + integración · 5.6 **verificar**

### Bloque 6 — `analisis` · Filiales + President

6.1 `repositories_filiales.py` + `services_filiales.py` · 6.2 ramas `segmento=filiales` de los 3
endpoints · 6.3 `/tendencia_filial` y `/president` · 6.4 tests · 6.5 **verificar**

### Bloque 7 — Features auxiliares

7.1 `ebitda` (18 componentes, signos, USD/BI, 503 con ops caída **y** con ops sin configurar —
AP-10). **Ancla: Castilla = 78.629 kUSD**
7.2 `mantenimientos` (A1 lock + A2 abiertos + A3 solape; **siempre 200**)
7.3 `diferidas` (pareto/tendencia/pozos + `impacto` según DA-4; **siempre 200**)
7.4 tests · 7.5 **verificar**

### Bloque 8 — Tipos

8.1 `pnpm gen:types`; confirmar los paths nuevos en el diff. **Commitear solo `api.d.ts`** (AP-7).

### Bloque 9 — Frontend por paneles (un turno cada uno, con sus tests)

9.1 `types/` + `mappers/` + los 4 services · 9.2 `hooks/` (con `enabled`) ·
9.3 `SelectorAmbito` + `AnalisisPage` + ruta · 9.4 `PanelFundacion` (primer gráfico real) ·
9.5 `PanelDesempeno` · 9.6 `PanelEjecutivo` sin acordeón · 9.7 `AcordeonFoco` + 4 pills ·
9.8 `PanelFiliales` · 9.9 **verificar:** `pnpm lint && pnpm typecheck && pnpm build && pnpm test:front`

### Bloque 10 — Verificación end-to-end (R3)

10.1 `pnpm dev` en pruebas **con VPN**. El usuario recorre `/analisis` y confirma: catálogo y
colisiones · heatmap · cobertura por hoja · KPIs y curva · tarjetas de cierre · focos en orden
Crudo→Gas→Blancos · las 4 pills cargan · **waterfall con Castilla = 78.629 kUSD** · filiales · P50.
10.2 **El usuario** marca F2 como verificada (R3).

---

## 7. Reglas no negociables

- **R1** — no tocar configuración de pnpm sin aprobación explícita.
- **R2** — ningún `data` memoizado de Plotly depende de selección/hover. Los 5 gráficos lo declaran.
- **R3** — build verde ≠ feature verificada. El usuario verifica en navegador.
- **ADR-001** — cero imports cross-feature. Lo común va a `shared/`.
- **U3** — mismo Postgres, mismo SQL. Se reescribe la capa de acceso, no la consulta.
- **CERO I/O en tiempo de import** (AP-2) — con test que lo garantiza.
- **Endpoints `def` sync**, nunca `async def`, en todo lo que toque BD síncrona o el LLM (AP-9).
- **Un solo punto de import de Plotly**: `shared/components/Grafico` (AP-5).
- **A1-A6** con su test cada una. **Q2 (REGLA CERO)**: si no hay rezago, se declara.
- **Python calcula, el LLM redacta.** Ninguna cifra, fecha, etiqueta ni label sale del LLM.
- **Degradación 200** en `/diferidas` y `/mantenimientos`; **503 claro** en `/ebitda`; **nunca
  fail-fast** del backend por una BD que no sea `db_auth`.
- **Ningún test sale a la red.**

---

## 8. Validaciones

```bash
# backend — el orden importa (black primero ahorra una vuelta)
uv run black . && uv run ruff check . && uv run mypy src
uv run pytest --cov=src --cov-fail-under=75      # el comando EXACTO de CI
# pipeline de tipos (prueba viva de AP-2: si cuelga, algo hace I/O al importar)
pnpm gen:types
# frontend
pnpm lint && pnpm typecheck && pnpm build && pnpm test:front
```

**Funcionales:** `/docs` con los 12 endpoints bajo 4 tags · `/health` reporta
`database_auth`/`database_prod`/`database_ops` · `escenario_mes` **no** está en `openapi.json` ·
con `EJECUTIVO_USAR_LLM=false`, `/ejecutivo` devuelve `secciones` completas y
`meta.generado_por="fallback"` · segunda llamada dentro del TTL **no** re-invoca al LLM ·
**Castilla EBITDA = 78.629 kUSD** · los KPIs de `/desempeno` coinciden dígito a dígito con el
sistema viejo.

---

## 9. Fuera de alcance

Chat/historial/insights conversacionales (**F4**) · menú de navegación · RBAC de UI (C4/DT-3) ·
promover componentes de `analisis` a `shared/` (lo decide F4) · el resto de `consulta/resolver.py`
(F4) · optimizar el SQL · recuperar la BD de 954 MB (tarea aparte, §5.8 V1) · **cualquier
escritura**: F2 es 100 % lectura · **frontend de F1 (`features/control/`)** — puede ir en paralelo,
solo comparte `router.tsx`.

---

## 10. Decisiones abiertas

| # | Decisión | Recomendación |
|---|---|---|
| **DA-1** | ¿`/analisis` propia o dentro del panel Insights de Consulta? | **`/analisis` propia** (precedente `/control`; lo otro invade F4 — H17) |
| **DA-2** | ¿F2 en una fase o cortada en F2a-F2d? | **Cortada**: F2a = Bloques 0-3 · F2b = 4-5 · F2c = 6-7 · F2d = 8-10 |
| **DA-3** | ¿Solo admin o todo autenticado? | **Todo autenticado** (igual que F1) |
| **DA-4** | 🔴 **Fuente de diferidas** (H8) | **V3 ahora + V1 en paralelo** |
| **DA-5** | ¿Se corrige `ci.yml` dentro de F2? | **Sí, Bloque 0.6** — si no, F2 nunca se valida en CI (AP-13) |
| **DA-6** | ¿`EJECUTIVO_USAR_LLM` en pruebas? | **`false`** hasta cerrar el portado; encender al final contra `gemma4:latest` |
| **DA-7** | 🆕 ¿Se desinstala `react-plotly.js` y se usa solo `dist-min`? | **No desinstalar** (R1: tocar deps requiere aprobación). Se usa el `factory` — mismo efecto sin cambiar `package.json` |
| **DA-8** | 🆕 ¿`Eventos_OW.xlsx` (259 kB) se versiona o se ignora? | **Ignorar** (`data/*.xlsx`) + documentar la copia en despliegue. Es dato operativo, no código |

---

## 11. Correcciones de pipeline propuestas (Bloque 0.6 — requiere DA-5)

```yaml
# .github/workflows/ci.yml — job frontend

# AP-13a: el lockfile del workspace vive en la RAÍZ, no en prodia_v02_frontend/.
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
          cache-dependency-path: pnpm-lock.yaml        # ← era prodia_v02_frontend/pnpm-lock.yaml
      - run: pnpm install --frozen-lockfile
        working-directory: .                            # ← install desde la raíz del workspace

# AP-13b (DT-6): `pnpm test -- --coverage` NO propaga el flag (pnpm se come el `--`).
      - run: pnpm test:front                            # ← ya trae `vitest run --coverage`

# AP-13c: sin `pnpm build`, un fallo de tsc/vite (AP-6 es exactamente eso) pasa CI.
      - run: pnpm build
```

**Mejora adicional recomendada** (job backend): añadir `- run: uv run python scripts/export_openapi.py`
antes de los tests. Es la única forma de que CI detecte un módulo que hace **I/O al importarse**
(AP-2) antes de que rompa el pre-commit de todo el equipo.

> Nota: el job usa `pnpm/action-setup@v4 version: 9` y el lock local es de pnpm 11 — verificar que
> `--frozen-lockfile` acepta el `lockfileVersion`; si no, subir CI a pnpm 11.

---

## 12. Apéndice A — endpoint → tablas

| Endpoint | Fuentes |
|---|---|
| `/catalogo` | `core.dim_fuente`, `dim_vicepresidencia`, `dim_empresa` |
| `/densidad` | `core.fact_produccion_dia_ecp` (idx `dia_fecha`), `dim_fuente`, `dim_vicepresidencia` |
| `/huella` | `fact_produccion_dia_ecp`, `fact_produccion_mes_ecp`, `dim_escenario`, `fact_programa_ecp` |
| `/cobertura` | `core.ingesta_log`, `bronze.hoja_landing` (ILIKE sobre JSONB) + facts ECP |
| `/desempeno` | `fact_produccion_mes_ecp`, `fact_produccion_dia_ecp`, `dim_tipo_producto`, `dim_escenario`, `dim_fuente`, `map_campo_activo` |
| `/desempeno_insight`, `/ejecutivo` | las anteriores + `fact_comentarios_produccion`, `config_reporte` |
| `/tendencia_filial` | `fact_produccion_diaria`, `dim_empresa`, `dim_tipo_producto` |
| `/president` | `fact_tabla_hoja` (hoja `REPORTE_PRESIDENT`), `config_reporte` |
| `/ebitda/unificado-waterfall` | `ops.{financial_results,operating_costs,flow_rates,wells_attributes}` |
| `/diferidas/frecuencia` | SQLite `AVM_DATADIF` |
| `/mantenimientos/eventos` | `Eventos_OW.xlsx` (`Sheet1`, cols 3/4/7/8/12/10/6) |

## 13. Apéndice B — función origen → archivo destino

| Origen (`analisis/api.py`) | Líneas | Destino |
|---|---|---|
| `_severidad`, `catalogo` | 20-90 | `services_catalogo` / `repositories_catalogo` |
| `densidad` | 93-187 | `services_catalogo` |
| `huella`, `_presencia_entidad`, `cobertura` | 190-348 | `services_catalogo` |
| `_NIVEL_COL_AMB`, `_parse_periodo`, `_ambito`, `_campos_sin_meta` | 361-478 | `services_desempeno` |
| `desempeno` | 486-625 | `api` + `services_desempeno` |
| `escenario_mes` | 635-666 | `services_desempeno` (**no ruta** — H15) |
| `_estado`, `_estado_cierre`, `_tarjetas_kpi`, `_UNIDADES_PRODUCTO` | 676-748 | `services_ejecutivo` |
| `_detectar_valle` … `_valle_diagnostico_entidad` | 750-963 | `services_ejecutivo` |
| `_extraer_json`, `_llm_insight`, `_llm_insight_once` | 966-1160 | **`shared/llm_client`** |
| `_situacion_general`, `_reglas_tesis` | 1011-1089 | `services_ejecutivo` + `prompts` |
| `desempeno_insight` | 1163-1338 | `api` |
| `_flags_ejecutivo`, `_ejec_fallback`, `_focos`, `_sin_foco` | 1349-1581 | `services_ejecutivo` |
| `_fil_difs_por_producto`, `_focos_filiales`, `_sin_foco_filiales` | 1592-1657 | `services_filiales` |
| `ejecutivo` | 1660-1988 | `api` |
| `_fil_intermedios` … `_ejecutivo_filiales` | 2001-2422 | `services_filiales` |
| `_fil_tendencia`, `tendencia_filial`, `_fil_serie_mensual` | 2432-2559 | `services_filiales` + `api` |
| `president` | 2562-2619 | `api` + `repositories` |
