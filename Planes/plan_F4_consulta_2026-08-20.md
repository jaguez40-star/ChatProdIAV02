# Plan F4 — Consulta (Motor Q v2 + chat + pila de paneles)

> **Plan v2** — auditado contra el código real del origen Y contra los **pipelines
> configurados** del destino (2026-08-20). Formato según CLAUDE.md §0. Para el executor:
> seguir el **Orden de ejecución**, un artefacto por turno, verificación al cerrar cada bloque.
>
> **Fuente de la auditoría**: lectura directa de las 6.009 líneas de
> `INGESTA/Rep_Prod/backend/app/features/consulta_v2/` y de las 5.308 de
> `static/js/multitab_shell.js`. Cada hallazgo cita fichero y línea del origen.
>
> **v2 añade** la §0.4 (auditoría de pipelines, AP-1…AP-8, con cifras medidas ejecutando
> los pipelines) y reformula el Orden de ejecución en consecuencia: el Bloque 0 pasa a ser
> bloqueante y se añade una verificación de cobertura **por bloque**, no al final.

---

## 0. Hallazgos de la auditoría — LEER PRIMERO

F4 es la fase **más grande** (6.009 líneas de origen, no 4.901 como decía el inventario) y la
única con un **LLM en el camino crítico de cada petición**. El riesgo dominante no es perder
datos —como en F3— sino **decir una cifra equivocada con total confianza**.

### 0.1 Correcciones al inventario de CLAUDE.md §6

Medido el 2026-08-20 con `wc -l`. Corregir §6 al cerrar la fase:

| Dato en CLAUDE.md | Real medido | Evidencia |
|---|---|---|
| `consulta_v2/` = 4.901 líneas + 442 YAML | **6.009 total** (5.567 `.py` + 442 YAML) | `find … \| xargs wc -l` |
| `clasificacion_golden.yaml` = 34 casos | **75 casos** | `grep -c` sobre el YAML |
| — (no inventariado) | `respuesta_jerarquizar.py` = **716 líneas**, el mayor del paquete | — |
| Tests a portar: "se portan con su feature" | **3.412 líneas** en 16 ficheros | `wc -l tests/test_{consulta,cuantificar,analizar,…}` |

Los otros dos golden sí coinciden: `cuantificar_golden` 24 casos, `analizar_golden` 10. Gate
≥90 % confirmado (`golden/run_golden.py:40`).

### 0.2 Hallazgos que condicionan la arquitectura (H1-H9)

| # | Hallazgo | Evidencia (origen) | Consecuencia | Acción |
|---|---|---|---|---|
| **H1** | **El ciclo de dependencias es bidireccional.** En F2 registramos `analisis → consulta`; el flujo dominante es el inverso: el motor Q **importa endpoints de análisis y los llama como funciones**. | `respuesta_analizar.py:19,28` · `cuantificar/ejecutor.py:12` · `cuantificar/niveles.py:7` · `analizar/economia.py:15` | Copiar tal cual viola ADR-001 en 4 sitios | **El origen ya inyecta** (`fn = _desempeno_fn or _desempeno_ep`): F4 consume **servicios**, no rutas. Ver §5.1 |
| **H2** | **La memoria conversacional es un `dict` de proceso sin TTL ni lock.** Reinicio = amnesia; multi-worker = memoria incoherente. | `maquina_q.py:35` (`_CTX = {}`) | El panel "Historial" del cascarón F1a **exige** persistencia | Migración `0004` en `db_auth`. Ver §5.6 |
| **H3** | **`cuant_kpi` NO existe en el dispatcher del frontend.** Verificado: `grep -c "cuant_kpi" multitab_shell.js` → **0**. El tipo más común (N1/N2) cae al fallback *por accidente*. | `respuesta_cuantificar.py:41,182` emite · `multitab_shell.js:2807` fallback | Es Q5 con prueba: un tipo nuevo pinta campos ajenos **sin error visible** | Unión discriminada + `PanelDesconocido` explícito. Ver §5.8 |
| **H4** | **I/O de fichero en tiempo de import.** `respuesta_cuantificar.py:27` ejecuta `_catalogo.get()` a nivel de módulo → lee YAML al importar. Como `api.py → maquina_q → respuesta_cuantificar`, **importar la app lee disco**. | `respuesta_cuantificar.py:27` | Rompe AP-2. El hook `gen-types-check` corre en cada `git commit` del equipo | Carga perezosa + validación en `lifespan`. Ver §5.2 |
| **H5** | **PyYAML no está declarado.** Llega solo como transitiva de `pre-commit` (dev) y de `uvicorn[standard]` (extra). | `pyproject.toml` sin `pyyaml`; `uv.lock:820,1360` | F4 depende de un detalle de otra librería | **DA-1**: declararlo explícito (R1 exige tu aprobación) |
| **H6** | **La libreta escribe en `core.clasificacion_log` de Postgres.** Hasta hoy `db_prod` es de solo lectura en las 3 fases. | `log.py:29,53,66` · migración origen `010_clasificacion_log.sql` (48 líneas) | F4 sería la 2ª fase que escribe (tras F3) y en **otra** BD | **DA-2**: decidir `db_prod` vs `db_auth`. Ver §5.7 |
| **H7** | **El golden runner llama al LLM real y a Postgres.** `run_golden_cuantificar.py:9-11` advierte "⚠️ NO correr en dev". | `golden/run_golden*.py` | **No puede correr en CI** (ningún test sale a la red) | Script CLI aparte, fuera de `pytest`. Ver §5.9 |
| **H8** | **El warm-up del LLM dispara I/O en el arranque** (hilo daemon, timeout 600 s). Sin él, la 1ª petición real cae en la ventana de carga en frío (**~342 s medidos**) y expira. | `warmup.py:19-40` · `main.py:39` del origen | Necesario, pero jamás en tiempo de import | Enganchar al `lifespan`, gated por `CONSULTA_WARMUP` |
| **H9** | **Q1 tiene 3 implementaciones divergentes.** `cuantificar` filtra dígitos **y** unidades; `analizar` solo dígitos; `jerarquizar` **no valida nada**. | `validador.py:96` · `respuesta_analizar.py:87` · `respuesta_jerarquizar.py:605` | Un intro de jerarquizar puede inventar cifras sin red | **Unificar en un solo `intro_valido`** aplicado a los 3 grupos |

