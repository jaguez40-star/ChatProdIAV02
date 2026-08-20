# ProdIA — Estado de Proyecto

| | |
|---|---|
| **Líder** | Jhon Polania |
| **Patrocinador** | Vicepresidencia de Exploración, Desarrollo y Producción |
| **Fecha** | 19 Ago 2026 |
| **Estado** | 🟡 **EN PROCESO** |

---

## ProdIA — Analítica Conversacional de Producción

Plataforma de consulta de producción de hidrocarburos en **lenguaje natural**.
El usuario pregunta en español y la aplicación resuelve la consulta contra el
Reporte Diario de Producción, entregando la cifra, su comparación contra la
referencia (PPTO / P50 / Compromiso) y el análisis causal de la desviación.

Cubre producción de crudo, gas y blancos por campo, activo, gerencia y
vicepresidencia, con ingesta automatizada del reporte diario (17 hojas
modeladas), tablero de desempeño mensual y análisis ejecutivo asistido por IA.

### Dos líneas de trabajo simultáneas

El proyecto avanza hoy en dos frentes que conviven y deben leerse por separado:

| Línea | Qué es | Estado |
|---|---|---|
| **A · Producto en operación** | ProdIA clásico — el sistema que hoy usan los usuarios. Motor conversacional, pills, panel de resultados, épicas gerenciales | 🟢 En evolución continua |
| **B · Reconstrucción arquitectónica (ProdIA V02)** | Reescritura de las 5 pestañas como aplicación autónoma, sobre los patrones probados de Robustez V02 | 🟡 F0 y F1a entregadas · quedan F1-F6 |

La línea B existe porque el sistema actual tiene el frontend en un único archivo
de **5.308 líneas** sin arquitectura, y su **backend de datos no tiene
autenticación** — quien alcanzara el puerto leía todo. La línea B es la que
absorbe hoy la mayor parte de la capacidad de desarrollo, y es el factor
principal detrás del riesgo de alcance descrito más abajo.

---

## 📊 Salud del proyecto

### 🕐 Tiempo — 🟢 EN REGLA

- **Motor conversacional:** 4 de 4 grupos respondiendo
- **Épicas gerenciales:** 4 de 7 cerradas o cerrables
- **Migración de arquitectura:** 1 de 7 fases cerrada (F0) + adelanto F1a
- 291 versiones entregadas · 202 en los últimos 30 días *(métrica del repositorio
  del sistema clásico; el repositorio de V02 se abrió el 18 Ago)*

### 💰 Presupuesto

- **Ejecutado:** —
- **Desviación:** —

### 🎯 Alcance — 🟡 EN SEGUIMIENTO

- **Épicas gerenciales:** 3 cerradas · 1 cerrable · 1 en pausa · 2 no iniciadas
- **Fases de arquitectura:** F0 completa · F1a completa · F1-F6 pendientes
- Alcance ampliado sobre la base inicial (ver Riesgo)

---

## 📋 Avance y cronograma

### ✅ Logros recientes — Línea A · Producto en operación (últimas 2 semanas)

- **El P50 se responde como cifra, no como causa.** Ante *"dame el P50 de
  Rubiales"* el asistente respondía "95,6% del presupuesto": la palabra solo
  servía para enrutar y nunca se usaba como referencia. Ahora entrega la cifra
  donde el P50 existe (ECP global y vicepresidencia) y **declina de forma
  explícita** a nivel campo, donde el dato no existe en ninguna de las hojas
  del reporte, ofreciendo la alternativa disponible.

- **Pill de Mantenimientos conectada a fuente real.** Dejó de ser una maqueta
  con 3 filas fijas idénticas en todos los campos: ahora lee **6.850 eventos**
  de servicio a pozo. Dos criterios nacieron de auditar el archivo real —
  evento sin fecha de cierre significa **abierto** (48% de las filas, que se
  habrían descartado), y el filtro es por solape con el mes analizado, no
  contra la fecha de hoy (que dejaba **3 eventos en toda la compañía**).

- **Panel derecho acumulativo.** Cada respuesta reemplazaba la anterior y
  borraba el resultado previo; ahora se apilan en orden cronológico con el
  panorama general fijo arriba, y persisten al navegar entre pestañas.

