import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';

import { useAuthStore } from '../../../app/store/authStore';

interface RutaAdminProps {
  children: ReactNode;
}

/**
 * Restringe una ruta a administradores.
 *
 * **Por qué es un componente aparte y no un flag de `ProtectedRoute`.** Aquél
 * envuelve el **layout entero** en una ruta pathless (`router.tsx`), así que un
 * `soloAdmin` allí restringiría Consulta, Análisis e Ingesta de golpe. Esta
 * guarda se aplica al `element` de una sola ruta.
 *
 * Solo comprueba el ROL: la autenticación ya la garantiza el `ProtectedRoute`
 * ancestro, y repetirla aquí volvería a mostrar el spinner de `isHydrated`.
 *
 * ⚠️ **Esto no es seguridad, es cortesía.** Quien decide es el backend, que
 * responde 403 a un no-admin (`require_admin`). Lo que evita este componente es
 * ofrecer una puerta que se va a cerrar en la cara. El sistema viejo hacía lo
 * contrario —autorizaba en el cliente comparando el nombre del usuario— y por
 * eso su backend no tenía autenticación de ningún tipo.
 */
export function RutaAdmin({ children }: RutaAdminProps) {
  const user = useAuthStore((estado) => estado.user);

  if (user === null || !user.isAdmin) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
