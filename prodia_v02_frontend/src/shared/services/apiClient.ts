import createClient from 'openapi-fetch';

import type { paths } from '../types/api';

/**
 * Ruta relativa: las llamadas /api/... pasan por el proxy de Vite en dev
 * y por el reverse proxy en producción — sin necesidad de CORS con
 * credenciales. Patrón literal de Robustez V02 (L12/L13).
 */
const apiClient = createClient<paths>({
  baseUrl: '/',
  credentials: 'include',
});

export default apiClient;

/**
 * Error tipado del backend — corrección C2 sobre Robustez V02: su
 * `apiClient.ts` son 11 líneas SIN normalización de error; el backend
 * produce un `correlation_id` excelente (ver core/exceptions.py) y el
 * frontend lo descartaba por completo. `ApiError` lo parsea y lo expone,
 * para que la UI pueda mostrarlo — convierte un ticket de soporte en 30
 * segundos de grep contra los logs del backend.
 */
export interface ApiErrorBody {
  status: number;
  detail: string;
  correlation_id: string | null;
  code?: string;
  errors?: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly correlationId: string | null;
  readonly code: string | undefined;

  constructor(body: ApiErrorBody) {
    super(body.detail);
    this.name = 'ApiError';
    this.status = body.status;
    this.correlationId = body.correlation_id;
    this.code = body.code;
  }
}

/**
 * Normaliza el `error` que devuelve openapi-fetch (ya parseado como JSON por
 * la librería cuando el content-type es application/json) al contrato de
 * `core/exceptions.py::_error_response`. N1: todo service pasa por
 * `apiClient` + este helper — nunca `fetch` desnudo (corrige C1).
 */
export function toApiError(error: unknown, fallbackDetail: string): ApiError {
  if (
    error !== null &&
    typeof error === 'object' &&
    'detail' in error &&
    'status' in error
  ) {
    return new ApiError(error as ApiErrorBody);
  }
  return new ApiError({ status: 0, detail: fallbackDetail, correlation_id: null });
}
