import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '../../../app/store/authStore';
import { useSessionTimeoutMinutes } from './useSessionTimeoutMinutes';

vi.mock('../services/authService', () => ({
  getSessionTimeoutMinutes: vi.fn(),
}));

import { getSessionTimeoutMinutes } from '../services/authService';

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe('useSessionTimeoutMinutes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().clearSession();
  });

  it('deshabilitado si no está autenticado', () => {
    const { result } = renderHook(() => useSessionTimeoutMinutes(), { wrapper });
    expect(result.current.isFetching).toBe(false);
    expect(getSessionTimeoutMinutes).not.toHaveBeenCalled();
  });

  it('autenticado -> consulta el timeout', async () => {
    useAuthStore.setState({ isAuthenticated: true });
    (getSessionTimeoutMinutes as ReturnType<typeof vi.fn>).mockResolvedValue(30);

    const { result } = renderHook(() => useSessionTimeoutMinutes(), { wrapper });
    await waitFor(() => expect(result.current.data).toBe(30));
  });
});
