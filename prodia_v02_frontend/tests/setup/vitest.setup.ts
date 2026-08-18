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
