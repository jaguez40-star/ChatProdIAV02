# Plan F6 — Corte · despliegue paralelo, paridad verificada y retiro del sistema viejo

> **Estado del plan: v1 — auditado contra el código real de AMBOS sistemas.** Los pasos 1-3 del
> flujo de 6 (Mapeo → Auditoría → Diagnóstico) se ejecutaron contra el código real: el destino en
> `ProdIA_V02/`, el origen en `12112025_prodIA/12112025_prodIA/`, y los seis pipelines configurados.
> Todos los números están **medidos**, no estimados.
>
> **Estado de ejecución (2026-08-20).** Los bloques **1, 2 y 3 están hechos** (commits `dfadab9`,
> `6965ed5`, `aaaa589`), y con ellos **B-3 y B-4 quedan cerrados**. F5 se completó, así que **B-2
> también cae**. Queda **B-1** (F1 sin frontend) y el Bloque 0 (R3 pendiente), que dependen de ti.
>
> | Bloqueante | Estado |
> |---|---|
> | B-1 · F1 sin frontend | ⛔ **abierto** — 7 endpoints sin consumidor |
> | B-2 · F5 al 0 % | ✅ **cerrado** — F5 completa (`df64d27`) |
> | B-3 · sin despliegue | ✅ **cerrado** — `Start_Prod.bat`, `desplegar_v02.bat`, `docs/DESPLIEGUE.md` |
> | B-4 · nadie sirve el `dist/` | ✅ **cerrado** — `StaticFiles` + fallback SPA, verificado contra servidor real |
>
> Lo que sigue bloqueado es el **Bloque 4** (paridad en el 139) y el **Bloque 5** (el corte).

---

## 0. Hallazgos de la auditoría — LEER PRIMERO

### 0.1 ⛔ Los cuatro bloqueantes (B-1…B-4)

Ninguno es opinable: los cuatro se midieron con `grep`/`ls` contra el código.

| # | Bloqueante | Evidencia medida | Sin resolverlo |
|---|---|---|---|
| **B-1** | **F1 no tiene frontend.** El backend `tablas` expone **7 endpoints** y **ningún componente los consume**. `features/control/` son **2 archivos muertos** (`controlMappers.ts` 119 L + `controlTypes.ts` 73 L = 192 líneas), sin páginas, sin servicios, sin tests. No hay ruta `/control` en `router.tsx` | `grep` de importadores de `controlMappers` fuera de su carpeta → **0** | La pestaña **Control** del sistema viejo no tiene reemplazo. No se puede retirar lo que no está portado |
| **B-2** | **F5 es 0 % código.** `senales.py` no existe, `require_admin` no se usa en `consulta/api.py`, no hay `GET /log`, no hay `RutaAdmin`, no hay `features/testclas` | Solo existe `Planes/plan_F5_test_clas_2026-08-20.md` | La pestaña **Test Clas** no tiene reemplazo |
| **B-3** | **No existe despliegue de producción.** 0 Dockerfile · 0 compose · 0 systemd · 0 nginx · 0 `deploy/` · 0 scripts `.sh` · 0 script `start`/`serve`/`deploy` en `package.json` | Los 2 `.bat` que hay son de **desarrollo**: `Start_Back.bat` usa `uvicorn --reload` y `Start_Front.bat` usa `pnpm run dev` (Vite dev server) | No hay con qué desplegar en el 139 |
| **B-4** | **Nadie sirve el frontend compilado.** `grep StaticFiles\|mount` en `src/main.py` → **0**. `apiClient` usa `baseUrl: '/'` (relativo) y el proxy `/api` vive **solo** en el dev server de Vite | Un `dist/` servido estáticamente **no alcanza el backend**. Y `createBrowserRouter` sin fallback a `index.html` da **404 del servidor** en `/analisis` | El frontend de producción no funciona |

**B-3 y B-4 son trabajo real de F6.** B-1 y B-2 son deuda de fases anteriores que F6 no puede
absorber sin dejar de ser un corte.

### 0.2 🔑 El hallazgo que redefine la fase (H1)

**F6 no es «apagar una aplicación». Es una cirugía de separación dentro de un proceso compartido.**

CLAUDE.md §1 dice que el chatbot clásico «es otra aplicación… sigue funcionando en paralelo». Es
cierto como *propósito*, pero **falso como topología**. Medido:

```
app.py (597 L) → socketio.run(app, host="0.0.0.0", port=8020)
   ├── main_bp        routes/main.py        131 L   /                 ← CHATBOT
   ├── chat_bp        routes/chat.py         63 L   /chat             ← CHATBOT
   ├── api_bp         routes/api.py       1.384 L   /api              ← MIXTO ⚠️
   ├── auth_bp        routes/auth.py        733 L   (sin prefijo)     ← CHATBOT (LDAP+SSO)
   └── colapsable_bp  routes/colapsable.py   52 L   /layout/colapsable ← ProdIA
```

