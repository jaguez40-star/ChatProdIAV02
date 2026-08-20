import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { useChatStore } from '../../store/chatStore';
import type { Panel } from '../../types/consultaTypes';
import { PilaResultados } from './PilaResultados';

const PANEL_KPI: Panel = {
  tipo: 'cuant_kpi',
  datos: {
    entidadCualificada: 'el Campo CASTILLA',
    producto: 'crudo',
    unidad: 'bbl',
    real: 1_000_000,
    referenciaValor: 1_056_000,
    referenciaLabel: 'presupuesto',
    cumplimientoPct: 94.7,
    estado: 'Alineado',
    mes: {
      nombre: 'Mayo',
      anio: 2026,
      completo: false,
      diasConData: 17,
      diasDelMes: 31,
    },
    avisos: [],
  },
};

beforeEach(() => {
  useChatStore.getState().limpiar();
});

function apilar(panel: Panel, pregunta = '¿cuánto produjo Castilla?') {
  const store = useChatStore.getState();
  store.enviar(pregunta);
  store.responder('Ahí va.', panel, 1, pregunta);
}

describe('PilaResultados', () => {
  it('sin resultados explica qué aparecerá aquí', () => {
    render(<PilaResultados />);
    expect(screen.getByText(/aparecerán aquí/)).toBeDefined();
  });

  it('apila un bloque con su turno, pregunta y hora', () => {
    apilar(PANEL_KPI);
    render(<PilaResultados />);

    expect(screen.getByText('¿cuánto produjo Castilla?')).toBeDefined();
    expect(screen.getByText('el Campo CASTILLA')).toBeDefined();
    // Un mes incompleto se declara como proyección con sus días.
    expect(screen.getByText(/17\/31 días/)).toBeDefined();
  });

  it('declara que el mes no está cerrado en vez de darlo por cierre', () => {
    apilar(PANEL_KPI);
    render(<PilaResultados />);
    expect(screen.getByText(/proyección/)).toBeDefined();
  });

  it('sin meta NO muestra un 0 %', () => {
    // 🔑 Q2 en la vista: `null` significa "no hay meta". Pintarlo como 0 %
    // inventaría un incumplimiento.
    apilar({
      ...PANEL_KPI,
      datos: { ...PANEL_KPI.datos, cumplimientoPct: null },
    } as Panel);
    render(<PilaResultados />);

    expect(screen.getByText(/Sin meta definida/)).toBeDefined();
    expect(screen.queryByText(/0,0%/)).toBeNull();
  });

  it('un panel de tipo desconocido avisa, no pinta una tarjeta falsa', () => {
    // 🔑 Q5. En el sistema viejo un tipo no registrado caía a un fallback sin
    // validar y pintaba campos ajenos —anillo al 0 %, título vacío— sin ningún
    // error visible. Aquí el usuario ve qué pasó.
    apilar({ tipo: 'inventado', datos: {} } as unknown as Panel);
    render(<PilaResultados />);

    expect(screen.getByRole('alert')).toBeDefined();
    expect(screen.getByText(/no sabe pintar/)).toBeDefined();
  });

  it('permite colapsar y expandir un bloque', async () => {
    const usuario = userEvent.setup();
    apilar(PANEL_KPI);
    render(<PilaResultados />);

    await usuario.click(screen.getByRole('button', { name: /Colapsar el resultado/ }));
    expect(screen.queryByText('el Campo CASTILLA')).toBeNull();

    await usuario.click(screen.getByRole('button', { name: /Expandir el resultado/ }));
    expect(screen.getByText('el Campo CASTILLA')).toBeDefined();
  });

  it('permite cerrar un bloque', async () => {
    const usuario = userEvent.setup();
    apilar(PANEL_KPI);
    render(<PilaResultados />);

    await usuario.click(screen.getByRole('button', { name: /Cerrar el resultado/ }));
    expect(screen.getByText(/aparecerán aquí/)).toBeDefined();
  });

  it('el ranking rotula los terceros y declara los que no tienen registro', () => {
    apilar({
      tipo: 'cuant_rank',
      datos: {
        nivelRanking: 'campo',
        metrica: 'real',
        direccion: 'top',
        producto: 'crudo',
        unidad: 'bbl',
        periodoLabel: 'Mayo 2026',
        esProyeccion: false,
        items: [
          {
            pos: 1,
            entidad: 'QUIFA',
            valor: 600,
            gap: 100,
            ppto: 500,
            operador: 'FRONTERA',
            esEcp: false,
          },
        ],
        totalUniverso: 10,
        sinRegistro: 3,
        concentracionPct: 45.5,
      },
    });
    render(<PilaResultados />);

    // Los terceros se incluyen y se nombran: ocultarlos daría un ranking falso.
    expect(screen.getByText(/FRONTERA/)).toBeDefined();
    // D4: los ceros se declaran aparte, no cuentan como "poca producción".
    expect(screen.getByText(/3 sin registro/)).toBeDefined();
  });
});
