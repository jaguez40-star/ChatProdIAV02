import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Ejecutivo } from '../../types/analisisTypes';
import { PanelEjecutivo } from './PanelEjecutivo';

const mocks = vi.hoisted(() => ({
  getEjecutivo: vi.fn(),
  getDiferidas: vi.fn(),
  getMantenimientos: vi.fn(),
  getWaterfall: vi.fn(),
}));

vi.mock('../../services/analisisService', () => ({
  getEjecutivo: mocks.getEjecutivo,
  getDiferidas: mocks.getDiferidas,
  getMantenimientos: mocks.getMantenimientos,
  getWaterfall: mocks.getWaterfall,
  getCatalogo: vi.fn(),
  getDensidad: vi.fn(),
  getHuella: vi.fn(),
  getCobertura: vi.fn(),
  getDesempeno: vi.fn(),
  getPresident: vi.fn(),
  getTendenciaFilial: vi.fn(),
}));

function envolver(nodo: ReactNode) {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={cliente}>{nodo}</QueryClientProvider>;
}

const BASE: Ejecutivo = {
  entidad: 'CASTILLA',
  encontrada: true,
  sinDatos: false,
  meta: {
    scope: 'CASTILLA',
    periodo: 'Mayo 2026',
    corte: '17/31',
    generadoPor: 'fallback',
  },
  titular: [],
  tarjetas: [
    {
      producto: 'CRUDO',
      unidad: 'bbl',
      metaMes: 1000,
      proyectadoCierre: 1080,
      brechaAbs: -80,
      rellenoPct: 100,
      alcanza: true,
      estado: 'alineado',
      metaDePromedio: false,
      bopd: { real: 60, requerido: 55, deltaPct: -8.3 },
      histProm: 950,
    },
    {
      producto: 'GAS',
      unidad: 'MSCF',
      metaMes: 0,
      proyectadoCierre: 500,
      brechaAbs: 0,
      rellenoPct: 0,
      alcanza: false,
      estado: '',
      metaDePromedio: false,
      bopd: null,
      histProm: null,
    },
  ],
  valle: null,
  pace: null,
  secciones: {
    insights: ['Cierre de Mayo 2026: Crudo 108%'],
    oportunidades: ['Sostener el ritmo'],
    puntosAtencion: ['Sin puntos críticos'],
    decisiones: ['Monitorear'],
  },
  focos: [
    {
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
        eventos: [],
      },
      accion: 'plan de recuperación específico',
      tipo: 'gap',
      rank: 1,
    },
  ],
  sinFoco: 'con excedentes: PAUTO SUR en gas (+100)',
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getEjecutivo.mockResolvedValue(BASE);
});

describe('PanelEjecutivo', () => {
  it('muestra las 4 secciones ejecutivas', async () => {
    render(envolver(<PanelEjecutivo ambito={{ entidad: 'CASTILLA' }} />));

    expect(await screen.findByText('Hallazgos')).toBeDefined();
    expect(screen.getByText('Oportunidades')).toBeDefined();
    expect(screen.getByText('Puntos de atención')).toBeDefined();
    expect(screen.getByText('Decisiones')).toBeDefined();
  });

  it('un producto sin meta muestra "Sin meta definida", no un 0 %', async () => {
    render(envolver(<PanelEjecutivo ambito={{ entidad: 'CASTILLA' }} />));

    expect(await screen.findByText('Sin meta definida')).toBeDefined();
  });

  it('el ritmo diario solo aparece si la curva reconcilia', async () => {
    render(envolver(<PanelEjecutivo ambito={{ entidad: 'CASTILLA' }} />));

    // CRUDO trae bopd; GAS no, y no debe inventarse una tasa.
    expect(await screen.findByText(/Ritmo/)).toBeDefined();
    expect(screen.getAllByText(/Ritmo/)).toHaveLength(1);
  });

  it('no marca la prosa como asistida cuando la compuso Python', async () => {
    render(envolver(<PanelEjecutivo ambito={{ entidad: 'CASTILLA' }} />));
    await screen.findByText('Hallazgos');

    expect(screen.queryByText('prosa asistida')).toBeNull();
  });

  it('declara cuando la prosa la pulió el modelo', async () => {
    mocks.getEjecutivo.mockResolvedValue({
      ...BASE,
      meta: { ...BASE.meta, generadoPor: 'llm' },
    });
    render(envolver(<PanelEjecutivo ambito={{ entidad: 'CASTILLA' }} />));

    expect(await screen.findByText('prosa asistida')).toBeDefined();
  });

  it('el foco se despliega y carga sus pills solo al abrirlo', async () => {
    const usuario = userEvent.setup();
    mocks.getDiferidas.mockResolvedValue({
      sinDatos: true,
      motivo: 'Sin diferidas',
      pareto: [],
      tendencia: [],
      pozosPorGrupo: [],
      impacto: {},
      meta: { scopeLabel: 'CUSIANA' },
    });

    render(envolver(<PanelEjecutivo ambito={{ entidad: 'CASTILLA' }} />));
    await screen.findByText('Hallazgos');

    // Cerrado: ninguna pill ha consultado todavía (carga perezosa).
    expect(mocks.getDiferidas).not.toHaveBeenCalled();

    await usuario.click(screen.getByText('CUSIANA'));
    expect(await screen.findByText('Diferidas')).toBeDefined();

    // Abierto pero en "Comportamiento": sigue sin pedir diferidas.
    expect(mocks.getDiferidas).not.toHaveBeenCalled();

    await usuario.click(screen.getByText('Diferidas'));
    expect(await screen.findByText('Sin diferidas')).toBeDefined();
    expect(mocks.getDiferidas).toHaveBeenCalledTimes(1);
  });

  it('el EBITDA se declara no aplicable fuera de crudo', async () => {
    const usuario = userEvent.setup();
    mocks.getEjecutivo.mockResolvedValue({
      ...BASE,
      focos: [{ ...BASE.focos[0], producto: 'GAS', entidades: ['CUSIANA'] }],
    });

    render(envolver(<PanelEjecutivo ambito={{ entidad: 'CASTILLA' }} />));
    await screen.findByText('Hallazgos');

    await usuario.click(screen.getByText('CUSIANA'));
    await usuario.click(screen.getByText('EBITDA-NOPAT'));

    expect(await screen.findByText('El EBITDA-NOPAT solo aplica a crudo.')).toBeDefined();
    expect(mocks.getWaterfall).not.toHaveBeenCalled();
  });

  it('avisa cuando no hay análisis para el ámbito', async () => {
    mocks.getEjecutivo.mockResolvedValue({ ...BASE, encontrada: false });
    render(envolver(<PanelEjecutivo ambito={{ entidad: 'NO EXISTE' }} />));

    expect(await screen.findByText(/Sin análisis disponible/)).toBeDefined();
  });
});
