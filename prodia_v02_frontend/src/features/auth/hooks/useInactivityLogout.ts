import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuthStore } from '../../../app/store/authStore';
import { useIdleTimer } from './useIdleTimer';
import { useLogout } from './useLogout';
import { useSessionTimeoutMinutes } from './useSessionTimeoutMinutes';

/**
 * Orquesta el modal "Sesión inactiva": detecta inactividad REAL del usuario
 * (useIdleTimer) durante el timeout configurado (useSessionTimeoutMinutes),
 * y al vencer cierra la sesión y redirige a /login.
 *
 * `paused=true` mientras el modal está abierto: la detección se congela
 * para que no se vuelva a resetear sola con la actividad de cerrar el modal.
 */
export function useInactivityLogout() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { data: timeoutMinutes } = useSessionTimeoutMinutes();
  const logout = useLogout();
  const navigate = useNavigate();

  const handleIdle = useCallback(() => {
    setIsModalOpen(true);
  }, []);

  useIdleTimer({
    timeoutMinutes: isAuthenticated ? timeoutMinutes : null,
    onIdle: handleIdle,
    paused: isModalOpen,
  });

  const handleAccept = useCallback(() => {
    setIsModalOpen(false);
    logout.mutate(undefined, {
      onSettled: () => {
        void navigate('/login', { replace: true });
      },
    });
  }, [logout, navigate]);

  return {
    isModalOpen,
    minutesInactive: timeoutMinutes ?? 0,
    onAccept: handleAccept,
  };
}
