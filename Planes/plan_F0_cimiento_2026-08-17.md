# Plan F0 — ProdIA V02: cimiento + login idéntico a Robustez V02

**Fecha:** 2026-08-17 · **Versión:** v4 (v3 + auditoría de entorno con 11 hallazgos H1-H11)
**Destino:** `C:\APLICACIONES\ProdIA\12112025_prodIA\ProdIA_V02` (**ya existe, vacía** — H1)
**Alcance de esta fase:** CLAUDE.md + estructura + arquitectura base + ambientes + **login funcional**
**Modo:** EXECUTOR (agente sin acceso a conversaciones previas ni al historial de esta sesión)

---

## 0. Prerequisitos verificados contra el sistema real (2026-08-17)

Estos hechos fueron **medidos, no estimados**. El Executor debe re-verificar los marcados 🔴 antes
de empezar; si alguno cambió, DETENERSE y reportar.

| # | Hecho verificado | Estado |
|---|---|---|
| P-1 | `C:\APLICACIONES\ProdIA\12112025_prodIA\ProdIA_V02` existe y está **vacía** | usar tal cual, NO recrear |
| P-2 | El padre `12112025_prodIA\` NO es repo git → sin riesgo de repo anidado | ✅ |
| P-3 | node v22.23 · pnpm 11.9 · uv 0.12.1 · git 2.54 disponibles | ✅ |
| P-4 | 🔴 **`make` NO está instalado** | los scripts pnpm/uv son el canal canónico; el `Makefile` se copia como opcional con nota |
| P-5 | Puertos 6033/6034 **libres** (Robustez usa 6023/6024) | ✅ |
| P-6 | 🔴 **Postgres local :5432 puede estar APAGADO** (verificado apagado hoy) | `db_prod` es OPCIONAL en F0 — el backend arranca sin él (H4) |
| P-7 | Los 33 archivos fuente de la plantilla en `Des_robustez_2.0` existen (0 faltantes) | ✅ |
| P-8 | `sqlite3.connect('file:...?mode=ro', uri=True)` funciona: lectura OK, escritura → `OperationalError` | ✅ base del seed 0003 |
| P-9 | BD origen: 29 usuarios (0 duplicados de username), 27/29 con `full_name` vacío, `alembic_version=0002` | ✅ |
| P-10 | `uv python list` no reporta Pythons instalados | ejecutar `uv python install 3.12` antes de `uv sync` (H11) |

---

## 1. Contexto

### Por qué se hace

Todo lo funcional bajo "Análisis avanzado de producción diaria" vive hoy **fundido en dos
aplicaciones con stacks incompatibles**, unidas por un proxy HTTP:

```
Usuario → Flask :8020 → static/js/multitab_shell.js (5.308 líneas, IIFE vanilla)
                          └─ proxy routes/api.py → FastAPI :8088 → PostgreSQL
```

| Síntoma | Evidencia medida |
|---|---|
| Frontend sin arquitectura | **5.308 líneas** en un IIFE; render por concatenación de strings; 0 componentes, 0 tipos |
| **Backend de datos sin autenticación** | `grep -r "ldap\|jwt\|session\|HTTPBearer"` en `INGESTA/Rep_Prod/backend/app/` → **0 resultados**. Quien alcance `:8088` lee todo |
| Sin observabilidad | Sin correlation_id, sin logging estructurado, sin forma uniforme de error |
| Estado disperso | 7 objetos-caché de módulo + `state` + `localStorage`, cada uno con su regla |
| Memoria conversacional volátil | `_CTX` es un `dict` de proceso — se pierde al reiniciar |

**ProdIA V02** es la reconstrucción de esas 5 pestañas como aplicación autónoma, sobre los patrones
ya probados en producción en `C:\APLICACIONES\Robustez\Des_robustez_2.0` — la app más estable del
equipo.

### Qué entrega F0 (esta fase)

Un usuario corporativo abre `http://localhost:6033`, ve una pantalla de login **visualmente idéntica
a la de Robustez V02**, entra con su cuenta LDAP y llega a una página protegida vacía. Debajo: el
monorepo, los 4 engines, observabilidad completa, auth con cookie firmada, CI y el CLAUDE.md.

**F1-F6 (fuera de esta fase, ver §9):** Control+Tablas · Análisis · Ingesta · Consulta · Test Clas · corte.

### Decisiones cerradas

| # | Decisión | Origen |
|---|---|---|
| U1 | Alcance total = las 5 pestañas (por fases) | usuario |
| U2 | Repo independiente, Robustez V02 como plantilla | usuario |
| U3 | Mismo PostgreSQL `daily_report_prod` tal cual | usuario |
| U4 | Ruta: `C:\APLICACIONES\ProdIA\12112025_prodIA\ProdIA_V02` | usuario |
| U5 | F0 llega hasta el login funcionando idéntico a Robustez V02 | usuario |
| **D1** | **Formulario idéntico, SIN panel decorativo** `DashboardPreview` | usuario |
| **D2** | **Padrón PROPIO, sembrado importando SOLO `username`, `email`, `full_name`** de `robustez_v02_auth.db`. El resto de esa base (grupos, permisos de campo, permisos de sección, bitácora) **no se copia** | usuario |
| **D3** | **Login local sí, pero con `*` prohibido** y comparación en tiempo constante | usuario |
| **D4** | **`ProdIA_V02` queda AUTOCONTENIDO**: CLAUDE.md con inventario de origen + reglas de dominio, `Planes/` con este plan copiado, `docs/decisions/` con 2 ADR. Se puede continuar desde allá sin esta conversación | usuario |