### 0.3 Hallazgos de dominio a preservar (Q1-Q5 + D1-D6)

Cada uno es un bug ya pagado. Localizados con su código exacto:

| # | Regla | Dónde vive en el origen |
|---|---|---|
| **Q1** | Python calcula, el LLM solo redacta | `cuantificar/validador.py:96-105` (`intro_valido`: sin dígitos, sin `_UNIDADES`) |
| **Q2** | REGLA CERO — sin rezago se **declara**, no se fabrica | `analizar/plantilla.py:162-177`. **Ramifica en 3**, no 2: hay rezago / no hay rezago con meta / **no hay meta** |
| **Q3** | El **orden** de los drills ES la corrección | `maquina_q.py:173-183` (`_REF_CONTINUA_KW`) **antes** de `:184-192` (`_ACUM_KW`). "promedio del año" contiene "DEL ANO" |
| **Q4** | Cobertura parcial **en cabecera**, nombrando campos | `analizar/plantilla.py:316-322`. Además cambia el sujeto gramatical (`de_quien`) |
| **Q5** | El dispatcher valida el tipo, nunca fallback silencioso | **Aspiración, no garantía** — ver H3 |
| **D1** | El **nivel se dice siempre**: "el Activo CASTILLA" | `multitab_shell.js:5227-5232`. Campo CASTILLA = 6,9 M bbl; Activo CASTILLA = 11,7 M |
| **D2** | Q3 tiene **un segundo eslabón** aguas abajo | `cuantificar/slots.py:130-136`: override débil/fuerte. Reescribir solo uno reintroduce el bug |
| **D3** | Semántica de ranking = `(metrica, direccion)`, **no** `(eje, asc/desc)` | `cuantificar/ranking.py:11-19`. La forma asc/desc devolvía **lo contrario** a lo pedido |
| **D4** | CERO TRAICIONERO: 0 no es "poca producción" | `ranking.py:208` (`con_real = [d for d in datos if d[1] > 0]`) |
| **D5** | Errores transitorios **no** se cachean; "sin datos" **sí** | `p50_referencia.py:100,145,221` · `diferidas.py:103,177` · `maquina_q.py:267` |
| **D6** | El marcador es `⟦…⟧`, **nunca markdown genérico** | `multitab_shell.js:4456-4465`. El validador bloquea dígitos pero **no asteriscos**; en OUT el texto del LLM llega sin filtro |

### 0.4 Auditoría de los pipelines configurados (AP-1…AP-8)

Medido **ejecutando** los pipelines el 2026-08-20, no leyéndolos. Ocho incoherencias entre lo
que el plan v1 proponía y lo que la infraestructura hace hoy. Tres habrían roto el build del
equipo.

| # | Hallazgo | Evidencia medida | Riesgo | Corrección en el plan |
|---|---|---|---|---|
| **AP-1** | 🔴 **La cobertura es el riesgo nº 1 de F4.** Hoy: `TOTAL 3363 líneas, 78,97 %` con `fail_under=75` **global** (no por módulo). F4 añade ~4.500 líneas de golpe al denominador. | `uv run pytest --cov=src` → `3363 628 792 88 79%`. Simulado: **+4.500 líneas al 70 % → 74,8 %, CI ROJO** para todo el equipo | El fallo aparecería en el Bloque 9, con 4.500 líneas ya escritas y sin saber cuáles cubrir | **Verificación de cobertura al cerrar CADA bloque**, no al final (§6). Umbral de admisión por bloque: **≥80 %** del código nuevo |
| **AP-2** | 🔴 **El hook `gen-types-check` se dispara con TODO fichero de F4.** Su patrón es `^prodia_v02_backend/src/(main\|features)/.*\.py$` — los ~30 ficheros de `features/consulta/` caen dentro. | `.pre-commit-config.yaml`, hook `gen-types-check`. Ejecuta `pnpm run gen:types` → `export_openapi.py` → `from src.main import app` | **Cada `git commit` del executor importa la app entera.** Un solo `yaml.safe_load()` en tiempo de import cuelga el commit sin VPN | H4 deja de ser "buena práctica": es **bloqueante**. El test de I/O se amplía a ficheros **en el Bloque 0**, antes de escribir código |
| **AP-3** | 🟡 **CI no levanta Ollama, ni Postgres, ni SQLite.** El job backend solo hace `uv sync` + lint + mypy + export + pytest. | `ci.yml`, job `backend`: 8 pasos, ninguno arranca un servicio | Un test que llame al LLM real cuelga 30 s y luego falla en CI, no en local (donde Ollama sí corre) | El doble de `_invocar_una_vez` ya existe (`tests/unit/test_llm_client.py:85`) y **se reutiliza**. Ver §5.11 |
| **AP-4** | 🔴 **Alembic solo versiona `db_auth`.** `alembic.ini:2` fija `sqlite:///./data/prodia_v02_auth.db`; `env.py:27` lo sobreescribe con `settings.database_url`, que es la de auth. | `grep sqlalchemy.url alembic.ini` | **DA-2 no era una preferencia: poner la libreta en `core.*` de Postgres exige inventar un mecanismo de migraciones que no existe** | DA-2 pasa de "recomendación" a **decisión técnicamente forzada**: `db_auth` |
| **AP-5** | 🟡 **`omit` de cobertura solo excluye `src/main.py`.** Los YAML de config no son código, pero `prompts.py` y los `schemas.py` sí cuentan. | `pyproject.toml`, `[tool.coverage.run] omit = ["src/main.py"]` | Un `prompts.py` de 150 líneas de literales cuenta como código sin cubrir y arrastra el total | Los prompts van en **constantes de módulo**, que sí se ejecutan al importar y cuentan como cubiertas. No crear ficheros de solo-datos sin test |
| **AP-6** | 🟡 **`--strict-markers` está activo.** Todo marcador nuevo debe declararse en `pyproject.toml` o el test falla al recogerse. | `addopts = "--strict-markers"`; hay 2 marcadores: `unit`, `integration` | Si el executor inventa `@pytest.mark.golden` o `@pytest.mark.llm`, la suite entera falla | **No inventar marcadores.** El golden es un script CLI, no un test (§5.9) |
| **AP-7** | 🟢 **El frontend NO necesita dependencias nuevas.** Zustand 5 y Zod ^3.24 ya están declarados. | `package.json:28-29` | — | R1 no se toca en el frontend. El único DA de dependencias es PyYAML (DA-1) |
| **AP-8** | 🟡 **`pnpm build` corre en CI y el bundle inicial es 331 kB.** F4 añade la página más pesada del proyecto. | `ci.yml` job frontend, paso `pnpm build`; medido hoy: `index 331,69 kB` · `AnalisisPage 4,7 MB` (lazy) | Importar Plotly desde el chat metería 4,7 MB en el bundle inicial | La página de Consulta va **lazy** como `AnalisisPage`, y **los paneles son SVG/CSS**, no Plotly (§5.12) |

