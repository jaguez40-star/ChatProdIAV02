# CLAUDE.md — ProdIA V02

> Memoria de proyecto. Léela completa antes de tocar código — especialmente §5 (herencia de
> Robustez V02), §6 (inventario de origen) y §7 (reglas de dominio) si vas a trabajar en F1+.

---

## 0. Reglas de trabajo

- **Todo en español**: código, comentarios, commits, ramas, nombres de test.
- **Modo Planner**: antes de escribir cualquier plan de fase (F1…F6), ejecuta primero los
  pasos 1-3 del flujo de 6 pasos (Mapeo → Auditoría → Diagnóstico) **contra el código real** —
  nunca desde memoria. El plan entregado debe nacer ya "v2 auditado", no un borrador v1 que se
  corrige después.
- **Flujo de 6 pasos** (heredado de Robustez V02, L11): Mapeo → Auditoría → Diagnóstico →
  Propuesta → Aplicación → Verificación. Un artefacto por turno de aplicación. Verificación =
  build + lint + tests + **interacción humana en navegador** para cualquier cambio visual (R3).
- **R1** — no tocar configuración de pnpm (`.npmrc`, `allowBuilds`, `node-linker`) sin que el
  usuario lo apruebe explícitamente. Ver el incidente documentado en §9 (DT-1).
- **R2** — si en fases futuras se usa Plotly, el `data` memoizado de un gráfico NUNCA depende
  de estado de selección/hover (`selectedKey`, `hoveredKey`) — causa bugs de re-render
  garantizados. Ver detalle completo en `CLAUDE.md` de Robustez V02 §17.5.
- **R3** — "build verde" no es "feature verificada" en nada con interacción visual. TypeScript
  y tests en verde no detectan layout roto, animaciones interrumpidas ni race conditions de
  Suspense. El usuario es quien marca una feature visual como verificada, en navegador.
- **Formato de commit**: `feat(F0.x): descripción` / `fix(F1.x): descripción`, en español,
  explicando el porqué cuando no sea obvio.
- **Formato de plan de fase**: Contexto → Objetivo → Prerequisitos verificables (con anclas
  `grep -c` contra el código real, no contra un hash de commit) → Inventario de archivos →
  Especificación → Orden de ejecución → Reglas no negociables → Validaciones → Fuera de
  alcance. Ver `Planes/plan_F0_cimiento_2026-08-17.md` como plantilla real.

---

## 1. Qué es ProdIA V02 y por qué existe

Todo lo funcional bajo "Análisis avanzado de producción diaria" (el sistema ProdIA clásico)
vivía **fundido en dos aplicaciones con stacks incompatibles**, unidas por un proxy HTTP:

```
Usuario → Flask :8020 → static/js/multitab_shell.js (5.308 líneas, IIFE vanilla)
                          └─ proxy routes/api.py → FastAPI :8088 → PostgreSQL
```

| Síntoma medido | Evidencia |
|---|---|
| Frontend sin arquitectura | 5.308 líneas en un IIFE; render por concatenación de strings; 0 componentes, 0 tipos |
| **Backend de datos sin autenticación** | `grep -r "ldap\|jwt\|session\|HTTPBearer"` en el backend viejo → 0 resultados. Quien alcanzara el puerto leía todo |
| Sin observabilidad | Sin correlation_id, sin logging estructurado, sin forma uniforme de error |
| Estado disperso | 7 objetos-caché de módulo + `state` + `localStorage`, cada uno con su regla |
| Memoria conversacional volátil | Un `dict` de proceso — se perdía al reiniciar |

**ProdIA V02** es la reconstrucción de esas 5 pestañas (Ingesta, Control, Análisis, Consulta,
Test Clas) como aplicación **autónoma**, sobre los patrones ya probados en producción en
`C:\APLICACIONES\Robustez\Des_robustez_2.0` — la app más estable del equipo.

**Qué reemplaza:** el sistema viejo de "Análisis avanzado de producción diaria" (`INGESTA/`,
`multitab_shell.js`, el proxy de `routes/api.py`), una vez completado F6 (corte).