### 🔴 El diagrama de stack aportado no coincide con el código real

Medido en `package.json` / `pyproject.toml`. **Se usa el stack real:**

| Diagrama | Realidad verificada |
|---|---|
| Zod 4 · Vite 8 · TypeScript 6 | **Zod ^3.24 · Vite ^6.0 · TypeScript ^5.7** |
| Bootstrap 5.3 + Icons + TanStack Table 8 | **No existen** — `lucide-react` + SCSS Modules propios |
| Plotly 3.5 | **`plotly.js-dist-min` ^2.35** |
| FastAPI 0.136 · pandas · numpy 2.4 · asyncpg | FastAPI **>=0.115** · **sin pandas** · numpy >=1.26 · **sin asyncpg** (SQLAlchemy síncrona) |
| Postgres `localhost:5433`, esquemas `ops`+`auth` | ops en `10.100.26.139:5432`; **`auth` NO es esquema Postgres — es SQLite** con Alembic |

---

## 2. 🔴 Hallazgo crítico: Robustez V02 no puede crear su primer usuario

Verificado exhaustivamente:

- `alembic/versions/0001_initial_auth.py` y `0002_app_settings.py`: **solo DDL, cero `INSERT`**
- `scripts/` (50+ archivos): ningún seed. El único relevante, `migrate_v01_auth.py`, **copia** usuarios
  desde una BD V01 preexistente — inútil para un proyecto nuevo
- `Makefile`: sin target `seed`/`bootstrap`. No hay CLI

**Consecuencia:** tras `alembic upgrade head`, `app_users` está vacía → **todo login falla con 401**
`"Usuario no registrado en la aplicación"` (`services.py:97-101`), aunque las credenciales LDAP sean
válidas y `ENABLE_LOCAL_LOGIN=true` — porque la verificación de existencia ocurre en el **paso 1**,
antes del login local (paso 3).

**Por eso D2 no es opcional:** sin sembrar `app_users`, F0 termina con un login que no deja entrar a
nadie. Es la primera corrección real que ProdIA V02 aporta sobre su plantilla.

### 2.1 De qué se siembra el padrón (D2) — medido en la BD real

Fuente: `C:\APLICACIONES\Robustez\Des_robustez_2.0\robustez_v02_backend\data\robustez_v02_auth.db`
(520 KB, `alembic_version = 0002_app_settings`).

| Tabla | Filas | ¿Se importa? |
|---|---:|---|
| `app_users` | **29** (26 activos, 4 admin) | **SÍ — solo `username`, `email`, `full_name`** |
| `permission_groups` | 2 (`Admin`, `Orinoquia`) | ❌ ProdIA define los suyos |
| `user_campo_permissions` | 1.030 | ❌ |
| `group_campo_permissions` | 143 | ❌ |
| `user_section_permissions` | 206 | ❌ apuntan a secciones de Robustez |
| `group_section_permissions` | 15 | ❌ (`analytics`, `regresiones`, `reports`, `ebitaPozosPri`…) |
| `auth_events` | 352 | ❌ bitácora de otra app |
| `user_actions` | 320 | ❌ |

**Calidad verificada de las 3 columnas que sí se importan:**
- `username`: 29/29 completos, **0 duplicados** (case-insensitive)
- `email`: 29/29 completos, dominio `@ecopetrol.com.co`
- ⚠️ **`full_name`: 27 de 29 VACÍOS.** Solo 2 usuarios lo traen

**Consecuencia del `full_name` vacío:** el `Header` de Robustez ya degrada con
`user?.fullName ?? user?.username ?? user?.email` — se conserva ese fallback y la UI no se rompe.
No se inventan nombres a partir del username.

**La BD de origen NO se modifica** (se lee, no se toca). ProdIA V02 crea su propia
`prodia_v02_auth.db` desde cero con `alembic upgrade head`.

---

## 3. Arquitectura destino (lo que F0 deja montado)

