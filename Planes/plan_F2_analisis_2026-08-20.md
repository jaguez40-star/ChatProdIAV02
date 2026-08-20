# Plan F2 — Análisis (ECP + Filiales + EBITDA + Diferidas + Mantenimientos)

> Plan **v1 auditado** (Modo Planner, CLAUDE.md §0): los pasos 1-3 del flujo de 6 pasos
> (Mapeo → Auditoría → Diagnóstico) se ejecutaron **contra el código real** de origen
> (`12112025_prodIA/`) y de destino (`ProdIA_V02/`) el **2026-08-20**, incluyendo inspección
> física de las BDs auxiliares. No hay nada en este documento tomado de memoria.
>
> **Para el executor:** este plan es largo a propósito. F2 es ~13× F1. Seguir el
> **Orden de ejecución** (§6) bloque por bloque, **un artefacto por turno**, con la
> verificación del bloque en verde antes de pasar al siguiente. No adelantar bloques.

---

## 0. Hallazgos de la auditoría — LEER PRIMERO

Cada hallazgo modifica el orden de ejecución o añade trabajo obligatorio. Ignorar uno = build
roto, dato falso en pantalla, o una regla de dominio perdida.

| # | Hallazgo | Evidencia (verificada hoy) | Consecuencia si se ignora | Acción en el plan |
|---|---|---|---|---|
| **H1** | **F1 está a medio ejecutar.** Existen `features/tablas/{schemas,repositories,services}.py` sin `api.py`, sin `__init__.py` y **sin registrar en `main.py`**. Están sin commitear (`git status` → `?? prodia_v02_backend/src/features/tablas/`). | `ls src/features/tablas/` = 3 archivos; `main.py:106-107` solo monta `auth` y `permissions`. | Arrancar F2 con F1 a medias deja dos features incompletas compitiendo por el mismo `main.py`, el mismo `conftest.py` y el mismo `api.d.ts`. Los merges de `openapi.json` se pisan. | **Bloque 0, paso 1:** cerrar F1 (o congelarlo en una rama) antes de tocar nada de F2. F2 **no depende del código** de F1, pero sí de que `main.py`/`conftest.py` no estén a medio editar. |
| **H2** | **El origen viola ADR-001.** `analisis/api.py:4` hace `from app.features.consulta.resolver import fuentes_de_activo, campos_de_activo`, y `resolver.py:3` importa `consulta.normaliza.norm`. | `api.py:4`, `resolver.py:1-3,138-152`. | Portar tal cual crea un import cross-feature `analisis → consulta` que **ADR-001 prohíbe**, y que además rompería F4 (consulta) al revés. | **Nuevo módulo compartido `src/shared/catalogo_entidades.py`** con `norm()`, `fuentes_de_activo()`, `campos_de_activo()`, `activo_de_campo()` y el índice cacheado. F2 y F4 lo consumen; ninguna feature importa a otra. |
| **H3** | **El índice del resolver es estado global mutable sin lock.** `_INDEX`, `_FUENTE_SETS` son globals de módulo con lazy-init sin protección. | `resolver.py:27,100,103-135`. | Bajo N peticiones concurrentes (el prefetch del login dispara varias), N hilos construyen el índice a la vez. Es el **mismo defecto que A1** describe para `Eventos_OW.xlsx`, pero en el resolver. | El módulo compartido usa **lock + doble chequeo** (patrón A1), igual que el singleton de mantenimientos. |
| **H4** | **La caché TTL + single-flight NO está en el backend: vive en el proxy Flask que NO se migra.** | `routes/api.py:153-228` (`_ANALISIS_TTL_S=900`, `_ANALISIS_CACHE`, `_ANALISIS_INFLIGHT`, `_analisis_es_cacheable`). El propio comentario dice *"/analisis/ejecutivo NO tiene caché en FastAPI (verificado)"*. | Sin re-implementarla, **cada** petición a `/ejecutivo` re-invoca a Gemma (~180 s). El prefetch del login dispara N generaciones en paralelo y Ollama las serializa → timeouts. **Es exactamente la regla A6→A4 del CLAUDE.md §7.** | **`src/shared/cache_ttl.py`** en el backend (A4), con el criterio de cacheabilidad portado tal cual (§5.6). |
| **H5** | **`mypy strict = true` sobre `src`.** El origen usa `dict`/`Any` sin tipar, lambdas asignadas a nombres, `import` dentro de funciones, y funciones sin anotar. | `pyproject.toml:[tool.mypy] strict=true, files=["src"]`; origen: `api.py:98,491,1168,1676` (`import calendar` dentro de la función), `api.py:926` (`_base = lambda s: ...`). | `uv run mypy src` (CI) falla. `ruff` con `select=["I","F","N","W"]` también marca varios. | Tipar **todo** lo portado: `TypedDict`/Pydantic para las filas, retornos anotados, imports al tope del módulo, `def` en vez de `lambda`. Es trabajo extra real sobre "copiar idéntico" — presupuestarlo. |
| **H6** | **CI no levanta Postgres ni tiene las BDs auxiliares.** | `.github/workflows/ci.yml` (jobs sin `services:`), `conftest.py` solo parchea `db_auth`. | Cualquier test de F2 que ejecute un endpoint con `Depends(get_prod_db)` / `get_ops_db` / SQLite de diferidas intenta salir a la red → **CI rojo**. | Los **5 archivos de test del origen son puros** (no tocan BD): se portan primero y dan cobertura sin infraestructura. Los tests de endpoint usan `app.dependency_overrides` (Bloque 1b). |
| **H7** | **La cobertura cuenta la feature nueva y F2 mete ~3.200 líneas de backend.** | `pyproject.toml` `fail_under=75`; `vitest.config.ts` `thresholds 80×4`. | F2 sin tests **hunde la cobertura global bajo el umbral** → build rojo aunque el código funcione. Es el riesgo nº1 de esta fase. | Tests obligatorios por bloque, no al final. El bloque no se cierra sin su suite en verde. |
| **H8** | 🔴 **La BD de diferidas de 954 MB está CORRUPTA.** `PRAGMA quick_check` devuelve `Tree 1389 page 120706/120707/120708: btreeInitPage() returns error code 11`; cualquier `SELECT count(*) FROM AVM_DATADIF` lanza `database disk image is malformed`. Y la alternativa **`ECP_DIFERIDAS_slim.db` (192 MB, 1.142.599 filas) está sana pero NO tiene `ACEITE_PERDIDO` ni `GAS_PERDIDO`** (solo 8 columnas: CAMPO, AREA, COMPLETION, EVENT_DATE, INI_DATE, END_DATE, CAUSE_NIVEL2, CAUSE_NIVEL4). | Inspección directa hoy de `data/ECP_DIFERIDAS/{ECP_DIFERIDAS.db, ECP_DIFERIDAS_slim.db}`. | El bloque **`impacto`** de `/diferidas/frecuencia` (`SUM(ACEITE_PERDIDO)`, `SUM(GAS_PERDIDO)`) **no se puede calcular con ninguna de las dos BDs actuales**. Portarlo a ciegas da un 500 o un panel vacío sin explicación. | **DA-4 (§10) requiere decisión del usuario.** El plan entrega los otros 3 bloques (pareto/tendencia/pozos) contra la **slim**, y deja `impacto` detrás de una degradación declarada hasta resolver la fuente. Ver §5.7 con las 3 vías. |
| **H9** | **`OPS_DATABASE_URL` está VACÍA en el `.env` de destino** — EBITDA no tiene fuente. | `prodia_v02_backend/.env` línea `OPS_DATABASE_URL=`. El valor conocido está en `Des_robustez_2.0/robustez_v02_backend/.env` (`postgresql://robustez:***@localhost:5432/robustez_v02?sslmode=disable`, con la variante `@10.100.26.139` comentada). | `/ebitda/unificado-waterfall` devuelve 503 siempre. | **Prerequisito P6**: configurar `OPS_DATABASE_URL` antes del bloque de EBITDA. `src/core/config.py:47` ya declara el campo. |
| **H10** | **Sin VPN, el Postgres 139 no responde** (verificado hoy: `timeout expired` a `10.100.26.139:5432`). | Ejecución de `check_prod_connection` equivalente, hoy, desde esta máquina. | Todo F2 lee de ese Postgres. El desarrollo puede avanzar, la **verificación R3 no**. | Mismo bloqueo que P3 de F1: el Bloque 0 exige VPN en la máquina de pruebas. |
| **H11** | **Dos fuentes distintas para "campos de un activo".** El backend FastAPI usa `core.map_campo_activo` (migración 008, *"fuente ÚNICA de la composición del activo"*); las rutas Flask nativas de diferidas/mantenimientos usan `data/Activo_campo.csv`. | `resolver.py:106-142` vs `routes/api.py:393,399-411`. | Portar ambas deja el panel de Diferidas discrepando del tablero para el mismo activo — el bug que `map_campo_activo` existe para evitar. | **Una sola fuente:** `shared/catalogo_entidades.campos_de_activo()` (Postgres). El CSV **no se porta**. Si Postgres está caído, el panel degrada (no cae a un CSV con otro contenido). |
| **H12** | **El LLM se llama con `urllib` BLOQUEANTE dentro de un endpoint `def` sync**, con `timeout=180`. | `api.py:1110-1160` (`_urlreq.urlopen`), `api.py:1957`, `api.py:2368`. | Un `async def` con esa llamada **bloquearía el event loop de FastAPI** y colgaría toda la app. Un `def` sync la manda al threadpool (por defecto 40 hilos) — aceptable, pero con 180 s por llamada y sin caché se agota. | Los endpoints que llaman al LLM se declaran **`def` (sync), nunca `async def`**, y **siempre** detrás de la caché de H4. Documentarlo en el código. |
| **H13** | **`_estado()` (90/75) y `_estado_cierre()` (banda ámbar 93 %) son dos ejes de estado DISTINTOS que conviven a propósito.** | `api.py:676-679` vs `api.py:691-701`; comentario explícito en `api.py:681-688`: *"Eje de estado PROPIO … NO SE TOCA"*. | "Simplificar" unificándolos cambia el color de tarjetas ya calibradas contra mayo-2026 (Rubiales 95,6 % → ajustado; APIAY 50,7 % → actuar). | Se portan **los dos**, con sus umbrales, en el mismo módulo y con el comentario que explica por qué son dos. |
| **H14** | **F2 introduce 5 gráficos Plotly** (heatmap de densidad, curva diaria, ritmo mensual, waterfall EBITDA, pareto de diferidas). Las dependencias ya están instaladas. | `prodia_v02_frontend/package.json`: `plotly.js-dist-min ^2.35`, `react-plotly.js ^2.6`, `@types/react-plotly.js`. | **R2** (CLAUDE.md §0): un `data` memoizado que dependa de `selectedKey`/`hoveredKey` provoca bugs de re-render **garantizados**. | R2 es regla no negociable de F2 (§7). Cada gráfico documenta en un comentario de qué depende su `useMemo`. |
| **H15** | **`escenario_mes()` es un helper deliberadamente SIN `@router.get`** — lo consume el motor Q v2 (F4/Cuantificar) llamándolo como función. | `api.py:628-666`, con la nota `AF-4.11 — sin @router.get, para que llamarlo como función normal no filtre objetos Query`. | Convertirlo en endpoint o no portarlo deja a F4 sin la referencia OPERATIVO/CONTABLE. | Se porta como función pública de `services_desempeno.py`, **no** como ruta. Test de que no aparece en el OpenAPI. |
| **H16** | **`president` lee `core.fact_tabla_hoja`** — la misma tabla de 50M+ filas que consume la feature `tablas` de F1. | `api.py:2562-2619` vs `features/tablas/repositories.py:89-118`. | Riesgo de duplicar SQL entre dos features. | **No** se comparte código entre features (ADR-001): cada una tiene su consulta, con su propio `WHERE hoja='REPORTE_PRESIDENT'`. Es solape de tabla, no de lógica. |
| **H17** | **En el sistema viejo los paneles de análisis se pintan DENTRO del chat** (`cn-*` en `multitab_shell.js`), no en la pestaña Análisis (que solo tiene "Fundación de datos": catálogo/densidad/cobertura). | `multitab_shell.js:663-681` (pestaña Análisis) vs `1388-2530, 3400-3900` (tarjetas KPI, focos, pills, waterfall dentro del conversacional). | Copiar la ubicación del viejo metería F2 dentro del territorio de F4 (panel Insights de Consulta, hoy vacío). | **F2 entrega una sección propia `/analisis`** (mismo precedente que `/control` en F1: por URL, sin menú). F4 decidirá después si promueve componentes a `shared/`. Declarado en §9. |
| **H18** | `pnpm test -- --coverage` en `ci.yml:45` no propaga el flag (DT-6) y el `cache-dependency-path`/`--frozen-lockfile` apuntan a un lock inexistente (DT-5/H6-bis de F1). | `ci.yml:41-45`; no existe `prodia_v02_frontend/pnpm-lock.yaml`. | El job frontend de CI probablemente **ya falla en el install**; F2 nunca se validaría en CI. | Si F1 no lo corrigió ya (su Bloque 4), F2 lo hereda como prerequisito P11. **Requiere confirmación del usuario** (tocar CI está fuera del alcance de "portar Análisis"). |