**Qué NO reemplaza:** el chatbot clásico de ProdIA (`chatbot/`, agentes SQL, SocketIO,
SQLite `ECP_PROD.db`) — es otra aplicación, con otro propósito, y sigue funcionando en
paralelo indefinidamente salvo decisión explícita en contrario (P1, decisión abierta).

---

## 2. Stack tecnológico

### 🔴 El diagrama de stack aportado inicialmente NO coincide con el código real

Verificado midiendo `package.json`/`pyproject.toml` de Robustez V02 el 2026-08-17. **Se usa
el stack real, no el del diagrama:**

| Diagrama decía | Realidad verificada y usada aquí |
|---|---|
| Zod 4 · Vite 8 · TypeScript 6 | **Zod ^3.24 · Vite ^6.0 · TypeScript ^5.7** |
| Bootstrap 5.3 + Icons + TanStack Table 8 | **No existen** — `lucide-react` + SCSS Modules propios |
| Plotly 3.5 | **`plotly.js-dist-min` ^2.35** (aún no usado en F0; llega en F1+) |
| FastAPI 0.136 · pandas · numpy 2.4 · asyncpg | FastAPI **>=0.115** · **sin pandas** · numpy — · **sin asyncpg** (SQLAlchemy síncrona) |
| Postgres `localhost:5433`, esquemas `ops`+`auth` | ops en servidor remoto; **`auth` NO es esquema Postgres — es SQLite** con Alembic |

### Backend (`prodia_v02_backend/`)

| Pieza | Versión (resuelta por `uv`) |
|---|---|
| Python | 3.12 |
| FastAPI | 0.137.x |
| SQLAlchemy | 2.0.x (Core, síncrona — sin ORM salvo en `features/auth`) |
| Alembic | 1.x |
| structlog | 26.x |
| pydantic-settings | 2.x |
| ldap3 + dnspython | auth LDAP + resolución DNS SRV |
| itsdangerous | cookie de sesión firmada |
| psycopg2-binary | driver Postgres (síncrono) |

Gestor: `uv`. Sin `requirements.txt` — todo en `pyproject.toml` + `uv.lock`.

### Frontend (`prodia_v02_frontend/`)

| Pieza | Versión |
|---|---|
| React | 19 |
| TypeScript | ^5.7 |
| Vite | ^6.0 |
| TanStack Query | 5 |
| Zustand | 5 |
| react-hook-form + @hookform/resolvers | ^7.74 + zod resolver |
| Zod | ^3.24 |
| openapi-fetch + openapi-typescript | cliente HTTP tipado end-to-end desde el OpenAPI real |
| react-router-dom | 7 |
| lucide-react | iconos |
| sass | CSS Modules + SCSS |
| vitest + @testing-library/react | tests |

Gestor: `pnpm` (workspace de un solo paquete — el backend usa `uv`, no es parte del workspace
de Node). Node 22.

### Base de datos

Ver §3 (arquitectura) — 4 engines potenciales, F0 monta 2.

---

## 3. Arquitectura

### Monorepo, vertical slicing

```
prodia_v02_backend/src/
├── main.py                 routers /api/v1, lifespan fail-fast
├── core/{config,exceptions,logger}.py
├── middleware/{auth,correlation_id,request_logger}.py
├── shared/{db_auth,db_prod,auth_guards,app_settings,utils}.py
└── features/{auth,permissions,audit}/{api,schemas,services,models,repositories}.py

prodia_v02_frontend/src/
├── app/{router,providers,App}.tsx + store/authStore.ts + layouts/
├── shared/{services,components,styles,utils,hooks,types}/
└── features/auth/{pages,components,hooks,services,schemas,mappers,types}/
```

**Cero imports cross-feature** (ADR-001) — cada feature es autocontenida.

### Los 4 engines de base de datos — regla de oro: nunca se mezclan

