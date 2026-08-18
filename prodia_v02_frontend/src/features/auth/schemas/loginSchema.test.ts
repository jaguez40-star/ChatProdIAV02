import { describe, expect, it } from 'vitest';

import { loginSchema } from './loginSchema';

describe('loginSchema', () => {
  it('acepta username/password no vacíos', () => {
    const result = loginSchema.safeParse({
      username: 'javier.guerrero',
      password: 'clave',
      remember: false,
    });
    expect(result.success).toBe(true);
  });

  it('rechaza username vacío', () => {
    const result = loginSchema.safeParse({ username: '', password: 'x', remember: false });
    expect(result.success).toBe(false);
  });

  it('rechaza password vacío', () => {
    const result = loginSchema.safeParse({ username: 'x', password: '', remember: false });
    expect(result.success).toBe(false);
  });
});