---

## 1. Contexto

F2 porta el corazón analítico del sistema viejo: los paneles que responden *"¿cómo va el mes, qué
lo explica y cuánto cuesta"*. Es la fase más grande del roadmap después de F4, y la primera que
mezcla **cuatro fuentes de datos distintas** en una sola pantalla.

### 1.1 Inventario de origen — medido, no estimado (2026-08-20)

| Archivo origen | Líneas | Qué aporta |
|---|---:|---|
| `INGESTA/Rep_Prod/backend/app/features/analisis/api.py` | **2.619** | Los 9 endpoints + 30 funciones auxiliares (ámbito, valle, gap, focos, tarjetas, prompts, composer determinista) |
| `INGESTA/Rep_Prod/backend/app/features/ebitda/api.py` | **123** | 1 endpoint waterfall Ingresos→NOPAT sobre `ops.*` |
| `routes/api.py:381-700` (Flask nativo, no proxy) | **320** | `/diferidas/frecuencia` + `/mantenimientos/eventos` |
| `routes/api.py:153-228` (caché TTL + single-flight) | **76** | A4 — hoy vive en el proxy que se retira |
| `INGESTA/…/features/consulta/resolver.py:91-181` + `normaliza.py` | **~97** | `norm`, `fuentes_de_activo`, `campos_de_activo`, índice cacheado |
| **Total backend a portar** | **~3.235** | |
| `tests/test_analisis_ejecutivo_tesis.py` | 151 | Reglas Q2/tesis + política de reintento del LLM (13 tests) |
| `tests/test_analisis_tarjetas_kpi.py` | 125 | Tarjetas KPI, `_estado_cierre`, unidades, focos por promedio (14 tests) |
| `tests/test_analisis_focos_gap.py` | 76 | Concentración, aritmética bruto/neto (4 tests) |
| `tests/test_analisis_focos_filiales.py` | 68 | Coherencia focos↔tarjetas en filiales (6 tests) |
| `tests/test_analisis_valle_atribucion.py` | 62 | Atribución honesta del comentario del valle (5 tests) |
| **Total tests a portar** | **482** (~42 tests) | **Todos son puros — no tocan BD** (H6) |

`static/js/multitab_shell.js` **no se porta** (§6 CLAUDE.md): es render por concatenación de
strings. Se usa **solo como especificación visual** de qué pinta cada panel.

### 1.2 Los 9 + 3 endpoints