| Engine | Fuente | Uso | Patrón | Estado en F0 |
|---|---|---|---|---|
| `db_auth` | SQLite `prodia_v02_auth.db` | usuarios, grupos, permisos, `auth_events` | eager + PRAGMA WAL | **Montado, CRÍTICO** |
| `db_prod` | PostgreSQL `daily_report_prod` | el dato (bronze/core, 62M filas) | lazy + `pool_pre_ping` | **Montado, OPCIONAL en F0** (H4 — pasa a crítico en F1) |
| `db_ops` | PostgreSQL `robustez_v02` (`ops.*`) | EBITDA, jerarquía de pozos | lazy, solo lectura | Llega en F2 |
| `db_diferidas` | SQLite `ECP_DIFERIDAS.db` (954 MB) | histórico de diferidas | lazy, solo lectura | Llega en F2 |

`db_auth` sin esquema válido → el backend **no arranca** (`raise` en el lifespan). `db_prod`
apagado → el backend arranca igual, `/health` reporta `degraded`. Este comportamiento
diferenciado es deliberado (H4/P-6): en F0 no hay ninguna feature que dependa de Postgres
todavía.

### API — `/api/v1`, deny-by-default

`PUBLIC_PATHS` = solo `login`, `health`, `/docs`, `/redoc`, `/openapi.json`. Todo lo demás
exige cookie de sesión válida (`prodia_session`, HttpOnly, SameSite=Lax) — el middleware de
auth corre **antes** del routing (verificado: una ruta inexistente sin cookie responde 401,
no 404).

### Contrato de error uniforme

Todo error HTTP: `{"status": int, "detail": str, "correlation_id": str | null, "code"?: str,
"errors"?: [...]}`. El `correlation_id` viaja también en el header `x-correlation-id` de
**toda** respuesta (éxito o error) — mismo id en los logs del backend, para poder hacer grep
directo desde un reporte de usuario.

---

## 4. Ambientes

| Variable | Desarrollo | Producción (139) |
|---|---|---|
| `APP_ENV` | `development` | `production` |
| Puertos | front **6033** / back **6034** | idem (evitan Robustez V02 en 6023/6024) |
| Cookie `secure` | `False` | `True` |
| Logs | consola coloreada | JSON |
| `db_auth` | `./data/prodia_v02_auth.db` | idem, fuera del repo |
| `db_prod` | Postgres local | servidor remoto |
| `ENABLE_LOCAL_LOGIN` | `true` (IP allowlist) | **`false`** |
| LLM (F4+) | `qwen2.5:3b` local | `gemma4:latest` remoto |

### Arranque

```bash
pnpm setup   # uv python install 3.12 + uv sync + pnpm install
# copiar prodia_v02_backend/.env.example a .env y completar
cd prodia_v02_backend && uv run alembic upgrade head   # crea la BD auth + siembra el padrón
cd ..
pnpm dev     # backend :6034 + frontend :6033 en paralelo
```

Variables de entorno completas y comentadas: `prodia_v02_backend/.env.example`.

---

## 5. Herencia de Robustez V02

Tres categorías. La ruta de referencia de cada fila apunta al archivo real en
`Des_robustez_2.0` en el momento de la auditoría (2026-08-17) — puede haber cambiado desde
entonces si Robustez V02 sigue en desarrollo activo.

### 5.1 🟢 Copiado literal (L1-L11)

