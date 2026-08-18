import { useEffect, useRef } from 'react';

const ACTIVITY_EVENTS = ['mousemove', 'keydown', 'scroll', 'click', 'touchstart'] as const;

// No resetear el timer en CADA mousemove (dispara decenas por segundo) —
// alcanza con notar que hubo actividad una vez por ventana de THROTTLE_MS.
const THROTTLE_MS = 1_000;

interface UseIdleTimerOptions {
  /** Minutos de inactividad antes de disparar onIdle. null/undefined = timer inactivo. */
  timeoutMinutes: number | null | undefined;
  /** Se dispara una sola vez al cumplirse el timeout. */
  onIdle: () => void;
  /** Congela la detección (no resetea, no dispara) — usarlo mientras el modal está abierto. */
  paused?: boolean;
}

/**
 * Detecta inactividad REAL del usuario (mouse/teclado/scroll/click/touch),
 * a diferencia de sessionInterceptor.ts que mide ausencia de requests HTTP.
 */
export function useIdleTimer({
  timeoutMinutes,
  onIdle,
  paused = false,
}: UseIdleTimerOptions): void {
  const onIdleRef = useRef(onIdle);
  onIdleRef.current = onIdle;

  useEffect(() => {
    if (!timeoutMinutes || timeoutMinutes <= 0 || paused) return undefined;

    const timeoutMs = timeoutMinutes * 60_000;
    let timeoutId: ReturnType<typeof setTimeout>;
    let lastReset = 0;

    const resetTimer = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => onIdleRef.current(), timeoutMs);
    };

    const handleActivity = () => {
      const now = Date.now();
      if (now - lastReset < THROTTLE_MS) return;
      lastReset = now;
      resetTimer();
    };

    resetTimer();
    ACTIVITY_EVENTS.forEach((event) =>
      window.addEventListener(event, handleActivity, { passive: true }),
    );

    return () => {
      clearTimeout(timeoutId);
      ACTIVITY_EVENTS.forEach((event) => window.removeEventListener(event, handleActivity));
    };
  }, [timeoutMinutes, paused]);
}
