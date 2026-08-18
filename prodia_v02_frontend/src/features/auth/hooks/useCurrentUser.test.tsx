import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '../../../app/store/authStore';
import { useCurrentUser } from './useCurrentUser';

vi.mock('../services/authService', () => ({
  getMe: vi.fn(),
}));

import { getMe } from '../services/authService';

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
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

describe('useCurrentUser', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().clearSession();
    localStorage.clear();
  });

  it('no hace fetch si no hay sesión ni localStorage', () => {
    const { result } = renderHook(() => useCurrentUser(), { wrapper });
    expect(result.current.isFetching).toBe(false);
  });

  it('con datos en localStorage, hace fetch y setSession', async () => {
    localStorage.setItem(
      'prodia_auth',
      JSON.stringify({ userId: 1, username: 'javier.guerrero', email: 'x', isAdmin: true }),
    );
    (getMe as ReturnType<typeof vi.fn>).mockResolvedValue(mockSession);

    const { result } = renderHook(() => useCurrentUser(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });

  it('getMe falla sin que el interceptor marque sessionExpired -> clearSession', async () => {
    localStorage.setItem(
      'prodia_auth',
      JSON.stringify({ userId: 1, username: 'javier.guerrero', email: 'x', isAdmin: true }),
    );
    (getMe as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('500'));

    const { result } = renderHook(() => useCurrentUser(), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().sessionExpired).toBe(false);
  });

  it('si el interceptor ya marcó sessionExpired, el catch no lo pisa con clearSession', async () => {
    localStorage.setItem(
      'prodia_auth',
      JSON.stringify({ userId: 1, username: 'javier.guerrero', email: 'x', isAdmin: true }),
    );
    (getMe as ReturnType<typeof vi.fn>).mockImplementation(async () => {
      // Simula lo que hace sessionInterceptor.onResponse antes de que el
      // error llegue aquí.
      useAuthStore.getState().markSessionExpired();
      throw new Error('401 expired');
    });

    const { result } = renderHook(() => useCurrentUser(), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(useAuthStore.getState().sessionExpired).toBe(true);
  });
});
