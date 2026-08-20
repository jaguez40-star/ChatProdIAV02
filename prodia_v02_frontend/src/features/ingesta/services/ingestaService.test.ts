/**
 * Tests del servicio de Ingesta — las funciones puras y el manejo de error de la subida.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../../shared/services/apiClient';
import { fechaDelNombre, rutaDeProgreso, subirArchivo } from './ingestaService';

describe('fechaDelNombre', () => {
  it('extrae la fecha en ISO desde el nombre', () => {
    expect(fechaDelNombre('20260815_Reporte.xlsm')).toBe('2026-08-15');
  });

  it('la encuentra esté donde esté en el nombre', () => {
    expect(fechaDelNombre('Reporte Diario 20241004 New.xlsm')).toBe('2024-10-04');
  });

  it('devuelve null si el nombre no trae fecha', () => {
    expect(fechaDelNombre('reporte.xlsm')).toBeNull();
  });
});

describe('rutaDeProgreso', () => {
  it('construye la ruta del flujo de eventos', () => {
    expect(rutaDeProgreso('abc123')).toBe('/api/v1/ingesta/progreso/abc123');
  });

  it('escapa el identificador', () => {
    expect(rutaDeProgreso('a b/c')).toBe('/api/v1/ingesta/progreso/a%20b%2Fc');
  });
});

describe('subirArchivo', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('devuelve el archivo aceptado', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          id: 'abc',
          archivo: '20260815_r.xlsm',
          hash: 'h',
          fecha_reporte: '2026-08-15',
        }),
      }),
    );

    const resultado = await subirArchivo(
      new File(['x'], '20260815_r.xlsm'),
    );

    expect(resultado.id).toBe('abc');
    expect(resultado.fechaReporte).toBe('2026-08-15');
  });

  it('conserva el código de dominio que envía el backend', async () => {
    // Es lo que permite al usuario saber si el problema es el archivo o la base.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 413,
        headers: new Headers({ 'X-Codigo': 'ARCHIVO_DEMASIADO_GRANDE' }),
        json: async () => ({ detail: 'Supera el máximo de 200 MB.' }),
      }),
    );

    await expect(subirArchivo(new File(['x'], '20260815_r.xlsm'))).rejects.toThrow(
      ApiError,
    );
  });

  it('sigue fallando de forma legible si el cuerpo del error no es JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        headers: new Headers(),
        json: async () => {
          throw new Error('no es json');
        },
      }),
    );

    await expect(
      subirArchivo(new File(['x'], '20260815_r.xlsm')),
    ).rejects.toThrow('No se pudo subir el archivo');
  });
});
