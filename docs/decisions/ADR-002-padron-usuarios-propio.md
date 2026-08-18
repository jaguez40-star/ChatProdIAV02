# ADR-002 — Padrón de usuarios propio, sembrado desde Robustez V02

**Estado:** Aceptada · **Fecha:** 2026-08-18 · **Decisores:** usuario, Claude (plan F0)
**Tarea relacionada:** Plan F0 — cimiento + login, migración `0003_seed_padron`

## Contexto

Robustez V02 **no tiene forma de crear su primer usuario**. Verificado exhaustivamente:
`alembic/versions/0001_initial_auth.py` y `0002_app_settings.py` son solo DDL, sin un
`INSERT`; sus `scripts/` no incluyen ningún seed reutilizable (el único candidato,
`migrate_v01_auth.py`, copia usuarios desde una BD V01 que no existe para un proyecto nuevo);
su `Makefile` no tiene target `seed`/`bootstrap`. Consecuencia: tras `alembic upgrade head`
sobre una BD vacía, **todo login falla con 401** "Usuario no registrado en la aplicación" —
incluso con LDAP válido y login local habilitado, porque la verificación de existencia en
`app_users` ocurre en el paso 1 de `AuthService.authenticate_ldap`, antes del login local.

ProdIA V02 hereda el mismo problema si copia la plantilla sin corregirlo — sin un seed
propio, F0 entrega un login que no deja entrar a nadie.

## Decisión

**Padrón PROPIO**, no compartido con Robustez V02, sembrado en la migración
`0003_seed_padron` importando de `robustez_v02_auth.db` **solo tres columnas**:
`username`, `email`, `full_name`. Todo lo demás de esa base (2 grupos, 1.030+143 permisos de
campo, 206+15 permisos de sección, 352+320 filas de bitácora) **no se copia** — los permisos
de sección de Robustez V02 apuntan a secciones que no existen en ProdIA
(`ebitda_rank`, `analytics`, `regresiones`…) y la bitácora es de otra aplicación.

La migración:
- Abre la BD origen en **modo solo lectura** (`file:...?mode=ro`, URI de SQLite) — nunca la
  modifica. Verificado con checksum idéntico antes/después (V6c).
- Crea 2 grupos propios: `Administradores` (is_admin=1) y `Consulta` (is_admin=0, destino por
  defecto de los 29 usuarios importados).
- Es **idempotente** (`INSERT ... ON CONFLICT DO NOTHING`) — re-ejecutar `alembic upgrade
  head` no duplica filas.
- **Falla ruidosamente** si `SEED_SOURCE_AUTH_DB` no existe o `SEED_ADMIN_USERNAMES` está
  vacío — nunca deja un padrón sin ningún administrador (el mismo problema que tiene hoy
  Robustez V02, evitado por diseño).

`full_name` se copia **tal cual**, incluidos los 27 de 29 registros vacíos (medido contra la
BD real) — no se derivan nombres a partir del username. El primer admin sembrado en F0 es
`javier.guerrero` (ya marcado `is_admin=1` en el origen).

## Alternativas consideradas

1. **Compartir la BD de Robustez V02** (`DATABASE_URL` apuntando directo a
   `robustez_v02_auth.db`) — rechazada por el usuario: acopla el ciclo de vida de dos
   aplicaciones con propósitos y calendarios de despliegue distintos; dar de alta a alguien en
   una app lo daría de alta en la otra sin que sea la intención.
2. **Copiar TODA la BD** (grupos, permisos, bitácora incluidos) — rechazada: los permisos de
   sección son específicos del dominio de Robustez (KPIs de EBITDA, regresiones…), no tienen
   sentido en ProdIA (Ingesta, Análisis, Consulta…); habría que reconciliar dos taxonomías de
   secciones desde el día 1 sin necesidad.
3. **Seed manual vía script aparte** (`scripts/seed_admin.py`, corrido a mano tras las
   migraciones) — rechazada por el usuario a favor de una migración Alembic versionada:
   reproducible en cualquier entorno con el mismo comando (`alembic upgrade head`), sin un
   paso manual que alguien pueda olvidar al desplegar.

## Consecuencias

**Positivas:**
- Login funcional desde el primer `alembic upgrade head` en cualquier entorno nuevo
- Las dos aplicaciones (Robustez V02, ProdIA V02) quedan desacopladas — mismo padrón humano
  de partida, gestión de acceso independiente de ahí en adelante
- Verificado con checksum que la migración NUNCA escribe en la BD de Robustez V02 (producción)

**Negativas / compromisos:**
- 27 de 29 usuarios importados no tienen `full_name` — el frontend degrada mostrando
  `username`/`email` (mismo fallback que ya usa Robustez V02 en su `Header`)
- El seed es un snapshot puntual (2026-08-17) de la BD de Robustez V02 — usuarios dados de
  alta ahí después de esa fecha no aparecen automáticamente en ProdIA V02; requiere gestión
  de usuarios propia en fases posteriores (fuera de alcance de F0)

## Verificación

- V6: `alembic upgrade head` sobre BD vacía → 29 usuarios, 2 grupos, admin correcto
- V6b: 0 filas en tablas de permisos/bitácora (no se importan)
- V6c: checksum de la BD origen idéntico antes/después
- V7: sin `SEED_ADMIN_USERNAMES` o con origen inexistente → falla con instrucciones claras

## Referencias

- `INGESTA`... n/a (no aplica a este proyecto)
- `prodia_v02_backend/alembic/versions/0003_seed_padron.py`
- `CLAUDE.md` §6 (inventario) y §8 (decisiones D1-D4)