```
C:\APLICACIONES\ProdIA\12112025_prodIA\ProdIA_V02\
├── CLAUDE.md                       ← memoria de proyecto (entregable de F0)
├── README.md · .gitignore · .editorconfig · .pre-commit-config.yaml
├── package.json                    ← concurrently back+front
├── pnpm-workspace.yaml             ← solo frontend (backend = uv)
├── Planes/                         ← plan_F0_*.md … plan_F6_*.md
├── docs/decisions/                 ← ADR-001 monorepo, ADR-002 seed de admin
├── .github/workflows/ci.yml        ← lint + typecheck + test
│
├── prodia_v02_backend/
│   ├── pyproject.toml · Makefile · .env.example
│   ├── alembic.ini · alembic/{env.py,versions/}
│   └── src/
│       ├── main.py                 ← routers /api/v1, lifespan fail-fast
│       ├── core/{config,exceptions,logger}.py
│       ├── middleware/{auth,correlation_id,request_logger}.py
│       ├── shared/{db_auth,db_prod,auth_guards,app_settings,utils}.py
│       └── features/{auth,permissions,audit}/{api,schemas,services,models,repositories}.py
│
└── prodia_v02_frontend/
    ├── package.json · vite.config.ts · vitest.config.ts · index.html
    └── src/
        ├── main.tsx
        ├── app/{router,providers}.tsx + layouts/LayoutMain.tsx + store/authStore.ts
        ├── shared/{services,components,styles,utils,types}/
        └── features/auth/{pages,components,hooks,services,schemas,mappers,types}/
```

### Los 4 engines (patrón `db.py`/`db_ops.py` — nunca se mezclan)

F0 monta **los dos primeros**; `db_ops` y `db_diferidas` llegan en F2.

| Engine | Fuente | Uso | Patrón | Fase |
|---|---|---|---|---|
| `db_auth` | SQLite `prodia_v02_auth.db` | usuarios, grupos, permisos, `auth_events` | eager + PRAGMA WAL | **F0** |
| `db_prod` | PostgreSQL `daily_report_prod` | el dato (bronze/core, 62M filas) | lazy + `pool_pre_ping` + pool 5/10 | **F0** (solo health) |
| `db_ops` | PostgreSQL `robustez_v02` (`ops.*`) | EBITDA, jerarquía de pozos | lazy, solo lectura | F2 |
| `db_diferidas` | SQLite `ECP_DIFERIDAS.db` (954 MB) | histórico de diferidas | lazy, solo lectura | F2 |

### Ambientes

| Variable | Desarrollo | Producción (139) |
|---|---|---|
| `APP_ENV` | `development` | `production` |
| Puertos | front **6033** / back **6034** | idem (evitan Robustez V02 en 6023/6024) |
| Cookie `secure` | `False` (deriva de `is_dev`) | `True` |
| Logs | consola coloreada | JSON |
| `db_auth` | `./data/prodia_v02_auth.db` | idem, fuera del repo |
| `db_prod` | Postgres local | `10.100.26.139:5432` |
| `ENABLE_LOCAL_LOGIN` | `true` (IP allowlist) | **`false`** |
| LLM (F4) | `qwen2.5:3b` local | `gemma4:latest` en 139 |

---

## 4. Qué se toma de Robustez V02

### 4.1 🟢 Copiar literal

| # | Pieza | Referencia | Por qué |
|---|---|---|---|
| L1 | **Observabilidad** (~170 líneas) | `src/core/{exceptions,logger}.py` + `middleware/{correlation_id,request_logger}.py` | JSON de error uniforme `{status, detail, correlation_id, errors?}`; el 500 nunca filtra el mensaje interno; `merge_contextvars` inyecta el id en cada log; **el id vuelve en el header** → el usuario reporta un ID y tú haces grep |
| L2 | **`conftest.py`** | `tests/conftest.py` (138 líneas) | SQLite **en memoria real** con `PRAGMA foreign_keys=ON` (no `MagicMock`); `httpx.AsyncClient`+`ASGITransport`; el fixture que aísla structlog con su docstring de 25 líneas |
| L3 | **Settings + `lru_cache`** | `src/core/config.py` | `env_file` con **ruta absoluta** (funciona con cualquier CWD); listas como CSV + property; `field_validator` que exige `SECRET_KEY` ≥16 |
| L4 | **Engines separados** | `shared/db.py` + `db_ops.py` | `pool_pre_ping` **es lo que sobrevive a cortes de VPN** |
| L5 | **Auth LDAP** | `features/auth/services.py` | Tres trampas ya pagadas: resolver DNS **fresco** por intento (si el backend arranca antes que la VPN, uno cacheado hace fallar todo login hasta reiniciar); `answers.nameserver` **no** `.target` (el hostname del DC da timeout por firewall); `commit()` **antes** de `raise` o el rollback borra la auditoría |
| L6 | **Alembic + su trampa** | `alembic/env.py` | El `connection.commit()` tras los PRAGMAs: sin él el `UPDATE` de `alembic_version` se pierde en el rollback — tablas creadas, versión vieja. **Invisible con una sola migración** |
| L7 | **Cobertura forzada** | `vitest.config.ts` 80% × 4 · `pyproject.toml` `fail_under=75` | *Esto* sostiene la estabilidad, no los tests en sí |
| L8 | **Plantilla de primitivo** | `primitives/Button/` | 4 archivos: `.tsx` + `.module.scss` + `.test.tsx` + `index.ts`; `extends HTMLAttributes` + `forwardRef` + `disabled \|\| loading` + `aria-busy` |
| L9 | **Tres capas de sesión** | `ProtectedRoute` + `SessionExpiryBanner` + `useInactivityLogout` + `sessionInterceptor` | `isHydrated` evita el parpadeo que manda a `/login` a un usuario ya autenticado |
| L10 | **RBAC aditivo** | `permissions/services.py` + `auth/repositories.py:36-68` | `permisos = UNIÓN(grupo, individuales)` con `sorted()` determinista |
| L11 | **Proceso R1-R3 + flujo 6 pasos** | `CLAUDE.md` §15/§17.5 | R3: *"build verde ≠ feature verificada"* |

