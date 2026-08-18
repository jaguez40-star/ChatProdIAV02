import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '../../../app/store/authStore';
import { useLogout } from './useLogout';

vi.mock('../services/authService', () => ({
  logout: vi.fn(),
}));

import { logout } from '../services/authService';

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe('useLogout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().setSession(
      {
        id: 1,
        username: 'x',
        email: 'x@ecopetrol.com.co',
        fullName: null,
        isAdmin: false,
        isActive: true,
        group: null,
        lastLoginAt: null,
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
      },
      { campos: [], sections: [] },
    );
  });

  it('logout exitoso: limpia la sesión local', async () => {
    (logout as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    const { result } = renderHook(() => useLogout(), { wrapper });

    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('logout falla en el servidor: igual limpia la sesión local (nunca deja atascado)', async () => {
    (logout as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('500'));
    const { result } = renderHook(() => useLogout(), { wrapper });

    result.current.mutate();
    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});
