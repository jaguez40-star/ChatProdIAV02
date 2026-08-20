import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import ConsultaPage from './ConsultaPage';

describe('ConsultaPage', () => {
  it('monta los tres paneles: dos abiertos y uno colapsado', () => {
    render(<ConsultaPage />);

    // Historial y Chat abiertos (ABIERTOS_INICIALES), Insights colapsado.
    expect(screen.getByRole('button', { name: 'Colapsar Historial' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Colapsar Chat' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Abrir Insights' })).toBeTruthy();
  });
});
