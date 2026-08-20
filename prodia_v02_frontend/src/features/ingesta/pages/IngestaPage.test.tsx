/**
 * Tests de la página de Ingesta.
 *
 * Verifican que se muestre **un solo momento del flujo a la vez**: durante una carga de
 * varios minutos, lo único que le importa al usuario es el progreso, no volver a ver la
 * zona de subida.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import * as hook from '../hooks/useIngesta';
import type { FaseIngesta } from '../types/ingestaTypes';
import IngestaPage from './IngestaPage';

type EstadoDelHook = ReturnType<typeof hook.useIngesta>['estado'];

const BASE: EstadoDelHook = {
  fase: 'inactiva',
  archivo: null,
  subida: null,
  existente: null,
  hojas: [],
  totalHojas: 0,
  resultado: null,
  error: null,
  codigoError: null,
  hojaDelError: null,
};

function conEstado(parcial: Partial<EstadoDelHook>) {
  vi.spyOn(hook, 'useIngesta').mockReturnValue({
    estado: { ...BASE, ...parcial } as EstadoDelHook,
    seleccionarArchivo: vi.fn(),
    procesar: vi.fn(),
    reiniciar: vi.fn(),
  });
  render(<IngestaPage />);
}

const SUBIDA = {
  id: 'sub-1',
  archivo: '20260815_r.xlsm',
  hash: 'h',
  fechaReporte: '2026-08-15',
};

describe('IngestaPage', () => {
  it('explica que la carga es todo o nada', () => {
    conEstado({});

    expect(screen.getByText(/no se procesa/i)).toBeTruthy();
  });

  it('muestra la zona de subida al empezar', () => {
    conEstado({});

    expect(screen.getByLabelText('Archivo de reporte')).toBeTruthy();
  });

  it('avisa mientras sube el archivo', () => {
    conEstado({ fase: 'subiendo', archivo: new File(['x'], 'r.xlsm') });

    expect(screen.getByRole('status').textContent).toMatch(/subiendo/i);
  });

  it('pide confirmación antes de procesar', () => {
    conEstado({ fase: 'confirmando', subida: SUBIDA });

    expect(screen.getByRole('button', { name: 'Procesar' })).toBeTruthy();
    // Ya no se ofrece elegir otro archivo: el flujo avanzó.
    expect(screen.queryByLabelText('Archivo de reporte')).toBeNull();
  });

  it('sustituye todo por el progreso mientras procesa', () => {
    conEstado({ fase: 'procesando', subida: SUBIDA, totalHojas: 3 });

    expect(screen.getByRole('progressbar')).toBeTruthy();
    expect(screen.queryByLabelText('Archivo de reporte')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Procesar' })).toBeNull();
  });

  it.each<FaseIngesta>(['confirmada', 'revertida'])(
    'muestra el resumen cuando la fase es %s',
    (fase) => {
      conEstado({
        fase,
        subida: SUBIDA,
        error: fase === 'revertida' ? 'algo falló' : null,
        resultado:
          fase === 'confirmada'
            ? {
                archivo: 'r.xlsm',
                reporteId: 1,
                fechaReporte: '2026-08-15',
                tipoArchivo: 'STD',
                tieneRaw: false,
                filasPorDestino: {},
                hojas: [],
                tablasVacias: [],
              }
            : null,
      });

      expect(screen.queryByLabelText('Archivo de reporte')).toBeNull();
    },
  );
});
