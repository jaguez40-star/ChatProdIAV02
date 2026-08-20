import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SECCIONES } from '../secciones';
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

function montar(rutaInicial = '/', opciones?: { isAdmin?: boolean }) {
  if (opciones?.isAdmin === false) {
    useAuthStore
      .getState()
      .setSession({ ...USUARIO, isAdmin: false }, { campos: [], sections: [] });
  }
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

    // Ha pasado TRES veces: F2 creó /analisis, F3 creó /ingesta y F5 creó
    // /test-clas, y ninguna quedó enlazada — la página existía pero solo se
    // llegaba escribiendo la URL a mano.
    //
    // 🔑 La versión anterior de este test NO lo atrapó, y por eso ocurrió la
    // tercera vez: repetía las rutas en una constante local, así que verificaba
    // su propia lista en vez de la que monta la aplicación. Una ruta nueva
    // nunca lo rompía.
    //
    // Ahora las rutas se derivan de `secciones.ts`, la misma fuente que usan
    // el router y el header. Añadir una sección sin enlazarla rompe el build.
    const enlazadas = screen
      .getAllByRole('link')
      .map((a) => a.getAttribute('href'));

    // El usuario del fixture es admin, así que debe ver TODAS las secciones.
    for (const { ruta } of SECCIONES) {
      expect(enlazadas).toContain(ruta);
    }
  });

  it('oculta las secciones admin a un usuario normal (DT-3)', async () => {
    // 🔑 El backend ya decide de verdad (403). Esto solo evita ofrecer una
    // puerta cerrada: sin el filtro, un usuario sin permiso ve "Test Clas" y
    // al pulsarlo recibe un error, que se lee como una avería del sistema.
    montar('/', { isAdmin: false });
    await screen.findByRole('button', { name: 'Menú de usuario' });

    const enlazadas = screen
      .getAllByRole('link')
      .map((a) => a.getAttribute('href'));

    expect(enlazadas).not.toContain('/test-clas');
    // Las abiertas siguen visibles: filtrar no puede dejar sin navegación.
    expect(enlazadas).toContain('/');
    expect(enlazadas).toContain('/analisis');
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
