import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { AcordeonHorizontal } from './AcordeonHorizontal';

describe('AcordeonHorizontal', () => {
  it('arranca con Control y Análisis abiertos, Ingesta colapsada', () => {
    render(<AcordeonHorizontal />);

    expect(
      screen.getByRole('button', { name: 'Colapsar Control' }).getAttribute('aria-expanded'),
    ).toBe('true');
    expect(
      screen.getByRole('button', { name: 'Abrir Ingesta' }).getAttribute('aria-expanded'),
    ).toBe('false');
  });

  it('al expandir un tercero, colapsa el más antiguo (máximo 2 abiertos)', async () => {
    const user = userEvent.setup();
    render(<AcordeonHorizontal />);

    await user.click(screen.getByRole('button', { name: 'Abrir Ingesta' }));

    // Ingesta entra; Control, el más antiguo de los abiertos, sale.
    expect(screen.getByRole('button', { name: 'Colapsar Ingesta' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Abrir Control' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Colapsar Análisis' })).toBeTruthy();
  });

  it('nunca deja cero paneles abiertos: el último queda deshabilitado', async () => {
    const user = userEvent.setup();
    render(<AcordeonHorizontal />);

    await user.click(screen.getByRole('button', { name: 'Colapsar Control' }));

    const ultimo = screen.getByRole('button', { name: 'Colapsar Análisis' }) as HTMLButtonElement;
    expect(ultimo.disabled).toBe(true);
    expect(ultimo.getAttribute('title')).toBe('Debe quedar al menos un panel abierto');

    // Y el clic sobre él no cambia nada.
    await user.click(ultimo);
    expect(screen.getByRole('button', { name: 'Colapsar Análisis' })).toBeTruthy();
  });
});
