# Plan F1a — Cascarón de Consulta: tres paneles con reparto por pareja

**Fecha:** 2026-08-18 · **Versión:** **v2** (v1 + auditoría de pipelines con 6 hallazgos H1-H6)
**Alcance:** re-propósito de los 3 paneles de la página principal + reparto de ancho dependiente
de la pareja abierta. **Solo el contenedor** — los cuerpos siguen vacíos.
**Modo:** EXECUTOR (agente sin acceso a la conversación que originó este plan)

---

## 0. Prerequisitos verificados contra el código real (2026-08-18)

Medidos, no estimados. El Executor debe **re-verificar todos** antes de empezar; si alguno no
coincide, DETENERSE y reportar — significa que el código cambió desde que se escribió el plan.

Rutas relativas a `prodia_v02_frontend/` salvo indicación contraria.

| # | Comando de verificación | Resultado esperado |
|---|---|---|
| P-1 | `grep -c "id: 'ingesta' \| 'control' \| 'analisis'" src/features/home/data/secciones.ts` | `1` |
| P-2 | `grep -c "ABIERTOS_INICIALES: SeccionPrincipal\['id'\]\[\] = \['control', 'analisis'\]" src/features/home/data/secciones.ts` | `1` |
| P-3 | `grep -c "flex: 1 1 0" src/features/home/components/PanelColapsable/PanelColapsable.module.scss` | `1` |
| P-4 | `grep -c "grow" src/features/home/components/PanelColapsable/PanelColapsable.tsx` | `0` (no existe todavía) |
| P-5 | `grep -c "features/home" src/app/router.tsx` | `1` |
| P-6 | `pnpm exec vitest run` | **132 tests, 32 archivos, todos en verde** |
| P-7 | `pnpm exec vitest run --coverage` | `All files ≈ 92.7 %` (umbral L7 = 80 %) |
| P-8 | *(raíz)* `git log --oneline` | **falla: "does not have any commits yet"** — ver H2 |
| P-9 | *(raíz)* `git config core.ignorecase` | `true` — Windows, ver H3 |

**P-10 — El directorio de trabajo es `prodia_v02_frontend/`.** Este plan NO toca el backend.

---

## 0-bis. Hallazgos de la auditoría de pipelines (H1-H6)

Esta sección es **nueva en v2**. Se auditó `.pre-commit-config.yaml`, `.github/workflows/ci.yml`,
`eslint.config.js`, `tsconfig*.json` y el estado de git contra los cambios que propone el plan.
Los hallazgos 🔴 son defectos **preexistentes** que este plan destapa o agrava; los 🟡 son
trampas del propio plan v1.

### 🔴 H1 — El CI nunca ha medido la cobertura (defecto preexistente)

`ci.yml` ejecuta `pnpm test -- --coverage`. El script `test` del frontend es `vitest run`, y pnpm
**se come el `--`**: el flag nunca llega a vitest. Verificado:

```
pnpm test -- --coverage | grep -c "All files"   →  0     (no genera cobertura)
pnpm exec vitest run --coverage | grep -c "All files"  →  1  (sí la genera)
```

**Consecuencia:** el umbral del 80 % × 4 de L7 —que `CLAUDE.md` §5.1 declara como *"esto sostiene
la estabilidad, no los tests en sí"*— **no se ha evaluado nunca en CI**. La build pasa en verde
con cualquier cobertura.

**Por qué importa a este plan:** el plan v1 pedía "no bajar del 80 %" apoyándose en un guardián
que no existe. Se corrige en el paso 0 (§5).

### 🔴 H2 — El repositorio no tiene ningún commit

`git log` falla con *"your current branch 'main' does not have any commits yet"*, y
`git status` reporta `features/` entero como `??` (sin seguimiento).

**Consecuencia doble:**
1. **No hay punto de retorno.** Si el renombrado sale mal, no existe `git checkout` que revierta.
2. El hook `gen-types-check` de pre-commit corre `git diff --exit-code` — sin `HEAD`, su
   comportamiento no está verificado.

