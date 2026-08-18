import { beforeEach, describe, expect, it } from 'vitest';

import { getPersistedAuth, useAuthStore } from './authStore';

const user = {
  id: 1,
  username: 'javier.guerrero',
  email: 'javier.guerrero@ecopetrol.com.co',
  fullName: 'Javier Guerrero',
  isAdmin: true,
  isActive: true,
  group: null,
  lastLoginAt: null,
  createdAt: '2026-08-18T00:00:00Z',
  updatedAt: '2026-08-18T00:00:00Z',
};

const permissions = { campos: ['CASTILLA'], sections: ['home'] };

describe('authStore', () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.getState().clearSession();
    useAuthStore.setState({ isHydrated: false });
  });

  it('estado inicial: no autenticado, no hidratado', () => {
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isHydrated).toBe(false);
    expect(state.user).toBeNull();
  });

  it('setSession marca autenticado y persiste en localStorage', () => {
    useAuthStore.getState().setSession(user, permissions);
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.user).toEqual(user);
    expect(state.sessionExpired).toBe(false);

    const persisted = getPersistedAuth();
    expect(persisted?.username).toBe('javier.guerrero');
    expect(persisted?.isAdmin).toBe(true);
  });

  it('clearSession limpia estado y localStorage, sessionExpired=false', () => {
    useAuthStore.getState().setSession(user, permissions);
    useAuthStore.getState().clearSession();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.user).toBeNull();
    expect(state.sessionExpired).toBe(false);
    expect(getPersistedAuth()).toBeNull();
  });

  it('markSessionExpired limpia estado pero deja sessionExpired=true', () => {
    useAuthStore.getState().setSession(user, permissions);
    useAuthStore.getState().markSessionExpired();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.sessionExpired).toBe(true);
    expect(getPersistedAuth()).toBeNull();
  });

  it('setHydrated marca isHydrated=true', () => {
    useAuthStore.getState().setHydrated();
    expect(useAuthStore.getState().isHydrated).toBe(true);
  });

  it('setSessionExpiry guarda el timestamp', () => {
    useAuthStore.getState().setSessionExpiry('2026-08-18T12:30:00Z');
    expect(useAuthStore.getState().sessionExpiresAt).toBe('2026-08-18T12:30:00Z');
  });

  it('getPersistedAuth sin nada guardado devuelve null', () => {
    expect(getPersistedAuth()).toBeNull();
  });

  it('getPersistedAuth con JSON corrupto devuelve null (no lanza)', () => {
    localStorage.setItem('prodia_auth', '{esto no es json valido');
    expect(getPersistedAuth()).toBeNull();
  });
});
