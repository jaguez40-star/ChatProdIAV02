import { useMutation } from '@tanstack/react-query';

import { useAuthStore } from '../../../app/store/authStore';
import { getMe, login } from '../services/authService';
import type { LoginCredentials } from '../types/authTypes';

/** login es un doble salto: POST /login (setea cookie) e inmediatamente
 * GET /me para obtener usuario+permisos. El body `access_token` de /login
 * se ignora — la cookie es la fuente de verdad de la sesión. */
export function useLogin() {
  const setSession = useAuthStore((s) => s.setSession);

  return useMutation({
    mutationFn: async (credentials: LoginCredentials) => {
      await login(credentials);
      return await getMe();
    },
    onSuccess: (session) => {
      setSession(session.user, session.permissions);
    },
  });
}
