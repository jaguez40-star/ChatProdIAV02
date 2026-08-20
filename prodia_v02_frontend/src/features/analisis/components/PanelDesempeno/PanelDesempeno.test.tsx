import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Desempeno } from '../../types/analisisTypes';
import { PanelDesempeno } from './PanelDesempeno';

const mocks = vi.hoisted(() => ({ getDesempeno: vi.fn() }));

vi.mock('../../services/analisisService', () => ({
  getDesempeno: mocks.getDesempeno,
  getCatalogo: vi.fn(),
  getDensidad: vi.fn(),
  getHuella: vi.fn(),
  getCobertura: vi.fn(),
  getEjecutivo: vi.fn(),
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

const BASE: Desempeno = {
  entidad: 'CASTILLA',
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
  porProducto: [{ producto: 'CRUDO', real: 1000, ppto: 1200, cumplimiento: 83.3 }],
  camposSinMeta: [],
  curva: {
    fechas: ['2026-05-01', '2026-05-02'],
    series: { CRUDO: [100, 120] },
  },
  ritmoMensual: {
    meses: ['Ene', 'Feb'],
    mesesNum: [1, 2],
    series: { CRUDO: [3000, 3100] },
    promedioMes: { CRUDO: 3050 },
    promedioDia: { CRUDO: 100 },
    mesActual: 5,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getDesempeno.mockResolvedValue(BASE);
});

describe('PanelDesempeno', () => {
  it('muestra el KPI con su cumplimiento', async () => {
    render(envolver(<PanelDesempeno ambito={{ entidad: 'CASTILLA' }} />));

    expect(await screen.findByText('CRUDO')).toBeDefined();
    expect(screen.getByText(/83,3%/)).toBeDefined();
  });

  it('renderiza la curva diaria y el ritmo mensual', async () => {
    render(envolver(<PanelDesempeno ambito={{ entidad: 'CASTILLA' }} />));

    expect(
      await screen.findByRole('img', { name: 'Curva de producción diaria' }),
    ).toBeDefined();
    expect(
      screen.getByRole('img', { name: 'Producción mensual del año con su promedio' }),
    ).toBeDefined();
  });

  it('declara los campos que producen sin meta', async () => {
    mocks.getDesempeno.mockResolvedValue({
      ...BASE,
      camposSinMeta: [{ campo: 'SURIA', producto: 'CRUDO', real: 500 }],
    });
    render(envolver(<PanelDesempeno ambito={{ entidad: 'APIAY', nivel: 'activo' }} />));

    expect(
      await screen.findByText('Campos que producen sin meta asignada'),
    ).toBeDefined();
    expect(screen.getByText(/SURIA/)).toBeDefined();
  });

  it('avisa cuando la entidad no existe', async () => {
    mocks.getDesempeno.mockResolvedValue({ ...BASE, encontrada: false });
    render(envolver(<PanelDesempeno ambito={{ entidad: 'NO EXISTE' }} />));

    expect(await screen.findByText(/No se encontró/)).toBeDefined();
  });

  it('avisa cuando la entidad existe pero no tiene datos', async () => {
    mocks.getDesempeno.mockResolvedValue({ ...BASE, sinDatos: true });
    render(envolver(<PanelDesempeno ambito={{ entidad: 'CASTILLA' }} />));

    expect(await screen.findByText(/no tiene datos de producción/)).toBeDefined();
  });

  it('declara la ausencia de grano diario', async () => {
    mocks.getDesempeno.mockResolvedValue({
      ...BASE,
      aplicaDiario: false,
      curva: null,
    });
    render(envolver(<PanelDesempeno ambito={{ entidad: 'VAS' }} />));

    expect(await screen.findByText(/solo reporta a nivel mensual/)).toBeDefined();
  });
});