- **Identidad visual por producto** (Crudo / Gas / Blancos) con contraste
  verificado, separada de la paleta de estado con la que antes colisionaba.

- **El ranking responde con la lectura, no con la tabla.** El chat y el panel
  mostraban exactamente lo mismo; ahora el chat entrega la interpretación
  (concentración, dominancia, participación de terceros) y el panel el detalle.

### ✅ Logros recientes — Línea B · Reconstrucción ProdIA V02

- **Fase F0 cerrada (17-18 Ago) — el cimiento y el login funcionan.** Monorepo
  con gestión de dependencias reproducible, observabilidad completa
  (identificador de correlación en cada log y en cada respuesta, para rastrear
  el reporte de un usuario hasta la línea exacta del servidor), autenticación
  **LDAP corporativa** operativa, versionado de base de datos y pantalla de
  ingreso funcional. **58 de 58 pruebas automatizadas en verde, 87% de
  cobertura.**

- **Se cierra el agujero de seguridad de origen.** El backend de datos actual no
  tiene ninguna autenticación. V02 nace con **denegación por defecto**: toda
  ruta que no sea ingreso o diagnóstico exige sesión válida, verificado antes
  incluso del enrutamiento.

- **Hallazgo crítico detectado y corregido a tiempo.** La aplicación tomada como
  plantilla **no tiene forma de crear su primer usuario**. De haberse copiado tal
  cual, F0 habría entregado un login que no deja entrar a nadie. Se añadió la
  siembra del padrón (29 usuarios importados) como migración versionada.

- **Adelanto F1a (18 Ago) — cascarón de la pantalla de Consulta.** Los tres
  paneles colapsables se re-proponen a **Historial / Chat / Insights**, con
  reparto de ancho por pareja abierta y transición animada. Contenido real
  diferido a F4. **141 de 141 pruebas de frontend en verde, 92,8% de cobertura.**

- **Auditoría de tuberías de integración continua.** Se detectó que el umbral de
  cobertura del 80% **nunca se estaba evaluando** desde F0 — el parámetro no
  llegaba a la herramienta de pruebas. Corregido.

- **Reglas de dominio documentadas antes de portarlas.** Las 11 reglas críticas
  del sistema actual (motor conversacional Q1-Q5 y análisis A1-A6) quedaron
  escritas en la memoria del proyecto. Cada una es un error ya pagado en el
  sistema viejo — incluido el caso en que un modelo de lenguaje **inventó un
  déficit inexistente** para un campo que estaba al 102,7% de cumplimiento, y el
  caso en que un factor de conversión mal aplicado mostró una cifra **mil veces
  menor sin ningún error visible**.

### 📅 Próximos hitos (siguientes 30 días)

| Hito | Línea | Fecha |
|---|---|---|
| Re-ingesta de `REPORTE_PRESIDENT` en dev y producción — cierra Épica 2 | A | **22 Ago** |
| Verificación en navegador de los cambios de agosto | A | **26 Ago** |
| Confirmación en navegador de la transición del cascarón de Consulta (F1a) | B | **26 Ago** |
| Inicio de Fase F1 — Control + Tablas (valida el patrón de extremo a extremo) | B | **30 Ago** |
| Definición de alcance para Épicas 3 y 7 (modos por foro · móvil) | A | **15 Sep** |

> **Corrección respecto al reporte anterior:** el hito *"Fase F0 — validación
> LDAP"* figuraba con fecha 30 Ago. Se completó el **18 Ago**, doce días antes de
> lo previsto. Esa fecha queda ahora asignada al inicio de F1.

### 🗺️ Avance de la reconstrucción (Línea B)

| Fase | Entrega | Estado |
|---|---|---|
| **F0** | Cimiento + login funcional con LDAP | ✅ **Completa** (18 Ago) |
| **F1a** | Cascarón de la pantalla de Consulta *(adelanto)* | ✅ **Completa** (18 Ago) |
| **F1** | Control + Tablas — árbol de reportes y visor | ⬜ Pendiente |
| **F2** | Análisis — 9 endpoints + EBITDA + diferidas + mantenimientos | ⬜ Pendiente |
| **F3** | Ingesta — ETL del reporte diario, 17 extractores | ⬜ Pendiente |
| **F4** | Consulta — motor conversacional completo | ⬜ Pendiente |
| **F5** | Test Clas — laboratorio del clasificador | ⬜ Pendiente |
| **F6** | Corte — despliegue paralelo y retiro del sistema viejo | ⬜ Pendiente |

