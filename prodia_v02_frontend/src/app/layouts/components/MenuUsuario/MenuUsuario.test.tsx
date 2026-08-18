import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { MenuUsuario } from './MenuUsuario';

function montar(props: Partial<Parameters<typeof MenuUsuario>[0]> = {}) {
  const onCerrar = vi.fn();
  const onLogout = vi.fn();
  render(
    <MemoryRouter>
      <MenuUsuario
        username="admin"
        fullName={null}
        email="admin@ecopetrol.com.co"
        isAdmin
        onCerrar={onCerrar}
        onLogout={onLogout}
        {...props}
      />
    </MemoryRouter>,
  );
  return { onCerrar, onLogout };
}

describe('MenuUsuario', () => {
  it('muestra el username cuando no hay fullName', () => {
    montar();
    expect(screen.getByText('admin')).toBeTruthy();
    expect(screen.getByText('admin@ecopetrol.com.co')).toBeTruthy();
  });

  it('prefiere el fullName sobre el username', () => {
    montar({ fullName: 'Javier Guerrero' });
    expect(screen.getByText('Javier Guerrero')).toBeTruthy();
  });

  it('un admin ve la insignia y el acceso Admin', () => {
    montar();
    expect(screen.getByText('ADMIN')).toBeTruthy();
    expect(screen.getByRole('menuitem', { name: 'Admin' })).toBeTruthy();
  });

  it('un no-admin no ve ni la insignia ni el acceso Admin', () => {
    montar({ isAdmin: false });
    expect(screen.queryByText('ADMIN')).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'Admin' })).toBeNull();
    // Los accesos comunes siguen presentes.
    expect(screen.getByRole('menuitem', { name: 'Configuración' })).toBeTruthy();
  });

  it('navegar por un acceso cierra el menú', async () => {
    const user = userEvent.setup();
    const { onCerrar } = montar();

    await user.click(screen.getByRole('menuitem', { name: 'Ayuda' }));
    expect(onCerrar).toHaveBeenCalledOnce();
  });

  it('cerrar sesión delega en onLogout', async () => {
    const user = userEvent.setup();
    const { onLogout } = montar();

    await user.click(screen.getByRole('menuitem', { name: 'Cerrar sesión' }));
    expect(onLogout).toHaveBeenCalledOnce();
  });

});
