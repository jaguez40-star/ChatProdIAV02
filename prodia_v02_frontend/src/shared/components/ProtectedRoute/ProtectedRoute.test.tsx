import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { useAuthStore } from '../../../app/store/authStore';
import { ProtectedRoute } from './ProtectedRoute';

function renderWithRouter() {
  return render(
    <MemoryRouter initialEntries={['/privado']}>
      <Routes>
        <Route path="/login" element={<div>Página de login</div>} />
        <Route
          path="/privado"
          element={
            <ProtectedRoute>
              <div>Contenido privado</div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    useAuthStore.getState().clearSession();
    useAuthStore.setState({ isHydrated: false });
  });

  it('sin hidratar -> muestra spinner de verificación, no el contenido', () => {
    renderWithRouter();
    expect(screen.getByRole('status').getAttribute('aria-label')).toBe(
      'Verificando sesión...',
    );
    expect(screen.queryByText('Contenido privado')).toBeNull();
  });

  it('hidratado pero no autenticado -> redirige a /login', () => {
    useAuthStore.setState({ isHydrated: true, isAuthenticated: false });
    renderWithRouter();
    expect(screen.getByText('Página de login')).toBeDefined();
    expect(screen.queryByText('Contenido privado')).toBeNull();
  });

  it('hidratado y autenticado -> muestra el contenido', () => {
    useAuthStore.setState({ isHydrated: true, isAuthenticated: true });
    renderWithRouter();
    expect(screen.getByText('Contenido privado')).toBeDefined();
  });
});
