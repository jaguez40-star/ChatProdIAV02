# Plan F1 — Control + Tablas (visor de reportes)

> Plan v3 — auditado contra el código real (origen y destino) Y contra los pipelines configurados
> (ci.yml, conftest, pyproject, vitest.config) el 2026-08-20. Formato según CLAUDE.md §0.
> Para el executor: seguir el **Orden de ejecución** paso a paso, un artefacto por turno,
> verificación al final de cada bloque.

---

## 0. Hallazgos de la auditoría de pipelines (v3) — leer PRIMERO

Estos hallazgos NACEN de auditar cómo el plan v2 chocaría con los pipelines reales. Cada uno
modifica el orden de ejecución o añade trabajo obligatorio. Ignorarlos = build roto en CI.

| # | Hallazgo | Evidencia | Consecuencia si se ignora | Acción en el plan |
|---|---|---|---|---|
| **H1** | **CI no tiene Postgres.** `ci.yml` corre `uv run pytest --cov=src --cov-fail-under=75` sin levantar ningún Postgres. | `ci.yml:25`, jobs sin `services: postgres`. | Cualquier test de `tablas` que ejecute un endpoint con `Depends(get_prod_db)` intenta conectar al 139 → **falla en CI** (sin VPN, sin red). El pipeline se cae. | **BLOQUE 1b nuevo:** añadir fixture `patch_prod_db` en `conftest.py` que use `app.dependency_overrides[get_prod_db]` con una BD SQLite en memoria (o fake). Los tests de `tablas` NUNCA tocan Postgres real. |
| **H2** | **`conftest.py` no tiene infraestructura para `db_prod`.** Solo parchea `db_auth` (`SessionLocal`) en dos lugares. `get_prod_db`/`get_prod_engine` no se parchean en ningún sitio. | `tests/conftest.py:93-125` (solo `patch_db_for_integration` para auth). | Sin fixture nuevo, no hay forma de testear `tablas` de forma aislada. | Igual que H1: crear el fixture de override de `get_prod_db`. |
| **H3** | **mypy `strict = true` sobre `src`.** El SQL del origen usa `dict`/`Any` sin tipar; portarlo tal cual **no pasa mypy**. | `pyproject.toml:62-64`. | `uv run mypy src` (CI:24) falla → pipeline roto. | El código de `tablas` DEBE llevar tipos completos (`Mapped`, `TypedDict`/Pydantic para las filas, retornos anotados). Es trabajo extra sobre el "copiar idéntico". |
| **H4** | **`--strict-markers` activo.** Todo test debe declarar `@pytest.mark.unit` o `@pytest.mark.integration`. | `pyproject.toml:73-77`. | Un test sin marker → error de colección → pipeline roto. | Los tests de `tablas` declaran su marker. |
| **H5** | **Cobertura cuenta la feature nueva.** Backend `fail_under=75` (omite solo `main.py`); frontend 80%×4 (`include: src/**`). | `pyproject.toml:79-84`, `vitest.config.ts:20-27`. | `features/tablas/*` y `features/control/*` sin tests suficientes **bajan la cobertura global bajo el umbral** → build rojo. | Tests obligatorios en ambos lados ANTES de considerar el bloque cerrado. No es opcional. |
| **H6 (DT-5)** | CI cachea un `pnpm-lock.yaml` inexistente y hace `pnpm install --frozen-lockfile` en `working-directory: prodia_v02_frontend`, pero el lock del workspace vive en la RAÍZ. | `ci.yml:41-42`. | El job frontend de CI probablemente **ya falla** (o nunca cachea). F1 lo empeora al añadir deps. | **Oportunidad de mejora:** corregir `ci.yml` (lock en raíz, `working-directory` raíz para install). Ver §11. |
| **H7 (DT-6)** | `pnpm test -- --coverage` no propaga `--coverage` a vitest (pnpm se come el `--`). El umbral 80% **nunca se evaluó en CI**. | `ci.yml:45`. | La red de seguridad de cobertura de F1 en CI no existe hasta arreglarlo. | Corregir a `pnpm test:front` (que ya trae `--coverage`, ver `package.json` raíz). Ver §11. |
| **H8** | **CI no corre `pnpm build`.** El fallo `tsc -b && vite build` (el que rompió hoy) no lo atraparía CI. | `ci.yml:43-45` (lint, typecheck, test; sin build). | Un error de build de F1 pasaría CI y solo se vería al desplegar. | **Oportunidad de mejora:** añadir `- run: pnpm build` al job frontend. Ver §11. |
| **H9** | **db_prod pasa a crítico, pero el arranque NO debe hacer fail-fast por él.** El login y Consulta no dependen de Postgres; solo `tablas` sí. | `db_prod.py:7-11` (TODO[F1]), `main.py` lifespan. | Si F1 hace `raise` en el lifespan cuando db_prod cae, rompe TODA la app (incluido el login) por una feature. | El lifespan sigue tolerante; `tablas` devuelve **503** claro si db_prod está caído. NO fail-fast global. |
| **H6-bis** | **`pnpm install --frozen-lockfile` ROMPE el job frontend entero**, no solo la caché. El `pnpm-lock.yaml` no existe en `prodia_v02_frontend/` (verificado en disco); el lock del workspace está en la RAÍZ. | `ci.yml:42` + ausencia del archivo. | El job frontend de CI **falla en el paso install**, antes de lint/test. F1 nunca se valida en CI. Es más grave que DT-5. | Parte del Bloque 4: install desde la raíz con el lock del workspace (ver §11). |
| **H10** | **`gen:types`/`export_openapi` NO están en CI.** Nadie verifica que `api.d.ts` esté sincronizado con el backend. | `ci.yml` sin pasos de gen:types; `package.json:14`. | F1 cambia el schema del backend; si olvida regenerar `api.d.ts`, CI **no lo detecta** (solo fallaría si el front usa un tipo roto, no si falta uno nuevo). Tipos desincronizados silenciosos. | El executor DEBE correr ambos pasos manualmente en el Bloque 2 y commitear `openapi.json` + `api.d.ts`. Opcional (§11): añadir un check de sincronía a CI. |
| **H11** | **Correr `uv run pytest` en local NO mide cobertura** (falso verde). `addopts` no tiene `--cov`; el gate solo existe cuando CI pasa `--cov=src --cov-fail-under=75`. | `pyproject.toml:77` (`addopts="--strict-markers"`, sin `--cov`). | El executor cree tener verde local pero CI puede fallar por cobertura. | El executor verifica SIEMPRE con el comando EXACTO de CI: `uv run pytest --cov=src --cov-fail-under=75`. Nunca `pytest` a secas. |

