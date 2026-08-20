# Plan F5 — Test Clas · laboratorio del clasificador

> **Estado del plan: v2 — auditado contra los pipelines y corregido.** Los pasos 1-3 del flujo
> de 6 (Mapeo → Auditoría → Diagnóstico) se ejecutaron contra el código real el 2026-08-20: el
> origen en `12112025_prodIA/`, el destino en `ProdIA_V02/`, y **los seis pipelines
> configurados** (`ci.yml`, `.pre-commit-config.yaml`, `pyproject.toml`, `vitest.config.ts`,
> `alembic.ini`, `package.json`). Todos los números están **medidos**, no estimados.
>
> **⛔ LEE §0.1 ANTES DE NADA.** Este plan **no es ejecutable hoy**: F5 depende de F4, que no
> existe. El plan está escrito para ejecutarse el día que F4 cierre, y los prerequisitos de §3
> están redactados para **fallar en voz alta** si se intenta antes.
>
> ### Qué cambió de v1 a v2
>
> La auditoría de pipelines encontró **cinco incoherencias** en v1. Dos habrían roto el build:
>
> | # | Incoherencia de v1 | Corrección en v2 |
> |---|---|---|
> | **AP-7** | v1 daba por hecho que `import yaml` compila. **No compila**: `yaml` no trae `py.typed` y no está en los overrides de mypy → `mypy --strict` falla con *"Library stubs not installed"*. **Reproducido ejecutándolo** | `types-PyYAML` **ya declarado y verificado** (§0.4). Resuelto antes de escribir la fase |
> | **AP-8** | v1 decía «añadir `soloAdmin` a `ProtectedRoute`». Pero `ProtectedRoute` envuelve el **layout entero** (ruta pathless), no cada ruta: el flag se habría aplicado a todas las secciones | Guarda **separada** `RutaAdmin` para el elemento de la ruta (§5.8) |
> | **AP-9** | v1 prometía «estrenar el campo `code` y cerrar DT-4». `http_exception_handler` **nunca pasa `code`** — habría exigido construir un subsistema de excepciones de dominio entero | `Literal` en el query param: FastAPI valida y devuelve 422 con `errors[]`. Sin código nuevo, sin f-string, y DT-4 sigue honestamente abierta (§5.2) |
> | **AP-10** | v1 no mencionaba que el único usuario sembrado en la BD de tests es **admin**. El test de 403 no tenía cómo escribirse | Fixture aditivo, sin tocar `_seed_integration_db` (§0.4) |
> | **AP-11** | v1 no mencionaba el hook `gen-types-check`, que hace `git diff --exit-code` sobre `api.d.ts` | Paso explícito en B3 y en §8 |

---

## 0. Hallazgos de la auditoría — LEER PRIMERO

### 0.1 ⛔ H1 (bloqueante) — F5 no es una fase independiente: es la UI de revisión de F4

Test Clas **no clasifica nada**. Su chat de prueba llama a `POST /api/consulta2/preguntar`
(`multitab_shell.js:4619`), que en el origen es literalmente
`maquina_q.clasificar(texto, log=True)` (`consulta_v2/api.py:43-46`). Todo lo que F5 aporta es
el aparato de **juicio** sobre lo que ese motor decidió:

| Pieza de F5 | Qué necesita de F4 |
|---|---|
| Chat de prueba | `maquina_q.clasificar()` + `POST /preguntar` |
| Libreta tabulada | La tabla `clasificacion_log` **con tráfico dentro** |
| Control 2 (señales) | Filas `pendiente` que comparar entre sí |
| Control 3 (revisión por lotes) | Lo mismo |
| `cargar_golden_libreta.py` | `clasificar()` + `clasificacion_golden.yaml` |

Medido en el destino hoy: `ls src/features/ | grep -c '^consulta$'` → **0**. No hay motor, no
hay tabla, no hay tráfico. Ejecutar F5 antes de F4 produciría una pantalla que lista una tabla
vacía de una base que no existe.

**El roadmap de CLAUDE.md §10 ya lo dice** (`F5 … depende de F4`) y el plan de F4 delimita la
frontera con precisión en su §9: *"F5 (Test Clas): `/veredicto_lote`, `/log`,
`revisar_lote.py` y el Control 3. F4 deja la libreta escribiendo y el Control 1 (✓/✗ en la
burbuja); la revisión por lotes es F5."*

Este plan **respeta esa frontera exacta**. No adelanta nada de F4 ni la duplica.

### 0.2 Correcciones al inventario de CLAUDE.md §6

§6 **no tiene fila para Test Clas**: sus líneas están repartidas dentro de `consulta_v2/`
(que §6 cuenta como F4) y dentro de `multitab_shell.js` (que §6 marca como "se reescribe").
Medido el 2026-08-20:

| Pieza | Líneas | Fase real |
|---|---:|---|
| `consulta_v2/senales.py` | 110 | **F5** (Control 2, íntegro) |
| `consulta_v2/log.py` — parte de veredicto/listado | ~55 de 113 | **F5** (`marcar_sospecha`, `listar`, `_FILTROS`) |
| `consulta_v2/log.py` — parte de escritura | ~58 | F4 (`registrar`, `poner_veredicto`) |
| `consulta_v2/api.py` — `/log`, `/veredicto_lote`, `/senal` | ~34 de 91 | **F5** |
| `consulta_v2/golden/revisar_lote.py` | 90 | **F5** (Control 3, CLI) |
| `cargar_golden_libreta.py` | 78 | **F5** |
| `config/clasificacion_feedback.yaml` | 9 | **F5** |
| `multitab_shell.js:4551-4954` (chat de prueba + libreta + teclado + lote) | **404** | **F5**, se reescribe |
| `colapsable.css` — reglas `.tc-*` / `.v2-*` | 60 bloques | **F5**, se reescribe |

**Total F5 ≈ 376 líneas de Python portadas + ~404 de JS reescritas.** Es la fase más pequeña
después de F1. Añadir la fila a §6 al cerrar.

### 0.3 Hallazgos que condicionan la arquitectura (H2-H8)