### 4.2 🟡 Copiar corrigiendo — deuda declarada en su propio código

| # | Deuda | Evidencia | Corrección |
|---|---|---|---|
| C1 | **45 de 47 services usan `fetch` desnudo** | `sessionInterceptor.ts:5-9` lo confiesa: *"un helper obligaría a tocar los 45"* → por eso **parchea `window.fetch`** | 100% por `apiClient` tipado desde el día 1; el interceptor es `middleware` de `openapi-fetch` |
| C2 | **El frontend descarta el `correlation_id`** | `apiClient.ts` son 11 líneas sin normalización de error | Clase `ApiError` que lo parsea y **lo muestra al usuario** |
| C3 | **Sin formateo de números compartido** | `LayoutMain.tsx:189,207` define `fmtNum`/`fmtCF` localmente | `shared/utils/format.ts` desde F0. **Crítico en ProdIA**: gas MSCF (÷1e6) vs crudo bbl ya causó bugs |
| C4 | **RBAC de UI no implementado** | 0 lecturas de `permissions.sections` en todo `src/`; los IDs ni coinciden (`'ebitda_rank'` vs `'rank'`) | `sectionId` con los IDs **del backend** + `useHasSection()` + `<SectionRoute>` |
| C5 | **Loading/error por ternarios inline** | `EbitdaRankPage.tsx:403-413` | `<QueryState>` que encapsula loading/error/vacío y muestra el `correlation_id` |
| C6 | `_get_allowed_campos` duplicado en cada `api.py` | Su propio docstring admite que es "el mismo criterio" | Dependencia única en `shared/auth_guards.py` |
| C7 | `Suspense` anidado 20 veces | `router.tsx` | Helper `withSuspense()` |
| C8 | `api.d.ts` desactualizado (jul-01 vs ago-13) | Consecuencia de C1 | `gen:types` **OFFLINE** (H5): script `scripts/export_openapi.py` vuelca `app.openapi()` a `openapi.json` SIN levantar el servidor → `openapi-typescript` corre sobre el archivo. En pre-commit sin depender de un backend vivo (el hook de Robustez exigía el server en :6024 — frágil) |
| C9 | Puertos en 3 fuentes contradictorias | README dice 8000/5173; real 6024/6023 | Una sola fuente |
| C11 | Tokens con 2 prefijos, sin escala de espaciado | 84 líneas con aliases legacy | Un prefijo `$pv-*` + escala 4/8/12/16/24 |
| C13 | Sin CI, sin git remote | El backup admite que la historia vive solo en `.git/` local | Remoto + GitHub Actions desde F0 |
| **C14** | **Sin seed de primer admin** (§2) | Migraciones solo DDL | **Migración `0003` parametrizada (D2)** |
| **C15** | **Login local: password plano, `*` desactiva IP filter** | `services.py:150-179`, su comentario dice *"usar solo temporalmente"* | `*` **rechazado en `config.py`** + `secrets.compare_digest` (D3) |

### 4.3 🔴 No copiar

Sin E2E (`tests/e2e/` solo tiene `__init__.py`) · `ErrorPages/` vs `errors/` duplicados ·
`useNow.ts` en `utils/` siendo hook · `htmlcov/` versionado · **`DashboardPreview`** (D1).

---

## 5. Entregable 1 — contexto autocontenido (`CLAUDE.md` + `Planes/` + `docs/`)

**Criterio de aceptación de este entregable (D4):** alguien abre Claude Code en `ProdIA_V02` **sin
acceso a esta conversación** y puede ejecutar F0 y planear F1 sin volver a auditar nada. Todo el
conocimiento de esta sesión queda escrito dentro del proyecto.

### 5.1 `CLAUDE.md` — 12 secciones

| § | Contenido |
|---|---|
| 0 | **Reglas de trabajo**: español en todo; modo Planner (pasos 1-3 antes de escribir un plan); R1-R3; formato de plan y de commit |
| 1 | **Qué es ProdIA V02 y por qué existe**: el problema de las dos apps fundidas (§1), qué reemplaza, qué NO (el chatbot clásico sobrevive) |
| 2 | **Stack real verificado** + la tabla de corrección del diagrama aportado |
| 3 | **Arquitectura**: monorepo, vertical slicing, 4 engines con su regla de no mezclar, `/api/v1`, deny-by-default |
| 4 | **Ambientes** (tabla §3) + cómo arrancar (`pnpm setup`, `pnpm dev`) |
| 5 | **Herencia de Robustez V02**: las 3 tablas de §4 — qué se copió literal (L1-L11), qué se corrigió (C1-C15) y **por qué**, con la ruta del archivo de referencia en cada fila |
| 6 | **🆕 Inventario de origen** (§5.2) — sin esto F1-F4 exigen re-auditar el proyecto viejo |
| 7 | **🆕 Reglas de dominio Q1-Q5 y A1-A6** (§5.3) — **escritas desde F0**, no diferidas |
| 8 | **Decisiones D1-D4** + heredadas vigentes (D5 whitelist abolida, D6 seguridad en capas, D13 DDL auth, D14 audit medio) |
| 9 | **Roadmap F0-F6** con estado y criterio de cierre por fase |
| 10 | **Deuda técnica** numerada (DT-1…), espejo obligatorio de cada `# TODO[Fx]` del código |
| 11 | **Bitácora** por sesión (fecha · qué se hizo · archivos · hallazgos) |