---

## 1. Contexto

F1 es la fase más pequeña del roadmap (§10). Su valor NO es la funcionalidad en sí (un visor de
tablas), sino **validar el patrón end-to-end** de ProdIA V02: una feature nueva que lee del
PostgreSQL real (`db_prod`, servidor 139) en el backend, expone endpoints tipados, y los pinta en
el frontend siguiendo los moldes de F0/F1a (apiClient → React Query → QueryState).

**Origen a portar** (sistema viejo, `12112025_prodIA/INGESTA/Rep_Prod/backend/app/features/`):

| Archivo origen | Líneas | Endpoints | Qué hace |
|---|---:|---|---|
| `tablas/api.py` | 205 | `GET /tablas`, `GET /tablas/datos`, `GET /tablas/arbol`, `GET /tablas/arbol/{reporte_id}` | Árbol año→mes→día de reportes + visor de tablas anchas (3 modos: fechas, matriz, texto) |
| `reportes/api.py` | 25 | `GET /reportes`, `GET /reportes/cobertura` | Lista de reportes + cobertura por fact |
| `kpis_prod/api.py` | 17 | `GET /kpis-prod/produccion-dia` | Suma de producción ECP por producto en una fecha |

Total: **247 líneas** de origen. Todo es SQL crudo (`sqlalchemy.text`) contra el esquema `core.*`
de `daily_report_prod`. Cero pandas, cero ORM.