| # | Endpoint origen | Motor de datos | LLM | Caché | Destino V02 |
|---|---|---|---|---|---|
| 1 | `GET /analisis/catalogo` | `db_prod` (`dim_fuente`, `dim_vicepresidencia`, `dim_empresa`) | no | no | `analisis` |
| 2 | `GET /analisis/densidad` | `db_prod` (`fact_produccion_dia_ecp`) | no | no | `analisis` |
| 3 | `GET /analisis/huella` | `db_prod` (facts ECP + `fact_programa_ecp`) | no | no | `analisis` |
| 4 | `GET /analisis/cobertura` | `db_prod` (`ingesta_log` + `bronze.hoja_landing`) | no | no | `analisis` |
| 5 | `GET /analisis/desempeno` | `db_prod` mes+día | no | **sí** (45 s) | `analisis` |
| 6 | `GET /analisis/desempeno_insight` | `db_prod` + comentarios | **sí** (60 s) | no (origen) → **sí** | `analisis` |
| 7 | `GET /analisis/ejecutivo` | `db_prod` completo | **sí** (180 s) | **sí** (200 s) | `analisis` |
| 8 | `GET /analisis/tendencia_filial` | `db_prod` (`fact_produccion_diaria`) | no | no | `analisis` |
| 9 | `GET /analisis/president` | `db_prod` (`fact_tabla_hoja`, hoja `REPORTE_PRESIDENT`) | no | **sí** (30 s) | `analisis` |
| 10 | `GET /ebitda/unificado-waterfall` | **`db_ops`** (`ops.financial_results`+`operating_costs`+`flow_rates`+`wells_attributes`) | no | no | `ebitda` |
| 11 | `GET /diferidas/frecuencia` | **SQLite `ECP_DIFERIDAS`** | no | sí (in-proc) | `diferidas` |
| 12 | `GET /mantenimientos/eventos` | **`Eventos_OW.xlsx`** | no | sí (singleton) | `mantenimientos` |

Los endpoints 5-9 aceptan además `segmento=filiales`, que **cambia por completo la fuente y las
reglas** (`fact_produccion_diaria`, meta = PROGRAMA o promedio 2026, sin PPTO, sin comentarios).

---

## 2. Objetivo

Entregar una sección **`/analisis`** en ProdIA V02 que reproduzca, con datos reales del 139:

1. **Fundación de datos** — catálogo de entidades (cardinalidad + colisiones + explorador por
   nivel), densidad temporal (heatmap + semáforo por familia estadística), huella y cobertura del
   reporte por hoja.
2. **Desempeño del mes** — KPIs REAL vs PPTO por producto, curva diaria, producción mensual del
   año, campos sin meta declarados (nunca inventados).
3. **Análisis ejecutivo** — tarjetas KPI de cierre con proyección, focos por producto (Crudo →
   Gas → Blancos, orden fijo), valle de crudo con su atribución, pace de cierre, y las 4 secciones
   (insights / oportunidades / puntos de atención / decisiones) generadas por el **composer
   determinista** (LLM = pulido opcional).
4. **Acordeón de foco** con las 4 pills: Comportamiento diario · **Diferidas** · **Mantenimientos**
   · **EBITDA-NOPAT**.
5. **Segmento Filiales** — panorama de las 3 filiales + panel de tendencia de una filial.
6. **Tarjeta P50** (compromiso corporativo, escala kbpe).

**Criterio de aceptación:** build verde + cobertura sobre umbral (L7) + **verificación humana en
navegador con datos del 139** (R3). Ancla de paridad obligatoria: `Castilla EBITDA = 78.629 kUSD`
(CLAUDE.md §6).

---

## 3. Prerequisitos verificables

El executor **debe confirmar cada uno antes de escribir código del bloque correspondiente**.

| # | Prerequisito | Cómo verificar | Estado auditado (2026-08-20) |
|---|---|---|---|
| P1 | F1 cerrado o congelado | `git status` limpio; `grep -c "tablas_router" src/main.py` | 🔴 **NO** — `features/tablas/` sin `api.py` y sin commitear (H1) |
| P2 | `db_prod` accesible con VPN | `uv run python -c "from src.shared.db_prod import check_prod_connection; print(check_prod_connection())"` | ⚠️ **PENDIENTE** — hoy `timeout expired` sin VPN (H10) |
| P3 | Tablas ECP existen y tienen datos | `SELECT count(*)` sobre `core.{dim_fuente,map_campo_activo,dim_vicepresidencia,dim_empresa,dim_escenario,dim_tipo_producto,fact_produccion_mes_ecp,fact_produccion_dia_ecp,fact_produccion_diaria,fact_programa_ecp,fact_comentarios_produccion,config_reporte,ingesta_log,fact_tabla_hoja}` + `bronze.hoja_landing` | ⚠️ **PENDIENTE** (bloqueado por P2) |
| P4 | La hoja `REPORTE_PRESIDENT` existe | `SELECT count(*) FROM core.fact_tabla_hoja WHERE hoja='REPORTE_PRESIDENT'` > 0 | ⚠️ PENDIENTE |
| P5 | `core.map_campo_activo` poblada (52 activos) | `SELECT count(DISTINCT activo) FROM core.map_campo_activo` | ⚠️ PENDIENTE |
| P6 | `OPS_DATABASE_URL` configurada | leer `.env`; el valor está en `Des_robustez_2.0/robustez_v02_backend/.env` | 🔴 **VACÍA** (H9) |
| P7 | `ops.*` accesible y con el mes objetivo | `SELECT count(*) FROM ops.financial_results WHERE year=:y AND month=:m` | ⚠️ PENDIENTE (bloqueado por P6) |
| P8 | Fuente de diferidas utilizable | `PRAGMA quick_check` sobre el `.db` elegido | 🔴 **954 MB CORRUPTA** · slim 192 MB sana pero **sin columnas de volumen** (H8) |
| P9 | `Eventos_OW.xlsx` disponible | `ls data/Eventos_OW.xlsx` | ✅ existe en origen (259.577 bytes, 2026-08-13) — hay que copiarlo a `prodia_v02_backend/data/` |
| P10 | Molde de feature backend/frontend | `src/features/auth/{api,schemas,services,repositories}.py`; `src/features/auth/{pages,components,hooks,services,mappers,types}` | ✅ auditado |
| P11 | CI capaz de validar F2 | `ci.yml` corregido (DT-5/DT-6/H18) | 🔴 pendiente — heredado de F1 §11 |
| P12 | Plotly instalado | `grep plotly prodia_v02_frontend/package.json` | ✅ `plotly.js-dist-min ^2.35` + `react-plotly.js ^2.6` + tipos |

**Bloqueantes duros:** P1 (antes de empezar), P2/P3 (antes de dar cualquier bloque por verificado),
P6 (antes del bloque EBITDA), P8 (antes del bloque Diferidas).

---

## 4. Inventario de archivos

### 4.1 Backend — `prodia_v02_backend/`

**CREAR — infraestructura compartida** (§5.1):

```
src/shared/catalogo_entidades.py     norm(), fuentes_de_activo(), campos_de_activo(),
                                     activo_de_campo(), índice con lock+doble chequeo (H2/H3/A1)
src/shared/db_ops.py                 engine PostgreSQL `robustez_v02` (ops.*), lazy, solo lectura (L4)
src/shared/db_diferidas.py           engine SQLite ECP_DIFERIDAS, lazy, read-only (`mode=ro`)
src/shared/cache_ttl.py              caché TTL + single-flight en el BACKEND (A4/H4)
src/shared/llm_client.py             cliente Ollama: extraer_json(), invocar(), política de
                                     reintento SOLO ante generacion_abortada (H12)
```

**CREAR — feature `analisis`** (split por sufijo, no subcarpetas — CLAUDE.md §6):