#### H2 — La libreta ya no vive en PostgreSQL, y eso invalida la mitad del SQL del origen

DA-2 del plan de F4 (**cerrada** el 2026-08-20) mueve `clasificacion_log` a **`db_auth`, que es
SQLite**. El SQL del origen es PostgreSQL puro y **no corre tal cual**. Lo que rompe, medido
línea a línea:

| Origen | Dónde | Por qué falla en SQLite | Corrección |
|---|---|---|---|
| `now() - make_interval(secs => :win)` | `senales.py:56, 88, 106` | `make_interval` no existe | Calcular el instante **en Python** y pasarlo como parámetro |
| `now() - make_interval(days => :d)` | `senales.py:78` | idem | idem |
| `COUNT(*) FILTER (WHERE capa_resolutora='regex')` | `log.py:99` | Soportado solo desde SQLite 3.30 | `SUM(CASE WHEN … THEN 1 ELSE 0 END)` |
| `CAST(:pat AS JSONB)` | `log.py:32` (F4) | No hay JSONB | Ya es problema de F4; F5 solo **lee** ese campo como texto |
| `SELECT now() > :ts + make_interval(…)` | `senales.py:105-107` | Consulta a la BD para comparar dos fechas | Comparar en Python: **es una query de más por cada fila pendiente** |

Calcular las fechas en Python no es solo portabilidad: hace las tres señales **testeables sin
BD**, que es lo que hoy impide probarlas.

#### H3 — `listar()` interpola SQL con f-string

```python
cond = _FILTROS.get(filtro, "TRUE")
filas = c.execute(sa.text(f"""… WHERE {cond} …"""))     # log.py:85, 93
```

Hoy es seguro porque `cond` sale de un diccionario cerrado, pero el patrón es exactamente el
que no debe copiarse: basta que alguien añada un filtro que acepte un fragmento del cliente
para tener inyección. En V02: el filtro se **valida contra el mapa** y se responde `400` si no
está; la cláusula nunca se concatena desde nada que venga del request.

#### H4 — La calificación optimista del origen miente cuando falla la red

```js
fetch("/api/consulta2/veredicto", {...}).catch(function () {});   // :4816
```

`__tcCalificarLocal` pinta el veredicto **antes** del POST y descarta el error. Si el POST
falla, la fila queda "confirmada" en pantalla y `pendiente` en la base — y el revisor cree
haberla juzgado. Sobre un dato que **alimenta el crecimiento del golden**, es el peor sitio
posible para una mentira silenciosa.

En V02: mutación optimista **con rollback** (`onError` restaura la fila y avisa). La respuesta
instantánea se conserva; lo que se corrige es que el fallo sea visible.

#### H5 — El escaneo de señales corre dentro de cada `GET /log`

```python
@router.get("/log")
def listar_log(...):
    try:
        senales.escanear()          # api.py:88
    except Exception:
        pass
```

`escanear()` recorre todas las filas `pendiente` de los últimos 7 días y lanza **2 consultas
por fila**. Cada vez que el revisor pulsa un chip de filtro, se dispara entero. Con la libreta
en SQLite y unos miles de pendientes son miles de queries por clic.

La decisión de fondo del origen (P4: *sin scheduler*) es razonable y se conserva. Lo que cambia
es **cuándo**: `POST /senales/escanear` explícito, que la UI llama **una vez al abrir la
página**, no en cada lectura. `GET /log` queda como lectura pura. Y el resultado del escaneo se
devuelve (`{sospechas_nuevas: n}`) en vez de tragarse — un escaneo que falla siempre y nadie ve
es peor que no tenerlo.

#### H6 — «Confirmar todos los pendientes» confirma lo que nadie ha leído

```js
var items = __tcPendIds.map(function (id) { return {log_id: id, veredicto: "confirmado_revision"}; });
```

`__tcPendIds` son **las 100 filas que cargó el filtro actual** (`limit=100`), no las que el
revisor miró. Un clic estampa `confirmado_revision` —que `log.py:41` describe como *"la verdad
final"*— sobre 100 clasificaciones sin verlas. Ese es justo el dato que después decide qué
patrones crecen y qué casos entran al golden.

En V02, tres cambios y ninguno quita la comodidad:
1. El botón dice **cuántas** va a confirmar y **exige confirmación explícita** por encima de un
   umbral (20).
2. Se marca con `nota_revision = "confirmación masiva"`, para poder distinguirlas después.
3. Se ofrece además **«confirmar las visitadas»** (las que el cursor recorrió), que es la
   operación que el revisor cree estar haciendo.

#### H7 — El atajo de teclado se registra en `document` y nunca se quita

```js
document.addEventListener("keydown", __tcKeydown);   // :4884 — sin removeEventListener
```

Se protege filtrando por `state.activeTab !== "testclas"`. En React eso es un `useEffect` con
cleanup; sin él, pulsar `3` en cualquier otra página seguiría calificando filas.

#### H8 — Test Clas es admin-only en V02, y hoy no existe el andamiaje

CLAUDE.md §10 lo define como *admin-only*. El origen **no tiene autenticación de ningún tipo**
(CLAUDE.md §1: `grep -r "ldap\|jwt\|session\|HTTPBearer"` → 0 resultados), así que no hay nada
que portar: se construye.

Medido en el destino:
- Backend: `require_admin` **ya existe** (`shared/auth_guards.py:23`, `grep -c` → 1). Listo.
- Frontend: `ProtectedRoute` **no conoce admin** (`grep -c admin` → 0). Hay que añadir la
  variante.
- `MenuUsuario` **ya tiene el patrón** `soloAdmin` (`grep -c` → 4) con rutas `/admin`,
  `/settings`, `/help` que todavía dan 404. F5 añade su entrada ahí.

Esto cierra parcialmente **DT-3 / C4** (RBAC de UI), que sigue abierta desde F0 justamente por
no haber tenido nunca una sección con requisito propio.

### 0.4 Auditoría de los pipelines configurados (AP-1…AP-11)

Leídos y medidos uno a uno el 2026-08-20. Los cinco últimos son los que **corrigen v1**.

