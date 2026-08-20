/**
 * La página completa. El test que más importa es el de H5: cambiar de filtro
 * NO debe disparar el escaneo de señales.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TestClasPage from './TestClasPage';
import * as servicio from '../services/testClasService';
import type { Libreta } from '../types/testClasTypes';

vi.mock('../services/testClasService');
vi.mock('../components/ChatPrueba/ChatPrueba', () => ({
  ChatPrueba: () => <div>chat</div>,
}));

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

function montar() {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={cliente}>
      <TestClasPage />
    </QueryClientProvider>,
  );
}

describe('TestClasPage', () => {
  beforeEach(() => {
    // Sin esto, el contador de llamadas arrastra las de los tests anteriores y
    // «se llamó 1 vez» pasa a ser «se llamó 3».
    vi.clearAllMocks();
    vi.mocked(servicio.cargarLibreta).mockResolvedValue(LIBRETA);
    vi.mocked(servicio.escanearSenales).mockResolvedValue({
      sospechasNuevas: 0,
      filasRevisadas: 0,
    });
    vi.mocked(servicio.enviarVeredictosEnLote).mockResolvedValue({
      aplicados: 1,
      total: 1,
    });
  });

  it('muestra la libreta con sus KPIs', async () => {
    montar();

    await waitFor(() => expect(screen.getByText('cuánto produjo Castilla')).toBeTruthy());
    expect(screen.getByText('100%')).toBeTruthy();
  });

  it('escanea señales UNA VEZ al abrir', async () => {
    montar();

    await waitFor(() => expect(servicio.escanearSenales).toHaveBeenCalledTimes(1));
  });

  it('cambiar de filtro NO dispara el escaneo (H5)', async () => {
    const usuario = userEvent.setup();
    montar();
    await waitFor(() => expect(servicio.escanearSenales).toHaveBeenCalledTimes(1));

    await usuario.click(screen.getByRole('button', { name: 'Pendientes' }));
    await usuario.click(screen.getByRole('button', { name: 'Sospecha' }));

    // El sistema viejo llamaba al escaneo dentro de CADA lectura de la libreta,
    // así que cada clic recorría todos los pendientes con dos consultas por fila.
    expect(servicio.escanearSenales).toHaveBeenCalledTimes(1);
    // Pero la libreta SÍ se relee con el filtro nuevo.
    expect(vi.mocked(servicio.cargarLibreta).mock.lastCall?.[0]).toBe('sospecha');
  });

  it('el botón de buscar señales sí lo dispara a propósito', async () => {
    const usuario = userEvent.setup();
    montar();
    await waitFor(() => expect(servicio.escanearSenales).toHaveBeenCalledTimes(1));

    await usuario.click(screen.getByRole('button', { name: /Buscar señales/ }));

    await waitFor(() => expect(servicio.escanearSenales).toHaveBeenCalledTimes(2));
  });

  it('declara el truncado en vez de dejar creer que se vio todo', async () => {
    vi.mocked(servicio.cargarLibreta).mockResolvedValue({ ...LIBRETA, truncado: true });

    montar();

    await waitFor(() => expect(screen.getByText(/hay más en la libreta/)).toBeTruthy());
  });

  it('avisa cuando el escaneo encuentra sospechas', async () => {
    vi.mocked(servicio.escanearSenales).mockResolvedValue({
      sospechasNuevas: 4,
      filasRevisadas: 30,
    });

    montar();

    await waitFor(() => expect(screen.getByText(/4 caso\(s\) marcados/)).toBeTruthy());
  });
});
