import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../shared/services/apiClient', async () => {
  const actual = await vi.importActual<
    typeof import('../../../shared/services/apiClient')
  >('../../../shared/services/apiClient');
  return {
    ...actual,
    default: { POST: vi.fn(), GET: vi.fn() },
  };
});

import apiClient, { ApiError } from '../../../shared/services/apiClient';
import { getMe, getSessionTimeoutMinutes, login, logout } from './authService';

const mockedPost = apiClient.POST as ReturnType<typeof vi.fn>;
const mockedGet = apiClient.GET as ReturnType<typeof vi.fn>;

describe('authService.login', () => {
  beforeEach(() => vi.clearAllMocks());

  it('éxito: devuelve el LoginResult mapeado', async () => {
    mockedPost.mockResolvedValue({
      data: { access_token: 'tok', token_type: 'bearer' },
      error: undefined,
    });
    const result = await login({ username: 'u', password: 'p' });
    expect(result).toEqual({ accessToken: 'tok', tokenType: 'bearer' });
  });

  it('401 -> lanza ApiError con status 401', async () => {
    mockedPost.mockResolvedValue({
      data: undefined,
      error: { status: 401, detail: 'Credenciales inválidas', correlation_id: 'abc' },
    });
    await expect(login({ username: 'u', password: 'mala' })).rejects.toMatchObject({
      status: 401,
      message: 'Credenciales inválidas',
    });
  });

  it('503 (LDAP inalcanzable) -> lanza ApiError con status 503', async () => {
    mockedPost.mockResolvedValue({
      data: undefined,
      error: { status: 503, detail: 'LDAP no responde', correlation_id: 'xyz' },
    });
    const err = await login({ username: 'u', password: 'p' }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(503);
  });
});

describe('authService.logout', () => {
  beforeEach(() => vi.clearAllMocks());

  it('éxito: no lanza', async () => {
    mockedPost.mockResolvedValue({ data: {}, error: undefined });
    await expect(logout()).resolves.toBeUndefined();
  });

  it('error -> lanza ApiError', async () => {
    mockedPost.mockResolvedValue({
      data: undefined,
      error: { status: 401, detail: 'No autenticado', correlation_id: null },
    });
    await expect(logout()).rejects.toBeInstanceOf(ApiError);
  });
});

describe('authService.getMe', () => {
  beforeEach(() => vi.clearAllMocks());

  it('éxito: devuelve la sesión mapeada', async () => {
    mockedGet.mockResolvedValue({
      data: {
        user: {
          id: 1,
          username: 'u',
          email: 'u@ecopetrol.com.co',
          is_admin: false,
          is_active: true,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
        permissions: { campos: [], sections: [] },
      },
      error: undefined,
    });
    const session = await getMe();
    expect(session.user.username).toBe('u');
  });
});

describe('authService.getSessionTimeoutMinutes', () => {
  beforeEach(() => vi.clearAllMocks());

  it('éxito: devuelve el número de minutos', async () => {
    mockedGet.mockResolvedValue({
      data: { session_timeout_minutes: 30 },
      error: undefined,
    });
    expect(await getSessionTimeoutMinutes()).toBe(30);
  });
});
