import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { useAuthStore } from '../../../app/store/authStore';
import { Spinner } from '../primitives/Spinner/Spinner';

interface ProtectedRouteProps {
  children: ReactNode;
}

/** Puente crítico entre `authStore.sessionExpired` y
 * `location.state.sessionExpired`, que lee LoginPage. */
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, isHydrated, sessionExpired } = useAuthStore();
  const location = useLocation();

  if (!isHydrated) {
    // El flag isHydrated evita el parpadeo: sin él, un usuario ya
    // autenticado vería un salto a /login mientras se resuelve /me.
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '100vh',
        }}
      >
        <Spinner size="lg" label="Verificando sesión..." />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <Navigate to="/login" state={{ from: location.pathname, sessionExpired }} replace />
    );
  }

  return <>{children}</>;
}
