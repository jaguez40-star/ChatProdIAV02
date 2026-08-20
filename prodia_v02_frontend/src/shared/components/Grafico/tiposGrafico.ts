// Los tipos se toman del paquete que SÍ es dependencia declarada del proyecto
// (`@types/react-plotly.js`), que reexporta los de `plotly.js`. Importar
// `plotly.js` directamente NO compila: `@types/plotly.js` entra en el árbol
// como dependencia transitiva de `@types/react-plotly.js` y, con el
// `node-linker` aislado de pnpm, no es resoluble por nombre desde `src/`
// (TS2307). Pasar por el paquete declarado respeta R1 — no hay que añadir
// ninguna dependencia para que esto compile.
import type { PlotParams } from 'react-plotly.js';

/**
 * Tipos de gráfico de ProdIA V02 — aíslan el desajuste entre los tipos y el
 * runtime de Plotly (AP-6 del plan F2).
 *
 * `@types/plotly.js` instalado es de la **3.x**; el runtime declarado en
 * `package.json` es `plotly.js-dist-min@^2.35`. Donde más muerde esa
 * diferencia es en `layout.title`:
 *
 *   layout={{ title: 'Producción' }}          ← idiom v2: NO COMPILA
 *   layout={{ title: { text: 'Producción' } }} ← forma exigida por los tipos v3
 *
 * Y como `pnpm build` ejecuta `tsc -b`, el idiom viejo **rompe el build**, no
 * solo el editor. Reexportar los tipos desde aquí hace que la forma correcta
 * sea la única disponible en toda la aplicación y que, si algún día se alinean
 * las versiones, haya UN archivo que tocar en vez de cinco gráficos.
 */

/** Series de un gráfico. */
export type DatosGrafico = PlotParams['data'];

/**
 * Diseño de un gráfico. Es parcial porque Plotly rellena por defecto todo lo
 * que no se especifique.
 *
 * Recordatorio: `title` SIEMPRE como objeto — `{ text: '…' }`.
 */
export type DisenoGrafico = Partial<PlotParams['layout']>;