```
src/features/analisis/__init__.py
src/features/analisis/api.py                    los 9 endpoints, response_model, Depends
src/features/analisis/schemas.py                DTOs Pydantic de salida (todos)
src/features/analisis/repositories.py           SQL ECP (mes/día/comentarios/dims)
src/features/analisis/repositories_catalogo.py  SQL de catálogo/densidad/huella/cobertura
src/features/analisis/repositories_filiales.py  SQL sobre core.fact_produccion_diaria
src/features/analisis/services_catalogo.py      severidad de colisiones, semáforo, por_mes, rachas
src/features/analisis/services_desempeno.py     ámbito+periodo, KPIs, curva, ritmo, campos_sin_meta,
                                                escenario_mes() (helper NO endpoint — H15)
src/features/analisis/services_ejecutivo.py     valle, gap reconciliado, flags, tarjetas, focos,
                                                síntesis, situación general, composer determinista
src/features/analisis/services_filiales.py      intermedios, tendencia, serie mensual, focos filiales
src/features/analisis/prompts.py                los 4 prompts + reglas_tesis (prosa aislada)
```

**CREAR — features auxiliares:**

```
src/features/ebitda/{__init__,api,schemas,services,repositories}.py
src/features/diferidas/{__init__,api,schemas,services,repositories}.py
src/features/mantenimientos/{__init__,api,schemas,services,repositories}.py
```

**CREAR — tests:**

```
tests/unit/test_analisis_tesis.py            ← port de test_analisis_ejecutivo_tesis.py
tests/unit/test_analisis_tarjetas_kpi.py     ← port
tests/unit/test_analisis_focos_gap.py        ← port
tests/unit/test_analisis_focos_filiales.py   ← port
tests/unit/test_analisis_valle_atribucion.py ← port
tests/unit/test_cache_ttl.py                 NUEVO (A4: TTL, single-flight, no cachear errores)
tests/unit/test_llm_client.py                NUEVO (extraer_json + política de reintento)
tests/unit/test_catalogo_entidades.py        NUEVO (norm, lock, composición de activo)
tests/unit/test_mantenimientos_service.py    NUEVO (A2 evento abierto, A3 solape con el mes)
tests/integration/test_analisis_api.py       NUEVO (endpoints con dependency_overrides)
tests/integration/test_ebitda_api.py         NUEVO (503 si ops caído)
tests/integration/test_diferidas_api.py      NUEVO (degradación SIEMPRE 200)
```

**MODIFICAR:**

```
src/main.py            + 4 routers (analisis, ebitda, diferidas, mantenimientos) + OPENAPI_TAGS
                       lifespan: db_prod pasa a CRÍTICA *funcionalmente* pero SIN fail-fast (H9 de F1)
                       /health: añadir estado de db_ops y de las fuentes de fichero
src/core/config.py     + consulta_ollama_url, consulta_llm_model, consulta_keep_alive (+ property
                       keep_alive_ollama), ejecutivo_usar_llm, ejecutivo_fallback,
                       kpi_cierre_ambar_pct, analisis_cache_ttl_s, diferidas_db_path,
                       eventos_ow_path
prodia_v02_backend/.env(.example)  + OPS_DATABASE_URL, EJECUTIVO_USAR_LLM=false (dev),
                       CONSULTA_OLLAMA_URL, CONSULTA_LLM_MODEL, DIFERIDAS_DB_PATH, EVENTOS_OW_PATH
tests/conftest.py      + fixtures patch_prod_db / patch_ops_db / patch_diferidas_db /
                       stub_llm (§5.8)
pyproject.toml         (sin cambios de dependencias: openpyxl ya está; NO añadir `requests`,
                       el cliente LLM usa urllib de stdlib como el origen)
```

> **Nota:** `openpyxl>=3.1` **ya está** en `pyproject.toml` — mantenimientos no añade dependencias.

### 4.2 Frontend — `prodia_v02_frontend/`

**CREAR — feature `analisis`:**

```
src/features/analisis/pages/AnalisisPage.tsx (+ .module.scss, .test.tsx)   default export (lazy)
src/features/analisis/components/
  ├─ SelectorAmbito/            entidad + nivel + periodo + segmento (ecp|filiales)
  ├─ PanelFundacion/            catálogo · densidad · huella/cobertura (3 vistas conmutables)
  │   ├─ TarjetasCardinalidad/  clic → explorador de entidades del nivel
  │   ├─ TablaColisiones/       severidad dura|media|blanda
  │   ├─ HeatmapDensidad/       Plotly — R2
  │   └─ MapaCobertura/         hojas por categoría (5 categorías fijas)
  ├─ PanelDesempeno/
  │   ├─ KpisPorProducto/       REAL vs PPTO + cumplimiento
  │   ├─ CurvaDiaria/           Plotly — R2
  │   └─ RitmoMensual/          Plotly barras + línea de promedio — R2
  ├─ PanelEjecutivo/
  │   ├─ TarjetaKpiCierre/      anillo SVG (arco topa en 100 %, texto muestra el % real)
  │   ├─ TarjetaP50/            president, escala kbpe
  │   ├─ FocosProducto/         orden fijo CRUDO→GAS→BLANCOS
  │   ├─ SeccionesEjecutivas/   insights/oportunidades/puntos_atencion/decisiones
  │   └─ AcordeonFoco/          4 pills, carga PEREZOSA por pill
  │        ├─ PillComportamiento/
  │        ├─ PillDiferidas/    Plotly pareto — R2
  │        ├─ PillMantenimientos/
  │        └─ PillEbitda/       Plotly waterfall — R2
  └─ PanelFiliales/             panorama 3 filiales + tendencia de una
src/features/analisis/services/analisisService.ts   (+ ebitdaService, diferidasService,
                                                     mantenimientosService — todos por apiClient)
src/features/analisis/hooks/                        un hook React Query por endpoint
src/features/analisis/mappers/analisisMappers.ts    snake_case → camelCase
src/features/analisis/types/analisisTypes.ts        modelo de vista
```

**MODIFICAR:**

```
src/app/router.tsx            + { path: '/analisis', element: withSuspense(AnalisisPage) }
                                dentro de children (hereda ProtectedRoute + LayoutMain)
src/shared/types/api.d.ts     regenerar con `pnpm gen:types` tras cerrar el backend
src/shared/utils/format.ts    + formatBopd, formatKbpe (A5/C3: cada escala su formateador)
```

---

## 5. Especificación

### 5.1 `shared/catalogo_entidades.py` — resuelve H2/H3

Porta `resolver.py:91-181` + `normaliza.py`, **sin** las partes conversacionales (`buscar_en_texto`,
`termino_candidato`, `_STOP`, `resolver()`, `clave_fisica()` — todo eso es **F4**).

Expone exactamente:

```python
def norm(s: str) -> str                              # UPPER + trim + NFKD sin combining
def fuentes_de_activo(activo: str) -> list[int]      # vía core.map_campo_activo
def campos_de_activo(activo: str) -> list[str]
def activo_de_campo(campo: str) -> str | None
def reset_cache() -> None                            # solo para tests
```

Reglas obligatorias:

1. **Lock + doble chequeo** al construir el índice (H3, patrón A1). El comentario debe decir por qué.
2. **D-A3 preservada:** no se rescatan fuentes con `campo` NULL usando `nombre` — es ruido de
   ingesta y el rescate alteró cifras validadas (Chichimene +56.003 bl). Copiar el comentario.
3. El activo **NO** sale de `dim_fuente.activos` ni de `grupo1` — sale de `core.map_campo_activo`.
   Copiar el bloque de comentario de `resolver.py:7-16` íntegro: explica los 3 errores que costó.
4. Recibe la sesión/engine inyectado, no lo crea (igual que `tablas/repositories.py`).

### 5.2 `shared/cache_ttl.py` — resuelve H4/A4

Porta `routes/api.py:153-228` a un decorador/helper reutilizable:

```python
class CacheTTL:
    def __init__(self, ttl_s: int) -> None: ...
    def get_or_call(self, clave: str, fn: Callable[[], T], es_cacheable: Callable[[T], bool]) -> T
```