### 5.2 §6 del CLAUDE.md — inventario de origen (medido, no estimado)

Tabla con **ruta absoluta de origen, líneas y destino** de cada pieza:

| Feature origen | Líneas | Destino | Fase |
|---|---:|---|---|
| `INGESTA/Rep_Prod/backend/app/features/consulta_v2/` | 4.901 (+442 YAML) | `features/consulta/` | F4 |
| `.../features/analisis/api.py` | 2.619 | `features/analisis/` (split por sufijo) | F2 |
| `.../features/ingesta/` (`services.py` = 1.940) | 2.195 | `features/ingesta/` | F3 |
| `.../features/tablas/` | 204 | `features/tablas/` | F1 |
| `.../features/ebitda/` | 123 | `features/ebitda/` | F2 |
| `.../features/{reportes,kpis_prod}/` | 57 | `features/reportes/` | F1 |
| `routes/api.py:381-700` (rutas **nativas**, no proxy) | ~320 | `features/{diferidas,mantenimientos}/` | F2 |
| `.../features/consulta/` (v1) | 1.470 | ❌ **no se migra** — congelada 2026-07-30 | — |
| `INGESTA/Rep_Prod/backend/tests/` | 3.933 (24 archivos) | se portan con su feature | F1-F4 |
| `static/js/multitab_shell.js` + `colapsable.css` | 7.411 | ❌ **se reescriben**, no se portan | F1-F5 |

Más: los **golden sets** (`clasificacion_golden.yaml` 34 casos · `cuantificar_golden.yaml` 24 ·
`analizar_golden.yaml` 10) y las **anclas de paridad** (Castilla EBITDA = 78.629 kUSD ·
`DATOS_MES` = 7.776 filas · `TD_datos_dia` = 5.209).

### 5.3 §7 del CLAUDE.md — reglas de dominio, escritas en F0

Se documentan **ahora**, aunque su código llegue en F2/F4: cada una es un bug ya pagado, y si no
están escritas se vuelven a cometer.

- **Q1-Q5 (Motor Q v2, F4)** — Python calcula / el LLM solo redacta · REGLA CERO (no fabricar
  faltantes) · el orden de los drills *es* la corrección · cobertura parcial en cabecera · el
  dispatcher valida el tipo, nunca cae a fallback silencioso
- **A1-A6 (Análisis, F2)** — singleton bajo lock · `FinalizaEvento` vacío = evento abierto (48% de
  las filas) · filtro por solape con el mes, no contra `now()` · caché TTL + single-flight en el
  backend · **el P50 está en bpd, no en la escala del fact** · `_sanitize_col()` para Infinity/NaN

Cada regla con: qué dice · qué pasa si se rompe · dónde se originó.

### 5.4 `Planes/` y `docs/decisions/`

