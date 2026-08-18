import { describe, expect, it } from 'vitest';

import { toAuthGroup, toAuthPermissions, toAuthSession, toAuthUser, toLoginResult } from './authMappers';

describe('toAuthGroup', () => {
  it('mapea snake_case a camelCase', () => {
    expect(toAuthGroup({ id: 1, name: 'Administradores', description: 'x', is_admin: true })).toEqual({
      id: 1,
      name: 'Administradores',
      description: 'x',
      isAdmin: true,
    });
  });

  it('description ausente -> null', () => {
    expect(toAuthGroup({ id: 1, name: 'Consulta', is_admin: false }).description).toBeNull();
  });
});

describe('toAuthUser', () => {
  it('mapea un usuario completo con grupo', () => {
    const result = toAuthUser({
      id: 1,
      username: 'javier.guerrero',
      email: 'javier.guerrero@ecopetrol.com.co',
      full_name: null,
      is_admin: true,
      is_active: true,
      group: { id: 1, name: 'Administradores', is_admin: true },
      last_login_at: null,
      created_at: '2026-08-18T00:00:00Z',
      updated_at: '2026-08-18T00:00:00Z',
    });
    expect(result.username).toBe('javier.guerrero');
    expect(result.fullName).toBeNull();
    expect(result.group?.name).toBe('Administradores');
  });

  it('sin grupo -> group null', () => {
    const result = toAuthUser({
      id: 2,
      username: 'sin.grupo',
      email: 'x@ecopetrol.com.co',
      is_admin: false,
      is_active: true,
      created_at: '2026-08-18T00:00:00Z',
      updated_at: '2026-08-18T00:00:00Z',
    });
    expect(result.group).toBeNull();
  });
});

describe('toAuthPermissions', () => {
  it('campos/sections ausentes -> arrays vacíos', () => {
    expect(toAuthPermissions({})).toEqual({ campos: [], sections: [] });
  });

  it('preserva las listas presentes', () => {
    expect(toAuthPermissions({ campos: ['CASTILLA'], sections: ['ingesta'] })).toEqual({
      campos: ['CASTILLA'],
      sections: ['ingesta'],
    });
  });
});

describe('toAuthSession', () => {
  it('combina user + permissions', () => {
    const result = toAuthSession({
      user: {
        id: 1,
        username: 'u',
        email: 'u@ecopetrol.com.co',
        is_admin: false,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      permissions: { campos: [], sections: ['home'] },
    });
    expect(result.user.username).toBe('u');
    expect(result.permissions.sections).toEqual(['home']);
  });
});

describe('toLoginResult', () => {
  it('mapea access_token/token_type', () => {
    expect(toLoginResult({ access_token: 'abc', token_type: 'bearer' })).toEqual({
      accessToken: 'abc',
      tokenType: 'bearer',
    });
  });
});