**Corrección:** commit inicial **antes** de tocar nada (paso 0). No es opcional.

### 🔴 H3 — `core.ignorecase=true`: el renombrado de directorio es frágil en Windows

Git está configurado para ignorar mayúsculas. Un renombrado `home` → `consulta` no colisiona por
caso, pero el patrón general (renombrar directorios en Windows + git) es una fuente conocida de
renombrados fantasma que git no registra.

**Corrección:** usar `git mv` en vez de `mv`/Explorador, **después** del commit inicial de H2, y
verificar con `git status` que git registró el rename y no un par borrado+añadido.

### 🔴 H4 — `ci.yml` apunta a un lockfile que no existe

```yaml
cache-dependency-path: prodia_v02_frontend/pnpm-lock.yaml
```

Ese archivo **no existe** — el lockfile vive en la raíz (`./pnpm-lock.yaml`), porque es un
workspace pnpm. Verificado: `ls prodia_v02_frontend/pnpm-lock.yaml` → *No such file*.

Además `pnpm install --frozen-lockfile` corre con `working-directory: prodia_v02_frontend`, lo
que en un workspace instala desde la raíz de todos modos, pero la caché queda inútil.

**Nota de alcance:** H4 **no bloquea** este plan (degrada la caché, no rompe la build) y tocar CI
excede el cascarón. Se **documenta como deuda técnica** (§8) y NO se corrige aquí.

### 🟡 H5 — El plan v1 subestimaba la superficie del renombrado

`grep -rn "features/home\|HomePage"` devuelve **6 referencias en código**, no las 2 que insinuaba
el inventario de v1: `router.tsx` (×2, el import y el nombre de la constante local),
`HomePage.tsx` (×1, el `export default`), `HomePage.test.tsx` (×3, import + `describe` + `render`).

**Corrección:** §3 lista las 6, y V-6 se endurece para cazarlas todas.

### 🟡 H6 — `flex: var(--pv-panel-grow, 1) 1 0` y la transición

La regla `.panel` anima `flex 0.32s`. Al mover el `flex-grow` a una custom property **sin
tipar**, el navegador la trata como texto y **la transición del grow puede no interpolar**, con
lo que el reparto saltaría en seco al cambiar de pareja — exactamente el defecto visual que R3
existe para atrapar.

**Corrección:** registrar la propiedad con `@property` (sintaxis `<number>`), lo que la hace
animable. Detalle en §4.4. Es la razón por la que V-7 (navegador) es obligatoria.

---

## 1. Contexto

### Qué existe hoy

La página principal (`/`) monta un acordeón horizontal de tres paneles colapsables, heredado del
`HorizontalAccordion` de Robustez V02 y repintado con los tokens `$pv-*`. Funciona: máximo 2
abiertos en escritorio, 1 en móvil, nunca cero. Los cuerpos están vacíos a propósito.

Los tres paneles se llaman hoy **Ingesta / Control / Análisis** — nombres tomados del roadmap de
fases, no de un diseño de producto.

### Qué cambia y por qué

El usuario definió el uso real de los tres paneles, que **no** es el que suponen los nombres
actuales:

| Panel | Propósito real |
|---|---|
| Izquierdo | **Historial** — registro de conversaciones del usuario |
| Central | **Chat** — la conversación activa |
| Derecho | **Insights** — gráficos derivados de la respuesta del chat |

Y con ello, un reparto de ancho que **depende de qué pareja está abierta**:

| Pareja abierta | Reparto |
|---|---|
| Historial + Chat | 25 % / 75 % |
| Chat + Insights | 50 % / 50 % |
| Historial + Insights | 25 % / 75 % (decisión del usuario) |

### 🔴 Advertencia de alcance que el Executor debe conocer

**Historial + Chat + Insights es la pestaña Consulta, es decir F4** — 4.901 líneas de origen,
Motor Q v2, y según `CLAUDE.md` §10 depende de F2. Este plan entrega **únicamente el cascarón**:
contenedor, títulos y reparto. Ningún cuerpo, ningún dato, ningún LLM.

