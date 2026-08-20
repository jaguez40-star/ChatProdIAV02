import { useMemo } from 'react';
// @ts-expect-error — `plotly.js-dist-min` no publica tipos propios; los tipos
// los aporta `@types/plotly.js`, que sí está instalado (ver nota AP-6 abajo).
import Plotly from 'plotly.js-dist-min';
import createPlotlyComponent from 'react-plotly.js/factory';

import styles from './Grafico.module.scss';
import type { DatosGrafico, DisenoGrafico } from './tiposGrafico';

/**
 * ÚNICO punto del repositorio que importa Plotly. Ningún componente de feature
 * debe importar `react-plotly.js` ni `plotly.js*` directamente (AP-5).
 *
 * ── Por qué el `factory` y no `import Plot from 'react-plotly.js'` ──────────
 * Hay DOS Plotly en el árbol de dependencias:
 *   · `plotly.js-dist-min@2.35.3`  →  4,3 MB   (el declarado en package.json)
 *   · `plotly.js@3.7.0`            → 10,7 MB   (peer auto-instalado por
 *     `react-plotly.js`, que además arrastra `mapbox-gl@1.13.3` y
 *     `@plotly/mapbox-gl@1.13.4`, este último marcado `deprecated` en el lock)
 *
 * El import "obvio" (`from 'react-plotly.js'`) resuelve al de 10,7 MB y mete
 * una librería de mapas que ProdIA no usa. Medido: arrancar el entorno de un
 * test con esa vía tarda ~17,5 s; con `dist-min` vía factory, ~1,8 s.
 *
 * ── Por qué los tipos son propios (AP-6) ────────────────────────────────────
 * `@types/plotly.js` instalado es de la 3.x mientras el runtime es 2.35. La
 * diferencia muerde en `layout.title`: el idiom de la v2 (`title: 'texto'`)
 * NO compila contra los tipos v3, que exigen `title: { text: 'texto' }`, y
 * como `pnpm build` corre `tsc -b`, eso ROMPE EL BUILD (no es un aviso del
 * editor). Casi todos los ejemplos de Plotly que circulan usan el idiom v2.
 * `tiposGrafico.ts` fija la forma correcta una sola vez para que el error no
 * se repita en cada gráfico de la aplicación.
 *
 * ── R2 (CLAUDE.md §0) ───────────────────────────────────────────────────────
 * `data` y `layout` se memoizan SOLO contra sus propias referencias. Este
 * componente NO acepta estado de selección/hover, y por construcción no puede
 * introducirlo: si un llamador necesita resaltar una serie, debe hacerlo por
 * `layout` (shapes/annotations) o por CSS, NUNCA recreando `data` — hacerlo
 * causa bugs de re-render garantizados.
 */
const Plot = createPlotlyComponent(Plotly);

/** Config de Plotly fija para toda la app: sin logo, sin barra de herramientas
 *  flotante y responsive. Se define fuera del componente para que su identidad
 *  referencial sea estable entre renders (si se recreara en cada render,
 *  Plotly volvería a aplicar la configuración en cada uno). */
const CONFIG_BASE = {
  displaylogo: false,
  displayModeBar: false,
  responsive: true,
} as const;

interface GraficoProps {
  /** Series a pintar. El llamador debe memoizarlas (R2). */
  data: DatosGrafico;
  /** Diseño del gráfico. `title` va como objeto: `{ text: '…' }` (AP-6). */
  layout?: DisenoGrafico;
  /** Alto en píxeles. El ancho siempre es el del contenedor (responsive). */
  alto?: number;
  /** Texto para lectores de pantalla — un gráfico sin descripción es opaco. */
  descripcion: string;
  className?: string;
}

export function Grafico({ data, layout, alto = 320, descripcion, className }: GraficoProps) {
  // Solo depende de `layout` y `alto`: jamás de selección/hover (R2).
  const disenoFinal = useMemo<DisenoGrafico>(
    () => ({
      autosize: true,
      height: alto,
      margin: { t: 32, r: 16, b: 40, l: 56 },
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'transparent',
      font: { family: 'Inter, system-ui, sans-serif', size: 12 },
      ...layout,
    }),
    [layout, alto],
  );

  return (
    <div className={className ?? styles.contenedor} role="img" aria-label={descripcion}>
      <Plot
        data={data}
        layout={disenoFinal}
        config={CONFIG_BASE}
        style={{ width: '100%', height: '100%' }}
        useResizeHandler
      />
    </div>
  );
}
