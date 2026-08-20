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

function montar(rutaInicial = '/') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[rutaInicial]}>
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

  it('el header ofrece las secciones navegables', async () => {
    montar();
    await screen.findByRole('button', { name: 'Menú de usuario' });

    const nav = screen.getByRole('navigation', { name: 'Secciones' });
    expect(nav).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Consulta' }).getAttribute('href')).toBe('/');
    expect(screen.getByRole('link', { name: 'Análisis' }).getAttribute('href')).toBe(
      '/analisis',
    );
    expect(screen.getByRole('link', { name: 'Ingesta' }).getAttribute('href')).toBe(
      '/ingesta',
    );
  });

  it('toda ruta de sección del router tiene su enlace en el header', async () => {
    montar();
    await screen.findByRole('button', { name: 'Menú de usuario' });

    // Ha pasado DOS veces: F2 creó /analisis y F3 creó /ingesta, y ninguna
    // quedó enlazada — la página existía pero solo se llegaba escribiendo la
    // URL a mano. Este test convierte ese descuido en un fallo de build.
    const RUTAS_DE_SECCION = ['/', '/analisis', '/ingesta'];
    const enlazadas = screen
      .getAllByRole('link')
      .map((a) => a.getAttribute('href'));

    for (const ruta of RUTAS_DE_SECCION) {
      expect(enlazadas).toContain(ruta);
    }
  });

  it('marca como activa la sección de la ruta actual', async () => {
    montar('/analisis');
    await screen.findByRole('button', { name: 'Menú de usuario' });

    // `aria-current` lo pone NavLink al estar activo: es la única señal que
    // se puede afirmar sin depender de los nombres de clase de CSS Modules.
    expect(
      screen.getByRole('link', { name: 'Análisis' }).getAttribute('aria-current'),
    ).toBe('page');
    // El `end` de la raíz: sin él '/' quedaría activa también aquí, porque
    // toda ruta empieza por '/'.
    expect(
      screen.getByRole('link', { name: 'Consulta' }).getAttribute('aria-current'),
    ).toBeNull();
  });

  it('sin usuario en el store, el menú no se monta aunque se pulse el avatar', async () => {
    const user = userEvent.setup();
    useAuthStore.getState().clearSession();
    montar();

    await user.click(await screen.findByRole('button', { name: 'Menú de usuario' }));
    expect(screen.queryByRole('menu')).toBeNull();
  });
});
