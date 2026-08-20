/**
 * El marcador `⟦…⟧` → negrita. **Nunca markdown genérico.**
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 🔑 D6 — es una decisión de seguridad, no cosmética.
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * El intro cordial lo escribe un LLM a temperatura 0.8, y su validador bloquea
 * dígitos y unidades pero **no asteriscos**. En la respuesta OUT el texto del
 * modelo llega sin filtro de contenido alguno. Interpretar `**` habría puesto
 * en negrita un «**Claro, Javier**» espontáneo del modelo en los cuatro
 * grupos.
 *
 * Con un marcador propio y acotado, solo se resalta lo que el backend decidió
 * resaltar. El modelo no conoce `⟦⟧` y no lo produce.
 *
 * **En React esto es más seguro que en el original**: allí el marcador se
 * aplica sobre HTML ya escapado con una regex, aquí se devuelven nodos, así
 * que no hay `dangerouslySetInnerHTML` en ninguna parte del camino.
 */

import type { ReactNode } from 'react';

/** No codiciosa y de una sola línea: un marcador sin cerrar no se come el resto. */
const MARCADOR = /⟦([^⟦⟧\n]*)⟧/g;

/**
 * Convierte `texto` en nodos, poniendo en negrita lo marcado.
 *
 * Devuelve un array de fragmentos porque el texto puede alternar entre plano y
 * resaltado varias veces.
 */
export function conMarcador(texto: string): ReactNode[] {
  const nodos: ReactNode[] = [];
  let ultimo = 0;
  let indice = 0;

  for (const coincidencia of texto.matchAll(MARCADOR)) {
    const inicio = coincidencia.index ?? 0;
    if (inicio > ultimo) {
      nodos.push(texto.slice(ultimo, inicio));
    }
    nodos.push(<strong key={`m${indice}`}>{coincidencia[1]}</strong>);
    ultimo = inicio + coincidencia[0].length;
    indice += 1;
  }

  if (ultimo < texto.length) {
    nodos.push(texto.slice(ultimo));
  }
  return nodos;
}