| # | Pipeline (verificado en) | Riesgo detectado | Resolución **antes** de codificar |
|---|---|---|---|
| AP-1 | `mypy src` **strict** + `plugins=["pydantic.mypy"]` (`pyproject.toml:87-95`) | El SQL de la libreta devuelve `Row`/`Mapping` sin tipar; en F1 esto ya costó una ronda | `TypedDict` para fila y resumen; nada de `dict[str, Any]` suelto |
| AP-2 | `uv run pytest --cov=src --cov-fail-under=75` (`ci.yml:37`) | `revisar_lote.py` es un CLI **interactivo** (`input()` en bucle). Bajo `src/` cuenta como código sin cubrir y hunde el umbral | Va a **`scripts/`** como `humo_ingesta.py` de F3: **verificado** que `--cov=src` no lo alcanza. Su lógica pura sí se extrae a `src` y sí se prueba |
| AP-3 | Hook `gen-types-check` → `pnpm run gen:types` → `scripts/export_openapi.py` → **importa `src.main`** | Si el `yaml.safe_load` de `senales.py` queda como constante de módulo, rompe CERO I/O al importar; el test-espía (`test_sin_io_al_importar.py`) lo caza | Conservar el singleton perezoso `_cfg()` del origen (`senales.py:30-34`) **tal cual**: aquí el origen ya lo hace bien |
| AP-4 | `vitest` `thresholds: {lines,branches,functions,statements: 80}` + `singleFork:true` | La libreta con teclado y rollback es la parte con más ramas. `singleFork` implica que **un fallo de importación contamina la corrida entera** (lección de F2) | `userEvent.keyboard` para `1/2/3/4/Enter/↑↓` + test de rollback. Sin imports pesados en la página |
| AP-5 | `alembic.ini` versiona **solo `db_auth`** | Coherente con DA-2 (la libreta está en `db_auth`): un índice nuevo sí puede versionarse | §4.3 — migración **solo si** la de F4 no indexó `veredicto` |
| AP-6 | `pnpm build` desde la raíz | Corregido el 2026-08-20 (DT-7): `build`/`build:front` ya existen | Nada que hacer, pero **no volver a tocarlo** (R1) |
| **AP-7** | `mypy --strict` vs. **PyYAML** | 🔴 **`import yaml` NO COMPILA.** `yaml` no trae `py.typed` y no está en `[[tool.mypy.overrides]]`. Reproducido con un módulo de prueba: `error: Library stubs not installed for "yaml" [import-untyped]`. Habría roto el pre-commit **y** CI en el primer commit de F5 (y de F4) | ✅ **Ya resuelto y verificado (2026-08-20)**: `types-PyYAML` declarado en `[project.optional-dependencies].dev` —el grupo que instala `uv sync --extra dev` de CI, **no** el `[dependency-groups]` que crea `uv add --dev` por defecto—. `mypy src` vuelve a *Success* |
| **AP-8** | `router.tsx` + `ProtectedRoute` | 🔴 v1 proponía `soloAdmin` en `ProtectedRoute`, pero **envuelve el layout entero** (ruta pathless con `children`): el flag habría restringido Consulta, Análisis e Ingesta a admins | Guarda **separada** `RutaAdmin`, aplicada solo al `element` de `/test-clas`. La autenticación ya la garantiza el ancestro (§5.8) |
| **AP-9** | `core/exceptions.py:51-60` | 🔴 v1 prometía «estrenar `code` y cerrar DT-4». `http_exception_handler` **descarta** cualquier `code`: solo `database_exception_handler` emite uno. Cumplirlo exigía un subsistema de excepciones de dominio | `Literal[...]` en el query param → FastAPI valida y devuelve **422 con `errors[]`**, que ya está en el contrato. Cero código nuevo. **DT-4 sigue abierta** y el plan lo dice (§5.2) |
| **AP-10** | `conftest.py:68-84` | 🔴 El único usuario sembrado es `test.user` con `is_admin=1`. **No hay forma de escribir el test de 403** sin tocar el seed compartido por 559 tests | Fixture **aditivo** `usuario_no_admin` que inserta su propia fila; `_seed_integration_db` **no se toca** (§8) |
| **AP-11** | Hook `gen-types-check`: `pnpm run gen:types && git diff --exit-code …/api.d.ts` | Se dispara con `^prodia_v02_backend/src/(main\|features)/.*\.py$` — o sea, con **todo** lo que toca F5. Si el ejecutor no regenera y **commitea** `api.d.ts`, el commit se rechaza | Paso explícito al final de B3 y en §8 |

### 0.5 Lo que este plan NO va a repetir del origen

`multitab_shell.js` guarda **HTML en el historial** y muta las burbujas con expresiones
regulares sobre strings:

```js
var rx = new RegExp('<div class="v2-verdict" id="v2v-' + logId + '">[\\s\\S]*?<\\/div>');
```

con un comentario que admite la fragilidad: *"⚠ La franja de veredicto NO puede contener `<div>`
anidados"*. En V02 el estado son **datos** y el render es una función pura de esos datos —
igual que ya decidió F4 en su §5.10. Si esta regla se rompe, F5 hereda el bug del origen entero.

---

## 1. Contexto

Test Clas es la pestaña con la que el equipo **audita al clasificador del Motor Q v2**. Su valor
no es la pantalla: es el **ciclo de crecimiento** que sostiene. El principio está escrito en el
propio origen (`log.py:8-10`):

> *"solo los casos VERIFICADOS alimentan el crecimiento de patrones y del golden. La libreta
> registra únicamente TRÁFICO REAL del API — el golden runner y los pytest llaman
> `clasificar(log=False)`."*

El ciclo tiene **tres jueces**, y F5 construye los dos que faltan:

| Control | Quién juzga | Veredicto que produce | Fase |
|---|---|---|---|
| **1** | El usuario, ✓/✗ en la burbuja del chat | `confirmado_usuario` · `corregido_usuario` | **F4** |
| **2** | Señal indirecta, automática | `sospecha` — **bandera de prioridad, NO veredicto** | **F5** |
| **3** | Revisión por lotes (la verdad final) | `confirmado_revision` · `corregido_revision` | **F5** |

