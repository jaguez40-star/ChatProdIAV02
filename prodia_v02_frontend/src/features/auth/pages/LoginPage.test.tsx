import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '../../../app/store/authStore';
import { ApiError } from '../../../shared/services/apiClient';

const mutateMock = vi.fn();
let mutationState: { isPending: boolean } = { isPending: false };

vi.mock('../hooks/useLogin', () => ({
  useLogin: () => ({ mutate: mutateMock, isPending: mutationState.isPending }),
}));

import LoginPage from './LoginPage';

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <LoginPage />
    </MemoryRouter>,
  );
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mutationState = { isPending: false };
    useAuthStore.getState().clearSession();
  });

  it('renderiza el formulario con los campos esperados', () => {
    renderPage();
    expect(screen.getByLabelText(/Usuario de red/)).toBeDefined();
    expect(screen.getByLabelText(/Contraseña/)).toBeDefined();
    expect(screen.getByRole('button', { name: /Iniciar sesión/ })).toBeDefined();
  });

  it('valida campos vacíos sin llamar a mutate', async () => {
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: /Iniciar sesión/ }));
    expect(await screen.findByText('Ingresa tu usuario de red')).toBeDefined();
    expect(mutateMock).not.toHaveBeenCalled();
  });

  it('con campos completos, llama a mutate con las credenciales', async () => {
    renderPage();
    await userEvent.type(screen.getByLabelText(/Usuario de red/), 'javier.guerrero');
    await userEvent.type(screen.getByLabelText(/Contraseña/), 'clave123');
    await userEvent.click(screen.getByRole('button', { name: /Iniciar sesión/ }));

    expect(mutateMock).toHaveBeenCalledWith(
      { username: 'javier.guerrero', password: 'clave123' },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    );
  });

  it('el ojo alterna el tipo de campo entre password y text', async () => {
    renderPage();
    const passwordInput = screen.getByLabelText(/Contraseña/) as HTMLInputElement;
    expect(passwordInput.type).toBe('password');
    await userEvent.click(screen.getByRole('button', { name: 'Mostrar contraseña' }));
    expect(passwordInput.type).toBe('text');
  });

  it('onError de la mutación muestra el toast con el correlationId', async () => {
    renderPage();
    await userEvent.type(screen.getByLabelText(/Usuario de red/), 'u');
    await userEvent.type(screen.getByLabelText(/Contraseña/), 'p');
    await userEvent.click(screen.getByRole('button', { name: /Iniciar sesión/ }));

    const { onError } = mutateMock.mock.calls[0][1] as {
      onError: (e: ApiError) => void;
    };
    onError(new ApiError({ status: 401, detail: 'Credenciales inválidas', correlation_id: 'abc-1' }));

    expect(await screen.findByText(/Credenciales inválidas \(ref\. abc-1\)/)).toBeDefined();
  });

  it('ya autenticado -> redirige (no muestra el formulario)', () => {
    useAuthStore.setState({ isAuthenticated: true });
    renderPage();
    expect(screen.queryByRole('button', { name: /Iniciar sesión/ })).toBeNull();
  });
});