**Tablas de PostgreSQL que consulta** (esquema `core`): `config_reporte`, `fact_tabla_hoja`,
`fact_comentarios_produccion`, `dim_tipo_producto`, `fact_produccion_mes_ecp`,
`fact_produccion_dia_ecp`, `fact_produccion_diaria`.

---

## 2. Objetivo

Entregar una **sección "Control"** en ProdIA V02 que:

1. Muestre el **árbol de reportes** (año → mes → día), cargado desde `db_prod`.
2. Al expandir un día, cargue **perezosamente** las hojas/tablas de ese reporte.
3. Al hacer clic en una tabla, muestre su **contenido en formato ancho** (visor con los 3 modos).
4. Sea accesible por **URL directa** (`/control`) — SIN menú de navegación entre secciones (fuera
   de alcance, decidido con el usuario 2026-08-20).
5. Lea del **Postgres 139 real** (`db_prod` pasa a CRÍTico en esta fase).

Criterio de aceptación: build verde + tests ≥ umbral (L7) + **verificación humana en navegador**
(R3) con datos reales del 139 — el usuario ve el árbol, expande un día, abre una tabla y ve datos.

---

## 3. Prerequisitos verificables

Anclas `grep`/inspección contra el código real (no contra un commit). El executor DEBE confirmar
cada uno antes de escribir código:

| # | Prerequisito | Cómo verificar | Estado auditado (2026-08-20) |
|---|---|---|---|
| P1 | `db_prod` tiene dependencia FastAPI lista | `get_prod_db` existe en `src/shared/db_prod.py` | ✅ Existe (`get_prod_db`, `get_prod_engine`, `check_prod_connection`) |
| P2 | `PROD_DATABASE_URL` apunta al 139 | Leer `prodia_v02_backend/.env` línea `PROD_DATABASE_URL=` | ✅ `postgresql+psycopg2://postgres:***@10.100.26.139:5432/daily_report_prod?sslmode=disable` |
| P3 | La conexión al 139 responde | `uv run python -c "from src.shared.db_prod import check_prod_connection; print(check_prod_connection())"` **con VPN** | ⚠️ **PENDIENTE** — falla sin VPN (desde desarrollo). Verificar en máquina de pruebas con VPN antes de F1 |
| P4 | Molde de feature backend | `src/features/auth/{api,schemas,services,repositories}.py` existen | ✅ Auditado |
| P5 | Registro de router | `main.py:106-107` monta routers con `app.include_router(x, prefix=API_PREFIX)` | ✅ Confirmado (`API_PREFIX="/api/v1"`) |
| P6 | Molde de feature frontend | `src/features/auth/{pages,components,hooks,services,mappers,types}` existen | ✅ Auditado |
| P7 | apiClient + QueryState + withSuspense | `shared/services/apiClient.ts`, `shared/components/QueryState/`, `app/withSuspense.tsx` existen | ✅ Auditado |
| P8 | gen:types funciona offline | `package.json` script `gen:types` + `scripts/export_openapi.py` | ✅ Existe (C8) |

**Bloqueante:** P3 debe pasar (en pruebas con VPN) antes de dar F1 por verificada. El desarrollo del
código puede avanzar sin él, pero la verificación R3 lo exige.

---

## 4. Inventario de archivos a crear/modificar

### Backend (`prodia_v02_backend/`)

**CREAR** — nueva feature `tablas` (agrupa los 3 orígenes; `reportes` y `kpis_prod` son tan chicos
que se pliegan como endpoints extra de la misma feature, evitando 3 features triviales):

```
src/features/tablas/__init__.py          (vacío)
src/features/tablas/api.py               (router: los 7 endpoints, portados)
src/features/tablas/schemas.py           (DTOs Pydantic de salida)
src/features/tablas/services.py          (lógica de pivote: los 3 modos de /datos)
src/features/tablas/repositories.py      (SQL crudo contra core.* con get_prod_db)
tests/features/test_tablas.py            (tests de la feature)
```

