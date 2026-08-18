import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { Spinner } from './Spinner';

describe('Spinner', () => {
  it('tiene role=status', () => {
    render(<Spinner />);
    expect(screen.getByRole('status')).toBeDefined();
  });

  it('usa el label como aria-label', () => {
    render(<Spinner label="Verificando sesión..." />);
    expect(screen.getByRole('status').getAttribute('aria-label')).toBe(
      'Verificando sesión...',
    );
  });

  it('label por defecto es "Cargando..."', () => {
    render(<Spinner />);
    expect(screen.getByRole('status').getAttribute('aria-label')).toBe('Cargando...');
  });
});