El Executor **no debe** implementar chat, historial persistido, gráficos ni llamadas a API.
Si el plan parece incompleto en ese sentido, es deliberado.

---

## 2. Objetivo

Al terminar, la página `/`:

1. Muestra tres paneles llamados **Historial**, **Chat** e **Insights**.
2. Aplica el reparto de ancho de la tabla anterior, **con transición animada** (H6).
3. Conserva intacta la mecánica actual: máx. 2 abiertos (1 en móvil), nunca cero, tira vertical
   al colapsar, apilado en columna bajo 1024 px.
4. Mantiene los cuerpos vacíos.
5. Pasa build + lint + typecheck + tests con cobertura ≥ 80 % **medida de verdad** (H1).

---

## 3. Inventario de archivos

### Se renombra (con `git mv`, ver H3)

| Origen | Destino |
|---|---|
| `src/features/home/` | `src/features/consulta/` |
| `…/pages/HomePage.tsx` | `…/pages/ConsultaPage.tsx` |
| `…/pages/HomePage.test.tsx` | `…/pages/ConsultaPage.test.tsx` |

Motivo: `home` describe una ruta, no un dominio. El dominio es Consulta (F4). Renombrarlo ahora
evita que F4 herede un nombre que miente.

### Las 6 referencias en código a actualizar (H5 — lista exhaustiva)

| Archivo | Línea aprox. | Referencia |
|---|---|---|
| `src/app/router.tsx` | 9 | `const HomePage = lazy(() => import('../features/home/pages/HomePage'))` |
| `src/app/router.tsx` | 23 | `element: withSuspense(HomePage)` |
| `…/pages/HomePage.tsx` | 8 | `export default function HomePage()` |
| `…/pages/HomePage.test.tsx` | 4 | `import HomePage from './HomePage'` |
| `…/pages/HomePage.test.tsx` | 6 | `describe('HomePage', …)` |
| `…/pages/HomePage.test.tsx` | 8 | `render(<HomePage />)` |

### Se modifica

| Archivo (tras el renombrado) | Cambio |
|---|---|
| `src/features/consulta/data/secciones.ts` | ids, títulos, subtítulos, iconos, abiertos iniciales |
| `…/components/AcordeonHorizontal/AcordeonHorizontal.tsx` | cálculo del `grow` y su paso como prop |
| `…/components/AcordeonHorizontal/AcordeonHorizontal.test.tsx` | tests de reparto |
| `…/components/PanelColapsable/PanelColapsable.tsx` | acepta y aplica `grow` |
| `…/components/PanelColapsable/PanelColapsable.module.scss` | `@property` + `flex-grow` por variable |
| `src/app/router.tsx` | ruta `/` apunta al nuevo path |
| `package.json` *(raíz)* | script `test:front` → cobertura real (H1, paso 0) |

### NO se toca

- `src/app/layouts/` — el header y el menú de usuario ya están verificados por el usuario.
- `src/shared/hooks/useIsMobile.ts`.
- `.github/workflows/ci.yml` — H4 queda como deuda documentada, no se corrige aquí.
- Cualquier archivo del backend.

---

## 4. Especificación

### 4.1 `secciones.ts`

```ts
export interface SeccionPrincipal {
  id: 'historial' | 'chat' | 'insights';
  num: number;
  titulo: string;
  subtitulo: string;
  icono: LucideIcon;
}
```

| id | num | titulo | subtitulo | icono (lucide-react) |
|---|---|---|---|---|
| `historial` | 1 | `Historial` | `Conversaciones anteriores` | `MessagesSquare` |
| `chat` | 2 | `Chat` | `Consulta en lenguaje natural` | `MessageCircle` |
| `insights` | 3 | `Insights` | `Gráficos de la respuesta` | `ChartColumn` |

```ts
export const ABIERTOS_INICIALES: SeccionPrincipal['id'][] = ['historial', 'chat'];
export const MAX_ABIERTOS_ESCRITORIO = 2;   // sin cambio
export const MAX_ABIERTOS_MOVIL = 1;        // sin cambio
```

