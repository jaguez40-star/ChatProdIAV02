import { useEffect, useState } from 'react';

/** Mismo umbral que el @media del acordeón (PanelColapsable.module.scss). */
const CONSULTA_MOVIL = '(max-width: 1023px)';

/**
 * Detecta viewport móvil de forma reactiva (<1024px).
 *
 * jsdom no implementa `matchMedia`, así que la ausencia de la función se
 * trata como "no es móvil" en vez de reventar — los tests que necesiten la
 * rama móvil deben mockear `window.matchMedia` explícitamente.
 */
export function useIsMobile(): boolean {
  const [esMovil, setEsMovil] = useState<boolean>(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return false;
    }
    return window.matchMedia(CONSULTA_MOVIL).matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mql = window.matchMedia(CONSULTA_MOVIL);
    const handler = (e: MediaQueryListEvent) => setEsMovil(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);

  return esMovil;
}
