import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

import '@testing-library/jest-dom/vitest';

// Desmonta y limpia el DOM tras CADA test. `pool: 'forks'` +
// `singleFork: true` (vitest.config.ts) corre todos los archivos de test
// en un único proceso — sin este cleanup explícito, el DOM renderizado por
// un test queda montado cuando empieza el siguiente y los queries de
// Testing Library encuentran elementos de tests previos ("multiple
// elements found"). El auto-registro de @testing-library/react no basta
// aquí de forma fiable con `pool: 'forks'`.
afterEach(() => {
  cleanup();
});

// jsdom no implementa ResizeObserver. Mock silencioso para que hooks que
// dependen de él no exploten en tests.
class ResizeObserverMock {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;

// jsdom no implementa URL.createObjectURL, y Plotly lo invoca al CARGARSE el
// módulo (no al renderizar). Sin este polyfill el fallo no es un test rojo:
// es `TypeError: window.URL.createObjectURL is not a function` durante la
// importación, que vitest reporta como "Failed Suites 1 · Tests: no tests"
// — el ARCHIVO ENTERO no llega a ejecutarse. Con `pool: 'forks'` +
// `singleFork: true` (vitest.config.ts) eso contamina la corrida completa y
// la cobertura ni se calcula.
//
// Verificado (AP-4 del plan F2): sin el polyfill, renderizar un gráfico da
// Failed Suite; con él, pasa en ~140 ms. Los avisos residuales
// `Not implemented: HTMLCanvasElement.prototype.getContext` que jsdom emite
// después son RUIDO, no fallo: Plotly detecta la ausencia de canvas y sigue.
if (!window.URL.createObjectURL) {
  window.URL.createObjectURL = (() =>
    'blob:test') as unknown as typeof window.URL.createObjectURL;
  window.URL.revokeObjectURL = (() => {}) as unknown as typeof window.URL.revokeObjectURL;
}

// jsdom no implementa matchMedia — usado indirectamente por hooks de layout.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

// jsdom no implementa `scrollIntoView`. El chat de F4 lo usa para llevar la
// vista al último mensaje, así que sin este stub cualquier test que monte la
// página revienta con un TypeError — un fallo del entorno, no del componente.
// Mismo criterio que el polyfill de `createObjectURL` para Plotly.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
