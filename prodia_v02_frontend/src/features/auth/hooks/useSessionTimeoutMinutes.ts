import { useQuery } from '@tanstack/react-query';

import { useAuthStore } from '../../../app/store/authStore';
import { getSessionTimeoutMinutes } from '../services/authService';

/**
 * Minutos de inactividad configurados (GET /auth/session-timeout). Alimenta
 * a useIdleTimer para que el modal de inactividad espere el mismo tiempo
 * que el backend usa para expirar la cookie de sesión.
 */
export function useSessionTimeoutMinutes() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  return useQuery({
    queryKey: ['auth', 'session-timeout'],
    queryFn: getSessionTimeoutMinutes,
    enabled: isAuthenticated,
    staleTime: 1000 * 60 * 5,
    retry: false,
  });
}
