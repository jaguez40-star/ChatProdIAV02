# ProdIA V02

Aplicación de análisis de producción petrolera (Ecopetrol), reconstruida como app autónoma
sobre el stack y las convenciones probadas en producción de `Robustez V02`
(`C:\APLICACIONES\Robustez\Des_robustez_2.0`).

**Antes de tocar nada, lee `CLAUDE.md`** — ahí vive el porqué, el inventario de lo que se está
migrando, las reglas de dominio que no se pueden romper, y el roadmap por fases (F0-F6).

## Arranque en 5 pasos

1. `pnpm setup` — instala Python 3.12 (uv), dependencias del backend y del frontend
2. Copia `prodia_v02_backend/.env.example` a `prodia_v02_backend/.env` y completa los valores
3. `cd prodia_v02_backend && uv run alembic upgrade head` — crea `data/prodia_v02_auth.db` y
   siembra el padrón de usuarios (ver `CLAUDE.md` §6 y `docs/decisions/ADR-002-*.md`)
4. `pnpm dev` — levanta backend (`:6034`) y frontend (`:6033`) en paralelo
5. Abre `http://localhost:6033`

## Estructura

```
prodia_v02_backend/    FastAPI, vertical slicing por feature, SQLAlchemy Core, Alembic
prodia_v02_frontend/   React 19 + TypeScript + Vite, TanStack Query, Zustand
Planes/                Plan ejecutable de cada fase (F0…F6)
docs/decisions/         ADRs — decisiones de arquitectura con su porqué
```

## Estado

Ver §9 de `CLAUDE.md` (roadmap) para el estado actual por fase.
