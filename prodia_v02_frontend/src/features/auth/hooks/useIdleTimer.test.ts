import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useIdleTimer } from './useIdleTimer';

describe('useIdleTimer', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('dispara onIdle tras el timeout sin actividad', () => {
    const onIdle = vi.fn();
    renderHook(() => useIdleTimer({ timeoutMinutes: 1, onIdle }));

    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(onIdle).toHaveBeenCalledTimes(1);
  });

  it('con timeoutMinutes null no arma el timer', () => {
    const onIdle = vi.fn();
    renderHook(() => useIdleTimer({ timeoutMinutes: null, onIdle }));

    act(() => {
      vi.advanceTimersByTime(10 * 60_000);
    });
    expect(onIdle).not.toHaveBeenCalled();
  });

  it('paused=true congela la detección', () => {
    const onIdle = vi.fn();
    renderHook(() => useIdleTimer({ timeoutMinutes: 1, onIdle, paused: true }));

    act(() => {
      vi.advanceTimersByTime(120_000);
    });
    expect(onIdle).not.toHaveBeenCalled();
  });

  it('la actividad reinicia el temporizador', () => {
    const onIdle = vi.fn();
    renderHook(() => useIdleTimer({ timeoutMinutes: 1, onIdle }));

    act(() => {
      vi.advanceTimersByTime(50_000);
      window.dispatchEvent(new Event('keydown'));
      vi.advanceTimersByTime(50_000);
    });
    // Sin el reset, a los 100s ya habría disparado (timeout=60s). Con
    // reset a los 50s, a los 100s totales (50s desde el reset) no dispara aún.
    expect(onIdle).not.toHaveBeenCalled();
  });
});