| # | Pieza | Referencia | Por qué |
|---|---|---|---|
| L1 | Observabilidad (~170 líneas) | `src/core/{exceptions,logger}.py` + `middleware/{correlation_id,request_logger}.py` | JSON de error uniforme; el 500 nunca filtra el mensaje interno; correlation_id en cada log y en el header |
| L2 | `conftest.py` | `tests/conftest.py` | SQLite en memoria REAL con FK activas (no `MagicMock`); `httpx.AsyncClient`+`ASGITransport`; aislamiento de structlog entre tests |
| L3 | Settings + `lru_cache` | `src/core/config.py` | `env_file` con ruta absoluta; listas como CSV+property; `SECRET_KEY` con validador de longitud |
| L4 | Engines separados | `shared/db.py` + `db_ops.py` | `pool_pre_ping=True` — sobrevive a cortes de VPN |
| L5 | Auth LDAP | `features/auth/services.py` | 3 trampas: resolver DNS fresco por intento, `answers.nameserver` (no `.target`), `commit()` antes de cada `raise` |
| L6 | Alembic + su trampa | `alembic/env.py` | `connection.commit()` tras los PRAGMAs — sin él, `alembic_version` se pierde en el rollback |
| L7 | Cobertura forzada | `vitest.config.ts` 80%×4 · `pyproject.toml` `fail_under=75` | Esto sostiene la estabilidad, no los tests en sí |
| L8 | Plantilla de primitivo | `primitives/Button/` | 4 archivos por componente; `extends HTMLAttributes`+`forwardRef`+`aria-busy` |
| L9 | Tres capas de sesión | `ProtectedRoute`+`SessionExpiryBanner`+`useInactivityLogout`+`sessionInterceptor` | `isHydrated` evita el parpadeo a `/login` de un usuario ya autenticado |
| L10 | RBAC aditivo | `permissions/services.py` + `auth/repositories.py:36-68` | `permisos = UNIÓN(grupo, individuales)`, `sorted()` determinista |
| L11 | Proceso (R1-R3, flujo 6 pasos) | `CLAUDE.md` §15/§17.5 de Robustez V02 | Ver §0 de este documento |

### 5.2 🟡 Copiado corrigiendo — deuda declarada en el propio código de Robustez V02

| # | Deuda en el original | Corrección aplicada aquí |
|---|---|---|
| C1 | 45 de 47 services usan `fetch` desnudo (su propio código lo admite) → parchea `window.fetch` globalmente | **N1**: 100% de los services por `apiClient` (openapi-fetch) desde el día 1. `sessionInterceptor` es un middleware de `apiClient.use()`, no un monkey-patch |
| C2 | El frontend descarta el `correlation_id` que produce el backend | Clase `ApiError` (`shared/services/apiClient.ts`) que lo parsea y lo expone; `QueryState` y `LoginPage` lo muestran al usuario |
| C3 | Sin formateo de números compartido — duplicado inline por todo el repo | `shared/utils/format.ts` desde F0: `formatBl`, `formatMscf`, `formatKUSD`, `formatPct`, `formatDelta` — cada producto con SU formateador (crítico: gas en MSCF ÷1e6 vs crudo en bbl ya causó bugs reales en el sistema viejo, ver A5 en §7) |
| C4 | RBAC de UI no implementado — el backend calcula `sections`, el frontend nunca las lee | Pendiente para F1+ cuando exista navegación real: `sectionId` con los IDs exactos del backend + `useHasSection()` |
| C5 | Loading/error como ternarios inline por página, sin `correlation_id` | Componente `QueryState` (`shared/components/QueryState/`) que encapsula el triángulo loading/error/vacío |
| C6 | `_get_allowed_campos` duplicado en cada `api.py` (el propio docstring lo admite) | Dependencia única `get_allowed_campos` en `shared/auth_guards.py`, lista para F2+ |
| C7 | `<Suspense>` anidado a mano ~20 veces en `router.tsx` | Helper `withSuspense(Component)` en `app/withSuspense.tsx` |
| C8 | `api.d.ts` desactualizado — consecuencia de C1 (nadie corre `gen:types` porque casi nadie usa `apiClient`) | `scripts/export_openapi.py` genera el schema **offline** (sin servidor vivo) — el pre-commit puede correr `gen:types` siempre |
| C9 | Puertos en 3 fuentes contradictorias (README/CLAUDE.md dicen 8000/5173; real 6024/6023) | Una sola fuente: `vite.config.ts` + `core/config.py`, por variable de entorno |
| C10 | El layout importa hooks de 4 features para alimentar un ticker (invierte la dependencia) | `LayoutMain` de F0 no tiene ticker — cuando F2+ lo necesite, las páginas publican sus KPIs, el layout no las importa |
| C11 | Tokens SCSS con 2 prefijos (`$rb-*`/`$ec-*`) y sin escala de espaciado | Un solo prefijo `$pv-*` (`shared/styles/_tokens.scss`), con escala 4/8/12/16/24 |
| C12 | Sin excepciones de dominio, solo 3 handlers globales | `core/exceptions.py` ya admite un campo `code` opcional en el JSON de error, listo para cuando F1+ necesite excepciones de dominio |
| C13 | Sin CI, sin git remote | `.github/workflows/ci.yml` desde F0 (lint+typecheck+test en push) |
| C14 | **Sin seed de primer admin** — Robustez V02 no puede crear su primer usuario | Migración `0003_seed_padron` (ver ADR-002) |
| C15 | Login local: contraseña comparada con `==` (no tiempo-constante), `*` desactiva el filtro de IP | `secrets.compare_digest` + `*` **rechazado por el validador de Settings**, sin excepción por entorno |

