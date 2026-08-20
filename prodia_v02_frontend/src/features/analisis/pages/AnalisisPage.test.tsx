import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AnalisisPage from './AnalisisPage';

/**
 * La página monta gráficos Plotly reales: si el polyfill de
 * `URL.createObjectURL` desapareciera del setup, este archivo fallaría como
 * SUITE entera (no como test), que es justo lo que AP-4 documenta.
 */

const mocks = vi.hoisted(() => ({
  getCatalogo: vi.fn(),
  getDesempeno: vi.fn(),
  getEjecutivo: vi.fn(),
  getDensidad: vi.fn(),
  getCobertura: vi.fn(),
}));

vi.mock('../services/analisisService', () => ({
  getCatalogo: mocks.getCatalogo,
  getDesempeno: mocks.getDesempeno,
  getEjecutivo: mocks.getEjecutivo,
  getDensidad: mocks.getDensidad,
  getCobertura: mocks.getCobertura,
  getHuella: vi.fn(),
  getPresident: vi.fn(),
  getTendenciaFilial: vi.fn(),
  getWaterfall: vi.fn(),
  getDiferidas: vi.fn(),
  getMantenimientos: vi.fn(),
}));

function envolver(nodo: ReactNode) {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={cliente}>{nodo}</QueryClientProvider>;
}

const DESEMPENO_BASE = {
  entidad: null,
  encontrada: true,
  sinDatos: false,
  aplicaDiario: true,
  sinCierre: false,
  periodoOk: true,
  mes: {
    anio: 2026,
    mes: 5,
    nombre: 'Mayo',
    diasConData: 17,
    diasDelMes: 31,
    completo: false,
  },
  porProducto: [
    { producto: 'CRUDO', real: 1000, ppto: 1200, cumplimiento: 83.3 },
    { producto: 'GAS', real: 500, ppto: 0, cumplimiento: null },
  ],
  camposSinMeta: [],
  curva: null,
  ritmoMensual: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getCatalogo.mockResolvedValue({
    cardinalidad: [{ nivel: 'campo', n: 128 }],
    productosValidos: [],
    colisiones: [],
    resumenColisiones: { dura: 0, media: 0, blanda: 0, total: 0 },
    filiales: ['Hocol'],
    entidadesPorNivel: { campo: ['CASTILLA'] },
  });
  mocks.getDesempeno.mockResolvedValue(DESEMPENO_BASE);
});

describe('AnalisisPage', () => {
  it('arranca en Desempeño y muestra los KPIs', async () => {
    render(envolver(<AnalisisPage />));

    expect(await screen.findByText('CRUDO')).toBeDefined();
    expect(screen.getByText('83,3%', { exact: false })).toBeDefined();
  });

  it('un producto sin meta se declara, no se muestra como 0 %', async () => {
    render(envolver(<AnalisisPage />));

    expect(await screen.findByText('Sin meta en el periodo')).toBeDefined();
  });

  it('declara cuando el periodo pedido no se pudo honrar', async () => {
    mocks.getDesempeno.mockResolvedValue({ ...DESEMPENO_BASE, periodoOk: false });
    render(envolver(<AnalisisPage />));

    expect(
      await screen.findByText(/El periodo solicitado no está soportado/),
    ).toBeDefined();
  });

  it('permite cambiar de sección', async () => {
    const usuario = userEvent.setup();
    mocks.getEjecutivo.mockResolvedValue({
      entidad: null,
      encontrada: true,
      sinDatos: false,
      meta: { scope: 'Global', periodo: 'Mayo 2026', corte: '17/31', generadoPor: 'fallback' },
      titular: [],
      tarjetas: [],
      valle: null,
      pace: null,
      secciones: {
        insights: ['Cierre de Mayo 2026'],
        oportunidades: [],
        puntosAtencion: [],
        decisiones: [],
      },
      focos: [],
      sinFoco: '',
    });

    render(envolver(<AnalisisPage />));
    await screen.findByText('CRUDO');

    await usuario.click(screen.getByText('Análisis ejecutivo'));

    expect(await screen.findByText('Cierre de Mayo 2026')).toBeDefined();
  });

  it('muestra un mensaje claro si la entidad no existe', async () => {
    mocks.getDesempeno.mockResolvedValue({
      ...DESEMPENO_BASE,
      encontrada: false,
      entidad: 'NO EXISTE',
    });
    render(envolver(<AnalisisPage />));

    expect(await screen.findByText(/No se encontró/)).toBeDefined();
  });
});