**Dato que corrige el plan v1**: la suite backend tiene **383 tests**, no los 314 que registró
el commit de F2 — se añadieron tests después. El plan v2 usa 383 como línea base.

### 0.5 La trampa de escala, tercera aparición

A5 ya nos costó un bug en F2 (corregido hoy, `a6d40ec`). En F4 reaparece **con un ratio distinto**:

- Gas del fact: `÷1e6` → MSCF.
- **Hoja P50 (`NEW MES-AÑO` t8): ratio ~29, NO 1e6.** El gas suma 75.974 donde el fact suma
  66.663.907 (`multitab_shell.js:3083-3092`). Aplicarle `__cnGasM` mostraba **"0,03" en vez de
  "33.453,2"** — mil veces menor, sin error visible.
- Solución del origen: el backend marca `fmt:"vp"` y el frontend usa otro formateador.

**Regla para F4**: la unidad **no** es función del producto; es función de **(producto, fuente)**.
Modelar como tipo, no como `if`.

---

## 1. Contexto

F4 reconstruye la pestaña **Consulta**: el chat en lenguaje natural sobre producción, su motor
de clasificación y la pila de paneles de resultado.

Depende de F2 (Análisis), **ya en código completo** pero con R3 parcial: el panel Fundación se
verificó contra el 139 el 2026-08-20 (139 campos, 185 fuentes, 151 colisiones); Desempeño
también. Quedan sin ejercitar el acordeón de focos y sus 4 pills (DT-8).

**Esa dependencia es dura**: `cuantificar` y `analizar` calculan **llamando a los servicios de
`analisis`**. Si `desempeno` da una cifra equivocada, el chat la repite con prosa cordial.

El cascarón de F1a ya define los 3 destinos (`consulta/data/secciones.ts`): **Historial**,
**Chat**, **Insights**, con el reparto de ancho y las reglas de emparejamiento verificadas en
navegador. F4 **solo llena cuerpos**; no toca la mecánica del acordeón.

---

## 2. Objetivo

Un chat que responde preguntas de producción en español, donde:

1. **Python calcula, el LLM solo redacta** — con una única red mecánica para los 3 grupos (H9).
2. **Ninguna cifra se inventa**: sin rezago se declara (Q2); sin meta se dice; cobertura parcial
   en cabecera (Q4).
3. **Cada panel tiene tipo** y un tipo desconocido produce un error visible, no una tarjeta con
   campos ajenos (H3/Q5).
4. **La conversación sobrevive al reinicio** — el panel Historial lo exige (H2).
5. **Cero I/O en tiempo de import** (H4), verificado por test.
6. **Ningún test sale a la red** — el golden corre como script CLI (H7).

**Fuera de alcance**: F5 (Test Clas) — los endpoints `/veredicto_lote` y `/log` son su base, no
la de F4. Ver §9.

---

## 3. Prerequisitos verificables

Anclas `grep -c` contra el código real (CLAUDE.md §0 exige anclas, no hashes):

```bash
# El origen está donde se cree (OJO: hay un nivel EXTRA de anidamiento)
test -d "C:/APLICACIONES/ProdIA/12112025_prodIA/12112025_prodIA/INGESTA/Rep_Prod/backend/app/features/consulta_v2"

# F2 expone los servicios que F4 consume (H1).
# OJO: `desempeno` es un MÉTODO de clase (indentado), `escenario_mes` una función suelta.
grep -c "def desempeno\|def escenario_mes" prodia_v02_backend/src/features/analisis/services_desempeno.py   # 2
grep -c "^def ejecutivo\|^def president" prodia_v02_backend/src/features/analisis/api.py                    # 2

# llm_client de F2 reutilizable
grep -c "def invocar\|def extraer_json" prodia_v02_backend/src/shared/llm_client.py    # 2

# catalogo_entidades NO trae lo conversacional: la única aparición de `resolver()`
# está en su docstring, declarando que eso es F4. Verificar que sigue siendo así:
grep -c "def resolver" prodia_v02_backend/src/shared/catalogo_entidades.py             # 0

# El cascarón de F1a existe y define los 3 paneles
grep -c "historial\|chat\|insights" prodia_v02_frontend/src/features/consulta/data/secciones.ts   # >=3

# El test de CERO I/O existe (hay que AMPLIARLO a ficheros, ver §5.2)
test -f prodia_v02_backend/tests/integration/test_sin_io_al_importar.py

# NO existe todavía la feature en backend
test ! -d prodia_v02_backend/src/features/consulta
```

**Decisiones bloqueantes antes del Bloque 1** — ver §10: DA-1 (PyYAML), DA-2 (dónde vive la
libreta), DA-3 (qué LLM en desarrollo).

---

## 4. Inventario de archivos

### 4.1 Backend — `src/features/consulta/`

Split por sufijo (no subcarpetas), como F2:

| Archivo | Origen | Líneas orig. | Contenido |
|---|---|---|---|
| `api.py` | `api.py` | 91 | 2 endpoints en F4 (`/preguntar`, `/veredicto`). **Sin `usuario` en el body** — sale de la cookie |
| `schemas.py` | — | nuevo | Unión discriminada de los **9** paneles + contrato de respuesta |
| `maquina.py` | `maquina_q.py` | 514 | Orquestador: Capa 1 → Capa 2 → despacho |
| `drills.py` | `maquina_q.py:58-212` | 155 | **Los 10 drills en orden** (Q3). Aislado para poder testear el orden |
| `clasificador.py` | `clasificador_llm.py` | 103 | Capa 2. **Reusa `shared/llm_client`** |
| `patrones.py` | `patrones.py` | 82 | Capa 1 regex |
| `dominio.py` | `dominio.py` | 64 | Filtro de dominio 2 niveles |
| `no_soportado.py` | `no_soportado.py` | 73 | Formas en-dominio-fuera-de-capacidad |
| `normaliza.py` | `normaliza.py` | 10 | `norm()`. **Pliega la ñ** — documentar |
| `resolver.py` | `cuantificar/resolver.py` | 230 | Lo conversacional que F2 dejó fuera |
| `memoria.py` | `maquina_q.py:30-56` | — | `_CTX` tipado + persistencia (H2) |
| `respuesta_jerarquizar.py` | idem | 716 | El mayor. 3 paneles |
| `respuesta_cuantificar.py` | idem | 206 | 4 paneles (N1-N5) |
| `respuesta_analizar.py` | idem | 318 | 5 sub-intenciones |
| `respuesta_out.py` | `respuesta_out.py` | 121 | Fuera de dominio. Frontera dura |
| `respuesta_base.py` | `respuesta_base.py` | 48 | `envolver(intro, cuerpo, cierre)` |
| `validador.py` | `cuantificar/validador.py` | 105 | **`intro_valido` único** (H9) |
| `slots.py` | `cuantificar/slots.py` | 151 | 100 % determinista. Incluye D2 |
| `ejecutor.py` | `cuantificar/ejecutor.py` | 253 | Consume servicios de `analisis` (H1) |
| `niveles.py` | `cuantificar/niveles.py` | 85 | N2/N3/N4 |
| `ranking.py` | `cuantificar/ranking.py` | 418 | N5. SQL propio. D3/D4 |
| `catalogo.py` | `cuantificar/catalogo.py` | 51 | Cargador YAML **perezoso** (H4) |
| `subrouter.py` | `analizar/subrouter.py` | 40 | Precedencia de sub-intención |
| `plantilla.py` | `analizar/plantilla.py` | 328 | **Q2 y Q4 viven aquí**. Puro |
| `p50_referencia.py` | `analizar/p50_referencia.py` | 352 | La trampa de escala (§0.5) |
| `analizar_diferidas.py` | `analizar/diferidas.py` | 204 | **Reusa `shared/db_diferidas`** de F2 |
| `analizar_economia.py` | `analizar/economia.py` | 75 | Consume el servicio de `ebitda` |
| `libreta.py` | `log.py` | 113 | `clasificacion_log` (H6) |
| `senales.py` | `senales.py` | 110 | Control 2 |
| `warmup.py` | `warmup.py` | 40 | Al `lifespan`, no al import (H8) |
| `prompts.py` | disperso | — | Los 3 prompts, literales |

`config/*.yaml` (4 ficheros, 442 líneas) se copian **sin tocar**.

### 4.2 Frontend — `src/features/consulta/`

Sobre el cascarón existente:

| Archivo | Contenido |
|---|---|
| `types/consultaTypes.ts` | Unión discriminada de los 9 paneles + `Mensaje` (**datos, no HTML**) |
| `mappers/consultaMappers.ts` | Normalización defensiva `unknown` → tipo, preservando `null` |
| `services/consultaService.ts` | `preguntar`, `veredicto`, `historial` |
| `hooks/useConsulta.ts` | TanStack Query + mutación |
| `store/chatStore.ts` | Zustand: mensajes, pila, desambiguación viva |
| `components/PanelChat/` | Historial + input + estado de envío |
| `components/Burbuja/` | Usuario / asistente |
| `components/IndicadorPensando/` | **2 fases por latencia** (900 ms) |
| `components/OpcionesDesambiguacion/` | Tarjetas con icono por nivel |
| `components/PilaResultados/` | Bloques apilados **con cierre y colapso** (el origen no los tiene) |
| `components/paneles/` | 9 componentes + **`PanelDesconocido`** (H3) |
| `components/PanelHistorial/` | Conversaciones persistidas (H2) |
| `utils/marcador.ts` | `⟦…⟧` → `<strong>`, **post-escape** (D6) |

**Reutilización**: `AcordeonFoco` de F2 sirve para `analiza_foco` sin duplicar — el panel solo
lleva el scope (`respuesta_analizar.py:282-289`, regla A7 del origen).

### 4.3 Migraciones

| # | Tabla | Motivo |
|---|---|---|
| `0004` | `conversaciones` + `mensajes` en `db_auth` | H2 — el panel Historial |
| `0005` | `clasificacion_log` | H6 — **destino según DA-2** |

---

## 5. Especificación

### 5.1 Romper el ciclo (H1) — consumir servicios, no rutas

El origen ya tiene el patrón: `fn = _desempeno_fn or _desempeno_ep`
(`cuantificar/ejecutor.py:77`). El endpoint es solo el **valor por defecto**; la función es
inyectable para tests.

En F4 se invierte la prioridad: **el parámetro es obligatorio**, y quien compone inyecta el
servicio de `analisis`. Ningún módulo de `consulta` importa de `features/analisis`.

```python
# consulta/ejecutor.py — la firma NO tiene default que apunte a otra feature
def ejecutar(
    slots: Slots,
    entidad: EntidadResuelta,
    *,
    desempeno_fn: DesempenoFn,      # inyectado por api.py
    escenario_fn: EscenarioFn,
) -> ResultadoCuantificar: ...
```

