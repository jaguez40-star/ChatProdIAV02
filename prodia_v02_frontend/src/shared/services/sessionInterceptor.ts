import type { Middleware } from 'openapi-fetch';

import { useAuthStore } from '../../app/store/authStore';
import apiClient from './apiClient';

/**
 * Reacciona al vencimiento de sesión en CADA respuesta de `apiClient`.
 *
 * Corrección C1 sobre Robustez V02: su `sessionInterceptor.ts` parchea
 * `window.fetch` GLOBALMENTE porque el 96% de sus services (45 de 47) usan
 * `fetch` desnudo en vez de su propio `apiClient` — su propio código lo
 * admite ("un helper obligaría a tocar los 45"). Aquí la regla N1 (100% de
 * los services por `apiClient` desde el día 1) hace innecesario ese parche
 * global: basta un middleware de `openapi-fetch`, registrado UNA vez sobre
 * el cliente compartido, y cubre toda la app sin tocar `window.fetch`.
 *
 * Dos headers distintos, no confundirlos:
 *   X-Session-Expires  -> timestamp ISO de cuándo expira (viene en toda
 *                         respuesta autenticada)
 *   X-Session-Expired  -> "true" SOLO en el 401 causado por token vencido
 *                         o cookie ausente
 */

// En estas rutas un 401 no significa "sesión vencida a mitad de trabajo": en
// el login son credenciales inválidas; en el logout el usuario YA decidió
// irse (con cookie vencida el backend responde 401 + X-Session-Expired, y
// sin esta exclusión el aviso de vencimiento aparecería tras un logout
// voluntario).
const EXCLUDED_PATHS = ['/api/v1/auth/login', '/api/v1/auth/logout'];

const sessionMiddleware: Middleware = {
  onResponse({ request, response }) {
    const path = new URL(request.url).pathname;
    if (EXCLUDED_PATHS.some((p) => path.includes(p))) return response;

    const store = useAuthStore.getState();

    // El backend renueva la cookie por su cuenta (sliding refresh); sin esto
    // el frontend se queda con la expiración que leyó al hidratar y el
    // aviso previo salta a destiempo.
    const expiresAt = response.headers.get('X-Session-Expires');
    if (expiresAt) store.setSessionExpiry(expiresAt);

    if (
      response.status === 401 &&
      response.headers.get('X-Session-Expired') === 'true'
    ) {
      // Idempotente por diseño: si varias queries fallan a la vez, todas
      // terminan dejando el store en el mismo estado.
      store.markSessionExpired();
    }

    return response;
  },
};

let installed = false;

/** Idempotente: llamarla dos veces no registra el middleware dos veces
 * (importa con StrictMode y con el hot reload de Vite). */
export function installSessionInterceptor(): void {
  if (installed) return;
  apiClient.use(sessionMiddleware);
  installed = true;
}

/** Existe para los tests. */
export function uninstallSessionInterceptor(): void {
  if (!installed) return;
  apiClient.eject(sessionMiddleware);
  installed = false;
}
