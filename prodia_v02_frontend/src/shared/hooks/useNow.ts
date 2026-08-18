import { useEffect, useState } from 'react';

/**
 * Hook que retorna Date.now() reactivo, refrescado cada `intervalMs`. Útil
 * para timestamps relativos que deben mantenerse vivos sin acción del
 * usuario. Vive en `shared/hooks/` — Robustez V02 lo tiene mal ubicado en
 * `shared/utils/` (es un hook, no una utilidad pura); corregido aquí desde
 * el día 1.
 *
 * @param intervalMs default 30 000 (30 s).
 */
export function useNow(intervalMs: number = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}