Las dos aplicaciones **comparten proceso, archivo y pantalla**:

1. **Comparten proceso**: un solo `python app.py` en `:8020`. Apagarlo mata el chatbot.
2. **Comparten archivo**: `routes/api.py` tiene **26 rutas proxy a retirar** y **7 rutas nativas
   del chatbot a conservar** (`/api/ai/generate` importa 6 agentes de `chatbot/` en L863-868).
   Borrar el archivo mata el chatbot.
3. **Comparten pantalla**: `templates/main.html` —la raíz del chatbot— carga en el **mismo
   documento** `multitab_shell.js` (ProdIA) y `chat.js` (chatbot).

**La dirección del acoplamiento es la favorable**, y esto es lo que hace viable el corte:

```
routes/api.py  ──importa──>  chatbot/            (L863-868, 1196, 1287, 1291)
chatbot/       ──importa──>  INGESTA/            : 0  ✅
chatbot/       ──importa──>  routes/api.py       : 0  ✅
chatbot/       ──depende──>  puerto 8088         : 0  ✅
```

Lo que se retira depende del chatbot; el chatbot no depende de lo que se retira. **Por eso el
corte es posible sin tocar una línea de `chatbot/`.**

### 0.3 🔑 La frontera del frontend viejo, medida script por script (H2)

`templates/main.html` carga 6 módulos JS que *parecen* de ProdIA. **Tres no lo son.** Se midió
quién consume cada uno:

| Módulo | LOC | ¿Lo usa `chat.js`? | Veredicto |
|---|---:|---|---|
| `multitab_shell.js` | **5.308** | no | ✅ **RETIRAR** — y no usa nada del chatbot (`ReportCardFactory`/`AnalyticsManager` → 0) |
| `reportTabs.js` | 329 | **no** | ✅ **RETIRAR** — código muerto: su único consumidor es el `<script>` de `main.html` |
| `dailyPerformanceReport.js` | 730 | **no** | ✅ **RETIRAR** — idem |
| `monthlyBalanceReport.js` | 767 | **no** | ✅ **RETIRAR** — idem |
| `reportCards.js` | 1.374 | **SÍ** — define `ReportCardFactory`, usada **10 veces** | ⛔ **CONSERVAR** |
| `monthlyBalance.js` | 220 | **SÍ** — define `monthlyBalanceRenderer` (`chat.js:1623-1626`) | ⛔ **CONSERVAR** |
| `charts.js` | 2.014 | **SÍ** — 48 referencias, `AnalyticsManager` | ⛔ **CONSERVAR** |
| `colapsable.css` | 2.103 | — | ✅ **RETIRAR** |

🔑 **La trampa**: las dos únicas menciones textuales de `reportCards` en `chat.js` (L2054, L2060)
son **comentarios** que dicen *«REMOVED: … Moved to ReportCardFactory»*. Un `grep` ingenuo
concluiría que no hay dependencia y retiraría el archivo, **rompiendo 10 llamadas reales**. Por
eso la frontera se midió por *símbolo definido* (`class ReportCardFactory`), no por nombre de
archivo.

### 0.4 Auditoría de los pipelines configurados (AP-1…AP-6)

| # | Hallazgo | Evidencia | Corrección en el plan |
|---|---|---|---|
| **AP-1** | **El 139 no puede usar el trampoline de `uv`.** `iniciar_backends.bat` documenta que WDAC/Smart App Control/EDR corporativo bloquea `.venv\Scripts\python.exe` con **«os error 4551»**, y por eso arranca con el **intérprete base** + `PYTHONPATH` al `site-packages` | `iniciar_backends.bat` L20-27 | `Start_Prod.bat` de F6 **hereda ese rodeo**, con fallback a `uv run`. `Start_Back.bat` actual (`uv run` directo) **no sirve** en el 139 |
| **AP-2** | **El 139 despliega con `git pull`, no con zip.** `desplegar_version.bat`: git pull → migración → reinicio | `desplegar_version.bat` L24-50 | F6 hereda ese patrón. V02 **ya tiene remoto**: `origin` → `github.com/jaguez40-star/ChatProdIAV02.git`, rama `main` |
| **AP-3** | `ci.yml` **no despliega nada** — solo lint/typecheck/test/build | `.github/workflows/ci.yml` | F6 **no toca CI**. El despliegue es manual y auditado, igual que en el sistema viejo |
| **AP-4** | El hook `gen-types-check` se dispara con todo `src/(main|features)/**.py` y corre `pnpm run gen:types`, que **importa `src.main` entero** | `.pre-commit-config.yaml` | Si F6 monta `StaticFiles` en `main.py` (§5.2), el `dist/` **debe poder no existir** sin reventar el import. Regla no negociable nº 5 |
| **AP-5** | **Gate de cobertura GLOBAL**: backend `fail_under=75`, frontend 80 % × 4 | `pyproject.toml:114`, `vitest.config.ts:31` | F1-frontend (B-1) añadiría ~600 líneas de golpe. **Es el mismo riesgo AP-1 que ya ocurrió de verdad con F3** (78,97 % → 72,41 %, CI rojo). Verificar cobertura al cerrar **cada bloque** |
| **AP-6** | El test de navegación **no protege de verdad**. `LayoutMain.test.tsx` verifica que toda ruta tenga enlace, pero `RUTAS_DE_SECCION = ['/', '/analisis', '/ingesta']` está **hardcodeada dentro del test** | Medido en el archivo | Una ruta nueva (`/control`, `/testclas`) **no rompe el test**. F6 debe derivar la lista de `router.tsx`, o el olvido que ya ocurrió dos veces (F2 y F3) se repetirá |

