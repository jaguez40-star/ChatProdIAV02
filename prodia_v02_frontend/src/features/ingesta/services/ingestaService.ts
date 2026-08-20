/**
 * Llamadas al backend de Ingesta.
 *
 * Las dos primeras pasan por `apiClient` como manda N1/C1. La tercera —el progreso— no
 * puede: `EventSource` es una API propia del navegador para flujos SSE, y no hay forma de
 * enrutarla por `openapi-fetch`. A cambio, el manejo de errores se normaliza a mano para
 * que el consumidor reciba el mismo tipo de error que en el resto de la aplicación.
 */

import apiClient, { ApiError, toApiError } from '../../../shared/services/apiClient';
import {
  aArchivoAceptado,
  aReporteExistente,
} from '../mappers/ingestaMappers';
import type { ArchivoAceptado, ReporteExistente } from '../types/ingestaTypes';

/** Ruta del flujo de eventos de una ingesta ya subida. */
export function rutaDeProgreso(idSubida: string): string {
  return `/api/v1/ingesta/progreso/${encodeURIComponent(idSubida)}`;
}

/**
 * Comprueba si ya existe un reporte para esa fecha.
 *
 * Es informativo: reingerir es seguro porque el ETL es idempotente, pero conviene que el
 * usuario sepa que va a sobrescribir antes de hacerlo.
 */
export async function consultarReporteExistente(
  fecha: string,
  hashArchivo?: string,
): Promise<ReporteExistente> {
  const { data, error } = await apiClient.GET('/api/v1/ingesta/reporte-existente', {
    params: { query: { fecha, hash_archivo: hashArchivo } },
  });
  if (error || data === undefined) {
    throw toApiError(error, 'No se pudo comprobar si el reporte ya existe');
  }
  return aReporteExistente(data);
}

/**
 * Sube el archivo y lo deja listo para procesar. **No lo ingiere todavía.**
 *
 * Se usa `fetch` directamente y no `apiClient` porque el cuerpo es `multipart/form-data`
 * con un archivo de hasta 200 MB: `openapi-fetch` serializa el cuerpo a JSON, que aquí
 * no aplica. El error se normaliza al mismo `ApiError` del resto de la aplicación, y se
 * conserva el código de dominio que el backend envía en la cabecera `X-Codigo` para
 * poder distinguir «archivo corrupto» de «demasiado grande».
 */
export async function subirArchivo(archivo: File): Promise<ArchivoAceptado> {
  const cuerpo = new FormData();
  cuerpo.append('archivo', archivo);

  const respuesta = await fetch('/api/v1/ingesta/archivo', {
    method: 'POST',
    body: cuerpo,
    credentials: 'include',
  });

  if (!respuesta.ok) {
    const detalle = await respuesta
      .json()
      .then((cuerpoError: { detail?: string }) => cuerpoError.detail)
      .catch(() => undefined);
    throw new ApiError({
      status: respuesta.status,
      detail: detalle ?? 'No se pudo subir el archivo',
      correlation_id: respuesta.headers.get('x-correlation-id'),
      code: respuesta.headers.get('X-Codigo') ?? undefined,
    });
  }

  return aArchivoAceptado(await respuesta.json());
}

/**
 * Calcula el SHA-256 del archivo en el navegador.
 *
 * Sirve para preguntarle al backend si el archivo es idéntico al ya ingerido, y así poder
 * decir «es el mismo archivo» en lugar del genérico «esta fecha ya existe».
 */
export async function calcularHash(archivo: File): Promise<string> {
  const contenido = await archivo.arrayBuffer();
  const resumen = await crypto.subtle.digest('SHA-256', contenido);
  return Array.from(new Uint8Array(resumen))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

/** Fecha `YYYYMMDD` embebida en el nombre, en formato ISO. `null` si no la trae. */
export function fechaDelNombre(nombre: string): string | null {
  const encontrada = /(\d{8})/.exec(nombre);
  if (!encontrada) return null;
  const crudo = encontrada[1];
  return `${crudo.slice(0, 4)}-${crudo.slice(4, 6)}-${crudo.slice(6, 8)}`;
}