- **TTL** configurable (`ANALISIS_CACHE_TTL`, default **900 s** = 15 min; el reporte cambia 1 vez/día).
- **Single-flight**: un `Lock` por clave, con **double-check** tras adquirirlo.
- **Criterio de cacheabilidad portado tal cual** (`_analisis_es_cacheable`), traducido a la forma
  de respuesta de V02:
  - nunca cachear si `encontrada is False`, `sin_datos`, o hay error;
  - nunca cachear si `meta.generado_por == "error"` (Gemma falló);
  - nunca cachear un `president` con `productos == []`.
- La clave = `ruta + "?" + params ordenados` (idéntico al origen).
- **Test obligatorio** (`test_cache_ttl.py`): hit/miss, expiración, single-flight con 2 hilos,
  y que un payload de error **no** se cachea.

### 5.3 `shared/llm_client.py` — resuelve H12

Porta `_extraer_json` (`api.py:966-1008`), `_llm_insight` (`1092-1107`) y `_llm_insight_once`
(`1110-1160`). Las **4 trampas** del original se preservan con su comentario:

| Trampa | Regla |
|---|---|
| T1 | `format="json"` en el body de Ollama — elimina fences/prosa/comas rotas de raíz. |
| T2 | `num_ctx=8192` **explícito** — el default de Ollama (2048) corta el objeto a media llave y produce un falso "json_invalido". |
| T3 | `resp["done"] is False` = **generación abortada** → devolver `None` sin intentar parsear el fragmento. Culpar al JSON manda a depurar el prompt equivocado. |
| T4 | Reintento (`intentos=2`) **solo** ante `generacion_abortada`. Un `json_invalido` con `temperature=0` daría lo mismo: solo latencia. |

`extraer_json` conserva la tolerancia a fences, comillas tipográficas (`“ ” ‘ ’` → rectas), comas
finales y el balanceo de llaves respetando strings/escapes.

El `diag` (status, model, host, raw truncado a 2000, done_reason, out_tok, prompt_tok) **se
conserva y se expone en `meta.llm_diag`**: es lo que permite distinguir "Gemma se cayó" de "el
prompt está mal". Encaja con C2/N6 (el usuario ve el problema, no un error mudo).

### 5.4 Reglas de dominio del CLAUDE.md §7 → dónde aterrizan

| Regla | Dónde se implementa en F2 | Cómo se verifica |
|---|---|---|
| **A1** singleton bajo lock con doble chequeo | `mantenimientos/repositories.py` (`Eventos_OW.xlsx`, ~1,53 s) **y** `shared/catalogo_entidades.py` (H3) | `test_mantenimientos_service.py`: dos hilos → un solo parseo |
| **A2** `FinalizaEvento` vacío = evento **ABIERTO** (3.305 de 6.850 filas = 48 %) | `mantenimientos/services.py`; además los 5 años mal tecleados (2526/2626/3026/2016) se tratan como abiertos | test explícito con fila sin fin y con año absurdo |
| **A3** filtro por **solape con el mes analizado**, nunca contra `now()` | `mantenimientos/services.py`: `inicio < fin_mes AND (fin IS NULL OR fin >= ini_mes)` | test: contra `now()` quedan 3 eventos; contra el mes, 2.741 |
| **A4** caché TTL + single-flight **en el backend** | `shared/cache_ttl.py` (§5.2) | `test_cache_ttl.py` |
| **A5** cada producto con SU escala/formateador | backend: `_UNIDADES_PRODUCTO = {CRUDO:"bbl", BLANCOS:"bbl", GAS:"MSCF"}`; frontend: `formatBl`/`formatMscf`/`formatKbpe`/`formatBopd` | test de unidades por producto (ya existe en el port) |
| **A6** `_sanitize_col` antes de toda response numérica | `services_*.py` y `ebitda/services.py` (donde el origen usa `_san()` en SQL) | test unitario ya existente (`test_utils.py`) + uso en cada service |
| **Q2** REGLA CERO (no fabricar rezago) | `services_ejecutivo.situacion_general()` + `prompts.reglas_tesis()` | los 9 tests de `test_analisis_tesis.py` |

### 5.5 Backend — reglas de portado por endpoint

**Regla madre: el SQL se copia IDÉNTICO** (U3). Está probado contra 62M filas y cada `JOIN`/índice
es deliberado. Lo único que cambia: el origen abre `get_engine().connect()`; aquí la sesión llega
por `Depends(get_prod_db)` y el repositorio **nunca la crea ni la cierra**.

Los comentarios del origen que explican **por qué** una decisión es como es **se preservan
traducidos, no se resumen**. Son la memoria de bugs ya pagados. Lista mínima de comentarios que
NO pueden perderse:

| Ancla en origen | Qué explica |
|---|---|
| `api.py:525-529` (H1) | El `volumen` de cada producto vive en UN SOLO proceso → `SUM` sobre todos los procesos **no** doble-cuenta. **No filtrar por proceso.** |
| `api.py:541-543` (H2) | Día y mes usan **medidas distintas** para algunos productos (BLANCOS: día ≈1,9M vs mes ≈0,9M). Los KPIs salen 100 % de `mes`; `día` solo alimenta la curva. |
| `api.py:594-606` | El promedio diario del año **solo** se entrega si la curva diaria RECONCILIA con el mensual (`mtd <= esperado*1.15`). Si no, el frontend cae a la media del mes y su título NO dice "vs 2026". |
| `api.py:608-613` (D-A4) | Campos que producen **sin PPTO** se **declaran**, no se les inventa meta (se descartó `PPTO = 1.25*REAL`: hundía APIAY de 108,8 % a 63,0 % con 385.409 bl fabricados). |
| `api.py:324-326` (F1) | La métrica de cobertura es `COUNT(DISTINCT reporte_id)`, **no** `SUM(filas_insertadas)` (sobre-cuenta ~26×: 11,2M vs 435K reales). |
| `api.py:794-800` | En `fact_comentarios_produccion` el área trae el producto como sufijo (`CUPIAGUA (CRUDO)`) en 144 de 648 comentarios → `SPLIT_PART(area,'(',1)`. Sin esto el panel decía "sin evento asociado" con 18 comentarios disponibles. |
| `api.py:804-812` (INS-A) | Solo el **onset** del valle da eventos limpios; el rango completo repite el mismo evento cada día → ranking basura. |
| `api.py:919-948` | **Atribución honesta**: si el comentario es del grupo y no de la entidad, se dice explícitamente. Comparar por **base** (sin el sufijo de producto), o el comentario propio se degrada a "ajeno". |
| `api.py:1754-1758` | El ritmo diario por producto solo se expone si `mtd <= real*1.05`. Verificado mayo-2026: CRUDO 54,6 % y GAS 55,2 % reconcilian; **BLANCOS 183,7 % no** → sin ritmo diario. |
| `api.py:1816-1820` | Concentración = `|top3| / |Σ detractores brutos|`, no sobre el gap neto (daría >100 % con compensadores grandes). |
| `api.py:1836-1840` | `faltante_bruto + excedente_bruto = gap_total_campos` — aritmética auditable. Sin estos totales el panel mostraba −10.813.358 con un detalle que sumaba 19.814.696. |
| `api.py:2579-2584` | `reporte_id` es un **serial por orden de ingesta, NO cronológico** → ordenar por `fecha_reporte DESC`, nunca `MAX(reporte_id)`. |
| `api.py:1505-1510` | La concentración del foco se calcula sobre **los campos que se nombran**, no sobre un top-3 fijo (con 2 campos: 88,2 %, no 90,6 %). |
| `api.py:2284-2288` | Filiales sin PPTO → meta = **promedio mensual 2026**, y el mes en curso se lleva a **proyección de cierre** (comparar 17 días contra un mes entero daría ~55 % siempre). |
| `api.py:2546-2547` (slim) | `_fil_serie_mensual` excluye meses con <60 % de días (Nov-2025 = 1 día distorsionaba la tendencia). |

**Constantes que se portan con su valor exacto:**

