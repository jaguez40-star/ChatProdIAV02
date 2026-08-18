/**
 * Formateo de números compartido (C3 — corrección sobre Robustez V02, que
 * NO tiene esto centralizado: `toLocaleString('es-CO', {...})` duplicado
 * inline por todo el repo, con dos definiciones locales distintas conviviendo
 * en el mismo archivo (LayoutMain.tsx:189,207)).
 *
 * Crítico en ProdIA específicamente: el gas se reporta en MSCF (÷1e6) y el
 * crudo/blancos en bbl — mezclar esas escalas ya causó bugs reales en el
 * sistema anterior (el P50 de gas se mostró "0,03 MSCF" en vez de
 * "33.453,2 bpd" por aplicar la conversión de MSCF a un valor que no la
 * necesitaba). Cada producto tiene SU formateador; nunca un `formatNumber`
 * genérico que un caller aplique a la escala equivocada.
 */

const LOCALE = 'es-CO';

export function formatBl(value: number, opts: { maximumFractionDigits?: number } = {}): string {
  return value.toLocaleString(LOCALE, {
    maximumFractionDigits: opts.maximumFractionDigits ?? 0,
  });
}

/** Gas en MSCF — el valor de entrada viene en la escala del fact (÷1e6 ya
 * aplicado por el backend, nunca en el frontend: ver A5 en CLAUDE.md). */
export function formatMscf(value: number, opts: { maximumFractionDigits?: number } = {}): string {
  return `${value.toLocaleString(LOCALE, { maximumFractionDigits: opts.maximumFractionDigits ?? 2 })} MSCF`;
}

export function formatKUSD(value: number, opts: { maximumFractionDigits?: number } = {}): string {
  return `${value.toLocaleString(LOCALE, { maximumFractionDigits: opts.maximumFractionDigits ?? 0 })} kUSD`;
}

export function formatPct(value: number, opts: { maximumFractionDigits?: number } = {}): string {
  return `${value.toLocaleString(LOCALE, { maximumFractionDigits: opts.maximumFractionDigits ?? 1 })}%`;
}

/** Con signo explícito (+/-) — para deltas y variaciones. */
export function formatDelta(value: number, opts: { maximumFractionDigits?: number } = {}): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toLocaleString(LOCALE, { maximumFractionDigits: opts.maximumFractionDigits ?? 1 })}`;
}

/**
 * Tiempo relativo en español. `now` inyectable como segundo parámetro
 * (patrón correcto de Robustez V02, `formatRelative.ts`): hace la función
 * pura y testeable sin `vi.useFakeTimers()`.
 */
export function formatRelativeES(date: Date | null, now: number = Date.now()): string {
  if (!date) return 'Sin cambios recientes';
  const diff = Math.max(0, now - date.getTime());
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return 'hace unos segundos';
  const min = Math.floor(sec / 60);
  if (min < 60) return `hace ${min} min`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `hace ${hr} h`;
  const days = Math.floor(hr / 24);
  return `hace ${days} d`;
}
