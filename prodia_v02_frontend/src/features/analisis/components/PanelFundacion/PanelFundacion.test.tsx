import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PanelFundacion } from './PanelFundacion';

const mocks = vi.hoisted(() => ({
  getCatalogo: vi.fn(),
  getDensidad: vi.fn(),
  getCobertura: vi.fn(),
}));

vi.mock('../../services/analisisService', () => ({
  getCatalogo: mocks.getCatalogo,
  getDensidad: mocks.getDensidad,
  getCobertura: mocks.getCobertura,
  getHuella: vi.fn(),
  getDesempeno: vi.fn(),
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

const DENSIDAD_BASE = {
  entidad: 'CASTILLA',
  aplicaEcp: true,
  dias: [{ fecha: '2026-05-01', filas: 10, fuentes: 4 }],
  porMes: [
    {
      anio: 2026,
      mes: 5,
      mesNombre: 'Mayo',
      diasConData: 1,
      diasDelMes: 31,
      huecos: 30,
      rango: ['2026-05-01', '2026-05-01'],
    },
  ],
  resumen: {
    totalDias: 1,
    rango: ['2026-05-01', '2026-05-01'],
    huecosTotales: 30,
    rachaMaxima: 1,
  },
  semaforo: [
    { familia: 'La foto', nivel: 'verde' as const, necesitaContinuidad: false },
    { familia: 'El movimiento', nivel: 'rojo' as const, necesitaContinuidad: true },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getCatalogo.mockResolvedValue({
    cardinalidad: [
      { nivel: 'campo', n: 128 },
      { nivel: 'fuente', n: 900 },
    ],
    productosValidos: [{ termino: 'aceite', dim: 'CRUDO' }],
    colisiones: [
      {
        nombre: 'RUBIALES',
        niveles: ['activo', 'campo'],
        nNiveles: 2,
        severidad: 'dura' as const,
      },
      {
        nombre: 'LORITO',
        niveles: ['campo', 'fuente'],
        nNiveles: 2,
        severidad: 'blanda' as const,
      },
    ],
    resumenColisiones: { dura: 1, media: 0, blanda: 1, total: 2 },
    filiales: ['Hocol', 'Permian'],
    entidadesPorNivel: { campo: ['CASTILLA'] },
  });
  mocks.getDensidad.mockResolvedValue(DENSIDAD_BASE);
  mocks.getCobertura.mockResolvedValue({
    entidad: null,
    totalHojas: 2,
    categorias: [
      {
        categoria: 'Producción ECP',
        hojas: [
          {
            hoja: 'BDP_datos_dia',
            categoria: 'Producción ECP',
            reportesTotal: 100,
            reportesEntidad: null,
          },
        ],
      },
    ],
    hojasConEntidad: null,
  });
});

describe('PanelFundacion', () => {
  it('arranca en el catálogo y muestra la cardinalidad', async () => {
    render(envolver(<PanelFundacion />));

    expect(await screen.findByText('campo')).toBeDefined();
    expect(screen.getByText('128')).toBeDefined();
  });

  it('solo lista las colisiones que obligan a contrapreguntar', async () => {
    render(envolver(<PanelFundacion />));
    await screen.findByText('campo');

    // Dura sí; blanda no, porque usa el nivel por defecto sin preguntar.
    expect(screen.getByText('RUBIALES')).toBeDefined();
    expect(screen.queryByText('LORITO')).toBeNull();
  });

  it('renderiza el heatmap de densidad', async () => {
    const usuario = userEvent.setup();
    render(envolver(<PanelFundacion entidad="CASTILLA" />));
    await screen.findByText('campo');

    await usuario.click(screen.getByText('Densidad temporal'));

    expect(
      await screen.findByRole('img', {
        name: 'Mapa de calor de días con dato por mes',
      }),
    ).toBeDefined();
  });

  it('explica que "sin grano diario" no es un error', async () => {
    const usuario = userEvent.setup();
    mocks.getDensidad.mockResolvedValue({ ...DENSIDAD_BASE, aplicaEcp: false });

    render(envolver(<PanelFundacion entidad="HOCOL" />));
    await screen.findByText('campo');
    await usuario.click(screen.getByText('Densidad temporal'));

    expect(await screen.findByText(/No es un error/)).toBeDefined();
  });

  it('muestra la cobertura agrupada por categoría', async () => {
    const usuario = userEvent.setup();
    render(envolver(<PanelFundacion />));
    await screen.findByText('campo');

    await usuario.click(screen.getByText('Cobertura del reporte'));

    expect(await screen.findByText('Producción ECP')).toBeDefined();
    expect(screen.getByText('BDP_datos_dia')).toBeDefined();
  });
});