### 5.3 🔴 No copiado

Sin E2E (Robustez V02 no tiene ninguno) · `ErrorPages/` vs `errors/` duplicados · `useNow.ts`
mal ubicado en `utils/` siendo un hook (aquí vive en `shared/hooks/`) · `htmlcov/` versionado
· el panel decorativo `DashboardPreview` del login (D1 — ~500 líneas + 2 hooks de KPIs de
mercado que ProdIA no tiene).

---

## 6. Inventario de origen — qué falta portar desde el sistema viejo

Medido, no estimado (auditoría 2026-08-17 contra `12112025_prodIA/`). Rutas relativas a la
raíz de ese repo.

| Feature origen | Líneas | Destino en ProdIA V02 | Fase |
|---|---:|---|---|
| `INGESTA/Rep_Prod/backend/app/features/consulta_v2/` | 4.901 (+442 YAML) | `features/consulta/` | F4 |
| `.../features/analisis/api.py` | 2.619 | `features/analisis/` (split por sufijo, no subcarpetas) | F2 |
| `.../features/ingesta/` (`services.py` = 1.940) | 2.195 | `features/ingesta/` | F3 |
| `.../features/tablas/` | 204 | `features/tablas/` | F1 |
| `.../features/ebitda/` | 123 | `features/ebitda/` | F2 |
| `.../features/{reportes,kpis_prod}/` | 57 | `features/reportes/` | F1 |
| `routes/api.py:381-700` (rutas nativas Flask, no proxy) | ~320 | `features/{diferidas,mantenimientos}/` | F2 |
| `.../features/consulta/` (v1) | 1.470 | ❌ **no se migra** — congelada desde 2026-07-30 | — |
| `INGESTA/Rep_Prod/backend/tests/` | 3.933 (24 archivos) | se portan junto con su feature | F1-F4 |
| `static/js/multitab_shell.js` + `colapsable.css` | 7.411 | ❌ **se reescriben** — es render por concatenación de strings, nada reutilizable | F1-F5 |

**Total a portar: ~10.100 líneas de Python + 24 archivos de test (3.933 líneas).**

Golden sets a portar tal cual (criterio de aceptación de F4): `clasificacion_golden.yaml`
(34 casos, gate ≥90%) · `cuantificar_golden.yaml` (24 casos) · `analizar_golden.yaml`
(10 casos). Anclas de paridad conocidas: Castilla EBITDA = 78.629 kUSD · `DATOS_MES` = 7.776
filas · `TD_datos_dia` = 5.209 filas.

---

## 7. Reglas de dominio — no se pueden perder al portar F2/F4

Documentadas ahora (F0), aunque su código llegue después — cada una es un bug ya pagado en el
sistema viejo, y si no quedan escritas se vuelven a cometer.

### Motor Q v2 (F4) — Q1-Q5

- **Q1** — Python calcula, el LLM solo redacta. `intro_valido` rechaza cualquier texto del LLM
  que contenga un dígito o una unidad — es lo que impide que el modelo invente cifras.
- **Q2** — REGLA CERO: si no hay rezago respecto a la meta, se **declara**, nunca se fabrica un
  faltante. Un LLM alucinó un déficit inexistente con Castilla al 102,7% de cumplimiento antes
  de que esta regla existiera.