| Constante | Valor | Origen |
|---|---|---|
| `MESES_ES` | lista 1-12 en español | `api.py:8` |
| `PRODUCTOS_VALIDOS` | `aceite→CRUDO`, `gas→GAS`, `blancos→BLANCOS` (**`agua` NO existe** en `dim_tipo_producto`) | `api.py:13-17` |
| umbral de valle | media × **0,997**, run contiguo ≥ **3** días, serie ≥ **5** puntos | `api.py:750-755` |
| `_estado` | ok ≥90 · warn ≥75 · alert <75 · `""` si `pct is None` | `api.py:676-679` |
| `kpi_cierre_ambar_pct` | **0,93** (alineado ≥meta · ajustado ≥meta×0,93 · actuar debajo) | config, `api.py:691-701` |
| `TOP_N` eventos del valle | **12** | `api.py:835` |
| flags | crítico <60 % · gap concentrado ≥70 % · pace exigente ≥10 % · reconciliado si desfase ≤2 % | `api.py:1349-1370`, `1829` |
| detractores/compensadores | top **3** / top **2** | `api.py:1813-1814` |
| `_FIL_BANDA_PCT` | **5,0 %** ("en línea") | `api.py:2430` |
| diferidas | años `2023/2024/2025` · top **8** grupos + "Otros" · top **6** causas de impacto · tendencia solo `empeora` (\|Δ\|>0,5 pp) | `routes/api.py:626,644,663,682` |
| mantenimientos | top **8** eventos, abiertos primero | `routes/api.py:546` |
| EBITDA | 18 componentes en orden fijo, signos `pos/negabs/neg/asis` | `ebitda/api.py:18-37` |
| statement_timeout | `40s` en huella, `60s` en cobertura | `api.py:200,317` |

**Tipado (H5):** cada consulta devuelve `Sequence[Mapping[str, Any]]` en el repositorio y el
service la convierte a un DTO tipado. Nada de `dict` suelto cruzando capas. Los `import calendar`
/ `import json` / `import re` dentro de funciones suben al tope del módulo. Los `lambda` asignados
a nombre pasan a `def`.

### 5.6 Política de LLM y caché por endpoint

| Endpoint | `def` sync (H12) | LLM | timeout | Caché TTL | Fallback |
|---|---|---|---|---|---|
| `/desempeno` | sí | no | — | 900 s | — |
| `/desempeno_insight` | sí | sí (lectura ejecutiva) | 60 s | **900 s (nuevo)** | prosa determinista compuesta en Python |
| `/ejecutivo` | sí | sí (4 secciones) | 180 s | 900 s | **composer determinista = entregable por defecto** |
| `/president` | sí | no | — | 900 s | — |
| resto | sí | no | — | no | — |

- `EJECUTIVO_USAR_LLM=false` en **desarrollo** (el qwen local confunde cifras y el gate solo valida
  estructura, no grounding). `true` en producción con `gemma4:latest`.
- `EJECUTIVO_FALLBACK=false` (solo pruebas) → si Gemma falla, `generado_por="error"` + `llm_diag`
  en vez de tapar el fallo con el texto base.
- El parámetro `pulir: bool = True` de `/ejecutivo` se **conserva**: F4 (Analizar) lo llamará con
  `pulir=False` para saltar el pulido de 180 s de una prosa que descarta (`api.py:1670-1673`).

### 5.7 Diferidas — las tres vías ante H8

`/diferidas/frecuencia` devuelve 4 bloques: `pareto` (N2 por año), `tendencia` (N4, solo los que
empeoran), `pozos_por_grupo`, e **`impacto`** (volumen perdido por causa, CRUDO/GAS).

| Vía | Qué implica | Coste | Riesgo |
|---|---|---|---|
| **V1 — recuperar la BD** | `sqlite3 ECP_DIFERIDAS.db ".recover" \| sqlite3 ECP_DIFERIDAS_recuperada.db`, luego regenerar una slim **incluyendo** `ACEITE_PERDIDO`/`GAS_PERDIDO` | ~1 h + espacio en disco | El `.recover` puede perder filas de las páginas dañadas (Tree 1389). Hay que reconciliar el conteo contra la slim sana (1.142.599 filas). |
| **V2 — regenerar desde la fuente original** | Volver a exportar `AVM_DATADIF` desde donde salió, con las 18 columnas | depende de disponibilidad de la fuente | La fuente puede no estar accesible. |
| **V3 — entregar sin `impacto`** | Los 3 bloques restantes contra la slim (sana, 1,14M filas); `impacto` degrada con `motivo` declarado en el JSON | inmediato | El panel pierde el "volumen perdido por causa" — un dato que el usuario ya usaba. |

**Recomendación del plan:** ejecutar **V3 ahora** (desbloquea el bloque completo) y **V1 en
paralelo** como tarea aparte. La degradación usa el contrato que el origen ya tiene: `sin_datos`
+ `motivo` con **HTTP 200 siempre** (nunca 500). El código queda escrito para las 18 columnas: en
cuanto la BD recuperada esté, `impacto` se enciende **sin tocar código**, solo cambiando
`DIFERIDAS_DB_PATH`.

Regla adicional (H11): el conjunto de campos de un activo sale de
`shared/catalogo_entidades.campos_de_activo()` (Postgres), **no** de `Activo_campo.csv`.

### 5.8 Infraestructura de test — resuelve H6

Añadir a `tests/conftest.py`, con el mismo estilo documentado de `patch_db_for_integration`:

```python
@pytest.fixture
def patch_prod_db(monkeypatch)      # app.dependency_overrides[get_prod_db] → sesión de test
@pytest.fixture
def patch_ops_db(monkeypatch)       # idem get_ops_db
@pytest.fixture
def patch_diferidas_db(tmp_path)    # SQLite temporal con AVM_DATADIF mínima (8 y 18 columnas)
@pytest.fixture
def stub_llm(monkeypatch)           # llm_client.invocar → respuesta fija; NUNCA sale a la red
@pytest.fixture
def eventos_ow_fake(tmp_path)       # .xlsx mínimo con fila abierta, cerrada y año corrupto
```

Reglas: **ningún test sale a la red** (ni Postgres, ni Ollama, ni ficheros de 192 MB). Todo test
declara `@pytest.mark.unit` o `@pytest.mark.integration` (`--strict-markers` está activo).

### 5.9 Frontend — reglas

1. **`multitab_shell.js` no se reutiliza.** Se lee como especificación de qué pinta cada panel;
   se reescribe en componentes React con el molde de `auth`/`consulta`.
2. **N1/C1** — todo service por `apiClient` (openapi-fetch). Cero `fetch` desnudo.
3. **C5** — cada fetch envuelto en `QueryState` (loading/error/vacío **con `correlation_id`**).
4. **C3/A5** — formateo por producto. Nunca un `formatNumber` genérico. El gas se muestra en MSCF
   **con la conversión ya aplicada por el backend** — el frontend no divide por 1e6.
5. **R2 (H14)** — el `data` memoizado de un gráfico Plotly **NUNCA** depende de estado de
   selección/hover. Cada `useMemo` lleva un comentario declarando sus dependencias reales.
6. **Carga perezosa del acordeón**: las pills Diferidas/Mantenimientos/EBITDA solo disparan su
   query cuando se muestran por primera vez (`enabled` de React Query). El origen ya lo hacía
   (`data-loaded="0"`) y es lo que evita 4 llamadas caras por cada foco.
7. **Scope explícito en las pills** — bug real del origen (`multitab_shell.js:3617-3619`): las
   pills leían el estado global del tablero, así que "Rubiales" mostraba las diferidas de
   "Castilla". En V02 la entidad/nivel **se pasan como props**, nunca se leen de un store global.
8. **Anillo de la tarjeta KPI**: el arco topa en 100 %, el texto muestra el % real (108 % se ve).
9. El **estado** de una tarjeta lo decide el **backend** (`estado`), no el frontend: derivarlo de
   `mes < histórico` marcaría un 94 % ajustado como rojo.
