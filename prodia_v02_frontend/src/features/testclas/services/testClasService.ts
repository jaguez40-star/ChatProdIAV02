/**
 * Services de Test Clas — por `apiClient`, nunca `fetch` desnudo (N1/C1).
 *
 * Cada error se convierte en `ApiError`, que expone `.status` y
 * `.correlationId` para que el revisor pueda reportar el problema con una
 * referencia grepeable en los logs del backend (C2/N6).
 */

import apiClient, { toApiError } from '../../../shared/services/apiClient';
import {
  aLibreta,
  aResultadoEscaneo,
  aResultadoLote,
} from '../mappers/testClasMappers';
import type {
  FiltroLibreta,
  Libreta,
  ResultadoEscaneo,
  ResultadoLote,
  VeredictoDeRevision,
} from '../types/testClasTypes';

/** La cola de revisión con sus KPIs. Lectura pura: no dispara el escaneo. */
export async function cargarLibreta(
  filtro: FiltroLibreta,
  limite = 100,
): Promise<Libreta> {
  const { data, error } = await apiClient.GET('/api/v1/consulta/revision/libreta', {
    params: { query: { filtro, limite } },
  });
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo cargar la libreta');
  }
  return aLibreta(data);
}

/**
 * Aplica varios veredictos del Control 3.
 *
 * `fuente` no se envía: la fija el servidor en `revision`. Si viniera del
 * cliente, cualquiera podría marcar veredictos como si fueran del revisor — y
 * `confirmado_revision` es la verdad final que alimenta el golden.
 */
export async function enviarVeredictosEnLote(
  items: VeredictoDeRevision[],
  nota?: string,
): Promise<ResultadoLote> {
  const { data, error } = await apiClient.POST(
    '/api/v1/consulta/revision/veredicto-lote',
    {
      body: {
        items: items.map(({ logId, grupoCorrecto }) => ({
          log_id: logId,
          veredicto: (grupoCorrecto
            ? 'corregido_revision'
            : 'confirmado_revision') as 'confirmado_revision' | 'corregido_revision',
          grupo_correcto: grupoCorrecto,
        })),
        nota: nota ?? null,
      },
    },
  );
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudieron guardar los veredictos');
  }
  return aResultadoLote(data);
}

/**
 * Ejecuta el Control 2 y devuelve qué encontró.
 *
 * Explícito a propósito: en el sistema viejo el escaneo corría dentro de cada
 * lectura de la libreta, así que cada clic en un filtro recorría todos los
 * pendientes lanzando dos consultas por fila.
 */
export async function escanearSenales(): Promise<ResultadoEscaneo> {
  const { data, error } = await apiClient.POST(
    '/api/v1/consulta/revision/escanear',
    {},
  );
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo escanear en busca de señales');
  }
  return aResultadoEscaneo(data);
}