- **Q3** — El **orden** de los drills de reescritura conversacional *es* la corrección: 3 bugs
  reales por colisión entre drills en el sistema viejo (ej. "promedio del año" contiene la
  substring "DEL ANO" y caía en el drill de acumulado en vez del de referencia).
- **Q4** — La cobertura parcial de un activo (ej. NARE: 1 de 8 campos con datos) se declara **en
  cabecera**, nombrando los campos incluidos — nunca al pie ni en silencio.
- **Q5** — El dispatcher del panel de resultados **valida el tipo** recibido; nunca cae a un
  fallback silencioso. En el sistema viejo (JS sin tipos), un `panel.tipo` no reconocido pintaba
  una tarjeta con campos ajenos sin ningún error visible.

### Análisis (F2) — A1-A6

- **A1** — El singleton que parsea `Eventos_OW.xlsx` va bajo lock con doble chequeo — el parseo
  mide ~1,53 s; sin lock, N logins concurrentes lo parsean N veces.
- **A2** — `FinalizaEvento` vacío en ese Excel significa evento **ABIERTO**, no fila inválida —
  son 3.305 de 6.850 filas (48%). Descartarlas perdía justo los eventos que siguen corriendo.
- **A3** — El filtro de mantenimientos vigentes es por **solape con el mes analizado**, nunca
  contra `now()` — contra "hoy" quedaban 3 eventos en toda la compañía.
- **A4** — La caché TTL + single-flight de los endpoints caros (equivalente a
  `ejecutivo`/`desempeno`/`president` del sistema viejo) debe vivir **en el backend**, no en un
  proxy intermedio — sin esto, el prefetch del login dispara N generaciones de LLM en paralelo.
- **A5** — El P50 de la hoja `NEW MES-AÑO` está en **promedio diario (bpd)**, no en la escala del
  fact operativo. Aplicarle la conversión de MSCF (÷1e6) que usa el gas dio "0,03 MSCF" en vez
  de "33.453,2 bpd" — mil veces menor, **sin error visible**. Es el ejemplo canónico de por qué
  cada producto necesita SU formateador (C3, `shared/utils/format.ts`).
- **A6** — `_sanitize_col()` (Infinity/NaN → `None`) se aplica **antes** de construir cualquier
  response numérica — ya existe en `shared/utils.py` desde F0, lista para F2.

---

## 8. Decisiones

| # | Decisión | Origen |
|---|---|---|
| U1 | Alcance total = las 5 pestañas, migradas por fases | usuario |
| U2 | Repo independiente, Robustez V02 como plantilla | usuario |
| U3 | Mismo PostgreSQL `daily_report_prod` tal cual — se reescribe la capa de acceso, no el esquema | usuario |
| U4 | Ruta: `C:\APLICACIONES\ProdIA\12112025_prodIA\ProdIA_V02` | usuario |
| U5 | F0 llega hasta el login funcionando, idéntico en comportamiento a Robustez V02 | usuario |
| D1 | Login: formulario idéntico, **sin** el panel decorativo `DashboardPreview` | usuario |
| D2 | Padrón **propio**, sembrado importando solo `username`/`email`/`full_name` de Robustez V02 | usuario — ver ADR-002 |
| D3 | Login local sí, pero `*` en la allowlist de IP **prohibido siempre** (no solo en producción) | usuario |
| D4 | ProdIA V02 queda **autocontenido**: este CLAUDE.md + `Planes/` + `docs/decisions/` bastan para continuar sin la conversación original | usuario |

Heredadas de Robustez V02, vigentes: whitelist de emails abolida (solo la tabla `app_users`
decide acceso) · seguridad en capas, HTTPS diferido a infraestructura · DDL de auth versionado
por Alembic · nivel de auditoría MEDIO (`auth_events` activa, `user_actions` con la tabla
creada pero sin instrumentar todavía).

### Decisiones abiertas (no bloquean F0)

