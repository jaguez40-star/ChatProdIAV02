import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useSessionExpiry, WARNING_THRESHOLD_MIN } from './useSessionExpiry';

describe('useSessionExpiry', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-18T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('sin sessionExpiresAt: minutesLeft null, no expira pronto', () => {
    const { result } = renderHook(() => useSessionExpiry(null));
    expect(result.current.minutesLeft).toBeNull();
    expect(result.current.isExpiringSoon).toBe(false);
  });

  it('con timestamp inválido: minutesLeft null', () => {
    const { result } = renderHook(() => useSessionExpiry('no-es-una-fecha'));
    expect(result.current.minutesLeft).toBeNull();
  });

  it('expira en 30 min: no está "expirando pronto" (umbral 5 min)', () => {
    const expiresAt = new Date('2026-08-18T12:30:00Z').toISOString();
    const { result } = renderHook(() => useSessionExpiry(expiresAt));
    expect(result.current.minutesLeft).toBe(30);
    expect(result.current.isExpiringSoon).toBe(false);
  });

  it(`expira en ${WARNING_THRESHOLD_MIN} min: SÍ está expirando pronto`, () => {
    const expiresAt = new Date(
      Date.now() + WARNING_THRESHOLD_MIN * 60_000,
    ).toISOString();
    const { result } = renderHook(() => useSessionExpiry(expiresAt));
    expect(result.current.isExpiringSoon).toBe(true);
  });

  it('ya expiró (negativo): minutesLeft negativo, no "expirando pronto"', () => {
    const expiresAt = new Date(Date.now() - 5 * 60_000).toISOString();
    const { result } = renderHook(() => useSessionExpiry(expiresAt));
    expect(result.current.minutesLeft).toBeLessThan(0);
    expect(result.current.isExpiringSoon).toBe(false);
  });
});