El Control 2 merece subrayado: una sospecha **no corrige nada**. Su único efecto es subir el
caso al tope de la cola de revisión. Confundirla con un veredicto —tratarla como "el motor se
equivocó"— convierte una señal débil en dato de entrenamiento falso.

Las tres señales del Control 2, tal como están razonadas en el origen (`senales.py:4-15`):

1. **Reformulación inmediata** — el *mismo usuario* repite una pregunta muy parecida en ≤120 s.
   El emparejamiento es **por usuario, nunca por `conversation_id`** (H2 del origen): el flujo
   real cruza chats con IDs distintos —prueba en Test Clas, repite en Consulta— y por
   conversación no casaría jamás.
2. **Cambio a motor v1** — empujada por el frontend. **En V02 esta señal desaparece**: solo
   existe v2 (plan F4 §9). Se documenta y se retira, no se porta muerta.
3. **Abandono tras `desconocido`** — sin actividad posterior del usuario en ≥600 s. Con una
   excepción razonada que hay que conservar: si la salida fue `regex+filtro` (OUT por filtro de
   dominio), es una salida **confiada** — abandonar tras un off-topic es lo esperado, no un
   fallo. Solo cuenta si la resolvió el LLM.

---

## 2. Objetivo

Entregar el laboratorio del clasificador como sección **admin-only** de ProdIA V02:

1. **Chat de prueba** — clasificar preguntas sueltas o por lote, viendo la traza de qué capa
   resolvió (`regex` / `regex+filtro` / `llm` / `regex+llm`). Esa traza es diagnóstico: se
   muestra **aquí y solo aquí**, nunca en Consulta.
2. **Libreta tabulada** — el tráfico clasificado con sus veredictos, filtros
   (todas/pendientes/sospecha/corregidas), KPIs del ciclo (total · sin veredicto · **% resuelto
   por Capa 1**) y calificación rápida con ratón y con teclado.
3. **Control 2** — las dos señales indirectas vivas, con umbrales en YAML y **calculadas en
   Python** para poder probarlas sin base de datos.
4. **Control 3** — revisión por lotes: en la UI (calificación rápida) y como **CLI** para sesiones
   largas.
5. **Cargador del golden a la libreta** — para ver los 75 casos del examen junto al tráfico real,
   idempotente y sin ensuciar la cola de pendientes.

Criterio de aceptación de la fase: **el % resuelto por Capa 1 es visible y medible**, que es el
KPI que decide si hay que engordar patrones (regla A4 del origen: si regex resuelve <50 %, el
sistema depende demasiado del LLM).

---

## 3. Prerequisitos verificables

Ejecutar desde la raíz del repo. **Los cuatro primeros fallan hoy** — es intencional: son la
comprobación de que F4 cerró.

```bash
# ── Bloqueantes: F4 tiene que existir ───────────────────────────────────────
ls prodia_v02_backend/src/features/ | grep -c '^consulta$'                    # espera 1  (hoy: 0)
grep -c "def clasificar" prodia_v02_backend/src/features/consulta/maquina_q.py # espera >=1 (hoy: no existe)
grep -c "def registrar"  prodia_v02_backend/src/features/consulta/log.py       # espera 1  (hoy: no existe)
grep -rc "clasificacion_log" prodia_v02_backend/alembic/versions/              # espera >=1 (hoy: 0)

# ── Ya verdes hoy (2026-08-20): no tocar, solo confirmar que siguen ─────────
grep -c "def require_admin" prodia_v02_backend/src/shared/auth_guards.py       # espera 1  ✔
grep -c "pyyaml" prodia_v02_backend/pyproject.toml                             # espera 1  ✔
grep -ci "types-PyYAML" prodia_v02_backend/pyproject.toml                      # espera 1  ✔ AP-7
grep -c "soloAdmin" prodia_v02_frontend/src/app/layouts/components/MenuUsuario/MenuUsuario.tsx  # espera 4 ✔
grep -c "build:front" package.json                                             # espera 1  ✔ (DT-7)

# AP-7 — la comprobación que de verdad importa: que el stub esté INSTALADO por
# la vía que usa CI (`uv sync --extra dev`), no solo escrito en el pyproject.
cd prodia_v02_backend && uv sync --extra dev && uv run mypy src && cd ..   # espera "Success"

# ── Deben seguir en 0: tocarlos es un error, no una tarea (AP-8) ───────────
grep -c "admin" prodia_v02_frontend/src/shared/components/ProtectedRoute/ProtectedRoute.tsx  # espera 0, SIGUE en 0
grep -c "test-clas" prodia_v02_frontend/src/app/layouts/LayoutMain.tsx                       # espera 0, SIGUE en 0
```

**Si el primer bloque no da verde, el ejecutor debe detenerse y decirlo.** No hay forma parcial
de hacer F5: sin motor no hay clasificaciones que juzgar.

Verificación adicional antes de escribir la primera línea (§0.3 H2 depende de ello):

```bash
# ¿Dónde quedó realmente la libreta? DA-2 dice db_auth; confirmarlo contra el código de F4.
grep -rn "clasificacion_log" prodia_v02_backend/src/features/consulta/ | head
```

Si F4 la hubiera dejado en `db_prod` en vez de `db_auth`, **todo §0.3 H2 se invierte** (el SQL
del origen sirve tal cual) y este plan debe re-auditarse antes de ejecutarse.

---

## 4. Inventario de archivos

### 4.1 Backend — `src/features/consulta/` (se **amplía** lo de F4, no se crea feature nueva)

Test Clas no es una feature aparte: juzga a `consulta`. Crear `features/test_clas/` obligaría a
importar `consulta.log` desde fuera, violando **ADR-001** (cero imports cross-feature). Vive
dentro, separado por sufijo — el mismo criterio que F2 usó para partir `analisis`.

