import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

import { getPersistedAuth, useAuthStore } from '../../../app/store/authStore';
import { getMe } from '../services/authService';

/**
 * Adaptación sobre Robustez V02: su `useCurrentUser` distingue la causa del
 * error con una clase `SessionExpiredError` propia de su `authService`.
 * Aquí la fuente de verdad es más directa — `sessionInterceptor.ts` YA
 * marcó `sessionExpired=true` en el store (síncronamente, dentro de
 * `onResponse`) antes de que `apiClient.GET` termine de resolver, para
 * cualquier 401 con header `X-Session-Expired`. Por eso el catch no limpia
 * la sesión incondicionalmente: si el store ya quedó marcado como expirado,
 * `clearSession()` lo pisaría de vuelta a `false` (esa acción resetea el
 * flag a propósito, para el logout voluntario). Dos caminos convergen en
 * `location.state.sessionExpired`: este hook y el interceptor.
 */
export function useCurrentUser() {
  const { setSession, clearSession, isAuthenticated } = useAuthStore();
  const hasPersisted = getPersistedAuth() !== null;
  const navigate = useNavigate();

  return useQuery({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      try {
        const session = await getMe();
        setSession(session.user, session.permissions);
        return session;
      } catch (error) {
        const expiredByInterceptor = useAuthStore.getState().sessionExpired;
        if (!expiredByInterceptor) {
          clearSession();
        } else {
          void navigate('/login', { state: { sessionExpired: true } });
        }
        throw error;
      }
    },
    enabled: isAuthenticated || hasPersisted,
    retry: false,
    staleTime: 1000 * 60 * 5,
  });
}
