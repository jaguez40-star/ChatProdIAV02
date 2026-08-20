/**
 * El test que fija H4: si el POST falla, la fila VUELVE a pendiente.
 *
 * Sin esta prueba, la corrección al sistema viejo se perdería en el primer
 * refactor y la UI volvería a mentir sobre un dato que alimenta el golden.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useLibreta } from './useLibreta';
import * as servicio from '../services/testClasService';
import type { Libreta } from '../types/testClasTypes';

vi.mock('../services/testClasService');

const LIBRETA: Libreta = {
  filas: [
    {
      id: 1,
      ts: '2026-08-20T09:00:00',
      usuario: 'javier',
      conversacionId: 'c1',
      textoPregunta: 'cuánto produjo Castilla',
      grupoAsignado: 'cuantificar',
      capaResolutora: 'regex',
      entidadCruda: null,
      llmDiag: null,
      veredicto: 'pendiente',
      grupoCorrecto: null,
      fuenteVeredicto: null,
      notaRevision: null,
    },
  ],
  resumen: { total: 1, porVeredicto: { pendiente: 1 }, pctCapa1: 100 },
  truncado: false,
};

function envoltorio() {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  function Envoltorio({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: cliente }, children);
  }
  return Envoltorio;
}

describe('useLibreta', () => {
  beforeEach(() => {
    vi.mocked(servicio.cargarLibreta).mockResolvedValue(LIBRETA);
  });

  it('carga la libreta con sus KPIs', async () => {
    const { result } = renderHook(() => useLibreta('todas'), {
      wrapper: envoltorio(),
    });

    await waitFor(() => expect(result.current.libreta).toBeDefined());
    expect(result.current.libreta?.resumen.pctCapa1).toBe(100);
  });

  it('pinta el veredicto al instante, sin esperar a la red', async () => {
    let resolver: (() => void) | undefined;
    vi.mocked(servicio.enviarVeredictosEnLote).mockReturnValue(
      new Promise((cumplir) => {
        resolver = () => cumplir({ aplicados: 1, total: 1 });
      }),
    );

    const { result } = renderHook(() => useLibreta('todas'), {
      wrapper: envoltorio(),
    });
    await waitFor(() => expect(result.current.libreta).toBeDefined());

    act(() => result.current.calificar([{ logId: 1, grupoCorrecto: null }]));

    // La petición sigue en vuelo y la UI ya muestra el resultado.
    await waitFor(() =>
      expect(result.current.libreta?.filas[0].veredicto).toBe('confirmado_revision'),
    );
    act(() => resolver?.());
  });

  it('DESHACE el cambio y avisa si la petición falla (H4)', async () => {
    vi.mocked(servicio.enviarVeredictosEnLote).mockRejectedValue(
      new Error('sin red'),
    );

    const { result } = renderHook(() => useLibreta('todas'), {
      wrapper: envoltorio(),
    });
    await waitFor(() => expect(result.current.libreta).toBeDefined());

    act(() => result.current.calificar([{ logId: 1, grupoCorrecto: null }]));

    await waitFor(() => expect(result.current.aviso).not.toBeNull());
    // Lo que el sistema viejo NO hacía: la fila vuelve a estar sin juzgar.
    expect(result.current.libreta?.filas[0].veredicto).toBe('pendiente');
    expect(result.current.aviso).toContain('sigue pendiente');
  });

  it('avisa cuando un lote se aplica solo a medias', async () => {
    vi.mocked(servicio.enviarVeredictosEnLote).mockResolvedValue({
      aplicados: 7,
      total: 10,
    });

    const { result } = renderHook(() => useLibreta('todas'), {
      wrapper: envoltorio(),
    });
    await waitFor(() => expect(result.current.libreta).toBeDefined());

    act(() => result.current.calificar([{ logId: 1, grupoCorrecto: null }]));

    await waitFor(() => expect(result.current.aviso).toContain('7 de 10'));
  });

  it('corregir a un grupo distinto registra la corrección, no una confirmación', async () => {
    // La petición se deja EN VUELO: al resolverse, `onSettled` invalida y el
    // mock de carga devolvería la libreta original, pisando lo que se afirma.
    // Lo que se prueba aquí es el cálculo optimista, no lo que responde el
    // servidor.
    vi.mocked(servicio.enviarVeredictosEnLote).mockReturnValue(
      new Promise(() => {}),
    );

    const { result } = renderHook(() => useLibreta('todas'), {
      wrapper: envoltorio(),
    });
    await waitFor(() => expect(result.current.libreta).toBeDefined());

    act(() => result.current.calificar([{ logId: 1, grupoCorrecto: 'analizar' }]));

    await waitFor(() =>
      expect(result.current.libreta?.filas[0].veredicto).toBe('corregido_revision'),
    );
    expect(result.current.libreta?.filas[0].grupoCorrecto).toBe('analizar');
  });

  it('corregir al MISMO grupo que asignó el motor es confirmar', async () => {
    vi.mocked(servicio.enviarVeredictosEnLote).mockReturnValue(
      new Promise(() => {}),
    );

    const { result } = renderHook(() => useLibreta('todas'), {
      wrapper: envoltorio(),
    });
    await waitFor(() => expect(result.current.libreta).toBeDefined());

    // El revisor tecleó «2» en vez de Enter: registrar una "corrección" a lo que
    // el motor ya dijo ensuciaría el dato de entrenamiento.
    act(() => result.current.calificar([{ logId: 1, grupoCorrecto: 'cuantificar' }]));

    await waitFor(() =>
      expect(result.current.libreta?.filas[0].veredicto).toBe('confirmado_revision'),
    );
    expect(result.current.libreta?.filas[0].grupoCorrecto).toBeNull();
  });

  it('el escaneo informa de lo que encontró', async () => {
    vi.mocked(servicio.escanearSenales).mockResolvedValue({
      sospechasNuevas: 3,
      filasRevisadas: 40,
    });

    const { result } = renderHook(() => useLibreta('todas'), {
      wrapper: envoltorio(),
    });
    await waitFor(() => expect(result.current.libreta).toBeDefined());

    act(() => result.current.escanear());

    await waitFor(() => expect(result.current.aviso).toContain('3 caso(s)'));
  });
});