`api.py` es el único punto que conoce ambas features, y lo hace a través de una **dependencia
de FastAPI**, no de un import de módulo. Esto respeta ADR-001 y además hace el motor testeable
sin BD.

### 5.2 CERO I/O al importar (H4) — y ampliar el guardián

El origen ejecuta `_catalogo.get()` al importar (`respuesta_cuantificar.py:27`), deliberadamente
("arranque ruidoso si el YAML está mal"). El objetivo es bueno; el momento, no.

**En F4**: carga perezosa con lock y doble chequeo (patrón A1, ya usado en
`catalogo_entidades`), más **validación explícita en el `lifespan`** — se conserva el arranque
ruidoso sin romper el import.

El test actual solo espía **sockets**. F4 trae 4 YAML, así que hay que ampliarlo:

```python
def test_importar_la_app_no_lee_ficheros(monkeypatch):
    """F4 añade 4 YAML de config. Sin esta guarda, `gen-types-check` leería disco
    en cada `git commit` del equipo."""
    abiertos: list[str] = []
    open_real = builtins.open
    def _open_espia(archivo, *a, **kw):
        abiertos.append(str(archivo))
        return open_real(archivo, *a, **kw)
    monkeypatch.setattr(builtins, "open", _open_espia)
    importlib.reload(src.main)
    yaml_leidos = [a for a in abiertos if a.endswith((".yaml", ".yml"))]
    assert not yaml_leidos, f"YAML leído al importar: {yaml_leidos}"
```

### 5.3 Q3 — el orden de los drills, con test que lo fija

**El orden completo, del origen** (`maquina_q.py:58-212`). Primer `return` gana:

| # | Drill | Guarda | Nota |
|---|---|---|---|
| 0 | Continuación temporal | `_TEMP_CONT_KW`, ctx cuantificar | **Excepción de longitud** (>5 tokens) |
| 1 | Corte por longitud | `len(toks) > 5` → `None` | Una pregunta larga es intención propia |
| 2 | Entidad nombrada | `ent` | `None` si además hay producto o `_ACUM_KW` |
| 3 | **Ranking** | `ctx.subgrupo == 'ranking'` | **Corta SIEMPRE** |
| 4 | **Analizar** | `ctx.grupo == 'analizar'` | **Corta SIEMPRE** |
| 5 | **Referencia** | `_REF_CONTINUA_KW` | ⚠️ **ANTES que el 6** |
| 6 | **Acumulado N1→N2** | `_ACUM_KW` o `_AFIRM` | ⚠️ "promedio del año" ⊃ "DEL ANO" |
| 7 | N1 genérico | ctx cuantificar + producto | |
| 8 | `ofrece_produccion` | post-jerarquizar | |
| 9 | Estructural | `_ESTRUCT_KW` | Pronombre elidido |

**Por qué #3 y #4 cortan siempre**: sus contextos **no llevan la clave `entidad`**, y los drills
#5-#8 hacen `ctx['entidad']` sin `.get()` → `KeyError`. En F4 esto se elimina de raíz tipando el
contexto como unión discriminada; el orden se conserva igual porque es semántico, no defensivo.

**Test obligatorio** (el bug real, fechado 2026-08-02):

```python
def test_promedio_del_anio_es_referencia_no_acumulado() -> None:
    """Q3: "promedio del año" contiene la substring "DEL ANO". Si el drill de
    acumulado corriera primero, devolvería el acumulado vs PPTO — una cifra
    DISTINTA a la pedida, servida con la misma confianza."""
    ctx = ContextoCuantificar(entidad="CASTILLA", producto="crudo")
    assert reescribir("¿y el promedio del año?", ctx) == (
        "produccion de CASTILLA ¿y el promedio del año?"
    )
```

Y **D2**, el segundo eslabón (`slots.py:130-136`): si la única señal de acumulado fue la débil
(`EN EL ANO`/`DEL ANO`) y hay referencia `promedio_anio`, el nivel se fuerza a N1. Test propio.

### 5.4 Q1 unificado (H9)

Una sola `intro_valido`, la más estricta (`validador.py:96-105`), aplicada a **los tres**
grupos:

```python
_TIENE_DIGITO = re.compile(r"\d")
_UNIDADES = ("barril", "bbl", "mscf", "%", "porcentaje", "presupuesto", "millones", "millón")

def intro_valido(intro: str) -> bool:
    """El intro es SOLO saludo: sin dígitos ni unidades.

    En el origen había TRES versiones: cuantificar filtraba ambos,
    analizar solo dígitos (`respuesta_analizar.py:87`) y jerarquizar
    NO validaba (`respuesta_jerarquizar.py:605`). Un intro de jerarquizar
    podía inventar cifras sin ninguna red.
    """
```

**Bucle de 2 intentos con corte inteligente** (`respuesta_cuantificar.py:59-72`): si el LLM
devuelve `""` (timeout) **no se reintenta** — sería otro timeout de 30 s. Solo se reintenta si
devolvió texto pero con número.

### 5.5 Q2 y Q4 — declarar, nunca fabricar

**Q2 ramifica en TRES** (`plantilla.py:162-177`), no dos:

1. Hay rezago → se explica.
2. No hay rezago **pero hay meta** → *"no hay rezago — todo producto con meta va en o sobre ella"*.
3. **No hay meta** → *"ningún producto tiene meta definida en el periodo — no hay cumplimiento
   que evaluar ni rezago que explicar"*.

`valor_pct is None` (sin meta) **nunca** se confunde con `valor_pct < 100`.

**Q4** (`plantilla.py:316-322`): la cobertura parcial va en la **primera línea**, nombra los
campos incluidos y **cambia el sujeto gramatical** de las cifras siguientes (`de_quien`). El
motivo, medido: NARE 1 de 8 campos, LISAMA 1/6, SURIA 5/10.

### 5.6 Memoria conversacional persistente (H2)

El origen: `_CTX = {}`, 4 formas distintas sin tipo común, sin TTL, sin lock, se pierde al
reiniciar.