| Archivo | Acción | Origen | Notas |
|---|---|---|---|
| `log.py` | **ampliar** | `consulta_v2/log.py:61-113` | `marcar_sospecha`, `listar`, `_FILTROS` validados (H3) |
| `senales.py` | **nuevo** | `consulta_v2/senales.py` (110) | Sin la señal 2 (§1); fechas en Python (H2) |
| `api_revision.py` | **nuevo** | `consulta_v2/api.py:58-91` | `GET /log`, `POST /veredicto_lote`, `POST /senales/escanear`. Todo con `require_admin` |
| `schemas_revision.py` | **nuevo** | — | `TypedDict`/Pydantic de fila y resumen (AP-1) |
| `config/clasificacion_feedback.yaml` | **copiar** | idéntico (9) | Umbrales; carga perezosa (AP-3) |

### 4.2 Backend — `scripts/` (fuera de `--cov=src`, AP-2)

| Archivo | Origen | Notas |
|---|---|---|
| `scripts/revisar_lote.py` | `golden/revisar_lote.py` (90) | CLI interactivo del Control 3 |
| `scripts/cargar_golden_libreta.py` | `cargar_golden_libreta.py` (78) | Idempotente por `usuario='golden'` |

### 4.3 Migraciones

**Probablemente ninguna.** La tabla la crea F4 (su migración `0005`). F5 solo necesita que la
cola de revisión sea rápida. Verificar y actuar:

```bash
grep -c "create_index.*veredicto" prodia_v02_backend/alembic/versions/*clasificacion*
```

- `>= 1` → nada que hacer.
- `0` → migración `0006_indice_cola_revision`: índice sobre `(veredicto, ts)`, que es el
  `ORDER BY` de las dos consultas calientes (`log.listar` y `revisar_lote.cola`).

### 4.4 Frontend — `src/features/testclas/`

Sí es feature propia en el frontend: es una **página distinta con ruta propia**, y no comparte
estado con Consulta.

| Archivo | Notas |
|---|---|
| `types/testClasTypes.ts` | `FilaLibreta`, `Veredicto`, `Grupo`, `ResumenLibreta` |
| `mappers/testClasMappers.ts` | Degradación segura: veredicto desconocido → `pendiente` |
| `services/testClasService.ts` | 100 % `apiClient` (N1) |
| `hooks/useLibreta.ts` | TanStack Query + mutación optimista **con rollback** (H4) |
| `hooks/useTecladoRevision.ts` | `useEffect` con cleanup (H7) |
| `components/ChatPrueba/` | Chat + carga por lote con barra de progreso |
| `components/TablaLibreta/` | Tabla, filtros, cursor, calificación inline |
| `components/ResumenLibreta/` | Los 3 KPIs, con el de Capa 1 destacado |
| `pages/TestClasPage.tsx` | Dos columnas. **No importa nada de `features/consulta`** (ADR-001) |

### 4.5 Frontend — compartido

| Archivo | Acción |
|---|---|
| `shared/components/RutaAdmin/` | **Nuevo** — 4 archivos (`.tsx`, `index.ts`, `.test.tsx`). Guarda de rol, no de sesión (AP-8) |
| `app/router.tsx` | Ruta `/test-clas` con `<RutaAdmin>` en su `element` |
| `app/layouts/components/MenuUsuario/MenuUsuario.tsx` | Una entrada más en `ACCESOS`, `soloAdmin: true` |
| `shared/types/api.d.ts` | **Regenerado** por `pnpm gen:types` y **commiteado** (AP-11) |

⚠️ **`ProtectedRoute.tsx` NO se toca** y **`LayoutMain.SECCIONES` NO se toca** (AP-8, §5.8).

### 4.6 Backend — dependencias

| Archivo | Acción |
|---|---|
| `pyproject.toml` | ✅ **Ya hecho (2026-08-20)**: `types-PyYAML` en `[project.optional-dependencies].dev`. Sin esto, `mypy --strict` rechaza el primer `import yaml` (AP-7) |

---

## 5. Especificación

### 5.1 Las fechas se calculan en Python (H2)

Regla: **ninguna consulta de `senales.py` contiene aritmética de fechas**. El módulo calcula los
instantes y los pasa como parámetros.

```python
def _ventana(desde: datetime, segundos: int) -> datetime:
    return desde + timedelta(seconds=segundos)
```

Dos ganancias, ambas medibles: el SQL es portable entre SQLite y Postgres, y las tres señales se
prueban **sin base de datos** pasando fechas fijas. Hoy, en el origen, no hay ni un solo test de
`escanear()` — solo de `similitud()`.

`similitud()` se porta **literal**: es Jaccard sobre tokens normalizados, ya es pura, y sus
tests del origen (`test_consulta_v2_clasificador.py`) se portan con ella.

### 5.2 El filtro se valida en el borde, nunca se concatena (H3 · corregido por AP-9)

El origen hace `cond = _FILTROS.get(filtro, "TRUE")` y luego `f"… WHERE {cond} …"`. Un filtro con
errata devolvía silenciosamente **todas** las filas, y el revisor creía estar viendo solo las
sospechas. Dos defectos en una línea: fallback mudo e interpolación.

**v1 proponía** una excepción de dominio con `code`. **AP-9 lo descarta**: `http_exception_handler`
(`core/exceptions.py:51-60`) construye la respuesta con `_error_response(exc.status_code,
str(exc.detail))` — **sin `code`**. Emitirlo exigiría un handler y una jerarquía de excepciones
nuevos: demasiado andamiaje para validar un enum, y fuera del alcance de F5.

La solución correcta ya está en el framework: **tipar el parámetro**.

```python
FiltroLibreta = Literal["todas", "pendientes", "sospecha", "corregidas"]

@router.get("/log")
def listar_log(
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    filtro: FiltroLibreta = "todas",
) -> RespuestaLibreta: ...
```

FastAPI rechaza cualquier otro valor con **422 y el array `errors[]`**, que ya forma parte del
contrato uniforme desde F0 (`validation_exception_handler`). Y en la capa de datos:

```python
_FILTROS: dict[FiltroLibreta, str] = {...}   # clave TIPADA
cond = _FILTROS[filtro]                       # KeyError sería un bug nuestro, no del cliente
```

