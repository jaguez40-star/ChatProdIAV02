import { useMemo } from 'react';

import { useNow } from '../../../shared/hooks/useNow';

// Umbral en minutos para mostrar el banner de aviso.
export const WARNING_THRESHOLD_MIN = 5;

/**
 * Calcula cuántos minutos quedan para que expire la sesión.
 *
 * @param sessionExpiresAt Timestamp ISO UTC del header X-Session-Expires,
 *   o null si no hay sesión.
 * @returns minutesLeft: minutos enteros restantes (negativo si ya expiró),
 *   o null si no hay dato. isExpiringSoon: true si minutesLeft está en
 *   [0, WARNING_THRESHOLD_MIN].
 */
export function useSessionExpiry(sessionExpiresAt: string | null): {
  minutesLeft: number | null;
  isExpiringSoon: boolean;
} {
  // Sin este reloj el useMemo solo se recalcula cuando cambia
  // sessionExpiresAt, así que el tiempo restante quedaba congelado y el
  // banner no aparecía nunca.
  const nowMs = useNow(30_000);

  return useMemo(() => {
    if (!sessionExpiresAt) return { minutesLeft: null, isExpiringSoon: false };

    const expiresMs = new Date(sessionExpiresAt).getTime();
    if (isNaN(expiresMs)) return { minutesLeft: null, isExpiringSoon: false };

    const minutesLeft = Math.floor((expiresMs - nowMs) / 60_000);
    const isExpiringSoon = minutesLeft >= 0 && minutesLeft <= WARNING_THRESHOLD_MIN;

    return { minutesLeft, isExpiringSoon };
  }, [sessionExpiresAt, nowMs]);
}
