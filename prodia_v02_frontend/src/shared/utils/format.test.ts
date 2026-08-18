import { describe, expect, it } from 'vitest';

import { formatBl, formatDelta, formatKUSD, formatMscf, formatPct, formatRelativeES } from './format';

describe('formatBl', () => {
  it('formatea con separador de miles es-CO, sin decimales por defecto', () => {
    expect(formatBl(1234567)).toBe('1.234.567');
  });

  it('respeta maximumFractionDigits', () => {
    expect(formatBl(1234.5678, { maximumFractionDigits: 2 })).toBe('1.234,57');
  });
});

describe('formatMscf', () => {
  it('agrega el sufijo MSCF', () => {
    expect(formatMscf(9.9)).toBe('9,9 MSCF');
  });
});

describe('formatKUSD', () => {
  it('agrega el sufijo kUSD', () => {
    expect(formatKUSD(78629)).toBe('78.629 kUSD');
  });
});

describe('formatPct', () => {
  it('agrega el signo de porcentaje', () => {
    expect(formatPct(95.6)).toBe('95,6%');
  });
});

describe('formatDelta', () => {
  it('antepone + para valores positivos', () => {
    expect(formatDelta(2.2)).toBe('+2,2');
  });

  it('no antepone signo para valores negativos (ya lo trae toLocaleString)', () => {
    expect(formatDelta(-9.8)).toBe('-9,8');
  });

  it('no antepone signo para cero', () => {
    expect(formatDelta(0)).toBe('0');
  });
});

describe('formatRelativeES', () => {
  const now = new Date('2026-08-18T12:00:00Z').getTime();

  it('sin fecha devuelve el mensaje por defecto', () => {
    expect(formatRelativeES(null, now)).toBe('Sin cambios recientes');
  });

  it('menos de 60s -> "hace unos segundos"', () => {
    const date = new Date(now - 30_000);
    expect(formatRelativeES(date, now)).toBe('hace unos segundos');
  });

  it('minutos', () => {
    const date = new Date(now - 5 * 60_000);
    expect(formatRelativeES(date, now)).toBe('hace 5 min');
  });

  it('horas', () => {
    const date = new Date(now - 3 * 3_600_000);
    expect(formatRelativeES(date, now)).toBe('hace 3 h');
  });

  it('días', () => {
    const date = new Date(now - 2 * 86_400_000);
    expect(formatRelativeES(date, now)).toBe('hace 2 d');
  });
});