**Estado inicial = Historial + Chat (25/75)**, que es la vista de trabajo por defecto.

⚠️ Verificar que los tres iconos existen en la versión instalada de `lucide-react` (^0.469).
Si `ChartColumn` no existiera, usar `BarChart3`. Un icono inexistente rompe el build.

### 4.2 Regla de reparto — el núcleo de esta fase

El ancho **no es propiedad de un panel**, sino de la pareja abierta. El mismo panel Chat vale
75 % junto a Historial y 50 % junto a Insights.

La regla completa, en una línea:

> **`grow` = 1 si el panel es `historial`; 3 en cualquier otro caso.**

Verificación de que produce los tres repartos pedidos, con `flex: <grow> 1 0`:

| Pareja | grows | Reparto resultante |
|---|---|---|
| historial + chat | 1 : 3 | 1/4 y 3/4 → **25 % / 75 %** ✅ |
| chat + insights | 3 : 3 | 1/2 y 1/2 → **50 % / 50 %** ✅ |
| historial + insights | 1 : 3 | 1/4 y 3/4 → **25 % / 75 %** ✅ |
| un solo panel abierto | cualquiera | **100 %** (ver §4.5) |

**No se calculan porcentajes ni píxeles.** El reparto emerge de flexbox.

### 4.3 `AcordeonHorizontal.tsx`

Añadir, sin tocar la lógica de apertura/colapso ya existente:

```ts
/**
 * El ancho depende de la PAREJA abierta, no del panel: Chat ocupa 75 % junto
 * a Historial y 50 % junto a Insights. Historial es el único angosto.
 */
const growDe = (id: IdSeccion) => (id === 'historial' ? 1 : 3);
```

y pasarlo al panel: `grow={growDe(seccion.id)}`.

⚠️ **No convertir `growDe` en `useCallback` ni meterlo en un `useMemo`.** Es una función pura sin
dependencias; envolverla añade ruido sin beneficio y `react-hooks/exhaustive-deps` (activo en
`eslint.config.js`) puede exigir dependencias artificiales.

### 4.4 `PanelColapsable` — y la trampa de la animación (H6)

Nueva prop en la interfaz:

```ts
/** Peso de reparto horizontal. Lo decide el acordeón, que es quien conoce
 *  la pareja abierta — ver AcordeonHorizontal.growDe(). */
grow: number;
```

Se aplica **por variable CSS**, no por clase (el valor es dinámico):

```tsx
<div className={clases} style={{ '--pv-panel-grow': grow } as CSSProperties}>
```

En el SCSS, **registrar primero la propiedad** para que sea animable (H6) — sin esto el
navegador la trata como texto y el reparto salta en seco en vez de transicionar:

```scss
// Sin @property, --pv-panel-grow es una cadena y la transición de `flex`
// no puede interpolarla: el ancho saltaría en seco al cambiar de pareja.
@property --pv-panel-grow {
  syntax: '<number>';
  inherits: false;
  initial-value: 1;
}

.abierto {
  flex: var(--pv-panel-grow, 1) 1 0;
  // …resto sin cambios
}
```

⚠️ El `grow` **solo aplica al panel abierto**. `.colapsado` conserva
`flex: 0 0 clamp(58px, 7vw, 80px)` — su ancho es fijo y no participa del reparto.

⚠️ Si stylelint o el compilador de Sass rechazara `@property`, **NO eliminarlo sin más**:
reportar. La alternativa aceptable es declararlo en `src/shared/styles/index.scss` (que es CSS
global, no un módulo), nunca renunciar a la animación en silencio.

### 4.5 Panel solitario (caso límite)

Cuando queda un único panel abierto ocupa el 100 %, incluido Historial. Se acepta así en esta
fase: es coherente con la regla y no rompe nada. **No añadir `max-width`** — sería una decisión
de diseño no solicitada.

### 4.6 Renombrado de `HomePage` → `ConsultaPage`