### 0.4.1 🔑 Lo que solo apareció al EJECUTAR los bloques 1-3

Tres hallazgos que ningún análisis estático habría dado, y que justifican por sí solos haber
verificado contra un servidor real en vez de contra mocks:

| # | Hallazgo | Cómo apareció |
|---|---|---|
| **E-1** | **`AuthMiddleware` dejaba la aplicación INARRANCABLE en producción.** Protegía también los ficheros del frontend, así que un usuario sin sesión pedía `/` y recibía un **401 en vez de la pantalla de login** — sin forma de autenticarse. Ni el HTML ni el CSS de esa pantalla cargaban | Un test del Bloque 1 falló al pedir `/analisis`. Nunca se había visto porque en desarrollo Vite sirve los estáticos **sin pasar por el backend**: el fallo solo existe al servirlos desde FastAPI, que es justo lo que exige el despliegue. **Corrección**: los estáticos son públicos (los mismos ficheros que ya sirve Vite); deny-by-default sigue intacto en todo `/api/v1/*`, verificado con un 401 real |
| **E-2** | **AP-6 se cumplió por tercera vez, y el guardián propuesto tampoco servía.** F5 montó `/test-clas` sin enlazarla. Y al probar el test corregido comparando el header contra `secciones.ts`, **seguía sin detectar nada**: quitar una sección la quita de las dos listas a la vez | Se descubrió provocando el fallo a propósito. **Corrección**: `router.test.ts` compara las dos fuentes **reales** entre sí —las rutas que monta `router.tsx` contra las secciones declaradas—, no una lista escrita en el test. Verificado: añadir `/control` al router sin declararla rompe el build |
| **E-3** | `user` es `null` durante el logout mientras el layout sigue montado, así que `user.isAdmin` reventaba | Lo atrapó la suite existente al filtrar la navegación. Sin permiso conocido se muestran solo las secciones abiertas — nunca una admin |

🔑 E-2 es el más instructivo: **un guardián mal construido es peor que ninguno**, porque da la
sensación de estar protegido. El test anterior llevaba desde F1a en el repo, tenía un comentario
explicando que el olvido «ha pasado DOS veces»… y no atrapó la tercera.

### 0.5 Hallazgos de seguridad del sistema viejo (S1-S3)

No bloquean F6 — pero el corte es el momento en que estas quedan documentadas o se pierden.

| # | Hallazgo | Dónde |
|---|---|---|
| **S1** | **Bypass de LDAP activo en producción**: `.env` del 139 tiene `DEVELOPMENT_MODE=true` y `LOGIN_BYPASS_EMAILS=javier.guerrero@ecopetrol.com.co` → entra con cualquier contraseña. El propio `auth.py` L25-43 documenta que en producción deben ir vacías | sistema viejo |
| **S2** | `allow_unsafe_werkzeug=True` con `debug=True` y bind `0.0.0.0` en `:8020` — servidor de desarrollo sirviendo producción | `app.py:586-595` |
| **S3** | `/api/sql/execute` (L794) ejecuta **SQL arbitrario** contra `ECP_PROD.db`. **Se conserva** (es del chatbot), así que hay que verificar su gating al cortar | `routes/api.py:794` |

🔑 S1 y S2 son del chatbot, que **sobrevive al corte**. F6 no los arregla, pero **debe dejarlos
escritos**: al retirar ProdIA del proceso, el chatbot se queda solo con estas condiciones y sin
nadie que las recuerde.

### 0.6 Lo que V02 hereda mal de Robustez V02 (H3)

Robustez V02 es la plantilla del proyecto, pero **su despliegue no es replicable tal cual**:
`DEPLOY.bat` termina levantando el frontend con **Vite en modo dev** (`:6023`) y su backend
tampoco monta `StaticFiles` (`grep` → 0). Es decir, **la app más estable del equipo sirve
producción con un dev server**.