**MODIFICAR:**
```
src/main.py                  → import + include_router del tablas_router + tag OPENAPI_TAGS
                             → reclasificar db_prod a CRÍTico en el lifespan (quitar el TODO[F1])
src/core/config.py           → (revisar si prod_database_url ya está; no requiere cambio si sí)
```

### Frontend (`prodia_v02_frontend/`)

**CREAR** — nueva feature `control`:
```
src/features/control/pages/ControlPage.tsx (+ .module.scss, .test.tsx)
src/features/control/components/ArbolReportes/   (árbol año→mes→día, carga perezosa)
src/features/control/components/VisorTabla/       (tabla ancha, 3 modos)
src/features/control/services/controlService.ts   (llamadas apiClient)
src/features/control/hooks/                        (useArbol, useHojasReporte, useDatosTabla)
src/features/control/mappers/controlMappers.ts     (snake→camel)
src/features/control/types/controlTypes.ts         (modelo de vista camelCase)
```

**MODIFICAR:**
```
src/app/router.tsx           → ruta { path: '/control', element: withSuspense(ControlPage) }
                               dentro de children (hereda ProtectedRoute + LayoutMain)
src/shared/types/api.d.ts    → regenerar con gen:types tras crear el backend
```

---

## 5. Especificación

### 5.1 Backend — reglas de portado

1. **SQL idéntico al origen.** Las 7 consultas se copian TAL CUAL del origen (`tablas/api.py`,
   `reportes/api.py`, `kpis_prod/api.py`). No optimizar, no reescribir — el SQL ya está probado en
   producción y toca 50M+ filas con índices específicos. Los comentarios del origen que explican el
   porqué de cada decisión (LIMIT FETCH_MAX, carga perezosa, etc.) se **preservan**.

2. **Cambiar solo la capa de acceso** (U3): el origen usa `get_engine()` global; aquí se usa la
   sesión inyectada `Depends(get_prod_db)`. El repository recibe la conexión, no la crea.

3. **Separación en capas** (molde `auth`):
   - `repositories.py`: cada consulta SQL en un método que recibe `conn`/`db` y devuelve filas crudas.
   - `services.py`: la lógica de pivote de `/datos` (los 3 modos: fechas/matriz/texto) — es lo único
     con lógica real; el resto son pass-through.
   - `api.py`: router con `response_model`, inyecta `Depends(get_prod_db)`, traduce errores.
   - `schemas.py`: DTOs de salida (NodoArbol, HojaReporte, TablaDatos, etc.).

4. **Constantes preservadas:** `CAP_FILAS=100`, `FETCH_MAX=50_000`, `MESES_ES`.

5. **Sanitización** (A6): aplicar `_sanitize_col` (Infinity/NaN → None) de `shared/utils.py` antes de
   construir cualquier response numérica de `/datos`.

6. **Guard de permisos:** los endpoints exigen sesión (deny-by-default ya lo da el middleware). Si el
   "Control" es admin-only, añadir `Depends(require_admin)` — **CONFIRMAR con el usuario** si Control
   es solo-admin o para todos los autenticados (decisión abierta, ver §7).

7. **Lifespan:** reclasificar `db_prod` a CRÍTico. Hoy el backend arranca con Postgres apagado
   (`/health` = degraded). En F1, si `db_prod` no conecta, la feature Control falla — pero **NO** debe
   impedir el arranque del backend entero (el login y Consulta no dependen de Postgres). Decisión:
   mantener el arranque tolerante, pero que `/tablas/*` devuelva 503 claro si `db_prod` está caído.
   (Documentar: no hacer fail-fast del backend por db_prod, solo de la feature.)

### 5.2 Frontend — reglas de portado