| # | Pregunta | Cuándo se debe cerrar |
|---|---|---|
| P1 | ¿ProdIA V02 reemplaza también al chatbot clásico, o conviven indefinidamente? | Antes de F6 |
| P3 | ¿Se sube `ECP_DIFERIDAS.db` (954 MB, no cabe en git) al servidor de producción? | Antes de F2 |
| P4 | ¿Qué usuarios de los 29 importados son admin? (hoy: `javier.guerrero`, ya admin en el origen) | Se puede ampliar cuando haga falta vía `SEED_ADMIN_USERNAMES` |

---

## 9. Deuda técnica

| # | Deuda | Origen | Impacto |
|---|---|---|---|
| DT-1 | `pnpm approve-builds` interactivo escribió `allowBuilds: false` por error durante el setup de F0, dejando `esbuild` sin construir | Ejecución de F0 (2026-08-18) | Corregido en el mismo commit (`allowBuilds: true` explícito en `pnpm-workspace.yaml`) — documentado aquí por si se repite en un `pnpm install` limpio en otra máquina |
| DT-2 | El `.venv` de `prodia_v02_backend` resolvió Python 3.14 en lugar de 3.12 en algún entorno de verificación (mientras `pyproject.toml` pide `>=3.12`) | Observado durante `pytest -v` de F0 | No bloqueante mientras los tests pasen; fijar la versión exacta con `uv python pin 3.12` si se vuelve a observar |
| DT-3 | RBAC de UI (C4) no implementado — no hay navegación con múltiples secciones todavía en F0 | Heredada de Robustez V02, diferida a F1+ | Cerrar cuando exista más de una sección navegable |
| DT-4 | Sin excepciones de dominio tipadas (C12) — solo el campo `code` opcional existe en el contrato | Heredada de Robustez V02, diferida | Añadir cuando una feature de F1+ necesite distinguir tipos de error de negocio |

---

## 10. Roadmap

| Fase | Entrega | Depende de | Estado |
|---|---|---|---|
| **F0** | Cimiento + login funcional idéntico a Robustez V02 | — | Ver `Planes/plan_F0_cimiento_2026-08-17.md` §8 para el detalle de verificación |
| **F1** | Control + Tablas — árbol de reportes + visor (204 líneas, la más chica: valida el patrón end-to-end) | F0 | Pendiente |
| **F2** | Análisis — 9 endpoints + EBITDA + diferidas + mantenimientos (2.619 líneas) | F0 | Pendiente |
| **F3** | Ingesta — ETL .xlsm, 17 extractores + SSE (2.195 líneas) | F0 | Pendiente |
| **F4** | Consulta — Motor Q v2 completo + panel apilable (4.901 líneas + 442 YAML) | F2 | Pendiente |
| **F5** | Test Clas — laboratorio del clasificador (admin-only) | F4 | Pendiente |
| **F6** | Corte — despliegue paralelo, paridad verificada, retiro del sistema viejo | F1-F5 | Pendiente |

Cada fase requiere su propio plan en `Planes/`, con el mismo formato de F0 (§0 de este
documento), auditado contra el código real antes de escribirse.

---

## 11. Bitácora

| Fecha | Qué se hizo | Archivos | Hallazgos |
|---|---|---|---|
| 2026-08-17/18 | **F0 completo**: cimiento del monorepo (uv+pnpm), observabilidad (L1), auth LDAP con las 3 trampas preservadas (L5), migraciones Alembic (0001/0002 DDL + 0003 seed del padrón), login funcional en frontend (React 19 + TanStack Query + Zustand) idéntico en comportamiento a Robustez V02 sin el panel decorativo. 58/58 tests backend (87% cobertura), suite de tests frontend en construcción. | Ver `Planes/plan_F0_cimiento_2026-08-17.md` para el diff completo | El hallazgo más importante: Robustez V02 no tiene forma de crear su primer usuario (ver ADR-002) — sin corregirlo, F0 habría entregado un login que no deja entrar a nadie. Segundo hallazgo: el body de los 401 emitidos por el middleware de auth no llevaba `correlation_id` (solo en el header) — corregido para cumplir N6 de forma consistente con los errores de router |
