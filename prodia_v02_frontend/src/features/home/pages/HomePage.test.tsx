import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import HomePage from './HomePage';

describe('HomePage', () => {
  it('monta los tres paneles: dos abiertos y uno colapsado', () => {
    render(<HomePage />);

    // Control y Análisis abiertos (ABIERTOS_INICIALES), Ingesta colapsada.
    expect(screen.getByRole('button', { name: 'Colapsar Control' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Colapsar Análisis' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Abrir Ingesta' })).toBeTruthy();
  });
});