El componente sigue siendo un envoltorio de una línea sobre `AcordeonHorizontal`. Actualizar las
6 referencias de §3. La ruta sigue siendo `/`.

---

## 5. Orden de ejecución

**Un artefacto por turno** (flujo de 6 pasos, `CLAUDE.md` §0). Verificar entre pasos.

| # | Paso | Verificación |
|---|---|---|
| **0a** | **Commit inicial del repo** (H2): `git add -A && git commit`. Mensaje: `chore: commit inicial — F0 completo + cascarón de paneles` | `git log --oneline` devuelve 1 commit |
| **0b** | **Arreglar la medición de cobertura** (H1): en `package.json` de la raíz, `"test:front"` pasa a `pnpm --filter prodia-v02-frontend test -- --coverage` **NO funciona** — usar `pnpm --filter prodia-v02-frontend exec vitest run --coverage` | `pnpm run test:front` imprime la tabla `All files` |
| 1 | `git mv` del directorio y de los dos archivos de página (H3); actualizar las 6 referencias de §3 | `git status` muestra **renames**, no borrado+añadido; `pnpm exec tsc -b --noEmit` en verde |
| 2 | Reescribir `secciones.ts` según §4.1 | `tsc` en verde; los tests fallarán (esperan nombres viejos) — correcto en este punto |
| 3 | Añadir `@property` + prop `grow` a `PanelColapsable` (§4.4) | `tsc` en verde |
| 4 | Añadir `growDe()` en `AcordeonHorizontal` y pasarlo (§4.3) | `tsc` en verde |
| 5 | Actualizar los tests con los nombres nuevos + añadir los de reparto (§6) | `pnpm exec vitest run` en verde |
| 6 | Verificación final completa | §7 |

⚠️ **El paso 0 no es opcional.** Sin commit inicial no hay forma de revertir el renombrado del
paso 1, y sin la corrección de cobertura V-4 mide algo que el CI ignora.

---

## 6. Tests obligatorios

Además de adaptar los existentes a los nombres nuevos, añadir en
`AcordeonHorizontal.test.tsx`:

| Test | Aserción |
|---|---|
| Estado inicial | Historial y Chat abiertos (`aria-expanded="true"`), Insights colapsado |
| Reparto Historial + Chat | el panel de Historial lleva `--pv-panel-grow: 1`; el de Chat, `3` |
| Reparto Chat + Insights | tras colapsar Historial y abrir Insights, ambos llevan `3` |
| Reparto Historial + Insights | con Chat colapsado, Historial lleva `1` e Insights `3` |
| Máximo 2 (ya existe) | abrir un tercero colapsa el más antiguo |
| Nunca cero (ya existe) | el último abierto queda `disabled` con su `title` |

### ⚠️ Dos convenciones de este repo que rompen el build si se ignoran

**1. Los matchers de `@testing-library/jest-dom` NO están tipados aquí.** Usar
`toBeInTheDocument`, `toHaveAttribute` o `toBeDisabled` produce `error TS2339` y el typecheck
falla. Assertar sobre propiedades directas del DOM:

```ts
expect(el.getAttribute('aria-expanded')).toBe('true');
expect(btn.disabled).toBe(true);
```

**2. El grow se lee del estilo inline, no del computado.** jsdom no resuelve `@property`:

```ts
const panel = boton.closest('div') as HTMLElement;
expect(panel.style.getPropertyValue('--pv-panel-grow')).toBe('1');
```

Ambas verificadas durante la implementación del acordeón actual.

---

## 7. Validaciones (todas obligatorias)

| # | Comando | Criterio |
|---|---|---|
| V-1 | `pnpm exec tsc -b --noEmit` | exit 0, sin salida |
| V-2 | `pnpm exec eslint .` | exit 0, sin salida |
| V-3 | `pnpm exec vitest run` | 100 % en verde, **≥ 132 tests** (no puede bajar) |
| V-4 | `pnpm exec vitest run --coverage` | `All files ≥ 80 %` (umbral L7) |
| V-5 | `pnpm exec vite build` | `✓ built` sin errores |
| V-6 | *(raíz)* `grep -rn "features/home\|HomePage" --include="*.ts" --include="*.tsx" prodia_v02_frontend/src` | **sin resultados** (H5) |
| V-7 | *(raíz)* `pnpm run test:front` | imprime la tabla `All files` (confirma H1 corregido) |
| V-8 | *(raíz)* `git status --short` | los renames aparecen como `R`, no como `D`+`A` (H3) |