F4: **unión discriminada persistida**.

```python
type ContextoConversacion = (
    ContextoJerarquizar | ContextoCuantificar | ContextoRanking | ContextoAnalizar
)
```

Tipar esto elimina de raíz la fragilidad que obligaba a los drills #3/#4 a cortar siempre.

**Migración `0004`** en `db_auth` (es estado de usuario, no dato de producción):

- `conversaciones(id, usuario_id, titulo, creada_en, actualizada_en)`
- `mensajes(id, conversacion_id, rol, contenido JSON, panel JSON, creado_en)`

**Regla madre del origen, conservar**: *"la memoria nunca tumba la respuesta"*
(`maquina_q.py:512`) — toda actualización va en `try/except`.

### 5.7 La libreta (H6) — DA-2

`core.clasificacion_log` es Postgres en el origen, y su DDL justifica por qué
(`010_clasificacion_log.sql:14-15`): *"los controles 2 y 3 consultan con filtros y ventanas de
tiempo; JSONL no da queries y una SQLite nueva no existe en 139"*.

Pero en ProdIA V02 `db_prod` ha sido de solo lectura en las 3 fases. **Recomendación**: llevarla
a `db_auth` junto a `auth_events` — es telemetría de uso, no dato de producción, y ya hay
`user_actions` creada sin instrumentar (CLAUDE.md §8) que esta feature puede cerrar.

Decisión tuya (DA-2).

### 5.8 Q5 — unión discriminada y fallo visible (H3)

Los **9** tipos, verificados uno a uno:

| tipo | Emisor | Panel |
|---|---|---|
| `cuant_kpi` | `respuesta_cuantificar.py:182` | **Ausente del dispatcher del origen** |
| `cuant_serie` | `:183` (N3) | Serie mensual |
| `cuant_var` | `:183` (N4) | Variación |
| `cuant_rank` | `:149` | Sub-discrimina por `metrica` |
| `jerarq_arbol` | `respuesta_jerarquizar.py:542` | Árbol |
| `jerarq_operador` | `:538` | Campos por operador |
| `jerarq_rank` | `:661` | Ranking estructural |
| `p50_vp` | `respuesta_analizar.py:200` | **Escala propia** (§0.5) |
| `analiza_foco` | `:286` | **Solo scope** → reusa `AcordeonFoco` |

```tsx
switch (panel.tipo) {
  case 'cuant_kpi': return <PanelCuantKpi datos={panel.datos} />;
  // … los 9
  default: {
    const _exhaustivo: never = panel;   // el compilador falla si el backend añade un tipo
    return <PanelDesconocido tipo={(panel as {tipo: string}).tipo} />;
  }
}
```

`assert_never` en el backend y `never` en el frontend: un tipo nuevo **rompe el build**, que es
exactamente lo que no ocurría en el origen.

### 5.9 El golden (H7) — fuera de pytest

`run_golden_cuantificar.py:9-11` advierte explícitamente que abre conexiones a Postgres varias
veces. **No puede correr en CI.**

- `scripts/golden_consulta.py` — CLI, `uv run python scripts/golden_consulta.py [--set clasificacion|cuantificar|analizar]`.
- Gate ≥90 %, más la métrica no bloqueante **% resuelto por Capa 1** (si el regex resuelve <50 %,
  el sistema depende demasiado del LLM).
- Los YAML se copian tal cual; política del origen: *"toda corrección verificada entra aquí.
  **Nunca sacar un caso**"*.
- En `pytest` sí entra la **estructura** del golden (que el YAML parsea y tiene los campos), no
  su ejecución.

### 5.10 Frontend — lo que NO se porta

Del `multitab_shell.js`, defectos identificados a no repetir:

| Defecto del origen | Qué hace F4 |
|---|---|
| `__cnHistory` guarda **HTML**, obligando a regex sobre strings para mutar burbujas | `Mensaje[]` con datos; render puro |
| Sin persistencia — F5 borra todo | Migración `0004` |
| 6 cachés sin TTL ni invalidación | TanStack Query con `staleTime` |
| Sin bloqueo del input en vuelo → respuestas fuera de orden | Deshabilitar durante la mutación |
| Errores de negocio en HTTP 200, guarda duplicada en 3 sitios | Una función, un `QueryState` |
| **Autorización por nombre propio en el cliente** (`=== "javier guerrero"`) | RBAC del servidor |
| Auto-scroll incondicional | Solo si el usuario está al final |
| Tope de pila silencioso (100, FIFO, sin aviso) | Declararlo (mismo criterio que `truncado`) |
| Bloques no cerrables ni colapsables | Con cierre y colapso |

**Sí se conserva** el marcador `⟦…⟧` post-escape (D6) — es política de sanitización razonada,
no cosmética.

### 5.11 Tests del LLM — el doble ya existe (AP-3)

CI no levanta Ollama. El patrón está resuelto en F2 y **se reutiliza tal cual**
(`tests/unit/test_llm_client.py:71-85`): se sustituye `_invocar_una_vez` por un doble que
consume un guion de respuestas, donde un `str` significa fallo con ese diagnóstico.

```python
def _stub(monkeypatch, guion: list[Any]) -> list[int]:
    """Sustituye `_invocar_una_vez`. Un `str` en el guion = fallo con ese status."""
    monkeypatch.setattr(llm_client, "_invocar_una_vez", _falso)
```

Los tests de F4 que ejerciten la Capa 2, el intro cordial y la respuesta OUT usan este doble.
**Ninguno abre un socket**, lo que el test de AP-2 verifica de forma independiente.

Los 5 flags de feature del origen (`consulta_{narra,out,jerarq,cuant,analiza}_llm`) se portan:
en tests van todos a `false`, de modo que el camino determinista es el que se ejercita y el
LLM queda como enriquecimiento opcional — que es exactamente la garantía Q1.

### 5.12 Presupuesto de bundle (AP-8)

Medido hoy: `index` 331,69 kB · `AnalisisPage` 4,7 MB (lazy, con Plotly dentro).

Dos reglas para que F4 no degrade el arranque:

1. **La página de Consulta va lazy**, igual que `AnalisisPage` (`router.tsx` ya usa
   `lazy()` + `withSuspense`).
2. **Los paneles de resultado son SVG/CSS, no Plotly.** No es una preferencia estética: el
   origen ya lo hace así deliberadamente — `__cnRankDotHtml`, `__cnP50VpHtml`, `__cnDonaHtml`,
   `__cnWaterfallSVG` son funciones puras que devuelven SVG. Solo `analiza_foco` arrastra
   Plotly, y ese panel **reutiliza el `AcordeonFoco` de F2** (ya lazy en su chunk).

**Criterio de aceptación del Bloque 14**: `index` no crece más de un 5 % (≈348 kB).

---

## 6. Orden de ejecución (reformulado según la auditoría de pipelines)

Un artefacto por turno. **No cerrar un bloque sin verificación verde.**

### 6.1 La regla que cambia respecto al plan v1 (AP-1)

El plan v1 dejaba la cobertura para el final. **Medido**: hoy el backend está en **78,97 %**
con `fail_under=75` — margen de 4 puntos. Con ~4.500 líneas nuevas al 70 %, el total cae a
**74,8 %** y CI se pone rojo **para todo el equipo**, no solo para F4.

Por eso cada bloque de backend cierra con:

```bash
uv run pytest --cov=src --cov-report=term-missing
# 1. La suite entera en verde (383 tests de línea base + los del bloque)
# 2. El TOTAL no baja de 78%  (margen sobre el 75% del gate)
# 3. Los ficheros del bloque, >=80% individualmente
```

Si un bloque no llega al 80 %, **se cubre antes de pasar al siguiente**. Descubrirlo en el
Bloque 9 significaría 4.500 líneas escritas sin saber cuáles cubrir.

### 6.2 Los bloques

| # | Bloque | Entregable | Verificación |
|---|---|---|---|
| **0** | 🔴 **Bloqueante: decisiones + guardián** | DA-1…DA-4 resueltas · PyYAML declarado (DA-1) · **test de I/O ampliado a ficheros** (AP-2) | `pytest tests/integration/test_sin_io_al_importar.py` **antes de escribir una línea de F4** |
| **1** | Núcleo determinista | `normaliza`, `patrones`, `dominio`, `no_soportado`, `catalogo` + 4 YAML (carga perezosa) | Tests portados de `test_consulta_v2_clasificador.py` (458 líneas) · cobertura §6.1 |
| **2** | **Drills (Q3)** | `drills.py` + `memoria.py` tipada | **Test del orden #5 antes de #6** + D2 · cobertura §6.1 |
| **3** | Resolver + desambiguación | `resolver.py` | `test_consulta_desambiguacion.py` (179) · cobertura §6.1 |
| **4** | Clasificador Capa 2 | `clasificador.py` sobre `shared/llm_client` | Doble de `_invocar_una_vez` (AP-3) · **ningún socket** · cobertura §6.1 |
| **5** | Cuantificar | `slots`, `ejecutor`, `niveles`, `validador` (Q1 unificado) | `test_cuantificar.py` (663) + `_rango` + D2 · cobertura §6.1 |
| **6** | Ranking (N5) | `ranking.py` con D3/D4 | `test_cuantificar_ranking.py` (253) · cobertura §6.1 |
| **7** | Jerarquizar | `respuesta_jerarquizar.py` (716) | `test_jerarquizar_ranking.py` + `test_conteo_jerarquia.py` · cobertura §6.1 |
| **8** | Analizar | `subrouter`, `plantilla` (**Q2/Q4**), `p50_referencia` (§0.5), `diferidas`, `economia` | `test_analizar.py` (314) + `test_p50_referencia.py` (454) · cobertura §6.1 |
| **9** | Orquestador + API | `maquina.py`, `api.py`, `schemas.py`, `libreta.py`, `warmup` al lifespan | `test_consulta_ejecucion.py` + integración · **`uv run python scripts/export_openapi.py`** (AP-2) |
| **10** | Migraciones | `0004` conversaciones · `0005` libreta — **ambas en `db_auth`** (AP-4) | `alembic upgrade head` **y** `downgrade -1` |
| **11** | Frontend: tipos y servicio | `consultaTypes` (unión de 9), `mappers`, `service`, `store` | `pnpm typecheck` · `pnpm run gen:types` sin diff |
| **12** | Frontend: chat | `PanelChat`, `Burbuja`, `IndicadorPensando`, desambiguación, marcador | Tests de componente · cobertura frontend ≥80 % × 4 |
| **13** | Frontend: pila | `PilaResultados` + 9 paneles + **`PanelDesconocido`** | Test del `default` con tipo inventado · cobertura |
| **14** | Frontend: historial | `PanelHistorial` | Test · **`pnpm build`**: el chunk de Consulta debe ser lazy (AP-8) |
| **15** | Golden CLI | `scripts/golden_consulta.py` | Ejecución manual contra Ollama. **NO entra en pytest** (AP-6) |
| **16** | **R3 — verificación humana** | — | **Tuya**, en navegador |

### 6.3 Verificación final (antes de commitear la fase)

```bash
# Backend
cd prodia_v02_backend
uv run ruff check . && uv run black --check . && uv run mypy src
uv run python scripts/export_openapi.py          # AP-2: no debe tocar la red
uv run pytest --cov=src --cov-fail-under=75      # AP-1: el gate real de CI

# Frontend
cd ../prodia_v02_frontend
pnpm lint && pnpm typecheck && pnpm build        # AP-8: vigilar el tamaño del chunk
cd .. && pnpm test:front                         # DT-6: este script SÍ evalúa el umbral
```

---

## 7. Reglas no negociables

