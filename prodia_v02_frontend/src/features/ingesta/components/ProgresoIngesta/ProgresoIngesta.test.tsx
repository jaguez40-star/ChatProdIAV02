/**
 * Tests del panel de progreso.
 *
 * El comportamiento que más importa: mientras la ingesta corre, la interfaz **no debe
 * afirmar que los datos están guardados**, y cuando se revierte debe decirlo con
 * claridad aunque el usuario haya visto hojas en verde (G2).
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { HojaEnProgreso, ResultadoIngesta } from '../../types/ingestaTypes';
import { ProgresoIngesta } from './ProgresoIngesta';

const HOJAS: HojaEnProgreso[] = [
  {
    hoja: 'INICIO',
    estado: 'procesada',
    destino: 'core.fact_tabla_hoja',
    filas: 80,
    tablas: [],
    detalle: null,
  },
  {
    hoja: 'PROGRAMA',
    estado: 'procesando',
    destino: null,
    filas: null,
    tablas: [],
    detalle: null,
  },
];

const RESULTADO: ResultadoIngesta = {
  archivo: '20260815_r.xlsm',
  reporteId: 1042,
  fechaReporte: '2026-08-15',
  tipoArchivo: 'NEW',
  tieneRaw: true,
  filasPorDestino: { 'core.fact_tabla_hoja': 1646 },
  hojas: [],
  tablasVacias: [],
};

function renderizar(props: Partial<Parameters<typeof ProgresoIngesta>[0]> = {}) {
  return render(
    <ProgresoIngesta
      fase="procesando"
      hojas={[]}
      totalHojas={0}
      resultado={null}
      error={null}
      hojaDelError={null}
      onReiniciar={vi.fn()}
      {...props}
    />,
  );
}

describe('mientras procesa', () => {
  it('avisa de que los datos aún no están guardados', () => {
    renderizar({ hojas: HOJAS, totalHojas: 5 });

    expect(screen.getByText(/no están guardados/i)).toBeTruthy();
  });

  it('muestra el avance sobre el total de hojas', () => {
    renderizar({ hojas: HOJAS, totalHojas: 5 });

    expect(screen.getByText(/1 de 5 hojas/i)).toBeTruthy();
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('20');
  });

  it('lista cada hoja con su estado', () => {
    renderizar({ hojas: HOJAS, totalHojas: 2 });

    expect(screen.getByText('INICIO')).toBeTruthy();
    expect(screen.getByText('Procesada')).toBeTruthy();
    expect(screen.getByText('Procesando')).toBeTruthy();
  });

  it('nunca dice "guardado" antes de terminar', () => {
    renderizar({ hojas: HOJAS, totalHojas: 2 });

    expect(screen.queryByText(/ingesta confirmada/i)).not.toBeTruthy();
  });
});

describe('cuando la ingesta se confirma', () => {
  it('afirma que quedó guardada y muestra el reporte', () => {
    renderizar({ fase: 'confirmada', resultado: RESULTADO });

    expect(screen.getByText(/ingesta confirmada/i)).toBeTruthy();
    expect(screen.getByText('#1042')).toBeTruthy();
    expect(screen.getByText('2026-08-15')).toBeTruthy();
  });

  it('destaca las tablas que salieron sin filas', () => {
    // Es la señal de que el diseño de una hoja pudo cambiar (G5).
    renderizar({
      fase: 'confirmada',
      resultado: { ...RESULTADO, tablasVacias: ['REPORTE_PRESIDENT → Tabla 1'] },
    });

    expect(screen.getByText(/1 tabla sin filas/i)).toBeTruthy();
    expect(screen.getByText('REPORTE_PRESIDENT → Tabla 1')).toBeTruthy();
  });

  it('no menciona tablas vacías cuando no las hay', () => {
    renderizar({ fase: 'confirmada', resultado: RESULTADO });

    expect(screen.queryByText(/sin filas/i)).not.toBeTruthy();
  });
});

describe('cuando la ingesta se revierte', () => {
  it('deja claro que no se guardó nada', () => {
    renderizar({
      fase: 'revertida',
      hojas: HOJAS,
      error: 'La hoja 30 cambió de formato.',
    });

    expect(screen.getByText(/no se guardó ningún dato/i)).toBeTruthy();
    expect(screen.getByText(/la base de datos quedó tal y como estaba/i)).toBeTruthy();
  });

  it('indica en qué hoja falló', () => {
    renderizar({ fase: 'revertida', error: 'x', hojaDelError: 'PROGRAMA' });

    expect(screen.getByText('PROGRAMA')).toBeTruthy();
  });

  it('no muestra el resumen de éxito', () => {
    renderizar({ fase: 'revertida', error: 'x' });

    expect(screen.queryByText(/ingesta confirmada/i)).not.toBeTruthy();
  });
});
