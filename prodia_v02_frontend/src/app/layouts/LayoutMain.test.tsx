import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '../store/authStore';
import { LayoutMain } from './LayoutMain';

vi.mock('../../features/auth/services/authService', () => ({
  logout: vi.fn(),
  getCurrentUser: vi.fn(),
  // useInactivityLogout lo consulta al montar; sin él la query real saldría a
  // la red y el layout no llegaría a renderizar.
  getSessionTimeoutMinutes: vi.fn().mockResolvedValue(30),
}));

const USUARIO = {
  id: 1,
  username: 'admin',
  email: 'admin@ecopetrol.com.co',
  fullName: null,
  isAdmin: true,
  isActive: true,
  group: null,
  lastLoginAt: null,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
};

function montar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LayoutMain />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('LayoutMain', () => {
  beforeEach(() => {
    useAuthStore.getState().setSession(USUARIO, { campos: [], sections: [] });
  });

  afterEach(() => {
    useAuthStore.getState().clearSession();
  });

  it('el header muestra la inicial del usuario y arranca con el menú cerrado', async () => {
    montar();
    // findBy* espera a que la query de timeout resuelva: sin ello el update
    // posterior cae fuera de act() y ensucia la salida de todo el archivo.
    const avatar = await screen.findByRole('button', { name: 'Menú de usuario' });
    expect(avatar.textContent).toBe('A');
    expect(avatar.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('el clic en el avatar abre el menú, y repetirlo lo cierra', async () => {
    const user = userEvent.setup();
    montar();
    const avatar = await screen.findByRole('button', { name: 'Menú de usuario' });

    await user.click(avatar);
    expect(screen.getByRole('menu')).toBeTruthy();
    expect(avatar.getAttribute('aria-expanded')).toBe('true');

    await user.click(avatar);
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('Escape cierra el menú abierto', async () => {
    const user = userEvent.setup();
    montar();

    await user.click(await screen.findByRole('button', { name: 'Menú de usuario' }));
    expect(screen.getByRole('menu')).toBeTruthy();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('un clic fuera del header cierra el menú', async () => {
    const user = userEvent.setup();
    montar();

    await user.click(await screen.findByRole('button', { name: 'Menú de usuario' }));
    expect(screen.getByRole('menu')).toBeTruthy();

    await user.click(screen.getByRole('contentinfo'));
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('sin usuario en el store, el menú no se monta aunque se pulse el avatar', async () => {
    const user = userEvent.setup();
    useAuthStore.getState().clearSession();
    montar();

    await user.click(await screen.findByRole('button', { name: 'Menú de usuario' }));
    expect(screen.queryByRole('menu')).toBeNull();
  });
});
