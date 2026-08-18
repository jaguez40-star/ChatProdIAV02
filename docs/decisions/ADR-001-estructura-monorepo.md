# ADR-001 — Estructura del monorepo

**Estado:** Aceptada · **Fecha:** 2026-08-18 · **Decisores:** usuario, Claude (plan F0)
**Tarea relacionada:** Plan F0 — cimiento + login

## Contexto

ProdIA V02 reconstruye "Análisis avanzado de producción diaria" como aplicación autónoma,
usando `C:\APLICACIONES\Robustez\Des_robustez_2.0` como plantilla arquitectónica. Robustez V02
ya resolvió esta decisión (su propio ADR-001) con un monorepo `uv`+`pnpm`; había que decidir
si replicar esa estructura o partir de otra.

## Decisión

Monorepo único, dos subproyectos hermanos:

```
ProdIA_V02/
├── prodia_v02_backend/     uv (Python), FastAPI, vertical slicing
├── prodia_v02_frontend/    pnpm (Node), React 19 + Vite + TS
├── Planes/                 plan ejecutable por fase (F0…F6)
└── docs/decisions/         ADRs
```

Vertical slicing en ambos lados: cada feature (`auth`, `permissions`, `audit` en F0; `tablas`,
`analisis`, `consulta`… en F1+) es autocontenida — `api.py`/`schemas.py`/`services.py` en el
backend, `components/hooks/mappers/pages/services/types` en el frontend. **Cero imports
cross-feature** (heredado de Robustez V02, ADR-001 original).

## Alternativas consideradas

1. **Dos repos separados** (backend / frontend) — rechazada: duplicaría configuración
   (`.gitignore`, `.editorconfig`), dificultaría coordinar el contrato OpenAPI↔tipos generados
   (`gen:types`, N3), y la coordinación de despliegue de F6 (corte con paridad verificada).
2. **Estructura por capas** (`api/services/repositories` transversales) — rechazada: el plan de
   Robustez V02 ya estableció vertical slicing como base de escalabilidad, y F1-F5 migran
   features completas una por una — la estructura por feature hace que cada fase sea un
   incremento aislado y revisable.
3. **Fusionar con el monorepo de Robustez V02** (nueva feature ahí) — rechazada explícitamente
   por el usuario: ProdIA V02 debe quedar desacoplada en despliegue y ciclo de vida (ver
   ADR-002 para la misma lógica aplicada al padrón de usuarios).

## Consecuencias

**Positivas:**
- Cada subproyecto usa su gestor de paquetes sin ceremonia (`uv sync` / `pnpm install`)
- Los tipos del frontend se regeneran desde el OpenAPI real del backend (`scripts/export_openapi.py`
  → `openapi-typescript`, ver corrección H5/N3 — offline, sin backend vivo)
- Cada feature es una unidad de migración clara para F1-F5

**Negativas / compromisos:**
- Dos comandos de arranque — mitigado con `concurrently` (`pnpm dev` levanta ambos)
- Sin CI hasta que exista un remoto configurado (a diferencia de Robustez V02, que tampoco
  tiene — corrección C13: ProdIA V02 sí trae el workflow desde F0, listo para cuando se
  configure el remoto)

## Verificación

- `pnpm setup && pnpm dev` levanta backend (`:6034`) y frontend (`:6033`) en paralelo
- `pnpm run gen:types` regenera `prodia_v02_frontend/src/shared/types/api.d.ts` sin requerir
  el backend corriendo (offline)

## Referencias

- Plantilla: `C:\APLICACIONES\Robustez\Des_robustez_2.0\robustez_v02_backend\docs\decisions\ADR-001-monorepo-structure.md`
- `CLAUDE.md` §3 (Arquitectura), §5 (Herencia de Robustez V02)