1. **El frontend viejo NO se reutiliza** (§6): `multitab_shell.js` es render por concatenación de
   strings. Se reescribe con componentes React siguiendo el molde de `auth`/`consulta`.

2. **Árbol de reportes** (`ArbolReportes`): consume `GET /api/v1/tablas/arbol` (año→mes→día). Al
   expandir un día, dispara `GET /api/v1/tablas/arbol/{reporte_id}` (carga perezosa de hojas/tablas).
   Usar React Query con `queryKey` por reporte_id.

3. **Visor** (`VisorTabla`): al clic en una tabla, `GET /api/v1/tablas/datos?reporte_id=&hoja=&tabla_idx=`.
   Renderiza según `modo` (`fechas`|`matriz`|`texto`). Respetar `total_filas` vs `CAP_FILAS`
   (mostrar "mostrando 100 de N").

4. **Formateo de números** (C3): usar `shared/utils/format.ts`. OJO A5 — cada producto su escala.
   Para el visor genérico de tablas, los valores vienen ya calculados; formatear con el formateador
   adecuado según el contexto de la hoja (a definir por hoja; por defecto `formatBl`/número plano).

5. **Estados:** envolver cada fetch en `QueryState` (loading/error/vacío, con correlation_id en error).

6. **Mappers** (contrato de dos interceptores): snake_case del backend → camelCase en la vista.

7. **Ruta por URL:** `/control`, sin entrada de menú (fuera de alcance). Se navega escribiendo la URL.

---

## 6. Orden de ejecución

Un artefacto por turno. Verificación (build/lint/test) al final de cada bloque backend/frontend.

**Bloque 0 — Prerequisito de datos**
1. Verificar P3 en máquina de pruebas con VPN: `check_prod_connection()` = True. Si falla, PARAR y
   resolver conectividad antes de seguir. (Sin el 139, no hay datos que pintar.)
2. Inspeccionar el esquema real: confirmar que las tablas `core.config_reporte`, `core.fact_tabla_hoja`,
   etc. existen en el 139 y tienen datos (una query `SELECT count(*)`).

**Bloque 1 — Backend feature tablas** (con tipos estrictos por H3)
3. Crear `features/tablas/schemas.py` (DTOs Pydantic tipados — definir PRIMERO para tipar el resto).
4. Crear `features/tablas/repositories.py` (las 7 consultas SQL portadas, con retornos anotados — H3).
5. Crear `features/tablas/services.py` (lógica de pivote de `/datos`; aplicar `_sanitize_col` — A6).
6. Crear `features/tablas/api.py` (router con `response_model`, `Depends(get_prod_db)`, 503 si db_prod caído — H9).
7. Modificar `main.py` (registrar router + tag OPENAPI_TAGS; NO fail-fast por db_prod — H9).

**Bloque 1b — Infraestructura de test para db_prod** (NUEVO, resuelve H1/H2 — hacer ANTES de los tests)
8. Añadir a `tests/conftest.py` un fixture `patch_prod_db` que registre
   `app.dependency_overrides[get_prod_db]` apuntando a una sesión de test (SQLite en memoria con
   un mini-esquema `core.*` sembrado, o un fake que devuelva filas fijas). Los tests de `tablas`
   usan este override — **jamás** conectan al Postgres real. Documentar el porqué en el docstring
   (mismo estilo que `patch_db_for_integration`).
9. Crear `tests/features/test_tablas.py` con `@pytest.mark.integration` (H4) usando `patch_prod_db`.
   Cubrir: árbol, hojas perezosas, los 3 modos de `/datos` (fechas/matriz/texto), COMENTARIOS, y el
   503 cuando db_prod cae. Cobertura suficiente para no bajar del 75% (H5).
10. **Verificar backend:** `uv run ruff check .`, `uv run black --check .`, `uv run mypy src` (strict, H3),
    `uv run pytest --cov=src --cov-fail-under=75` (mismo comando que CI). Todo verde SIN Postgres.
11. **Prueba manual contra el 139** (con VPN, en pruebas): endpoints en `/docs` devuelven datos reales.

