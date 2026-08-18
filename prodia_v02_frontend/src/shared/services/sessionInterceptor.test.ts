import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./apiClient', () => ({
  default: { use: vi.fn(), eject: vi.fn() },
}));

import { useAuthStore } from '../../app/store/authStore';
import apiClient from './apiClient';
import {
  installSessionInterceptor,
  uninstallSessionInterceptor,
} from './sessionInterceptor';

const mockedUse = apiClient.use as ReturnType<typeof vi.fn>;
const mockedEject = apiClient.eject as ReturnType<typeof vi.fn>;

function fakeResponse(init: { status?: number; headers?: Record<string, string> } = {}) {
  return new Response(null, { status: init.status ?? 200, headers: init.headers });
}

describe('sessionInterceptor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().clearSession();
    uninstallSessionInterceptor(); // resetea el flag `installed` entre tests
  });

  afterEach(() => {
    uninstallSessionInterceptor();
  });

  it('install registra el middleware una sola vez (idempotente)', () => {
    installSessionInterceptor();
    installSessionInterceptor();
    expect(mockedUse).toHaveBeenCalledTimes(1);
  });

  it('uninstall lo desregistra', () => {
    installSessionInterceptor();
    uninstallSessionInterceptor();
    expect(mockedEject).toHaveBeenCalledTimes(1);
  });

  it('onResponse propaga X-Session-Expires al store', () => {
    installSessionInterceptor();
    const middleware = mockedUse.mock.calls[0][0];
    const request = new Request('http://localhost/api/v1/permissions/my-permissions');
    const response = fakeResponse({ headers: { 'X-Session-Expires': '2026-08-18T13:00:00Z' } });

    middleware.onResponse({ request, response });
    expect(useAuthStore.getState().sessionExpiresAt).toBe('2026-08-18T13:00:00Z');
  });

  it('401 + X-Session-Expired en ruta protegida -> markSessionExpired', () => {
    installSessionInterceptor();
    const middleware = mockedUse.mock.calls[0][0];
    const request = new Request('http://localhost/api/v1/auth/me');
    const response = fakeResponse({ status: 401, headers: { 'X-Session-Expired': 'true' } });

    middleware.onResponse({ request, response });
    expect(useAuthStore.getState().sessionExpired).toBe(true);
  });

  it('401 en /auth/login está excluido: NO marca sessionExpired', () => {
    installSessionInterceptor();
    const middleware = mockedUse.mock.calls[0][0];
    const request = new Request('http://localhost/api/v1/auth/login');
    const response = fakeResponse({ status: 401, headers: { 'X-Session-Expired': 'true' } });

    middleware.onResponse({ request, response });
    expect(useAuthStore.getState().sessionExpired).toBe(false);
  });

  it('401 en /auth/logout está excluido: NO marca sessionExpired', () => {
    installSessionInterceptor();
    const middleware = mockedUse.mock.calls[0][0];
    const request = new Request('http://localhost/api/v1/auth/logout');
    const response = fakeResponse({ status: 401, headers: { 'X-Session-Expired': 'true' } });

    middleware.onResponse({ request, response });
    expect(useAuthStore.getState().sessionExpired).toBe(false);
  });
});