1. **R1** — no tocar config de pnpm ni añadir dependencias sin tu aprobación. **PyYAML es DA-1.**
2. **R2** — el `data` memoizado de un gráfico Plotly nunca depende de selección/hover.
3. **R3** — build verde ≠ feature verificada. Solo tú marcas F4 verificada.
4. **CERO I/O en tiempo de import** — sockets **y ficheros** (§5.2).
5. **Endpoints `def` sync**, nunca `async def`.
6. **ADR-001** — `consulta` no importa de `analisis`/`ebitda`. Se inyectan servicios (§5.1).
7. **U3** — el SQL se copia idéntico.
8. **Ningún test sale a la red**: ni Postgres, ni Ollama, ni SQLite de 954 MB.
9. **Python calcula, el LLM redacta** — `intro_valido` único, en los 3 grupos (§5.4).
10. **El usuario sale de la cookie**, jamás del body.
11. **Un tipo de panel nuevo rompe el build** — `assert_never` / `never` (§5.8).
12. **Cobertura verificada al cerrar CADA bloque** (AP-1), nunca al final. El TOTAL no baja
    de 78 %; el código del bloque, ≥80 %.
13. **No inventar marcadores de pytest** (AP-6): `--strict-markers` está activo y solo existen
    `unit` e `integration`.
14. **Las migraciones van a `db_auth`** (AP-4): es la única BD que Alembic versiona.

---

## 8. Validaciones

**Backend**: `ruff` · `black` · `mypy strict` · `pytest` con `fail_under=75`.
**Frontend**: `eslint` · `tsc -b` · `vitest --coverage` (80 % × 4) · `pnpm build`.
**Ambos**: `scripts/export_openapi.py` sin tocar la red.

**Línea base medida el 2026-08-20** (para saber si F4 mejora o degrada):

| Métrica | Hoy | Criterio en F4 |
|---|---|---|
| Tests backend | **383** en 25,7 s | Suben; ninguno sale a la red |
| Cobertura backend | **78,97 %** (3.363 líneas) | **No baja de 78 %** (AP-1) |
| Tests frontend | 39 archivos, **84,98 %** | No baja de 80 % × 4 |
| Bundle inicial | **331,69 kB** | ≤348 kB (+5 %, AP-8) |
| Rutas en OpenAPI | 25 | +2 (`/preguntar`, `/veredicto`) |

**Anclas de paridad** (criterio de aceptación, CLAUDE.md §6):
- `clasificacion_golden` ≥90 % sobre **75** casos.
- `cuantificar_golden` ≥90 % sobre 24.
- `analizar_golden` ≥90 % sobre 10.
- Los **3.412 líneas de tests portados** pasan contra el código nuevo — como en F2, es la
  validación más fuerte de que la conducta se conserva.

---

## 9. Fuera de alcance

- **F5 (Test Clas)**: `/veredicto_lote`, `/log`, `revisar_lote.py` y el Control 3. F4 deja la
  libreta escribiendo y el Control 1 (✓/✗ en la burbuja); la revisión por lotes es F5.
- **`consulta/` v1** (1.470 líneas): congelada desde 2026-07-30, no se migra (CLAUDE.md §6).
- **El selector de motor v1/v2** y su `localStorage`: en V02 solo existe v2.
- **`chat.js`** (175 KB): es el chatbot clásico, otra aplicación (CLAUDE.md §1).

---

## 10. Decisiones abiertas — BLOQUEAN el Bloque 1

| # | Pregunta | Recomendación |
|---|---|---|
| **DA-1** | **PyYAML**: ¿se declara explícito en `pyproject.toml`? Hoy llega solo como transitiva de `pre-commit` (dev) y `uvicorn[standard]` (extra). **R1 exige tu aprobación.** | **Sí, declararlo.** Depender de una transitiva es el mismo fallo que `@types/plotly.js` en F2 |
| **DA-2** | **¿Dónde vive `clasificacion_log`?** El origen la pone en `core.*` de Postgres; nuestras 3 fases solo leen de ahí (H6) | **`db_auth` — y ya no es una preferencia.** AP-4: `alembic.ini:2` versiona **solo** `db_auth`. Ponerla en Postgres exigiría inventar un mecanismo de migraciones que no existe. Además es telemetría de uso, no dato de producción, y cierra la deuda de `user_actions` |
| **DA-3** | **¿Qué LLM en desarrollo?** El origen mide **~342 s** de arranque en frío con gemma@139. `qwen2.5:3b` local es más rápido pero *"confunde cifras"* (nuestro `config.py`) | qwen local para desarrollo, con `CONSULTA_*_LLM=false` en tests. **Q1 protege de la confusión de cifras** |
| **DA-4** | **¿F4 antes o después de cerrar DT-8?** El chat repite las cifras de `analisis` con prosa cordial | Cerrar DT-8 primero (el acordeón y las 4 pills contra el 139). Es media hora tuya de navegador |

---

## 11. Apéndice A — tablas que consulta el motor Q

| Tabla | Uso |
|---|---|
| `core.map_campo_robustez` | Jerarquía VP→gerencia→activo→campo. **16 referencias**, la más usada |
| `core.dim_fuente` | Catálogo de nombres |
| `core.clasificacion_log` | La libreta (H6) |
| `core.map_campo_activo` | activo ↔ campo (ya usado por `catalogo_entidades` de F2) |
| `core.fact_produccion_mes_ecp` | Ranking N5 |
| `core.fact_tabla_hoja` | Hoja `NEW MES-AÑO` t8/t2 — P50. **62 M filas**: exige `reporte_id` fijo (0,00 s vs 2,61 s) |
| `core.dim_{escenario,tipo_producto,vicepresidencia,empresa}` | Dimensiones |
| `core.config_reporte` | `fecha_reporte` |
| `ops.wells_attributes` | Conteo de pozos (cross-DB, degrada con gracia) |
| `AVM_DATADIF` (SQLite) | Diferidas — **nunca `count(*)` a secas** (DT-7) |

## 12. Apéndice B — las 5 sub-intenciones de analizar

Precedencia fija (`subrouter.py:29-40`): `economia` > `diferidas` > `proyeccion` >
`referencia` > `causal` (default).

`referencia` exige **P50 como token exacto** y ausencia de expresiones causales — *"¿vamos a
llegar al P50?"* sigue siendo **proyección**, no referencia.
