import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { Card } from './Card';

describe('Card', () => {
  it('renderiza children', () => {
    render(<Card>Contenido</Card>);
    expect(screen.getByText('Contenido')).toBeDefined();
  });

  it('pasa atributos HTML adicionales', () => {
    render(<Card data-testid="mi-card">X</Card>);
    expect(screen.getByTestId('mi-card')).toBeDefined();
  });
});
