import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Foco } from '../../types/analisisTypes';
import { AcordeonFoco } from './AcordeonFoco';

const mocks = vi.hoisted(() => ({
  getDiferidas: vi.fn(),
  getMantenimientos: vi.fn(),
  getWaterfall: vi.fn(),
}));

vi.mock('../../services/analisisService', () => ({
  getDiferidas: mocks.getDiferidas,
  getMantenimientos: mocks.getMantenimientos,
  getWaterfall: mocks.getWaterfall,
  getCatalogo: vi.fn(),
  getDensidad: vi.fn(),
  getHuella: vi.fn(),
  getCobertura: vi.fn(),
  getDesempeno: vi.fn(),
  getEjecutivo: vi.fn(),
  getPresident: vi.fn(),
  getTendenciaFilial: vi.fn(),
}));

function envolver(nodo: ReactNode) {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={cliente}>{nodo}</QueryClientProvider>;
}

const FOCO_GAP: Foco = {
  producto: 'CRUDO',
  entidades: ['CUSIANA'],
  faltanteAbs: -500,
  pesoRelativoPct: 88.2,
  esOk: false,
  estadoLabel: 'Foco',
  sinProduccion: false,
  titulo: 'concentra el rezago del producto',
  causa: {
    texto: 'CUSIANA (2026-05-10): «falla eléctrica»',
    cobertura: 'con_evento',
    detalle: ['CUSIANA: faltante 500'],
    eventos: [{ campo: 'CUSIANA', fecha: '2026-05-10', texto: 'falla eléctrica' }],
  },
  accion: 'plan de recuperación específico',
  tipo: 'gap',
  rank: 1,
};

async function abrir(foco: Foco = FOCO_GAP) {
  const usuario = userEvent.setup();
  render(envolver(<AcordeonFoco foco={foco} ambito={{ entidad: 'CASTILLA' }} />));
  await usuario.click(screen.getByText('CUSIANA'));
  return usuario;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AcordeonFoco', () => {
  it('empieza cerrado y no consulta ninguna pill', () => {
    render(envolver(<AcordeonFoco foco={FOCO_GAP} ambito={{ entidad: 'CASTILLA' }} />));

    expect(screen.queryByText('Diferidas')).toBeNull();
    expect(mocks.getDiferidas).not.toHaveBeenCalled();
    expect(mocks.getMantenimientos).not.toHaveBeenCalled();
    expect(mocks.getWaterfall).not.toHaveBeenCalled();
  });

  it('al abrirlo muestra la causa y su detalle', async () => {
    await abrir();

    // `getAllByText`: el texto aparece en la causa Y en la lista de eventos de
    // la pill de comportamiento, que es lo esperado.
    expect(screen.getAllByText(/falla eléctrica/).length).toBeGreaterThan(0);
    expect(screen.getByText('CUSIANA: faltante 500')).toBeDefined();
    expect(screen.getByText('plan de recuperación específico')).toBeDefined();
  });

  it('la pill de mantenimientos lista los eventos abiertos', async () => {
    mocks.getMantenimientos.mockResolvedValue({
      sinDatos: false,
      motivo: null,
      eventos: [
        {
          pozo: 'CS-12',
          tipo: 'Workover',
          estado: 'abierto',
          inicio: '5 May',
          fin: '—',
        },
      ],
      meta: { scopeLabel: 'CUSIANA', periodo: 'Mayo 2026', total: 1, abiertos: 1 },
    });

    const usuario = await abrir();
    await usuario.click(screen.getByText('Mantenimientos'));

    expect(await screen.findByText('CS-12')).toBeDefined();
    expect(screen.getByText('abierto')).toBeDefined();
  });

  it('la pill de mantenimientos propaga su degradación', async () => {
    mocks.getMantenimientos.mockResolvedValue({
      sinDatos: true,
      motivo: 'Archivo de eventos no disponible en este entorno',
      eventos: [],
      meta: { scopeLabel: 'CUSIANA' },
    });

    const usuario = await abrir();
    await usuario.click(screen.getByText('Mantenimientos'));

    expect(
      await screen.findByText('Archivo de eventos no disponible en este entorno'),
    ).toBeDefined();
  });

  it('la pill de diferidas pinta el pareto', async () => {
    mocks.getDiferidas.mockResolvedValue({
      sinDatos: false,
      motivo: null,
      pareto: [{ grupo: 'Operacional', total: 30, pct: 60.0, anios: {} }],
      tendencia: [],
      pozosPorGrupo: [],
      impacto: {},
      meta: { scopeLabel: 'CUSIANA' },
    });

    const usuario = await abrir();
    await usuario.click(screen.getByText('Diferidas'));

    expect(
      await screen.findByRole('img', {
        name: 'Pareto de causas de producción diferida',
      }),
    ).toBeDefined();
  });

  it('la pill de EBITDA pinta el waterfall para crudo', async () => {
    mocks.getWaterfall.mockResolvedValue({
      components: [
        { key: 'ingresos', label: 'Ingresos', valueKusd: 1000, valueUsdBl: 20, type: 'total' },
        { key: 'util_neta', label: 'NOPAT', valueKusd: 300, valueUsdBl: 6, type: 'total' },
      ],
      totalBls: 500,
      meta: { year: 2026, month: 5, nivel: 'campo', entidad: 'CUSIANA' },
    });

    const usuario = await abrir();
    await usuario.click(screen.getByText('EBITDA-NOPAT'));

    expect(
      await screen.findByRole('img', {
        name: 'Waterfall económico de Ingresos a NOPAT',
      }),
    ).toBeDefined();
  });

  it('un foco sin faltante muestra sus extremos', async () => {
    const focoOk: Foco = {
      ...FOCO_GAP,
      esOk: true,
      estadoLabel: 'Alineado',
      titulo: '',
      causa: { texto: '', cobertura: 'ok', detalle: [], eventos: [] },
      accion: '',
      tipo: 'ok',
      extremos: [{ campo: 'CUSIANA', real: 900, meta: 800 }],
    };

    await abrir(focoOk);

    expect(screen.getByText('Real')).toBeDefined();
    expect(screen.getByText('900')).toBeDefined();
  });
});
