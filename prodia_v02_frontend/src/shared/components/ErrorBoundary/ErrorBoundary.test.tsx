import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ErrorBoundary } from './ErrorBoundary';

function Bomb(): never {
  throw new Error('boom');
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    // React y nuestro componentDidCatch loguean a console.error — se
    // silencia para no ensuciar la salida del test, es ruido esperado.
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sin error, renderiza los children normalmente', () => {
    render(
      <ErrorBoundary>
        <div>Todo bien</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText('Todo bien')).toBeDefined();
  });

  it('con un error en un descendiente, muestra el fallback', () => {
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toBeDefined();
    expect(screen.getByText('Error inesperado')).toBeDefined();
  });
});