**V-9 — Verificación humana en navegador (R3, no negociable).** Build verde **no** es feature
verificada. El Executor debe reportar que falta esta verificación y NO declarar la fase
completa sin ella. Puntos a comprobar por el usuario:

- El reparto 25/75 y 50/50 se ve correcto.
- 🔴 **La transición ANIMA al cambiar de pareja** — no salta en seco. Es el punto exacto que H6
  identifica como riesgo; si salta, `@property` no está surtiendo efecto.
- Bajo 1024 px el acordeón pasa a columna y las tiras vuelven a horizontales.
- El último panel abierto no se puede colapsar.

---

## 8. Reglas no negociables

1. **Todo en español**: código, comentarios, nombres de test, commits (`CLAUDE.md` §0).
2. **Cuerpos vacíos.** No implementar chat, historial, gráficos ni llamadas a API. Este plan
   entrega un cascarón; el contenido es F4.
3. **No tocar el backend**, ni `src/app/layouts/`, ni la configuración de pnpm (**R1**).
4. **No tocar `.github/workflows/ci.yml`.** H4 (lockfile inexistente en la caché) queda como
   deuda técnica documentada — corregirlo excede este plan.
5. **Cero imports cross-feature** (ADR-001): `features/consulta/` no importa de otra feature.
6. **Tokens `$pv-*` únicamente** (C11). Nada de `$rb-*`/`$ec-*` ni colores literales.
7. **No bajar la cobertura** por debajo de 80 % (L7).
8. **No añadir dependencias.** Todo lo necesario ya está instalado.
9. Si un prerequisito de §0 no coincide, o si `@property` no se puede aplicar (§4.4),
   **DETENERSE y reportar** en vez de improvisar.

---

## 9. Fuera de alcance

- Contenido de los tres paneles (chat, historial persistido, gráficos) → **F4**.
- Motor Q v2 y sus reglas Q1-Q5 → **F4**.
- Corrección de H4 (`cache-dependency-path` en `ci.yml`) → deuda documentada.
- Persistencia del conjunto de paneles abiertos entre sesiones (decisión abierta).
- `max-width` para el panel solitario (§4.5).
- RBAC de UI / `useHasSection()` (C4, DT-3) → cuando exista navegación multi-sección.
- Header, menú de usuario, footer — ya verificados por el usuario.
- Cualquier cambio en el backend.

---

## 10. Deuda técnica a registrar en `CLAUDE.md` §9

El Executor debe añadir estas filas al terminar:

| # | Deuda | Origen | Impacto |
|---|---|---|---|
| DT-5 | `ci.yml` usa `cache-dependency-path: prodia_v02_frontend/pnpm-lock.yaml`, archivo que no existe — el lockfile del workspace vive en la raíz | Auditoría F1a (2026-08-18) | La caché de pnpm en CI nunca acierta; builds más lentas, sin fallo funcional |
| DT-6 | `pnpm test -- --coverage` no propaga el flag a vitest: el umbral L7 del 80 % no se evaluó en CI desde F0 | Auditoría F1a (2026-08-18) | Corregido en `test:front`; **`ci.yml` sigue usando el comando roto** — cerrar cuando se toque CI |

---

## 11. Formato de commit

```
feat(F1a): re-propósito de los 3 paneles a Historial/Chat/Insights con reparto por pareja
```

Explicando en el cuerpo **por qué** el grow lo calcula el acordeón y no el panel: el ancho es
propiedad de la pareja abierta, no del panel individual — Chat vale 75 % junto a Historial y
50 % junto a Insights.
