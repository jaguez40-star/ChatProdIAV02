import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';

import { Input } from './Input';

describe('Input', () => {
  it('renderiza el label asociado', () => {
    render(<Input label="Usuario" />);
    expect(screen.getByLabelText('Usuario')).toBeDefined();
  });

  it('muestra el error con role=alert', () => {
    render(<Input label="Usuario" error="Campo requerido" />);
    expect(screen.getByRole('alert').textContent).toBe('Campo requerido');
  });

  it('marca aria-invalid cuando hay error', () => {
    render(<Input label="Usuario" error="Campo requerido" />);
    expect(screen.getByLabelText('Usuario').getAttribute('aria-invalid')).toBe('true');
  });

  it('el hint no se muestra si hay error', () => {
    render(<Input label="Usuario" error="Campo requerido" hint="LDAP" />);
    expect(screen.queryByText('LDAP')).toBeNull();
  });

  it('acepta texto escrito por el usuario', async () => {
    render(<Input label="Usuario" />);
    const input = screen.getByLabelText('Usuario') as HTMLInputElement;
    await userEvent.type(input, 'javier.guerrero');
    expect(input.value).toBe('javier.guerrero');
  });
});