10. Ruta `/analisis` por URL, **sin entrada de menú** (mismo criterio que `/control` en F1).

---

## 6. Orden de ejecución

Un artefacto por turno. Verificación al final de cada bloque, con **el comando exacto de CI**.

### Bloque 0 — Prerequisitos (sin escribir código)

1. Cerrar o congelar F1 (P1). `git status` limpio.
2. En la máquina de pruebas **con VPN**: verificar P2 y P3 (conteos de las 14 tablas). Si falla,
   PARAR.
3. Configurar `OPS_DATABASE_URL` (P6) y verificar P7.
4. Decidir DA-4 (§10) sobre la fuente de diferidas; copiar el `.db` elegido y `Eventos_OW.xlsx` a
   `prodia_v02_backend/data/` (fuera de git — añadir al `.gitignore`).
5. Añadir a `core/config.py` + `.env` + `.env.example` las 9 variables nuevas (§4.1).

### Bloque 1 — Infraestructura compartida (sin endpoints todavía)

6. `shared/catalogo_entidades.py` + `tests/unit/test_catalogo_entidades.py`.
7. `shared/cache_ttl.py` + `tests/unit/test_cache_ttl.py`.
8. `shared/llm_client.py` + `tests/unit/test_llm_client.py`.
9. `shared/db_ops.py` y `shared/db_diferidas.py`.
10. Ampliar `tests/conftest.py` con los 5 fixtures de §5.8.
11. **Verificar:** `uv run ruff check . && uv run black --check . && uv run mypy src && uv run pytest --cov=src --cov-fail-under=75` — verde **sin red**.

### Bloque 2 — Port de los tests puros (antes que su código: son la especificación)

12. Portar los 5 archivos de test del origen a `tests/unit/`, adaptando imports a la nueva
    estructura y añadiendo el marker `@pytest.mark.unit`. Quedarán **rojos** (el código no existe):
    es correcto, sirven de contrato.

### Bloque 3 — `analisis` · Fundación de datos (sin LLM, sin filiales)

13. `schemas.py` (DTOs de catálogo/densidad/huella/cobertura).
14. `repositories_catalogo.py` (SQL de los 4 endpoints, idéntico al origen).
15. `services_catalogo.py` (severidad de colisiones, `por_mes`, racha máxima, semáforo de 5 familias).
16. `api.py` (endpoints 1-4) + registro en `main.py` + `OPENAPI_TAGS`.
17. Tests de integración de los 4 endpoints con `patch_prod_db`.
18. **Verificar** (comando de CI completo).

### Bloque 4 — `analisis` · Desempeño ECP

19. Ampliar `schemas.py`.
20. `repositories.py` (ámbito, KPIs mes, curva día, ritmo mensual, campos sin meta).
21. `services_desempeno.py` — incluye `parse_periodo`, `ambito` (nivel+periodo aware) y
    `escenario_mes()` **como función, no endpoint** (H15).
22. Endpoint `/desempeno` (con `segmento=ecp`; `filiales` llega en el Bloque 6) + caché TTL.
23. Tests. **Verificar.**

### Bloque 5 — `analisis` · Ejecutivo ECP (el bloque más denso)

24. `services_ejecutivo.py` parte 1: `detectar_valle`, `eventos_valle`, `comentarios_campo_mes`,
    `valle_diagnostico_entidad`, `nombres_entidad`.
25. `services_ejecutivo.py` parte 2: `gap_campo` reconciliado, `flags`, `tarjetas_kpi`,
    `estado_cierre`, `focos`, `sin_foco`.
26. `services_ejecutivo.py` parte 3: `situacion_general`, `sintesis`, `ejec_fallback` (composer
    determinista).
27. `prompts.py` (los 4 prompts + `reglas_tesis` ramificado).
28. Endpoints `/desempeno_insight` y `/ejecutivo` (con `pulir`) + caché TTL + `llm_diag`.
29. **Los 5 archivos de test del Bloque 2 deben pasar a verde aquí.** Añadir los de integración.
30. **Verificar.**

### Bloque 6 — `analisis` · Filiales + President

31. `repositories_filiales.py` + `services_filiales.py` (intermedios, `fil_tendencia`,
    `fil_serie_mensual`, `focos_filiales`, `sin_foco_filiales`, `valle_diagnostico_filiales`).
32. Ramas `segmento=filiales` de `/desempeno`, `/desempeno_insight`, `/ejecutivo`.
33. Endpoints `/tendencia_filial` y `/president`.
34. Tests. **Verificar.**

### Bloque 7 — Features auxiliares

35. `features/ebitda/` completa (18 componentes, signos, USD/BI, 503 claro si `ops` cae).
    **Ancla obligatoria: Castilla = 78.629 kUSD.**
36. `features/mantenimientos/` completa (A1 lock + A2 abiertos + A3 solape; **siempre 200**).
37. `features/diferidas/` completa (pareto/tendencia/pozos + `impacto` según DA-4; **siempre 200**).
38. Tests de los 3. **Verificar.**

### Bloque 8 — Tipos

39. `pnpm gen:types`; confirmar en el diff de `api.d.ts` los paths `/api/v1/{analisis,ebitda,diferidas,mantenimientos}/*`. Commitear `openapi.json` + `api.d.ts`.

### Bloque 9 — Frontend por paneles (uno por turno, con sus tests)

40. `types/` + `mappers/` + `services/` (4 services por `apiClient`).
41. `hooks/` (uno por endpoint, con `enabled` para la carga perezosa).
42. `SelectorAmbito` + `AnalisisPage` + ruta en `router.tsx`.
43. `PanelFundacion` (incluye el primer Plotly: heatmap — aplicar R2).
44. `PanelDesempeno` (curva diaria + ritmo mensual).
45. `PanelEjecutivo` sin acordeón (tarjetas KPI, P50, focos, secciones).
46. `AcordeonFoco` + las 4 pills (waterfall y pareto Plotly).
47. `PanelFiliales`.
48. **Verificar frontend:** `pnpm lint && pnpm typecheck && pnpm build && pnpm test:front` (80 %×4).

### Bloque 10 — Verificación end-to-end (R3)

49. `pnpm dev` en la máquina de pruebas **con VPN**. El usuario recorre `/analisis` y confirma:
    catálogo y colisiones · heatmap de densidad · cobertura por hoja · KPIs y curva del mes ·
    tarjetas de cierre con su anillo · focos en orden Crudo→Gas→Blancos · las 4 pills abren y
    cargan · waterfall EBITDA con **Castilla = 78.629 kUSD** · panorama de filiales · tarjeta P50.
50. **El usuario** marca F2 como verificada (R3 — build verde ≠ feature verificada).

---

## 7. Reglas no negociables

- **R1** — no tocar configuración de pnpm sin aprobación explícita.
- **R2** — ningún `data` memoizado de Plotly depende de `selectedKey`/`hoveredKey`. Los 5 gráficos
  de F2 lo documentan en un comentario.
- **R3** — F2 es casi toda interacción visual: el usuario verifica en navegador.
- **ADR-001** — cero imports cross-feature. Lo compartido va a `shared/` (es la razón de
  `catalogo_entidades.py`, H2).
- **U3** — mismo Postgres y mismo esquema: se reescribe la capa de acceso, **no el SQL**.
- **A1-A6** — las 6 reglas de dominio de §5.4, cada una con su test.
- **Q2 (REGLA CERO)** — si no hay rezago, se **declara**; jamás se fabrica un faltante. Python
  calcula la verdad, el prompt se ramifica sobre ella.
- **Python calcula, el LLM redacta** — ninguna cifra, fecha, etiqueta de estado o label de gráfico
  proviene del LLM. El composer determinista es el entregable por defecto.
- **Degradación 200** — `/diferidas` y `/mantenimientos` devuelven **siempre** HTTP 200 con
  `sin_datos` + `motivo`. Nunca 500 por un fichero ausente.