Volumen medido pendiente de portar: **~10.100 líneas de lógica de servidor** y
**24 archivos de pruebas (3.933 líneas)**. El frontend actual (7.411 líneas) **no
se porta: se reescribe** — está construido por concatenación de texto y no hay
nada reutilizable.

---

## ⚠️ Atención gerencial

### 🚫 Bloqueo actual (crítico)

**Dos épicas bloqueadas por datos, no por código.** En ambas la mecánica está
construida y verificada:

- **Épica 2 (Baseline P50 vs compromiso):** espera la re-ingesta de la hoja
  `REPORTE_PRESIDENT`. El script está listo.
- **Épica 4 (Mapa semáforo por campo):** solo **71 de 139 campos (51%)** tienen
  coordenadas geográficas. Entre los 68 sin ubicación hay focos activos
  (CAJUA, CAÑO LIMÓN, PAUTO SUR) — un mapa de atención que omite justo los
  peores campos sería engañoso. Requiere el export del maestro GIS corporativo.

### ⚠️ Riesgo principal

**Alcance ampliado sobre el plan inicial.** El backlog gerencial de 7 épicas se
levantó en julio. Desde entonces se incorporaron dos bloques no planeados:

1. Funcionalidades sobre el producto en operación (motor conversacional
   completo, panel apilado, identidad visual, análisis causal).
2. **La reconstrucción arquitectónica completa (línea B)** — no contemplada en el
   backlog de julio y hoy el mayor consumidor de capacidad. Justificada por el
   agujero de autenticación y por la imposibilidad de mantener un frontend de
   5.308 líneas sin arquitectura, pero con costo real: quedan **6 de 7 fases**.

Ambos bloques han absorbido capacidad de los temas definidos originalmente. Dos
épicas (3 · modos por foro y 7 · experiencia móvil) siguen **sin iniciar**.

*Riesgo secundario — validación humana:* hay cambios verificados técnicamente
que esperan confirmación en navegador. La política del proyecto no permite
declarar completada una funcionalidad visual sin esa validación. Aplica hoy a
los cambios de agosto de la línea A y a la transición del cascarón de F1a.

*Riesgo terciario — deuda técnica registrada:* 6 elementos abiertos en el
registro del proyecto, ninguno bloqueante. Los dos de mayor impacto están en la
tubería de integración continua (una caché que nunca acierta y un comando de
cobertura que se corrigió parcialmente). Se cierran al tocar CI en F1.

### 📌 Decisión requerida

**Priorizar las épicas no iniciadas.** Las épicas 3 (modos por instancia de
reporte: Sistemática, BP, POP, Junta, Comité) y 7 (experiencia móvil-ejecutiva)
están en 0%. La 7 es relevante porque la gerencia declaró consumir el **80%
desde el teléfono**. Se requiere definición de prioridad y alcance.

**Definir la convivencia de las dos líneas.** Hay que decidir si la capacidad
sigue repartida entre evolucionar el producto actual y reconstruirlo, o si una
de las dos toma prioridad hasta cerrar. Toda funcionalidad nueva sobre la línea
A deberá reconstruirse después en la línea B.

**Gestionar el maestro GIS de campos.** Sin las coordenadas de los 68 campos
faltantes, la Épica 4 permanece en pausa indefinida.

**Resolver el histórico de diferidas (antes de F2).** El archivo histórico pesa
**954 MB** y no puede versionarse. Se requiere decisión sobre su despliegue en
el servidor de producción.

**Definir el futuro del chatbot clásico (antes de F6).** Falta decidir si ProdIA
V02 lo reemplaza o si ambos conviven de forma indefinida.

**Reajuste del plan.** Reformular el cronograma de acuerdo con las
funcionalidades incorporadas y con las 6 fases de reconstrucción pendientes,
para ajustarlo a la realidad de los tiempos de desarrollo actuales.

---

<sub>Próxima reunión de seguimiento: 26 de Agosto, 2026 · Confidencial — Uso Exclusivo del Comité Ejecutivo</sub>
