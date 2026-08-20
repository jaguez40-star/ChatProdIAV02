/**
 * La guarda de rol. Lo que más importa aquí es que falle CERRADO: ante la duda,
 * no dejar pasar.
 */

import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';

import { RutaAdmin } from './RutaAdmin';
import { useAuthStore } from '../../../app/store/authStore';
import type { AuthUser } from '../../../features/auth/types/authTypes';

function usuario(isAdmin: boolean): AuthUser {
  return {
    id: 1,
    username: 'test.user',
    email: 'test.user@ecopetrol.com.co',
    fullName: 'Usuario de Prueba',
    isAdmin,
  } as AuthUser;
}

function montar() {
  return render(
    <MemoryRouter initialEntries={['/test-clas']}>
      <Routes>
        <Route path="/" element={<p>inicio</p>} />
        <Route
          path="/test-clas"
          element={
            <RutaAdmin>
              <p>laboratorio</p>
            </RutaAdmin>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('RutaAdmin', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, permissions: null, isAuthenticated: false });
  });

  it('deja pasar a un administrador', () => {
    useAuthStore.setState({ user: usuario(true), isAuthenticated: true });

    montar();

    expect(screen.getByText('laboratorio')).toBeTruthy();
  });

  it('redirige a un usuario sin privilegios', () => {
    useAuthStore.setState({ user: usuario(false), isAuthenticated: true });

    montar();

    expect(screen.queryByText('laboratorio')).toBeNull();
    expect(screen.getByText('inicio')).toBeTruthy();
  });

  it('sin usuario, falla CERRADO', () => {
    // No debería ocurrir —el ProtectedRoute ancestro ya exige sesión— pero si
    // ocurriera, conceder acceso sería el peor error posible.
    montar();

    expect(screen.queryByText('laboratorio')).toBeNull();
  });
});