F6 **no hereda eso**. Sí hereda dos piezas útiles y probadas: `migra.py` (empaquetar) y
`deploy_zip.py` (desplegar), como alternativa al `git pull` cuando el 139 no tenga acceso a
GitHub.

---

## 1. Contexto

Las 5 pestañas del sistema viejo tienen hoy este estado real en V02:

| Pestaña vieja | Backend V02 | Frontend V02 | Ruta | ¿Reemplazable? |
|---|---|---|---|---|
| Ingesta | 3 endpoints ✅ | página + 3 componentes ✅ | `/ingesta` | ✅ sí |
| **Control** | **7 endpoints ✅** | **0 — 192 líneas muertas** | **✘** | ⛔ **NO (B-1)** |
| Análisis | 12 endpoints ✅ | página + 5 componentes ✅ | `/analisis` | ✅ sí |
| Consulta | 2 endpoints + 23 módulos ✅ | página + 5 componentes ✅ | `/` | ✅ sí |
| **Test Clas** | **0** | **0** | **✘** | ⛔ **NO (B-2)** |

**3 de 5 pestañas están listas. 2 no tienen una sola línea de frontend.**

Además, ninguna fase ha pasado R3 completo: DT-8 sigue abierta (panel Ejecutivo y las 4 pills sin
ejercitar contra el 139; ancla **Castilla = 78.629 kUSD** sin comprobar), F3 no se ha abierto en
navegador, y el golden de `clasificacion` está en **61/75 (81 %)** por falta de Ollama, sin correr
con modelo.

---

## 2. Objetivo

Dejar ProdIA V02 sirviendo en el 139 **en paralelo** al sistema viejo, verificar paridad con
anclas medibles, y **solo entonces** retirar quirúrgicamente la parte vieja de ProdIA **sin tocar
el chatbot clásico**, que sigue vivo en `:8020`.

**Criterio de terminación**: `http://10.100.26.139:6033` responde con las 5 secciones navegables,
las 3 anclas de paridad coinciden, y `multitab_shell.js` ya no se carga en `main.html` — con el
chatbot funcionando idéntico antes y después.

---

## 3. Prerequisitos verificables

Anclas `grep -c` contra el código real (CLAUDE.md §0 exige anclas, no hashes):

```bash
# ── Bloqueantes: los 4 deben cambiar de resultado antes del Bloque 1 ──

# B-1: F1 frontend debe existir
test -f prodia_v02_frontend/src/features/control/pages/ControlPage.tsx   # hoy: NO existe
grep -c "'/control'" prodia_v02_frontend/src/app/router.tsx              # hoy: 0

# B-2: F5 debe existir
test -f prodia_v02_backend/src/features/consulta/senales.py              # hoy: NO existe
grep -c "RutaAdmin" prodia_v02_frontend/src/app/router.tsx               # hoy: 0

# B-3: debe existir un arranque de PRODUCCIÓN (sin --reload, sin dev server)
grep -c "reload" prodia_v02_backend/Start_Back.bat                       # hoy: 1  ← es de dev
test -f Start_Prod.bat                                                   # hoy: NO existe

# B-4: alguien debe servir el frontend compilado
grep -c "StaticFiles" prodia_v02_backend/src/main.py                     # hoy: 0

# ── El origen está donde se cree (OJO: nivel EXTRA de anidamiento) ──
test -f "C:/APLICACIONES/ProdIA/12112025_prodIA/12112025_prodIA/app.py"

# La frontera del frontend viejo sigue siendo la medida en §0.3
cd "C:/APLICACIONES/ProdIA/12112025_prodIA/12112025_prodIA"
grep -c "ReportCardFactory"    static/js/chat.js          # 10  → reportCards.js SE CONSERVA
grep -c "monthlyBalanceRenderer" static/js/chat.js        # >=1 → monthlyBalance.js SE CONSERVA
grep -c "charts"               static/js/chat.js          # 48  → charts.js SE CONSERVA
grep -c "ReportCardFactory\|AnalyticsManager" static/js/multitab_shell.js   # 0 → autocontenido

# El chatbot NO depende de lo que se retira
grep -rc "INGESTA\|8088" chatbot/ --include="*.py" | grep -v ":0" | wc -l  # 0

# V02 tiene remoto para el `git pull` del 139 (AP-2)
git -C "C:/APLICACIONES/ProdIA/12112025_prodIA/ProdIA_V02" remote get-url origin
```

**Decisiones bloqueantes antes del Bloque 1** — ver §10: DC-1 (qué hacer con B-1/B-2), DC-2
(quién sirve los estáticos), DC-3 (puerto y coexistencia), DC-4 (P1 de CLAUDE.md, aún abierta).

---

## 4. Inventario de archivos