**Bloque 2 — Tipos**
12. `pnpm gen:types` → regenerar `api.d.ts` con los nuevos endpoints tipados (offline, sin servidor — C8).
    Verificar que el diff de `api.d.ts` contiene los paths `/api/v1/tablas/*`.

**Bloque 3 — Frontend feature control** (tests junto al código por H5)
13. Crear `features/control/types/` + `mappers/` (camelCase; contrato de dos interceptores).
14. Crear `features/control/services/controlService.ts` (apiClient + toApiError — N1/C1; nunca fetch).
15. Crear `features/control/hooks/` (useArbol, useHojasReporte, useDatosTabla — React Query).
16. Crear `features/control/components/ArbolReportes/` (+ .module.scss + index.ts + .test.tsx).
17. Crear `features/control/components/VisorTabla/` (+ .module.scss + index.ts + .test.tsx).
18. Crear `features/control/pages/ControlPage.tsx` (default export para lazy; + .test.tsx).
19. Modificar `app/router.tsx` (ruta `/control` dentro de children de ProtectedRoute).
20. **Verificar frontend con los MISMOS comandos que debería usar CI:**
    `pnpm lint`, `pnpm typecheck`, `pnpm build` (H8), y `pnpm test:front` (que SÍ propaga --coverage,
    a diferencia del roto `pnpm test -- --coverage` — H7). Umbral 80%×4 (H5) verde.

**Bloque 4 — Corrección de pipelines** (resuelve H6/H7/H8 — ver §11; requiere tocar ci.yml, fuera del
alcance de código de F1 pero necesario para que F1 se valide en CI)
21. Aplicar las correcciones de `ci.yml` de §11 (lock en raíz, `test:front`, añadir `pnpm build`).
    **CONFIRMAR con el usuario antes** — tocar CI está fuera del alcance estricto de "portar Control".

**Bloque 5 — Verificación end-to-end (R3)**
22. Arrancar `pnpm dev` en pruebas (con VPN). Abrir `/control`. El usuario:
    - ve el árbol año→mes→día,
    - expande un día → aparecen hojas/tablas,
    - abre una tabla → ve datos reales del 139.
23. El **usuario** marca F1 como verificada (R3 — build verde no basta).

---

## 7. Reglas no negociables

- **R1** — no tocar config de pnpm sin aprobación explícita.
- **R3** — F1 tiene interacción visual: build verde ≠ verificada. El usuario verifica en navegador.
- **U3** — mismo PostgreSQL y mismo esquema `core.*`; se reescribe solo la capa de acceso, no el SQL.
- **A6** — `_sanitize_col` antes de toda response numérica.
- **C3** — formateadores de `shared/utils/format.ts`, cada producto su escala (A5).
- **ADR-001** — cero imports cross-feature. `control` (front) y `tablas` (back) son autocontenidas.
- **N1/C1** — todo service frontend por `apiClient`, nunca `fetch` desnudo.
- **Contrato de error** — endpoints devuelven el JSON uniforme; 503 claro si db_prod caído.
- **SQL idéntico al origen** — no reescribir las consultas; están probadas en 50M+ filas.

---

## 8. Validaciones

- Backend: `uv run pytest` (cobertura ≥75%, L7), `ruff check`, `mypy src` — todo verde.
- Frontend: `pnpm build`, `pnpm lint`, `pnpm test` con cobertura ≥80% (L7).
- `/docs` muestra los endpoints de `tablas` bajo su tag.
- `/health` sigue reportando el estado de db_prod correctamente.
- Verificación humana en navegador (R3) con datos del 139.

---

## 9. Fuera de alcance (F1)

- **Menú de navegación** entre secciones (Consulta ↔ Control) — decidido con el usuario. Se hará
  cuando haya 3-4 secciones. Control se accede por URL `/control`.
- **RBAC de UI** (C4/DT-3): `useHasSection()`/gating por `permissions.sections`. Diferido junto con
  el menú.
