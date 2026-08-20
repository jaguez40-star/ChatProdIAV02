/**
 * Services de Consulta — por `apiClient`, nunca `fetch` desnudo (N1/C1).
 *
 * Cada error se convierte en `ApiError`, que expone `.status` y
 * `.correlationId`: es lo que permite mostrar al usuario la referencia con la
 * que reportar el problema, y a quien lo atienda hacer grep en los logs del
 * backend (C2/N6).
 */

import apiClient, { toApiError } from '../../../shared/services/apiClient';
import { aRespuestaQ } from '../mappers/consultaMappers';
import type { GrupoQ, RespuestaQ } from '../types/consultaTypes';

/** Envía una pregunta del chat y devuelve su clasificación y respuesta. */
export async function preguntar(
  texto: string,
  conversacionId: string,
): Promise<RespuestaQ> {
  const { data, error } = await apiClient.POST('/api/v1/consulta/preguntar', {
    // El `usuario` NO viaja aquí: sale de la cookie de sesión. Enviarlo sería
    // dejar que el cliente declare quién es.
    body: { texto, conversacion_id: conversacionId },
  });
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo procesar la pregunta');
  }
  return aRespuestaQ(data);
}

/**
 * Registra el ✓/✗ del usuario sobre una clasificación (control 1).
 *
 * `fuente` no se envía: la fija el servidor. Si viniera del cliente, se
 * podrían marcar veredictos como si fueran de la revisión por lotes.
 */
export async function enviarVeredicto(
  logId: number,
  veredicto: 'confirmado_usuario' | 'corregido_usuario',
  grupoCorrecto?: GrupoQ,
): Promise<void> {
  const { error } = await apiClient.POST('/api/v1/consulta/veredicto', {
    body: {
      log_id: logId,
      veredicto,
      grupo_correcto: grupoCorrecto ?? null,
    },
  });
  if (error) throw toApiError(error, 'No se pudo registrar el veredicto');
}
