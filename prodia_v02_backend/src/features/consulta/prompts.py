"""Los prompts del Motor Q, literales.

Se agrupan aquí —el origen los tiene dispersos por tres módulos— para que el
texto que se envía al modelo sea auditable de un vistazo. Son constantes de
módulo, así que cuentan como código ejecutado y no inflan el denominador de
cobertura con líneas sin cubrir.

🔑 **Q1 — Python calcula, el LLM solo redacta.** Ninguno de estos prompts pide
una cifra: el clasificador devuelve una etiqueta, y los de prosa escriben un
saludo cuyo contenido numérico se valida y descarta mecánicamente
(`validador.intro_valido`). Es lo que impide que el modelo invente cifras.
"""

from __future__ import annotations

# ── Capa 2: clasificación de grupo ───────────────────────────────────────────
# Copiado literal de `clasificador_llm.py:18-41`. El bloque "CUIDADO con
# palabras que parecen del negocio" es el que evita que "los campos de un
# formulario" o "los activos de un banco" entren como preguntas de producción.
PROMPT_CLASIFICADOR = """Eres un clasificador de preguntas para un sistema de producción petrolera.
Responde SOLO con JSON válido. Sin explicaciones, sin markdown.

Grupos:
1. jerarquizar — estructura organizacional, pertenencia, identidad de entidades
   (qué campos tiene un activo, a qué pertenece algo, qué es algo)
2. cuantificar — magnitudes medibles: valores, conteos, acumulados, series
   temporales, variaciones (cuánto produjo, cuántos pozos, cómo varió)
3. analizar — causas, explicaciones, proyecciones, cumplimiento de metas,
   acciones recomendadas (por qué, cómo vamos, vamos a llegar, qué hacer)

Si la pregunta NO es de producción petrolera ni de la información del sistema (matemáticas,
geografía, cultura general, entretenimiento, finanzas no petroleras, saludos, texto suelto,
un nombre a secas): "desconocido".

CUIDADO con palabras que parecen del negocio pero NO lo son en ese contexto: los "campos" de
un formulario, los "pozos" de una casa o sépticos, los "activos" financieros de un banco, el
"cierre" de la bolsa. Si el tema real no es producción petrolera de Ecopetrol → "desconocido".

Formato de respuesta (SOLO esto):
{{"grupo": "<jerarquizar|cuantificar|analizar|desconocido>", "entidad": "<string|null>"}}

Pregunta: {texto}
JSON:"""

GRUPOS_VALIDOS = frozenset({"jerarquizar", "cuantificar", "analizar", "desconocido"})