### 4.1 Backend V02 — nuevos y modificados

| Archivo | Acción | Por qué |
|---|---|---|
| `src/main.py` | **modificar** | Montar `StaticFiles` con fallback SPA (B-4/§5.2). Debe tolerar `dist/` ausente (AP-4) |
| `src/core/config.py` | **modificar** | `SERVE_STATIC: bool`, `STATIC_DIR: Path`, `cors_origins` para el 139 |
| `.env.example` | **modificar** | Bloque «Producción 139» con los valores reales documentados |
| `scripts/humo_paridad.py` | **nuevo** | Gate de paridad: compara V02 contra las 3 anclas (§5.4). Sigue el patrón ya probado de `humo_tablas.py` |

### 4.2 Raíz del repo V02

| Archivo | Acción | Por qué |
|---|---|---|
| `Start_Prod.bat` | **nuevo** | Arranque de producción: sin `--reload`, con el rodeo del trampoline (AP-1), `alembic upgrade head`, build del frontend |
| `desplegar_v02.bat` | **nuevo** | `git pull` → `uv sync` → `alembic upgrade head` → `pnpm build` → reinicio (AP-2) |
| `docs/DESPLIEGUE.md` | **nuevo** | Runbook: pasos, verificación, y **rollback** |

### 4.3 Sistema viejo — edición quirúrgica (Bloque 5, el último)

| Archivo | Acción | Detalle medido |
|---|---|---|
| `routes/api.py` | **editar** | Quitar **26 rutas proxy** + helpers `_DIF_DB`/`_MTTO_*` (L383-490) + rutas nativas L492 (`/mantenimientos/eventos`) y L562 (`/diferidas/frecuencia`). **Conservar las 7 del chatbot.** 1.384 L → ~600 L |
| `templates/main.html` | **editar** | Quitar **4** `<script>` (`multitab_shell`, `reportTabs`, `dailyPerformanceReport`, `monthlyBalanceReport`), el `<link>` de `colapsable.css` y el `<div id="multitab-shell-container">` (L35). **Conservar** `reportCards`, `monthlyBalance`, `charts`, `chat.js` |
| `app.py` | **editar** | Desregistrar `colapsable_bp` (1 línea) |
| `iniciar_backends.bat` | **editar** | Quitar el bloque INGESTA (:8088) |
| `desplegar_version.bat` | **editar** | Quitar el paso 2 (migración `006_ix_tabla_hoja_covering.sql`) |
| `routes/colapsable.py`, `Colapsable/`, `static/js/multitab_shell.js`, `reportTabs.js`, `dailyPerformanceReport.js`, `monthlyBalanceReport.js`, `static/css/colapsable.css`, `run.bat` | **borrar** | ~10.700 líneas |
| `INGESTA/Rep_Prod/` | **borrar** | Backend FastAPI :8088 completo + React |

**⛔ NO SE TOCA**: `chatbot/`, `routes/main.py`, `routes/chat.py`, `routes/auth.py`,
`static/js/chat.js`, `reportCards.js`, `monthlyBalance.js`, `charts.js`, `ECP_PROD.db`,
`ROBUSTEZ.db`, `chat_history.db`, las reglas de firewall de Ollama.

---

## 5. Especificación

### 5.1 Coexistencia — el corte es reversible hasta el Bloque 5

Los puertos **no chocan**: viejo `8020`/`8088`, V02 `6033`/`6034`. Ambos sistemas corren a la vez
durante toda la fase. El sistema viejo **solo se toca en el Bloque 5**, cuando la paridad ya está
verificada y firmada. Hasta ese momento, el rollback es *no hacer nada*.

### 5.2 B-4 — quién sirve el frontend (la decisión técnica central)

`apiClient` usa `baseUrl: '/'` y el proxy `/api` vive solo en Vite. Tres opciones reales:

| Opción | Cómo | Coste | Riesgo |
|---|---|---|---|
| **A — FastAPI sirve el `dist/`** ✅ recomendada | `StaticFiles` en `main.py` + fallback SPA a `index.html`. **Un solo puerto (6034)**, mismo origen → `baseUrl: '/'` funciona sin tocar nada, y **CORS deja de ser un problema** | ~25 líneas | Bajo |
| B — nginx delante | Reverse proxy: `/api` → 6034, resto → `dist/` | Instalar y configurar nginx en el 139 | Medio: pieza nueva en un servidor Windows corporativo |
| C — Vite dev en producción | Lo que hace Robustez V02 (§0.6) | 0 | **Alto** — dev server sirviendo producción |

**Recomendación: A.** Elimina B-4 y el problema de CORS de un golpe, no añade infraestructura, y
es el único que respeta el `baseUrl: '/'` ya escrito.

Tres requisitos no negociables de la opción A:

1. **El montaje va DESPUÉS de los routers** — si no, `StaticFiles` en `/` se traga `/api/v1/*`.
2. **Fallback SPA**: cualquier ruta no-API que no exista como fichero devuelve `index.html`, o
   `createBrowserRouter` da 404 del servidor al recargar en `/analisis`.
3. **Tolerar `dist/` ausente** (AP-4): en desarrollo no hay build, y el hook `gen-types-check`
   importa `src.main` en cada commit. Si el import revienta sin `dist/`, **bloquea todos los
   commits del repo**. Se monta solo si el directorio existe, y se declara en el log.

### 5.3 B-3 — arranque de producción con el rodeo del trampoline (AP-1)

`Start_Prod.bat` **no puede** ser `Start_Back.bat` sin `--reload`. En el 139, WDAC bloquea
`.venv\Scripts\python.exe` con «os error 4551». El sistema viejo ya resolvió esto y su solución se
hereda literal: leer el intérprete base de `pyvenv.cfg`, exportar `PYTHONPATH` al `site-packages`
del venv, y lanzar con ese intérprete. Fallback a `uv run` si no se halla el base.

Además: liberar los puertos antes de lanzar (`netstat` + `taskkill`, patrón de
`iniciar_backends.bat`), correr `alembic upgrade head`, y `pnpm build` antes de arrancar.

### 5.4 El gate de paridad — `scripts/humo_paridad.py`

Sigue el patrón ya probado de `humo_tablas.py` (solo lee, sale con código 1 si falla). Compara V02
contra las **3 anclas de CLAUDE.md §6**, que son el criterio de aceptación de la fase:

| Ancla | Valor esperado | Estado hoy |
|---|---|---|
| Castilla EBITDA | **78.629 kUSD** | ⏳ nunca comprobada (DT-8) |
| `DATOS_MES` | **7.776 filas** | ✅ verificada en F3 |
| `TD_datos_dia` | **5.209 filas** | ✅ verificada en F3 |

Más los 3 golden del Motor Q: `analizar` 10/10 ✅ · `cuantificar` 24/24 ✅ · `clasificacion`
**61/75, pendiente de correr con Ollama**.

🔑 El corte **no se ejecuta** si el ancla de Castilla no coincide. Es la única que cruza `db_ops`,
y la única que nunca se ha medido.

### 5.5 El corte quirúrgico (Bloque 5) — orden que preserva el chatbot

El orden importa: cada paso deja el sistema viejo funcionando.

1. **Apagar solo `:8088`.** El chatbot sobrevive intacto; las 26 rutas proxy devuelven error de
   conexión, ninguna de las 7 nativas del chatbot depende de :8088. **Verificar el chatbot aquí**
   — este paso solo es reversible relanzando el proceso.
2. **Quitar los 4 `<script>` y el `<link>` de `main.html`** (§0.3). El chatbot pierde la pestañería
   de ProdIA y conserva la suya. **Verificar el chatbot.**
3. **Desregistrar `colapsable_bp`** en `app.py`.
4. **Podar `routes/api.py`**: las 26 proxy + helpers L383-490 + rutas L492/L562. **Conservar las 7
   nativas.** Reiniciar `:8020`. **Verificar el chatbot: login LDAP, envío de mensaje por SocketIO,
   generación de gráfico** (los 3 caminos que tocan `ReportCardFactory`/`AnalyticsManager`).
5. **Borrar archivos** (§4.3) y podar los `.bat`.

### 5.6 AP-6 — el test de navegación tiene que proteger de verdad

Hoy `RUTAS_DE_SECCION` está hardcodeada en el test, así que una ruta nueva no lo rompe — que es
exactamente el olvido que ya ocurrió **dos veces** (F2 y F3 entregaron páginas inalcanzables). F6
añade dos secciones más (`/control`, `/testclas`), así que la lista se deriva de `router.tsx` y el
test falla si una ruta de sección no tiene enlace.

### 5.7 DT-3 / C4 — el RBAC de UI deja de ser diferible

`get_effective_sections` existe en el backend, el dato viaja hasta `authStore` (`sections: string[]`)
y **nadie lo lee**: `grep` de `useHasSection` → 0. Con 3 secciones era tolerable. Con 5 —una de
ellas **Test Clas, admin-only**— deja de serlo: un usuario sin permiso vería el enlace.

F6 cierra la parte de navegación: `LayoutMain` filtra `SECCIONES` por `sections`. La guarda de
ruta (`RutaAdmin`) es de F5 (B-2).

---

## 6. Orden de ejecución

### 6.0 Precondición — B-1 y B-2 fuera de F6

F6 **no absorbe** el frontend de F1 ni la fase F5. Son fases con su propio plan (F5 ya lo tiene, v3
listo). Meterlas aquí convertiría el corte en «terminar el producto», que es como una fase de
retiro se vuelve interminable. Ver DC-1.

