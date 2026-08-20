import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Grafico } from './Grafico';
import type { DatosGrafico } from './tiposGrafico';

/**
 * Test de HUMO del wrapper de Plotly — la puerta de salida del Bloque 0 (F2).
 *
 * Su valor no es comprobar que Plotly dibuja bien (eso es cosa de Plotly), sino
 * que **el módulo carga en jsdom sin tumbar la suite**. Plotly invoca
 * `URL.createObjectURL` al CARGARSE, y jsdom no lo implementa: sin el polyfill
 * de `tests/setup/vitest.setup.ts` esto no da un test rojo, da
 * `Failed Suites 1 · Tests: no tests` — el archivo entero no llega a
 * ejecutarse, y con `singleFork: true` contamina la corrida completa (AP-4).
 *
 * Es decir: si alguien borra ese polyfill, ESTE archivo es el que lo delata.
 */

const DATOS_MINIMOS: DatosGrafico = [
  { x: [1, 2, 3], y: [10, 20, 15], type: 'scatter', mode: 'lines', name: 'Crudo' },
];

describe('Grafico', () => {
  it('renderiza sin romper la suite en jsdom (regresión del polyfill, AP-4)', () => {
    render(<Grafico data={DATOS_MINIMOS} descripcion="Producción diaria de crudo" />);

    // `role="img"` + aria-label: un gráfico sin descripción es opaco para
    // lectores de pantalla, así que la prop es obligatoria por tipos.
    expect(screen.getByRole('img', { name: 'Producción diaria de crudo' })).toBeDefined();
  });

  it('acepta `title` como objeto, que es la forma que exigen los tipos (AP-6)', () => {
    // El idiom de Plotly v2 (`title: 'texto'`) no compila contra
    // `@types/plotly.js@3.x` y rompería `pnpm build`. Este test fija la forma
    // correcta: si alguien alinea las versiones, aquí se ve el efecto.
    render(
      <Grafico
        data={DATOS_MINIMOS}
        layout={{ title: { text: 'Producción diaria' } }}
        descripcion="Producción con título"
      />,
    );

    expect(screen.getByRole('img', { name: 'Producción con título' })).toBeDefined();
  });

  it('respeta el alto recibido', () => {
    render(<Grafico data={DATOS_MINIMOS} alto={480} descripcion="Gráfico alto" />);

    expect(screen.getByRole('img', { name: 'Gráfico alto' })).toBeDefined();
  });
});
