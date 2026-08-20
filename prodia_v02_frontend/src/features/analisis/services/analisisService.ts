/**
 * Services de Análisis — todos por `apiClient` (N1/C1), nunca `fetch` desnudo.
 *
 * Cada error se convierte en `ApiError`, que expone `.status` y
 * `.correlationId`: es lo que permite a `QueryState` mostrar la referencia con
 * la que el usuario puede reportar el problema y alguien hacer grep en los logs
 * del backend (C2/N6).
 */

import apiClient, { toApiError } from '../../../shared/services/apiClient';
import {
  toCatalogo,
  toCobertura,
  toDensidad,
  toDesempeno,
  toDiferidas,
  toEjecutivo,
  toHuella,
  toMantenimientos,
  toPresident,
  toWaterfall,
} from '../mappers/analisisMappers';
import type {
  Ambito,
  Catalogo,
  Cobertura,
  Densidad,
  Desempeno,
  Diferidas,
  Ejecutivo,
  Huella,
  Mantenimientos,
  President,
  Waterfall,
} from '../types/analisisTypes';

/**
 * Los parámetros vacíos se OMITEN, no se mandan como `""`.
 *
 * El backend distingue "sin entidad" (panorama global) de `entidad=""`, que
 * resolvería a "no encontrada". El sistema viejo ya tropezó con esto.
 */
function soloDefinidos(ambito: Ambito): Record<string, string> {
  const salida: Record<string, string> = {};
  if (ambito.entidad?.trim()) salida.entidad = ambito.entidad.trim();
  if (ambito.nivel?.trim()) salida.nivel = ambito.nivel.trim();
  if (ambito.periodo?.trim()) salida.periodo = ambito.periodo.trim();
  if (ambito.segmento) salida.segmento = ambito.segmento;
  return salida;
}

// ── Fundación de datos ──────────────────────────────────────────────────────

export async function getCatalogo(): Promise<Catalogo> {
  const { data, error } = await apiClient.GET('/api/v1/analisis/catalogo');
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo cargar el catálogo de entidades');
  }
  return toCatalogo(data);
}

export async function getDensidad(entidad?: string): Promise<Densidad> {
  const { data, error } = await apiClient.GET('/api/v1/analisis/densidad', {
    params: { query: entidad?.trim() ? { entidad: entidad.trim() } : {} },
  });
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo calcular la densidad temporal');
  }
  return toDensidad(data);
}

export async function getHuella(entidad?: string): Promise<Huella> {
  const { data, error } = await apiClient.GET('/api/v1/analisis/huella', {
    params: { query: entidad?.trim() ? { entidad: entidad.trim() } : {} },
  });
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo cargar la huella de datos');
  }
  return toHuella(data);
}

export async function getCobertura(entidad?: string): Promise<Cobertura> {
  const { data, error } = await apiClient.GET('/api/v1/analisis/cobertura', {
    params: { query: entidad?.trim() ? { entidad: entidad.trim() } : {} },
  });
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo cargar la cobertura del reporte');
  }
  return toCobertura(data);
}

// ── Desempeño y ejecutivo ───────────────────────────────────────────────────

export async function getDesempeno(ambito: Ambito): Promise<Desempeno> {
  const { data, error } = await apiClient.GET('/api/v1/analisis/desempeno', {
    params: { query: soloDefinidos(ambito) },
  });
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo cargar el desempeño del mes');
  }
  return toDesempeno(data);
}

export async function getEjecutivo(ambito: Ambito): Promise<Ejecutivo> {
  const { data, error } = await apiClient.GET('/api/v1/analisis/ejecutivo', {
    params: { query: soloDefinidos(ambito) },
  });
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo cargar el análisis ejecutivo');
  }
  return toEjecutivo(data);
}

export async function getPresident(periodo?: string): Promise<President> {
  const { data, error } = await apiClient.GET('/api/v1/analisis/president', {
    params: { query: periodo?.trim() ? { periodo: periodo.trim() } : {} },
  });
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo cargar el compromiso corporativo');
  }
  return toPresident(data);
}

export async function getTendenciaFilial(empresa: string): Promise<Ejecutivo> {
  const { data, error } = await apiClient.GET('/api/v1/analisis/tendencia_filial', {
    params: { query: { empresa } },
  });
  if (error || data === undefined) {
    throw toApiError(error, `No se pudo cargar la tendencia de ${empresa}`);
  }
  return toEjecutivo(data);
}

// ── Pills del acordeón ──────────────────────────────────────────────────────

export async function getWaterfall(
  entidad?: string,
  nivel?: string,
): Promise<Waterfall> {
  const query: Record<string, string> = {};
  if (entidad?.trim()) query.entidad = entidad.trim();
  if (nivel?.trim()) query.nivel = nivel.trim();

  const { data, error } = await apiClient.GET('/api/v1/ebitda/unificado-waterfall', {
    params: { query },
  });
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo cargar el EBITDA');
  }
  return toWaterfall(data);
}

export async function getDiferidas(
  entidad?: string,
  nivel?: string,
): Promise<Diferidas> {
  const query: Record<string, string> = {};
  if (entidad?.trim()) query.entidad = entidad.trim();
  if (nivel?.trim()) query.nivel = nivel.trim();

  const { data, error } = await apiClient.GET('/api/v1/diferidas/frecuencia', {
    params: { query },
  });
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudieron cargar las diferidas');
  }
  return toDiferidas(data);
}

export async function getMantenimientos(
  entidad?: string,
  nivel?: string,
  periodo?: string,
): Promise<Mantenimientos> {
  const query: Record<string, string> = {};
  if (entidad?.trim()) query.entidad = entidad.trim();
  if (nivel?.trim()) query.nivel = nivel.trim();
  if (periodo?.trim()) query.periodo = periodo.trim();

  const { data, error } = await apiClient.GET('/api/v1/mantenimientos/eventos', {
    params: { query },
  });
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudieron cargar los mantenimientos');
  }
  return toMantenimientos(data);
}