| Bloque | Qué | Depende de | Verificación |
|---|---|---|---|
| **0** | Cerrar R3 pendiente: DT-8 (Ejecutivo + 4 pills), `/ingesta` en navegador, golden `clasificacion` con Ollama | VPN + Ollama | El usuario firma cada uno (R3) |
| ~~**1**~~ ✅ | **B-4**: `StaticFiles` + fallback SPA + tolerar `dist/` ausente (§5.2) | — | **Hecho** (`dfadab9`) — verificado contra servidor real: raíz 200 HTML, `/analisis` 200 al recargar, API sin cookie 401 con `correlation_id`, assets 200 |
| ~~**2**~~ ✅ | **B-3**: `Start_Prod.bat` + `desplegar_v02.bat` + `docs/DESPLIEGUE.md` (§5.3) | 1 | **Hecho** (`6965ed5`) |
| ~~**3**~~ ✅ | `humo_paridad.py` + AP-6 + DT-3 | 1 | **Hecho** (`6965ed5`, `aaaa589`) — 866 tests backend 84,12 % · 336 frontend 84,93 % |
| **4** | **Despliegue paralelo en el 139** y verificación de paridad (§5.4) | 0,2,3 + B-1 + B-2 | Las 3 anclas coinciden. **Castilla = 78.629 kUSD** |
| **5** | **El corte** (§5.5), paso a paso, verificando el chatbot entre cada uno | 4 firmado | El chatbot funciona idéntico antes y después |
| **6** | Actualizar CLAUDE.md: cerrar P1, DT-3, DT-8; bitácora | 5 | — |

**Los bloques 1-3 son ejecutables hoy** — no dependen de B-1/B-2 y son trabajo real de F6. El
bloque 4 es el que está bloqueado.

---

## 7. Reglas no negociables

1. **No se toca `chatbot/`.** Ni una línea. Si el corte parece exigirlo, el corte está mal
   planteado.
2. **`routes/api.py` y `templates/main.html` se editan, nunca se borran** (§0.2). Son archivos
   compartidos.
3. **La frontera del frontend viejo es la de §0.3, medida por símbolo definido**, no por nombre de
   archivo. `reportCards.js`, `monthlyBalance.js` y `charts.js` **se conservan** aunque parezcan de
   ProdIA.
4. **El corte (Bloque 5) no empieza hasta que la paridad esté firmada** por el usuario (R3), con
   el ancla de Castilla comprobada.
5. **`StaticFiles` debe tolerar `dist/` ausente** (AP-4). Si no, bloquea el pre-commit de todo el
   repo.
6. **El montaje de estáticos va después de los routers**, o se traga `/api/v1/*`.
7. **Verificar el chatbot entre cada paso del Bloque 5**, no al final: login LDAP, mensaje por
   SocketIO y generación de gráfico.
8. **R1** — no se toca configuración de pnpm.
9. **R3** — «build verde» no es «corte verificado». Solo el usuario marca F6 completa.
10. **Nada de `--reload` ni dev server en producción** (§0.6). Es lo único de Robustez V02 que no
    se hereda.
11. Todo en español: código, comentarios, commits, tests.

---

## 8. Validaciones

**Antes de commitear cada bloque** — lo mismo que corre `ci.yml`, en el mismo orden:
`ruff` · `black --check` · `mypy src` · `export_openapi.py` · `pytest --cov --cov-fail-under=75` ·
`pnpm lint` · `pnpm typecheck` · `pnpm build` · `pnpm test:front`.

**Línea base medida el 2026-08-20** (F4 cerrada, commit `76167ad`):

| Métrica | Hoy | Criterio en F6 |
|---|---|---|
| Tests backend | **819** | No baja; ninguno sale a la red |
| Cobertura backend | **83,86 %** | ≥ 75 % **al cerrar cada bloque** (AP-5) |
| Tests frontend | **50 archivos, 291 tests** | — |
| Cobertura frontend | **84,04 %** | ≥ 80 % × 4 |
| Bundle inicial | **331,92 kB** | Sin regresión |
| Rutas OpenAPI | **30** | 30 (F6 no añade endpoints) |

**Verificación del corte** (Bloque 5) — el chatbot, antes y después:

| # | Prueba | Esperado |
|---|---|---|
| C1 | Login LDAP en `:8020` | Entra igual |
| C2 | Enviar mensaje en el chat (SocketIO) | Responde igual |
| C3 | Pedir un gráfico (`AnalyticsManager` → `charts.js`) | Se pinta igual |
| C4 | Una tarjeta de reporte (`ReportCardFactory` → `reportCards.js`) | Se pinta igual |
| C5 | `/layout/colapsable` | **404** — retirada |
| C6 | Cualquier `/api/ingesta/*`, `/api/analisis/*`, `/api/consulta2/*` | **404** — retiradas |