Tres ganancias sobre v1: cero código nuevo, el `Literal` viaja al **`api.d.ts` del frontend** (el
selector de filtros no puede mandar un valor inválido ni compilando), y mypy verifica la
exhaustividad del diccionario.

> **DT-4 sigue abierta.** Este plan **no** la cierra, y no debe decir que lo hace: se cerrará
> cuando una feature necesite de verdad distinguir tipos de error de negocio. Validar un enum no
> es ese caso.

El `limit` también se acota en el borde (`ge=1, le=500`) en vez de con el
`max(1, min(int(limit), 500))` del origen (`log.py:96`), que corregía en silencio un valor
absurdo en lugar de rechazarlo.

### 5.3 La sospecha nunca pisa un veredicto humano

Se conserva textualmente la guarda del origen (`log.py:69`):

```sql
WHERE id = :id AND veredicto = 'pendiente'
```

Con un test que lo fija: marcar sospecha sobre una fila ya `confirmado_usuario` **no la
cambia**. Es la diferencia entre una bandera de prioridad y un juez.

### 5.4 El escaneo es explícito (H5)

- `GET /log` → **lectura pura**, sin efectos.
- `POST /senales/escanear` → devuelve `{sospechas_nuevas: int, filas_revisadas: int}`.
- La página lo llama **una vez al montar**, no en cada cambio de filtro.
- Si falla, se ve: `QueryState` con el `correlation_id` (C2/C5). Nada de `except: pass`.

Se conserva el acotado del origen (H7 suyo): solo filas `pendiente` de los últimos
`escaneo_dias` (7 por defecto, en el YAML).

### 5.5 Calificación optimista con rollback (H4)

```ts
useMutation({
  mutationFn: enviarVeredicto,
  onMutate: async (v) => {
    await qc.cancelQueries({ queryKey: ['libreta'] });
    const previo = qc.getQueryData(['libreta']);
    qc.setQueryData(['libreta'], aplicarVeredicto(v));
    return { previo };                       // ← lo que permite deshacer
  },
  onError: (_e, _v, ctx) => {
    qc.setQueryData(['libreta'], ctx?.previo);
    avisar('No se pudo guardar el veredicto. La fila sigue pendiente.');
  },
  onSettled: () => qc.invalidateQueries({ queryKey: ['libreta'] }),
});
```

El test que lo fija: mutación que rechaza → la fila **vuelve** a pendiente y aparece el aviso.
Sin ese test, la corrección de H4 se pierde en el primer refactor.

### 5.6 La confirmación masiva se declara (H6)

| Situación | Conducta |
|---|---|
| ≤ 20 pendientes | Botón directo: «Confirmar los 14 pendientes» |
| > 20 pendientes | Diálogo con el número explícito: *«Vas a marcar 100 clasificaciones como correctas sin revisarlas una a una. Esto alimenta el golden. ¿Seguro?»* |
| Siempre | `nota_revision = "confirmación masiva"` |
| Alternativa | Botón «Confirmar las visitadas (N)» — solo las que el cursor recorrió |

`veredicto_lote` conserva del origen la propiedad buena: **una fila inválida no tumba el resto**,
y devuelve `{aplicados, total}`. Si `aplicados < total`, la UI lo dice — el origen lo devolvía y
lo ignoraba.

### 5.7 Teclado con cleanup (H7)

`useTecladoRevision` en un `useEffect` que registra en `document` y **devuelve el
`removeEventListener`**. Ignora el evento si el foco está en `input`/`textarea`/contenteditable
(se conserva esa guarda del origen, `:4877`).

Mapa idéntico al del origen, porque el revisor ya lo tiene en los dedos:
`1`=jerarquizar · `2`=cuantificar · `3`=analizar · `4`=desconocido · `Enter`=correcta ·
`↑↓`=mover. Y el detalle que hace usable el flujo: al calificar, el cursor **avanza solo** a la
siguiente pendiente.

### 5.8 Acceso admin en las dos capas (H8 · corregido por AP-8)

**Backend** — `dependencies=[Depends(require_admin)]` en el router de revisión. `require_admin`
ya existe (`shared/auth_guards.py:23`) y aplica el criterio aditivo de L10:
`user.is_admin OR user.group.is_admin`. Un no-admin recibe **403**, no una lista vacía: un
permiso que se manifiesta como "no hay datos" es indistinguible de un bug.

**Frontend — aquí v1 se equivocaba.** `ProtectedRoute` **no** envuelve rutas individuales:
envuelve el **layout entero**, en una ruta pathless (`router.tsx:20-24`):

```tsx
{
  element: (<ProtectedRoute>{withSuspense(LayoutMain)}</ProtectedRoute>),
  children: [ '/', '/analisis', '/ingesta', … ],
}
```

Añadirle `soloAdmin` habría restringido **Consulta, Análisis e Ingesta** a administradores. La
guarda va en el `element` de la ruta, no en el ancestro:

```tsx
// shared/components/RutaAdmin/RutaAdmin.tsx
// Solo comprueba el rol: la AUTENTICACIÓN ya la garantiza el ProtectedRoute
// que envuelve al layout. Duplicarla aquí repetiría el spinner de `isHydrated`.
export function RutaAdmin({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  if (!user?.isAdmin) return <Navigate to="/" replace />;
  return <>{children}</>;
}
```

```tsx
{ path: '/test-clas', element: <RutaAdmin>{withSuspense(TestClasPage)}</RutaAdmin> },
```

**Menú** — entrada con `soloAdmin: true` en `MenuUsuario.ACCESOS`, que ya filtra por ese flag
(`MenuUsuario.tsx:31`). Es el primer uso real del patrón: `/admin` existe en la lista pero su
ruta todavía da 404.

**No se toca `SECCIONES` de `LayoutMain`**: esa lista no sabe de permisos y su test
(`LayoutMain.test.tsx:98`) afirma qué secciones ofrece el header. Test Clas es una herramienta
de administración, no una sección del producto — su sitio es el menú de usuario.

