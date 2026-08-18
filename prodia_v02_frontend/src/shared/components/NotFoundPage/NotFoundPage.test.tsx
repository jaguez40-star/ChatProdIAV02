import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import NotFoundPage from './NotFoundPage';

describe('NotFoundPage', () => {
  it('muestra 404 y un enlace de vuelta al inicio', () => {
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>,
    );
    expect(screen.getByText('404')).toBeDefined();
    expect(screen.getByRole('link', { name: 'Volver al inicio' })).toBeDefined();
  });
});
