import { describe, expect, it } from 'vitest';

import { ApiError, toApiError } from './apiClient';

describe('ApiError', () => {
  it('expone status, message, correlationId y code', () => {
    const err = new ApiError({
      status: 401,
      detail: 'Credenciales inválidas',
      correlation_id: 'abc-123',
      code: 'INVALID_CREDENTIALS',
    });
    expect(err.status).toBe(401);
    expect(err.message).toBe('Credenciales inválidas');
    expect(err.correlationId).toBe('abc-123');
    expect(err.code).toBe('INVALID_CREDENTIALS');
    expect(err.name).toBe('ApiError');
    expect(err).toBeInstanceOf(Error);
  });

  it('code es opcional', () => {
    const err = new ApiError({ status: 500, detail: 'x', correlation_id: null });
    expect(err.code).toBeUndefined();
  });
});

describe('toApiError', () => {
  it('normaliza un body de error válido del backend', () => {
    const err = toApiError(
      { status: 503, detail: 'LDAP no responde', correlation_id: 'xyz' },
      'fallback',
    );
    expect(err.status).toBe(503);
    expect(err.message).toBe('LDAP no responde');
    expect(err.correlationId).toBe('xyz');
  });

  it('con un error no reconocible usa el fallback', () => {
    const err = toApiError(new TypeError('network down'), 'No se pudo iniciar sesión');
    expect(err.status).toBe(0);
    expect(err.message).toBe('No se pudo iniciar sesión');
    expect(err.correlationId).toBeNull();
  });

  it('con undefined usa el fallback', () => {
    const err = toApiError(undefined, 'fallback msg');
    expect(err.message).toBe('fallback msg');
  });
});