El backend es la autoridad; el frontend solo evita ofrecer una puerta cerrada. Nunca al revés:
el origen decidía autorización en el cliente comparando el nombre propio del usuario
(`=== "javier guerrero"`, ver plan F4 §5.10).

### 5.9 El cargador del golden

Se porta conservando sus tres propiedades, que están bien pensadas:

1. **Idempotente**: borra `WHERE usuario='golden'` antes de insertar. Solo toca lo que él creó.
2. **Distinguible**: `usuario='golden'`, `conversation_id='golden'`.
3. **Fuera de la cola**: cada fila se marca confirmada o corregida según el YAML, así que **no
   entra a pendientes** — la cola sigue mostrando solo lo que de verdad falta revisar.

Añadido de V02: **se niega a correr si la BD objetivo no es la esperada**, igual que
`humo_ingesta.py` de F3 comprueba que la URL es local antes de escribir. El script del origen
imprime el host y confía.

### 5.10 Del frontend del origen: qué se conserva y qué no

| Del origen | En F5 |
|---|---|
| Carga por lote **en serie** (una a una) | ✅ Se conserva: si una tropieza con el LLM frío, solo falla esa. La razón está escrita en `:4665` |
| Dedup de líneas preservando orden (`:4641`) | ✅ Se conserva |
| Pintado en vivo de la fila recién clasificada | ✅ Se conserva (es lo que hace el lote soportable) |
| KPI **% resuelto por Capa 1** destacado | ✅ Se conserva: es el KPI de la fase |
| Sospecha pintada como *pendiente con bandera* | ✅ Se conserva — refleja que no es un veredicto |
| Historial como **HTML** + regex para mutar | ❌ Datos + render puro (§0.5) |
| `catch(){}` en la calificación | ❌ Rollback visible (H4) |
| Confirmar-todo sin declarar el alcance | ❌ Declarado y acotado (H6) |
| `document.addEventListener` sin cleanup | ❌ `useEffect` con cleanup (H7) |
| Selector de motor v1/v2 y su `localStorage` | ❌ En V02 solo existe v2 |
| Señal 2 (cambio a v1) | ❌ Muere con v1 |

---

## 6. Orden de ejecución

**Un artefacto por turno.** Cada bloque termina con lint + typecheck + tests en verde antes de
pasar al siguiente.

| # | Bloque | Entrega | Se verifica con |
|---|---|---|---|
| **B0** | Prerequisitos | §3 completo en verde · confirmar dónde quedó la libreta · índice si falta · confirmar que `types-PyYAML` sigue declarado (AP-7) | Los `grep -c` de §3 + `uv run mypy src` |
| **B1** | `log.py` ampliado | `marcar_sospecha`, `listar` con `Literal` tipado, `TypedDict` de fila y resumen | Tests con `db_auth` en memoria (L2). Incluye el test de §5.3 |
| **B2** | `senales.py` | `similitud` (portada literal, con sus tests del origen) + señales 1 y 3 con fechas en Python | **Tests sin BD** para las ventanas; con BD en memoria para `escanear()` |
| **B3** | `api_revision.py` | Los 3 endpoints con `require_admin`. **Termina con `pnpm gen:types` y `api.d.ts` commiteado** (AP-11) | Test de **403 no-admin** (fixture de AP-10) y **422** por filtro inválido · `git diff --exit-code api.d.ts` limpio |
| **B4** | Scripts + **datos reales** | `revisar_lote.py` + `cargar_golden_libreta.py`, y **cargar los 75 casos del golden en una libreta de verdad** | Idempotencia (2ª pasada = mismos conteos) y cola vacía de pendientes |
| **B5** | Frontend base | tipos, mappers, service, `useLibreta` con rollback | Test de rollback (§5.5) |
| **B6** | `ChatPrueba` | Individual + lote en serie con progreso | Tests de componente |
| **B7** | `TablaLibreta` + teclado | Filtros, cursor, calificación, confirmación acotada | `userEvent.keyboard` (AP-4) |
| **B8** | `RutaAdmin` + cierre | Guarda **nueva** (no tocar `ProtectedRoute`), entrada de menú, CLAUDE.md §6/§10/§11, commit | Verificación final de §8 |

**Dos reglas de orden, ambas aprendidas pagando:**

1. **B3 no termina sin regenerar `api.d.ts`.** El hook `gen-types-check` compara con
   `git diff --exit-code`: si no se commitea, el commit se rechaza y el ejecutor pierde el turno
   depurando el hook en vez de la feature.
2. **B4 va antes que el frontend, no al final.** En F1 y en F3, el bloque contra datos reales fue
   el que encontró lo que ningún test encontró (la columna `VICE`, el `codigo` de
   `dim_vicepresidencia`, la transacción abortada). Aquí el equivalente es cargar el golden en
   una libreta de verdad. Dejarlo para el final porque "los tests están verdes" es exactamente el
   error que R3 previene.

**Regla aprendida en F3 y confirmada en F1:** el bloque de verificación contra datos reales
(**B4**, cargando el golden en una libreta de verdad) es el que encuentra lo que ningún test
encuentra. No dejarlo para el final ni saltárselo porque "los tests están verdes" (R3).

---

## 7. Reglas no negociables

1. **ADR-001** — `features/testclas` (frontend) no importa nada de `features/consulta`. En el
   backend, la revisión vive **dentro** de `consulta` por la misma razón.
2. **N1** — 100 % del acceso HTTP por `apiClient`. Ni un `fetch` desnudo.
3. **La sospecha no es un veredicto.** No corrige, no cierra el caso, no entra al golden. Solo
   prioriza.
4. **`confirmado_revision` es la verdad final.** Todo lo que lo produzca masivamente se declara
   al usuario y se marca en `nota_revision`.
5. **CERO I/O en tiempo de import** (AP-3). El YAML se carga perezoso.
6. **Ninguna aritmética de fechas dentro del SQL** (H2).
7. **El filtro es un `Literal` tipado en el borde** (H3/AP-9). Nunca f-string sobre entrada, y
   **nunca un fallback mudo** al filtro más permisivo.