- `Planes/plan_F0_cimiento_2026-08-17.md` — **este plan, copiado íntegro** (hoy vive en
  `C:\Users\jague\.claude\plans\`, fuera del proyecto: si no se copia, se pierde el razonamiento
  de esta sesión)
- `docs/decisions/ADR-001-estructura-monorepo.md` — por qué monorepo con `uv`+`pnpm` y vertical
  slicing; alternativas rechazadas
- `docs/decisions/ADR-002-padron-usuarios-propio.md` — por qué padrón propio importando solo
  3 columnas (§2.1), y por qué **no** se comparte la BD de Robustez V02
- `README.md` — arranque en 5 pasos para alguien que clona el repo por primera vez

---

## 6. Entregable 2 — estructura y cimiento

### Paso 1 · Monorepo

Sobre la carpeta **YA EXISTENTE y vacía** (P-1): `git init` dentro + remoto. Copiar y adaptar de
`Des_robustez_2.0`: `package.json` (concurrently), `pnpm-workspace.yaml`, `.gitignore`,
`.editorconfig`, `.pre-commit-config.yaml`.

- 🔴 **H3/P-4 — `make` no existe en esta máquina**: los **scripts de `package.json` y `uv run` son
  el canal canónico** de lint/format/typecheck/test. El `Makefile` se copia igualmente (documenta
  los comandos y sirve en máquinas que sí lo tengan) con nota en cabecera: "OPCIONAL — canal
  canónico = pnpm scripts".
- Puertos **6033/6034** en **una sola fuente** (`vite.config.ts` + `config.py`, por env) — C9.
- **H11/P-10**: el `setup` de `package.json` incluye `uv python install 3.12` antes de `uv sync`.

### Paso 2 · Backend: núcleo

1. **L1 observabilidad completa** — los 4 archivos, ~170 líneas. Primer commit de código.
2. **L3** `core/config.py` + **C15/H6**: `field_validator` que **rechaza `*` SIEMPRE** en
   `local_login_allowed_ips` — en dev Y en producción (D3 lo prohíbe sin condición; dev usa
   `127.0.0.1,::1`, no necesita comodín).
3. **L4** `shared/db_auth.py` (eager, PRAGMA WAL) + `shared/db_prod.py` (lazy, `pool_pre_ping`).
4. `main.py` con lifespan fail-fast — **clasificación explícita por BD (H4/P-6)**:
   - `db_auth` = **CRÍTICA** → sin esquema válido, `raise` (no arranca)
   - `db_prod` = **OPCIONAL en F0** → si Postgres está apagado, `logger.warning` + arranca igual;
     `/health` reporta `"database_prod": "disconnected"` y `status: "degraded"`.
     **Pasa a crítica en F1** (cuando `tablas` dependa de ella) — anotar `# TODO[F1]`
5. `shared/utils.py` con `_sanitize_col()` (Infinity/NaN) — DT-18 de la plantilla, desde el día 1.

### Paso 3 · Backend: auth

Portar íntegros `features/{auth,permissions,audit}/` + `middleware/auth.py` +
`shared/{auth_guards,app_settings}.py`, preservando **L5** (las 3 trampas del LDAP) y aplicando:

- **C6**: `_get_allowed_campos` como dependencia única
- **C15**: `secrets.compare_digest` en el login local (hoy es `==` directo)
- **C12**: excepciones de dominio + campo `code` en el JSON de error

**Endpoints de F0:** `POST /api/v1/auth/login`, `POST /auth/logout`, `GET /auth/me`,
`GET /api/v1/permissions/my-permissions`, `GET /api/v1/health`.

**`PUBLIC_PATHS` = solo `login`, `health`, `/docs`, `/redoc`, `/openapi.json`** — todo lo demás
protegido (N5, deny-by-default).

### Paso 4 · Alembic

- `0001_initial_auth` — 8 tablas. Convenciones: timestamps `sa.Text()` con
  `server_default=datetime('now')`; booleanos `Integer` + `CheckConstraint("x IN (0,1)")`;
  JSON validado con `json_valid()`; `downgrade()` completo
- `0002_app_settings`
- **`0003_seed_padron`** 🆕 (**D2/C14**) — siembra `permission_groups` (`Administradores` is_admin=1,
  `Consulta` is_admin=0) y puebla `app_users` **importando solo `username`, `email`, `full_name`**
  de la BD de Robustez V02. Reglas:
  - Ruta de origen por entorno `SEED_SOURCE_AUTH_DB`; **la BD origen se abre en modo solo lectura**
    (`file:...?mode=ro`) — nunca se modifica
  - **Idempotente**: `INSERT ... ON CONFLICT(username) DO NOTHING`; re-ejecutar no duplica
  - `full_name` se copia **tal cual, incluidos los 27 vacíos** (§2.1) — no se derivan nombres
  - Todos entran con `is_active=1`, `is_admin=0` y `group_id` del grupo `Consulta`;
    los admins se elevan con `SEED_ADMIN_USERNAMES` (CSV) del entorno
  - Si la BD origen no existe **o** `SEED_ADMIN_USERNAMES` está vacío → **falla ruidosamente** con
    instrucciones. Nunca deja un padrón sin ningún admin
  - **No copia** ningún permiso de campo/sección ni bitácora de Robustez (§2.1)
- **L6**: el `connection.commit()` tras los PRAGMAs en `env.py`

### Paso 5 · Frontend: base

`main.tsx` (orden de hidratación), `app/{router,providers}.tsx` con **C7** `withSuspense()`,
`app/store/authStore.ts`, y en `shared/`:

- **C1+C2** `services/apiClient.ts` con `openapi-fetch` + clase `ApiError` que parsea
  `{status, detail, correlation_id}`
- `services/sessionInterceptor.ts` como **middleware de `openapi-fetch`**, no monkey-patch
- **C3** `utils/format.ts`: `formatBl`, `formatMscf`, `formatKUSD`, `formatPct`, `formatDelta`
- **C11** `styles/{index.scss,_tokens.scss}` con prefijo único `$pv-*` + escala de espaciado
- **C5** `components/QueryState`
- **L8** primitivos: `Button`, `Input`, `Toast`, `Spinner`, `Card` (los 5 que el login necesita),
  cada uno con sus 4 archivos

---

## 7. Entregable 3 — el login

### Backend (ya cubierto en Paso 3)

Contrato exacto de Robustez V02: `POST /auth/login {username, password}` → cookie
`prodia_session` (`httponly`, `samesite=lax`, `secure=not is_dev`) + `UserSessionOut`.
Errores: 401 `"Usuario no registrado en la aplicación"` / `"Credenciales inválidas"`,
503 si LDAP no responde.

### Frontend — cadena completa

| Archivo | Origen | Nota |
|---|---|---|
| `features/auth/pages/LoginPage.tsx` + `.module.scss` | copia | **Sin `DashboardPreview`** (D1): el panel izquierdo queda como área de marca |
| `features/auth/schemas/loginSchema.ts` | copia literal | zod: `username`/`password` no vacíos, `remember` bool |
| `features/auth/services/authService.ts` | copia + **C1/C2** | pasa por `apiClient`; **distingue 401 de 503** (Robustez V02 no lo hace) |
| `features/auth/hooks/` | copia | `useLogin`, `useLogout`, `useCurrentUser`, `useSessionExpiry`, `useInactivityLogout`, `useIdleTimer`, `useSessionTimeoutMinutes` |
| `features/auth/mappers/authMappers.ts` | copia literal | snake→camel |
| `features/auth/components/InactivitySessionModal/` | copia literal | |
| `app/store/authStore.ts` | copia literal | persiste en `localStorage` clave `prodia_auth` |
| `shared/components/{ProtectedRoute,SessionExpiryBanner}/` | copia literal | **L9**: `isHydrated` |

**Comportamiento a preservar exactamente:**
- `remember` es **UI-only**, nunca se envía al backend
- Toast de sesión expirada con `duration={0}` (no auto-cierra); el de error, 6000 ms
- Dos caminos convergen en `location.state.sessionExpired`: el interceptor (401 +
  `X-Session-Expired`) y `useCurrentUser` capturando `SessionExpiredError`
- Ojo de contraseña, `autoComplete`, `noValidate` en el form, iconos `lucide-react`
- **Mejora sobre el original (C2):** si el error trae `correlation_id`, se muestra en el toast

### Branding

Estructura y comportamiento idénticos; textos e imagen propios de ProdIA en lugar de
«ROBUSTEZ · ROBUSTEZ OPERATIVO V2.0» y `Gota.png`. Footer «© 2026 ECOPETROL S.A. · v2.0.0».

---

## 8. Verificación de F0

Ninguna casilla se marca sin ejecutarse.

| # | Prueba | Resultado esperado |
|---|---|---|
| V1 | `pnpm setup && pnpm dev` | Ambos procesos arrancan; front 6033, back 6034 |
| V2 | `curl :6034/api/v1/health` **con Postgres encendido** | `{"status":"ok","database_prod":"connected",...}` |
| V2b | `curl :6034/api/v1/health` **con Postgres APAGADO** (H4) | El backend **arranca igual**; `{"status":"degraded","database_prod":"disconnected"}`; el login sigue funcionando (solo usa `db_auth`) |
| V3 | `curl :6034/api/v1/auth/me` sin cookie | **401** con `{status, detail, correlation_id}` + header `X-Session-Expired` |
| V4 | `curl :6034/api/v1/ruta-inexistente` | **401, no 404** — el middleware corre antes del routing (test de seguridad disfrazado) |
| V5 | Header `x-correlation-id` en la respuesta | Presente, UUID de 36 chars; el mismo id aparece en los logs |
| V6 | `alembic upgrade head` sobre BD vacía | 3 migraciones; `app_users` = **29 filas**, 2 grupos; los de `SEED_ADMIN_USERNAMES` con `is_admin=1`; re-ejecutar **no duplica** |
| V6b | Tras el seed, contar en la BD nueva | `user_campo_permissions`, `*_section_permissions`, `auth_events`, `user_actions` = **0 filas** (§2.1: no se importan) |
| V6c | Checksum de la BD **origen** antes/después del seed | Idéntico — `robustez_v02_auth.db` no se modifica |
| V7 | `alembic upgrade head` sin `SEED_ADMIN_USERNAMES` o con origen inexistente | Falla ruidosamente con instrucciones — nunca deja un padrón sin admin |
| V8 | Login con credencial LDAP real (VPN activa) | Cookie `prodia_session`; redirige a `/`; fila `login_success` en `auth_events` |
| V9 | Login con contraseña incorrecta | Toast rojo "Credenciales inválidas"; fila `login_failure` con `reason="invalid_credentials"` |
| V10 | Login con usuario no registrado | 401 `"Usuario no registrado en la aplicación"`; `reason="not_in_app_users"` |
| V11 | Login local con `ENABLE_LOCAL_LOGIN=true` desde IP permitida | Entra; `reason="local_login_dev"` |
| V12 | Login local desde IP **no** permitida | Rechazado; log `local_login_rejected_ip` |
| V13 | `LOCAL_LOGIN_ALLOWED_IPS=*` en **cualquier** entorno (H6) | **El backend no arranca** — el validator rechaza `*` siempre (C15/D3) |
| V14 | Cookie expirada → petición | 401 + `X-Session-Expired`; la UI redirige a `/login` con el aviso |
| V15 | Sesión al <50% de vida | Cookie renovada (sliding refresh); `X-Session-Expires` actualizado |
| V16 | Recargar página estando logueado | Sin parpadeo a `/login` (`isHydrated`) |
| V17 | `pytest` + `pnpm test` | Verde; cobertura ≥75% back / ≥80% front |
| V18 | `make lint typecheck` + `pnpm lint` | Sin errores; `mypy --strict` limpio |
| V19 | CI en push | Los 3 jobs en verde |
| V20 | **Comparación visual** con Robustez V02 | Lado a lado: misma maqueta, tipografía, espaciados, estados de error |
| **V21** | **Prueba de autonomía (D4)**: abrir Claude Code en `ProdIA_V02` **sin esta conversación** y pedir "planea F1" | Debe poder hacerlo leyendo solo `CLAUDE.md` + `Planes/` + `docs/decisions/`: sabe qué portar (`tablas`, 204 líneas), desde qué ruta, con qué patrón y contra qué anclas verificar. **Si necesita re-auditar el proyecto viejo, D4 no está cumplida** |

**R3 aplica:** V20 y el golden path de login los valida **el usuario en navegador**. Hasta entonces,
el estado es "pendiente de validación humana", no "verificado".

---

## 9. Fases siguientes (fuera de F0)

| Fase | Entrega | Depende de |
|---|---|---|
| **F1 · Control + Tablas** | Árbol de reportes + visor (204 líneas: valida el patrón end-to-end con riesgo mínimo) | F0 |
| **F2 · Análisis** | 9 endpoints + EBITDA + diferidas + mantenimientos (2.619 líneas) | F0 |
| **F3 · Ingesta** | ETL .xlsm, 17 extractores + SSE (2.195 líneas) | F0 |
| **F4 · Consulta** | Motor Q v2 completo + panel apilable (4.901 líneas + 442 YAML) | F2 |
| **F5 · Test Clas** | Laboratorio del clasificador (admin-only) | F4 |
| **F6 · Corte** | Despliegue paralelo, paridad, retiro del viejo | F1-F5 |

**Total a portar: ~10.100 líneas de Python + 24 archivos de test (3.933 líneas).**
`consulta/` v1 (1.470) no se migra: congelada desde 2026-07-30, v2 la reemplaza.

---

## 10. Riesgos de F0

| # | Riesgo | Sev. | Mitigación |
|---|---|---|---|
| R1 | **LDAP no accesible sin VPN** → no se puede probar el login real | 🔴 | Login local (D3) permite avanzar; V8 se valida con VPN antes de cerrar F0 |
| R2 | El seed `0003` deja el padrón sin admin y nadie puede entrar | 🟡 | Idempotente + falla ruidosa si faltan `SEED_ADMIN_USERNAMES` o la BD origen (V7); documentado en `.env.example` |
| R2b | El seed escribe por error en la BD de Robustez V02 (producción) | 🔴 | Origen abierto **solo lectura** (`mode=ro`) + V6c verifica checksum idéntico antes/después |
| R3 | Copiar auth sin sus 3 trampas → fallos intermitentes difíciles de diagnosticar | 🟡 | L5 explícito en el plan; cada trampa con su comentario del porqué en el código |
| R4 | El `.env` real se commitea | 🔴 | `.gitignore` desde el commit 1 + `.env.example` sin secretos |
| R5 | Divergencia visual con Robustez V02 | 🟢 | V20 comparación lado a lado |

---

## 11. Reglas no negociables

**Heredadas (L11):** R1 (no tocar config de pnpm sin ADR) · R2 (el `data` memoizado de Plotly nunca
depende de selección/hover) · R3 (build verde ≠ feature verificada) · flujo de 6 pasos, con los
pasos 1-3 **antes** de escribir cada plan · cero imports cross-feature · todo en español.

**Nuevas:** N1 100% por `apiClient` · N2 puertos en una sola fuente · N3 `gen:types` OFFLINE en pre-commit (sin backend vivo, H5) ·
N4 un prefijo de tokens con escala de espaciado · N5 deny-by-default · N6 todo error visible muestra
su `correlation_id`.

---

## 12. Decisiones abiertas (no bloquean F0)

| # | Pregunta | Cuándo |
|---|---|---|
| P1 | ¿La app nueva reemplaza también al chatbot clásico, o conviven? | Antes de F6 |
| P3 | ¿Se sube `ECP_DIFERIDAS.db` (954 MB) al servidor 139? | Antes de F2 |
| P4 | ¿Qué usuarios de los 29 importados son admin de ProdIA? (`SEED_ADMIN_USERNAMES`) | **Al ejecutar F0** — sin al menos uno, la migración falla por diseño |

✅ **P2 cerrada (D2):** padrón **propio**, sembrado importando solo `username`/`email`/`full_name`
de Robustez V02. Las dos aplicaciones quedan desacopladas: dar de alta a alguien en una no lo da de
alta en la otra.

---

## 13. Alcance de este documento

Plan de **F0**. Su ejecución produce el `CLAUDE.md` que gobierna el resto. Cada fase siguiente
requiere su propio plan en `Planes/`, con el formato de Robustez V02 (Contexto → Objetivo →
Prerequisitos verificables con anclas `grep -c` → Inventario → Especificación → Orden → Reglas no
negociables → Validaciones → Fuera de alcance), auditado contra el código real antes de escribirse.
