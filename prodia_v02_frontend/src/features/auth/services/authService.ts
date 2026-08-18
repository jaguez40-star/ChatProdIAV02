import apiClient, { toApiError } from '../../../shared/services/apiClient';
import { toAuthSession, toLoginResult } from '../mappers/authMappers';
import type { AuthSession, LoginCredentials, LoginResult } from '../types/authTypes';

/**
 * Corrección sobre Robustez V02: su `authService.login()` solo lee
 * `error.detail` y lanza un `Error` genérico — el LLAMADOR no puede
 * distinguir "credenciales inválidas" (401, el usuario se equivocó) de
 * "LDAP no responde" (503, problema de infraestructura). Aquí ambos casos
 * llegan como `ApiError` con `.status` — LoginPage puede mostrar un mensaje
 * distinto para cada uno si quiere, y siempre tiene el `correlationId` a
 * mano para reportarlo.
 *
 * Nota de tipos: `apiClient.POST/GET` de openapi-fetch tipa `data` como
 * `T | undefined` (no es un discriminated union estricto) — `data ===
 * undefined` se chequea explícitamente junto a `error`, no solo `error`,
 * para que TypeScript pueda descartar `undefined` en el `return`.
 */
export async function login(credentials: LoginCredentials): Promise<LoginResult> {
  const { data, error } = await apiClient.POST('/api/v1/auth/login', {
    body: { username: credentials.username, password: credentials.password },
  });

  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo iniciar sesión');
  }

  return toLoginResult(data);
}

export async function logout(): Promise<void> {
  const { error } = await apiClient.POST('/api/v1/auth/logout');
  if (error) {
    throw toApiError(error, 'No se pudo cerrar sesión');
  }
}

export async function getMe(): Promise<AuthSession> {
  const { data, error } = await apiClient.GET('/api/v1/auth/me');
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo obtener la sesión');
  }
  return toAuthSession(data);
}

export async function getSessionTimeoutMinutes(): Promise<number> {
  const { data, error } = await apiClient.GET('/api/v1/auth/session-timeout');
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo obtener el timeout de sesión');
  }
  return data.session_timeout_minutes;
}