8. **403, no lista vacía**, para el no-admin.
8b. **No se toca `ProtectedRoute` ni `LayoutMain.SECCIONES`** (AP-8): la guarda de rol es un
    componente nuevo. Tocar el ancestro restringiría las tres secciones existentes.
8c. **No se toca `_seed_integration_db`** (AP-10): el fixture del no-admin es aditivo y se limpia.
8d. **`api.d.ts` se regenera y se commitea** en cuanto cambie un endpoint (AP-11).
9. **El estado del chat son datos, nunca HTML** (§0.5).
10. **R1** — no se toca configuración de pnpm.
11. **R3** — la fase no se marca completa hasta que el usuario recorra la pantalla en navegador.
12. Todo en español: código, comentarios, commits, tests.

---

## 8. Validaciones

### Antes de commitear la fase — **lo mismo que corre `ci.yml`, en el mismo orden**

```bash
# Backend (ci.yml:14-37)
cd prodia_v02_backend
uv sync --extra dev                    # AP-7: verifica que types-PyYAML entra por aquí
uv run ruff check .
uv run black --check .
uv run mypy src                        # strict — falla si falta algún stub
uv run python scripts/export_openapi.py   # importa src.main: caza I/O en tiempo de import
uv run pytest --cov=src --cov-fail-under=75

# Frontend (ci.yml:40-70)
cd .. && pnpm lint && pnpm typecheck && pnpm build && pnpm test:front   # 80% x 4

# AP-11 — el hook que rechaza el commit si esto no está al día
pnpm run gen:types && git diff --exit-code prodia_v02_frontend/src/shared/types/api.d.ts
```

### El test de 403 y por qué necesita un fixture nuevo (AP-10)

`_seed_integration_db` (`conftest.py:68-84`) siembra **un** usuario, `test.user`, con
`is_admin=1`. No hay no-admin con quien probar el 403, y el engine SQLite es **de sesión**: una
fila insertada dentro de un test sobrevive a los siguientes.

El fixture es **aditivo y se limpia**; `_seed_integration_db` no se toca, porque lo comparten los
559 tests existentes:

```python
@pytest.fixture
def usuario_no_admin(integration_engine: Engine) -> Iterator[User]:
    """Un usuario sin privilegios, creado y retirado por el propio test.

    El engine es de SESIÓN: sin el borrado del final, esta fila quedaría visible
    para los tests siguientes y cualquiera que cuente usuarios empezaría a fallar
    por una causa que no está en su archivo.
    """
    ...
```

Sin ese `finally`, el fallo aparecería en otro archivo y el ejecutor lo buscaría donde no está.

### Verificación funcional (la que no dan los tests)

1. `uv run python scripts/cargar_golden_libreta.py` → **75 casos** cargados, ninguno en la cola
   de pendientes, segunda ejecución deja los mismos conteos (idempotencia).
2. `uv run python scripts/revisar_lote.py --lote 5` → la cola sale ordenada
   (sospecha → pendiente-LLM → resto) y las teclas escriben lo que dicen.
3. **% resuelto por Capa 1 visible** en la libreta, y coincide con lo que reporta
   `scripts/golden_consulta.py` de F4 sobre el mismo conjunto. Si difieren, uno de los dos
   miente.

### Verificación en navegador (R3 — la marca el usuario)

| # | Qué probar | Qué debe pasar |
|---|---|---|
| 1 | Entrar a `/test-clas` **sin ser admin** | Redirección, y la entrada no aparece en el menú |
| 2 | Clasificar una pregunta suelta | Burbuja con grupo, **traza de capa visible** y la fila al tope de la libreta |
| 3 | Lote de 20 preguntas | Barra de progreso avanzando, filas apareciendo una a una |
| 4 | Calificar con `1/2/3/4/Enter` | Veredicto instantáneo y el cursor avanza solo |
| 5 | **Cortar la red y calificar** | La fila **vuelve** a pendiente y aparece el aviso (H4) |
| 6 | «Confirmar todos» con >20 | Diálogo con el número explícito (H6) |
| 7 | Cambiar de filtro | No se dispara el escaneo (H5) |
| 8 | Pulsar `3` en `/analisis` | **No pasa nada** (H7) |

Los casos **5, 6, 7 y 8 son las cuatro correcciones al origen**. Si no se prueban, F5 entrega
los mismos bugs con otra sintaxis.

---

## 9. Fuera de alcance

- **Todo F4**: el motor, `/preguntar`, el Control 1, la memoria conversacional, los paneles de
  respuesta. F5 **consume**, no construye.
- **El crecimiento automático de patrones**. La libreta produce el dato verificado; convertirlo
  en patrones nuevos es trabajo humano y deliberado. Automatizarlo cerraría el bucle sin juez.
- **`consulta/` v1** y el selector de motor: congelados, no se migran.
- **El scheduler de señales**. P4 del origen (sin scheduler) se conserva; §5.4 solo cambia
  *cuándo* se dispara.
- **La señal 2** (cambio a v1): muere con v1.
- **`/admin`, `/settings`, `/help`**: siguen dando 404. F5 solo añade su propia entrada.

---

## 10. Decisiones abiertas

| # | Pregunta | Recomendación |
|---|---|---|
| **DB-1** | ¿La libreta muestra **solo tráfico propio** o el de todos los usuarios? El origen no distingue porque no tiene auth | **Todos.** Es una herramienta de auditoría del clasificador, no un historial personal; ya es admin-only |
| **DB-2** | ¿`limit=100` fijo, o paginación? | Empezar con 100 + **declarar el truncado** (mismo criterio que el `truncado` de F4). Paginar si estorba |
| **DB-3** | ¿El cargador del golden puede correr contra el 139? | **No por defecto.** Que exija `--confirmar-produccion`, igual que F3 protegió `humo_ingesta.py` |
| **DB-4** | ¿F5 cierra DT-3 (RBAC de UI) entera o solo su parte? | Solo su parte (`soloAdmin`). `useHasSection()` con los IDs del backend sigue pendiente hasta que haya secciones con permiso granular |
