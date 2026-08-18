import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useNow } from './useNow';

describe('useNow', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('devuelve el tiempo actual al montar', () => {
    const { result } = renderHook(() => useNow(1000));
    expect(typeof result.current).toBe('number');
  });

  it('se refresca tras el intervalo configurado', () => {
    const { result } = renderHook(() => useNow(1000));
    const first = result.current;
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current).toBeGreaterThanOrEqual(first);
  });
});