- **503 claro** — `/ebitda` responde 503 con mensaje si `ops` no está disponible; **el backend no
  hace fail-fast** en el lifespan por ninguna BD que no sea `db_auth`.
- **N1/C1** — todo service frontend por `apiClient`.
- **Ningún test sale a la red.**

---

## 8. Validaciones

**Por bloque** (comando exacto de CI, no variantes — `uv run pytest` a secas **no mide cobertura**):

```bash
# backend
uv run ruff check . && uv run black --check . && uv run mypy src
uv run pytest --cov=src --cov-fail-under=75
# frontend
pnpm lint && pnpm typecheck && pnpm build && pnpm test:front
```

**Funcionales:**

- `/docs` muestra los 12 endpoints bajo sus 4 tags.
- `/health` reporta `database_auth`, `database_prod` y (nuevo) `database_ops`.
- `escenario_mes` **no** aparece en `openapi.json` (H15).
- Con `EJECUTIVO_USAR_LLM=false`, `/ejecutivo` devuelve `secciones` completas y
  `meta.generado_por="fallback"` — nunca vacío.
- Segunda llamada idéntica a `/ejecutivo` dentro del TTL **no** vuelve a invocar al LLM
  (comprobable por latencia y por `llm_diag`).
- Anclas de paridad contra el sistema viejo: **Castilla EBITDA = 78.629 kUSD**; y para cualquier
  entidad, los KPIs de `/desempeno` deben coincidir con los del sistema viejo dígito a dígito.

---

## 9. Fuera de alcance (F2)

- **El chat, el historial y los insights conversacionales** — es **F4**. F2 solo entrega los
  endpoints y una sección `/analisis` propia (H17).
- **Menú de navegación** entre secciones (Consulta ↔ Control ↔ Análisis) — se hará cuando existan
  3-4 secciones. Se navega por URL.
- **RBAC de UI** (C4/DT-3).
- **Promover componentes de `analisis` a `shared/`** para que F4 los reutilice — lo decide F4.
- **El resto de `consulta/resolver.py`** (`resolver()`, `buscar_en_texto`, `clave_fisica`,
  `_STOP`) — F4.
- **Optimizar el SQL** — se porta idéntico.
- **Recuperar la BD de diferidas de 954 MB** — tarea aparte (§5.7 V1), no bloquea F2 si se
  acepta V3.
- **Escritura** de cualquier tipo: F2 es 100 % lectura.

---

## 10. Decisiones abiertas — requieren confirmación del usuario

| # | Decisión | Recomendación del plan |
|---|---|---|
| **DA-1** | ¿La sección vive en `/analisis` propia (como `/control`), o dentro del panel Insights de Consulta? | **`/analisis` propia.** Mismo precedente que F1; meterla en Consulta invade F4 (H17). |
| **DA-2** | ¿F2 se ejecuta como una sola fase o se corta en F2a (fundación) / F2b (desempeño+ejecutivo) / F2c (filiales+auxiliares) / F2d (frontend)? | **Cortar.** Los bloques de §6 ya están agrupados para eso; cada corte es entregable y verificable por separado. |
| **DA-3** | ¿`/analisis` es para todo usuario autenticado o solo admin? | **Todo autenticado** (coherente con DA-1 de F1: basta la sesión que ya exige el middleware). |
| **DA-4** | 🔴 **Fuente de diferidas** (H8): ¿V1 recuperar, V2 regenerar, o V3 entregar sin `impacto`? | **V3 ahora + V1 en paralelo.** El código queda listo para las 18 columnas; encender `impacto` será cambiar una ruta en el `.env`. |
| **DA-5** | ¿Se corrige `ci.yml` (DT-5/DT-6/H18) dentro de F2? | **Sí, en el Bloque 0** — si no, F2 nunca se valida en CI. Requiere aprobación explícita (tocar infraestructura). |
| **DA-6** | ¿`EJECUTIVO_USAR_LLM` en la máquina de pruebas? | **`false`** mientras se valida el portado (composer determinista, reproducible). Encenderlo solo al final, contra `gemma4:latest` del 139. |

---

## 11. Apéndice A — Mapa endpoint → tablas

| Endpoint | Tablas / fuentes |
|---|---|
| `/catalogo` | `core.dim_fuente`, `core.dim_vicepresidencia`, `core.dim_empresa` |
| `/densidad` | `core.fact_produccion_dia_ecp` (idx `dia_fecha`), `core.dim_fuente`, `core.dim_vicepresidencia` |
| `/huella` | `core.fact_produccion_dia_ecp`, `core.fact_produccion_mes_ecp`, `core.dim_escenario`, `core.fact_programa_ecp` |
| `/cobertura` | `core.ingesta_log`, `bronze.hoja_landing` (ILIKE sobre JSONB), + facts ECP para la presencia |
| `/desempeno` | `core.fact_produccion_mes_ecp`, `core.fact_produccion_dia_ecp`, `core.dim_tipo_producto`, `core.dim_escenario`, `core.dim_fuente`, `core.map_campo_activo` |
| `/desempeno_insight` | las anteriores + `core.fact_comentarios_produccion`, `core.config_reporte` |
| `/ejecutivo` | las anteriores (idénticas) |
| `/tendencia_filial` | `core.fact_produccion_diaria`, `core.dim_empresa`, `core.dim_tipo_producto` |
| `/president` | `core.fact_tabla_hoja` (hoja `REPORTE_PRESIDENT`), `core.config_reporte` |
| `/ebitda/unificado-waterfall` | `ops.financial_results`, `ops.operating_costs`, `ops.flow_rates`, `ops.wells_attributes` |
| `/diferidas/frecuencia` | SQLite `AVM_DATADIF` |
| `/mantenimientos/eventos` | `Eventos_OW.xlsx` (hoja `Sheet1`, cols 3/4/7/8/12/10/6) |

## 12. Apéndice B — Funciones del origen y su destino

| Origen (`analisis/api.py`) | Líneas | Destino |
|---|---|---|
| `_severidad`, `catalogo` | 20-90 | `services_catalogo` / `repositories_catalogo` |
| `densidad` | 93-187 | `services_catalogo` |
| `huella`, `_presencia_entidad`, `cobertura` | 190-348 | `services_catalogo` |
| `_NIVEL_COL_AMB`, `_parse_periodo`, `_ambito`, `_campos_sin_meta` | 361-478 | `services_desempeno` |
| `desempeno` | 486-625 | `api` + `services_desempeno` |
| `escenario_mes` | 635-666 | `services_desempeno` (**función, no ruta** — H15) |
| `_estado`, `_estado_cierre`, `_tarjetas_kpi`, `_UNIDADES_PRODUCTO` | 676-748 | `services_ejecutivo` |
| `_detectar_valle`, `_nombres_entidad`, `_eventos_valle`, `_comentarios_campo_mes`, `_valle_diagnostico_entidad` | 750-963 | `services_ejecutivo` |
| `_extraer_json`, `_llm_insight`, `_llm_insight_once` | 966-1160 | **`shared/llm_client`** |
| `_situacion_general`, `_reglas_tesis` | 1011-1089 | `services_ejecutivo` + `prompts` |
| `desempeno_insight` | 1163-1338 | `api` |
| `_flags_ejecutivo`, `_ejec_fallback`, `_focos`, `_sin_foco` | 1349-1581 | `services_ejecutivo` |
| `_fil_difs_por_producto`, `_focos_filiales`, `_sin_foco_filiales` | 1592-1657 | `services_filiales` |
| `ejecutivo` | 1660-1988 | `api` |
| `_fil_intermedios`, `_desempeno_filiales`, `_valle_diag_fallback`, `_valle_diagnostico_filiales`, `_desempeno_insight_filiales`, `_ejecutivo_filiales` | 2001-2422 | `services_filiales` |
| `_fil_tendencia`, `tendencia_filial`, `_fil_serie_mensual` | 2432-2559 | `services_filiales` + `api` |
| `president` | 2562-2619 | `api` + `repositories` |
