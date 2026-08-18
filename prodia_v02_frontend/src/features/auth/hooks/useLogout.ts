import { useMutation, useQueryClient } from '@tanstack/react-query';

import { useAuthStore } from '../../../app/store/authStore';
import { logout } from '../services/authService';

/** onError hace lo mismo que onSuccess: si el logout falla en el servidor,
 * la sesión local se limpia igual — nunca deja al usuario atascado. */
export function useLogout() {
  const clearSession = useAuthStore((s) => s.clearSession);
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: logout,
    onSuccess: () => {
      clearSession();
      queryClient.removeQueries({ queryKey: ['auth', 'me'] });
    },
    onError: () => {
      clearSession();
      queryClient.removeQueries({ queryKey: ['auth', 'me'] });
    },
  });
}
