/**
 * Tests del hook que orquesta la ingesta.
 *
 * `EventSource` no existe en jsdom, así que se sustituye por un doble que además permite
 * comprobar lo que más importa: que la conexión se cierre siempre. Un `EventSource`
 * huérfano reintenta conectarse solo, y cada reintento relanzaría el ETL en el servidor.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as servicio from '../services/ingestaService';
import { useIngesta } from './useIngesta';

class EventSourceFalso {
  static ultima: EventSourceFalso | null = null;

  readonly url: string;
  cerrado = false;
  onerror: (() => void) | null = null;
  private oyentes = new Map<string, (evento: MessageEvent<string>) => void>();

  constructor(url: string) {
    this.url = url;
    EventSourceFalso.ultima = this;
  }

  addEventListener(tipo: string, oyente: (evento: MessageEvent<string>) => void) {
    this.oyentes.set(tipo, oyente);
  }

  close() {
    this.cerrado = true;
  }

  /** Simula un evento del servidor. */
  emitir(tipo: string, datos: unknown) {
    this.oyentes.get(tipo)?.({ data: JSON.stringify(datos) } as MessageEvent<string>);
  }
}

const ARCHIVO = new File(['x'], '20260815_r.xlsm');

beforeEach(() => {
  EventSourceFalso.ultima = null;
  vi.stubGlobal('EventSource', EventSourceFalso);
  vi.spyOn(servicio, 'subirArchivo').mockResolvedValue({
    id: 'sub-1',
    archivo: '20260815_r.xlsm',
    hash: 'h',
    fechaReporte: '2026-08-15',
  });
  vi.spyOn(servicio, 'calcularHash').mockResolvedValue('h');
  vi.spyOn(servicio, 'consultarReporteExistente').mockResolvedValue({
    existe: false,
    reporteId: null,
    archivo: null,
    tipoArchivo: null,
    ingeridoEn: null,
    mismoContenido: null,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function subirYProcesar() {
  const { result, unmount } = renderHook(() => useIngesta());
  await act(async () => {
    await result.current.seleccionarArchivo(ARCHIVO);
  });
  act(() => {
    result.current.procesar();
  });
  return { result, unmount };
}

describe('selección del archivo', () => {
  it('empieza inactivo', () => {
    const { result } = renderHook(() => useIngesta());

    expect(result.current.estado.fase).toBe('inactiva');
  });

  it('pasa a confirmando tras subir', async () => {
    const { result } = renderHook(() => useIngesta());

    await act(async () => {
      await result.current.seleccionarArchivo(ARCHIVO);
    });

    expect(result.current.estado.fase).toBe('confirmando');
    expect(result.current.estado.subida?.id).toBe('sub-1');
  });

  it('reporta el fallo de subida sin dejar el flujo colgado', async () => {
    vi.spyOn(servicio, 'subirArchivo').mockRejectedValue(new Error('demasiado grande'));
    const { result } = renderHook(() => useIngesta());

    await act(async () => {
      await result.current.seleccionarArchivo(ARCHIVO);
    });

    expect(result.current.estado.fase).toBe('revertida');
    expect(result.current.estado.error).toBe('demasiado grande');
  });
});

describe('progreso', () => {
  it('acumula las hojas que llegan', async () => {
    const { result } = await subirYProcesar();

    act(() => {
      EventSourceFalso.ultima?.emitir('inicio', {
        tipo: 'inicio',
        archivo: 'r.xlsm',
        tipo_archivo: 'STD',
        hojas: ['INICIO'],
        total: 1,
      });
      EventSourceFalso.ultima?.emitir('hoja', {
        tipo: 'hoja',
        hoja: 'INICIO',
        estado: 'procesando',
      });
    });

    expect(result.current.estado.totalHojas).toBe(1);
    expect(result.current.estado.hojas).toHaveLength(1);
  });

  it('reemplaza la hoja en su sitio en vez de duplicarla', async () => {
    // Una hoja pasa por varios estados; si se añadiera cada vez, la lista crecería y
    // se reordenaría bajo el cursor del usuario.
    const { result } = await subirYProcesar();

    act(() => {
      EventSourceFalso.ultima?.emitir('hoja', {
        tipo: 'hoja',
        hoja: 'INICIO',
        estado: 'procesando',
      });
      EventSourceFalso.ultima?.emitir('hoja', {
        tipo: 'hoja',
        hoja: 'INICIO',
        estado: 'procesada',
        filas: 80,
      });
    });

    expect(result.current.estado.hojas).toHaveLength(1);
    expect(result.current.estado.hojas[0].estado).toBe('procesada');
    expect(result.current.estado.hojas[0].filas).toBe(80);
  });
});

describe('cierre del flujo', () => {
  it('marca confirmada y cierra la conexión', async () => {
    const { result } = await subirYProcesar();

    act(() => {
      EventSourceFalso.ultima?.emitir('fin', {
        tipo: 'fin',
        estado: 'confirmado',
        resultado: {
          archivo: 'r.xlsm',
          reporte_id: 1042,
          tipo_archivo: 'STD',
          tiene_raw: false,
        },
      });
    });

    expect(result.current.estado.fase).toBe('confirmada');
    expect(result.current.estado.resultado?.reporteId).toBe(1042);
    expect(EventSourceFalso.ultima?.cerrado).toBe(true);
  });

  it('marca revertida y conserva la hoja que falló', async () => {
    const { result } = await subirYProcesar();

    act(() => {
      EventSourceFalso.ultima?.emitir('fin', {
        tipo: 'fin',
        estado: 'revertido',
        code: 'HOJA_ILEGIBLE',
        hoja: 'PROGRAMA',
        detalle: 'La hoja cambió de formato.',
      });
    });

    expect(result.current.estado.fase).toBe('revertida');
    expect(result.current.estado.hojaDelError).toBe('PROGRAMA');
    expect(result.current.estado.codigoError).toBe('HOJA_ILEGIBLE');
  });

  it('avisa si se pierde la conexión a mitad', async () => {
    const { result } = await subirYProcesar();

    act(() => {
      EventSourceFalso.ultima?.onerror?.();
    });

    expect(result.current.estado.fase).toBe('revertida');
    expect(result.current.estado.error).toMatch(/perdió la conexión/i);
  });

  it('cierra la conexión al desmontar', async () => {
    // Sin esto, el navegador reintentaría solo y relanzaría el ETL.
    const { unmount } = await subirYProcesar();
    const fuente = EventSourceFalso.ultima;

    unmount();

    expect(fuente?.cerrado).toBe(true);
  });
});

describe('reinicio', () => {
  it('vuelve al estado inicial', async () => {
    const { result } = await subirYProcesar();

    act(() => {
      result.current.reiniciar();
    });

    await waitFor(() => {
      expect(result.current.estado.fase).toBe('inactiva');
    });
    expect(result.current.estado.hojas).toEqual([]);
    expect(EventSourceFalso.ultima?.cerrado).toBe(true);
  });
});