---

## 9. Fuera de alcance

- **B-1 (frontend de F1) y B-2 (F5 completa)**: fases propias, no se absorben aquí (§6.0).
- **Arreglar S1/S2/S3** del sistema viejo: son del chatbot, que sobrevive. F6 los **documenta**.
- **Migrar datos**: `daily_report_prod` es el mismo Postgres (U3 de CLAUDE.md). No hay ETL de corte.
- **Retirar el chatbot clásico**: decisión P1, aún abierta (DC-4).
- **Recuperar `ECP_DIFERIDAS.db`** (DT-7): tarea aparte.
- **HTTPS**: diferido a infraestructura, decisión heredada vigente.
- **CI de despliegue** (AP-3): el despliegue sigue siendo manual y auditado.

---

## 10. Decisiones abiertas

| # | Pregunta | Recomendación |
|---|---|---|
| **DC-1** | ¿F6 absorbe B-1 (frontend F1) y B-2 (F5)? | **No.** Ejecutar **F1-frontend** y **F5** como fases propias antes de F6. Absorberlas convierte el corte en «terminar el producto». Alternativa honesta si urge: **corte parcial** — retirar solo Ingesta/Análisis/Consulta y dejar Control y Test Clas vivas en el sistema viejo, que es viable porque el corte ya es ruta por ruta |
| **DC-2** | ¿Quién sirve los estáticos? | **FastAPI (opción A, §5.2).** Un puerto, sin CORS, sin infraestructura nueva, respeta el `baseUrl: '/'` existente |
| **DC-3** | ¿V02 usa 6033+6034, o un solo puerto? | Con la opción A, **un solo puerto: 6034**. 6033 queda solo para desarrollo. Simplifica el firewall del 139 a una regla |
| **DC-4** | **P1 de CLAUDE.md**: ¿el chatbot clásico convive indefinidamente? | CLAUDE.md dice «antes de F6». Este plan **asume que convive** y por eso el corte es quirúrgico. Si la respuesta fuera «también se retira», F6 cambia por completo: se apaga `:8020` entero y desaparece toda la cirugía de §5.5 |
| **DC-5** | ¿Despliegue por `git pull` (AP-2) o por zip (`migra.py`/`deploy_zip.py`)? | **`git pull`**, que es lo que ya hace el 139 y V02 tiene remoto. Conservar el zip como plan B si el 139 pierde acceso a GitHub |

---

## 11. Apéndice — mapa del corte, medido

El árbol del sistema viejo mide **61 GB** en disco (incluye `venv/`, `vector_db/` y el árbol de
INGESTA). El corte libera ~2,7 GB de SQLite más lo que ocupe `INGESTA/Rep_Prod/`; los ~45 GB del
PostgreSQL `daily_report_prod` **no se tocan** — es el mismo servidor que usa V02 (U3).

```
SE RETIRA (~10.700 líneas + ~2,7 GB de datos)
  INGESTA/Rep_Prod/           backend FastAPI :8088 (8 routers) + React
  routes/api.py               26 rutas proxy + helpers L383-490 + L492 + L562
  routes/colapsable.py        52 L
  Colapsable/                 templates + static
  static/js/multitab_shell.js          5.308 L
  static/js/reportTabs.js                329 L   (código muerto)
  static/js/dailyPerformanceReport.js    730 L   (código muerto)
  static/js/monthlyBalanceReport.js      767 L   (código muerto)
  static/css/colapsable.css            2.103 L
  data/ECP_DIFERIDAS*.db               ~1,1 GB
  data/Eventos_OW.xlsx                  254 KB
  run.bat

SE CONSERVA (el chatbot clásico, intacto)
  app.py :8020 · chatbot/ · main_bp · chat_bp · auth_bp (LDAP+SSO)
  routes/api.py            7 rutas nativas (L764, 794, 819, 846, 1183, 1234, 1261)
  static/js/chat.js        4.794 L
  static/js/reportCards.js 1.374 L   ← ReportCardFactory, 10 usos en chat.js
  static/js/charts.js      2.014 L   ← AnalyticsManager, 48 refs
  static/js/monthlyBalance.js 220 L  ← monthlyBalanceRenderer
  data/{ECP_PROD,ROBUSTEZ,chat_history}.db
  vector_db/               índice vectorial del chatbot — regenerable, pero borrarlo
                           obliga a reindexar (scripts/refresh_vector_db.py)
  scripts/                 refresh_vector_db.py, dependencia operativa del chatbot
  Ollama :11434 + sus 4 reglas de firewall

ACOPLADO — editar, nunca borrar
  routes/api.py · templates/main.html · app.py
  iniciar_backends.bat · desplegar_version.bat
```
