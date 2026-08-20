/** Los KPIs del ciclo — y el aviso de la regla A4. */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ResumenLibreta } from './ResumenLibreta';
import type { ResumenLibreta as Resumen } from '../../types/testClasTypes';

function resumen(extra: Partial<Resumen> = {}): Resumen {
  return {
    total: 100,
    porVeredicto: { pendiente: 10, sospecha: 5, confirmado_revision: 85 },
    pctCapa1: 70,
    ...extra,
  };
}

describe('ResumenLibreta', () => {
  it('muestra el total de clasificaciones', () => {
    render(<ResumenLibreta resumen={resumen()} />);

    expect(screen.getByText('100')).toBeTruthy();
  });

  it('cuenta las sospechas como SIN VEREDICTO', () => {
    // Una sospecha es una bandera de prioridad, no un juicio: la fila sigue sin
    // juzgar y tiene que aparecer en el contador de trabajo pendiente.
    render(<ResumenLibreta resumen={resumen()} />);

    expect(screen.getByText('15')).toBeTruthy(); // 10 pendientes + 5 sospechas
  });

  it('avisa cuando la Capa 1 resuelve menos de la mitad (regla A4)', () => {
    render(<ResumenLibreta resumen={resumen({ pctCapa1: 40 })} />);

    expect(screen.getByText('40%')).toBeTruthy();
    expect(screen.getByText(/engordar patrones/)).toBeTruthy();
  });

  it('no avisa cuando la Capa 1 va holgada', () => {
    render(<ResumenLibreta resumen={resumen({ pctCapa1: 70 })} />);

    expect(screen.queryByText(/engordar patrones/)).toBeNull();
  });

  it('una libreta vacía muestra un guion, no un 0 %', () => {
    // Un 0 % afirmaría que la regex no resuelve nada; «—» dice que aún no hay
    // datos, que es una conclusión muy distinta.
    render(
      <ResumenLibreta resumen={resumen({ total: 0, porVeredicto: {}, pctCapa1: null })} />,
    );

    expect(screen.getByText('—')).toBeTruthy();
    expect(screen.queryByText(/engordar patrones/)).toBeNull();
  });
});