- **Edición/escritura** de reportes o tablas — F1 es solo lectura (visor).
- **El chat, historial e insights** (paneles vacíos de Consulta) — eso es **F4**, depende de F2.
- **EBITDA, diferidas, mantenimientos** — F2.
- Optimización del SQL — se porta idéntico.

---

## 10. Decisiones (cerradas 2026-08-20)

| # | Decisión | Resuelto |
|---|---|---|
| DA-1 | **Control = todo usuario autenticado.** Los endpoints NO llevan `Depends(require_admin)`; basta la sesión válida que ya exige el middleware deny-by-default. | ✅ Usuario |
| DA-2 | **Una sola feature `tablas`** agrupa los 7 endpoints (tablas + reportes + kpis_prod). Evita 3 features triviales. | ✅ Usuario |
| DA-3 | Formateo del visor **genérico (número plano)** en F1; el refinamiento por hoja (formatBl/formatMscf, A5) se hace en F4 cuando el contexto de producto esté disponible. | ✅ Por defecto |

---

## 11. Correcciones de pipeline (H6/H7/H8) — Bloque 4

Oportunidades de mejora detectadas en la auditoría. Cierran DT-5 y DT-6 (ver CLAUDE.md §9) y añaden
la red de seguridad de build que hoy no existe. **Tocar `ci.yml` está fuera del alcance de "portar
Control" — requiere confirmación explícita del usuario (R1-análogo: no cambiar infraestructura sin
aprobación).** Diff propuesto para `.github/workflows/ci.yml`:

```yaml
# Job frontend — 3 cambios:

# H6 (DT-5): el lockfile del workspace vive en la RAÍZ, no en prodia_v02_frontend/.
# El install debe correr desde la raíz. Cambiar:
- uses: actions/setup-node@v4
  with:
    node-version: 22
    cache: pnpm
    cache-dependency-path: pnpm-lock.yaml          # ← era prodia_v02_frontend/pnpm-lock.yaml
# y mover el `pnpm install --frozen-lockfile` a working-directory raíz (o quitar el default y
# usar `pnpm -w install --frozen-lockfile`).

# H7 (DT-6): reemplazar el comando de test roto:
- run: pnpm test -- --coverage      # ← NO propaga --coverage (pnpm se come el `--`)
# por el script de la raíz que ya lo trae:
- run: pnpm test:front              # ← corre `vitest run --coverage`, evalúa el umbral 80%

# H8: añadir build al pipeline (el fallo tsc/vite no se atrapa hoy):
- run: pnpm build
```

**Nota:** el job frontend usa `pnpm/action-setup@v4 version: 9` — coincide con pnpm 11 local en mayor;
verificar que `--frozen-lockfile` acepta el lock generado por pnpm 11 (si CI usa pnpm 9 y el lock es
v11, puede haber incompatibilidad de `lockfileVersion` → considerar subir CI a pnpm 11).

---

## 12. Resumen de cambios v2 → v3 (por la auditoría de pipelines)

1. **Nuevo Bloque 1b**: fixture de override de `get_prod_db` en conftest — sin él, los tests de F1
   rompen CI (no hay Postgres). Era el hueco más grave del v2.
2. **Tipos estrictos obligatorios** (H3): portar el SQL "idéntico" NO basta; mypy strict exige tipar.
3. **Tests no opcionales** (H5): la cobertura cuenta la feature nueva en ambos lados.
4. **Markers obligatorios** (H4) y **comando de verificación = comando de CI** (usar exactamente
   `pytest --cov=src --cov-fail-under=75` y `pnpm test:front`, no variantes).
5. **db_prod crítico pero sin fail-fast global** (H9): 503 en la feature, no `raise` en el lifespan.
6. **Nuevo Bloque 4**: corrección de `ci.yml` (H6/H7/H8) — con confirmación del usuario.
7. **Verificación frontend incluye `pnpm build`** (H8): el error que rompió hoy no lo atrapa el CI actual.
