import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '../../../app/store/authStore';
import { useLogin } from './useLogin';

vi.mock('../services/authService', () => ({
  login: vi.fn(),
  getMe: vi.fn(),
}));

import { getMe, login } from '../services/authService';

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

const mockSession = {
  user: {
    id: 1,
    username: 'javier.guerrero',
    email: 'javier.guerrero@ecopetrol.com.co',
    fullName: null,
    isAdmin: true,
    isActive: true,
    group: null,
    lastLoginAt: null,
    createdAt: '2026-08-18T00:00:00Z',
    updatedAt: '2026-08-18T00:00:00Z',
  },
  permissions: { campos: [], sections: [] },
};

describe('useLogin', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().clearSession();
  });

  it('login exitoso: encadena login()+getMe() y setSession()', async () => {
    (login as ReturnType<typeof vi.fn>).mockResolvedValue({
      accessToken: 'tok',
      tokenType: 'bearer',
    });
    (getMe as ReturnType<typeof vi.fn>).mockResolvedValue(mockSession);

    const { result } = renderHook(() => useLogin(), { wrapper });
    result.current.mutate({ username: 'javier.guerrero', password: 'x' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(login).toHaveBeenCalledWith({ username: 'javier.guerrero', password: 'x' });
    expect(getMe).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().user?.username).toBe('javier.guerrero');
  });

  it('login falla: no llama getMe ni setSession', async () => {
    (login as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Credenciales inválidas'));

    const { result } = renderHook(() => useLogin(), { wrapper });
    result.current.mutate({ username: 'x', password: 'mala' });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(getMe).not.toHaveBeenCalled();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});
