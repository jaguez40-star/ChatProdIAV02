import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ApiError } from '../../services/apiClient';
import { QueryState } from './QueryState';

interface QueryLike<T> {
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  data: T | undefined;
}

function baseQuery<T>(overrides: Partial<QueryLike<T>> = {}): QueryLike<T> {
  return {
    isLoading: false,
    isError: false,
    error: null,
    data: undefined,
    ...overrides,
  };
}

describe('QueryState', () => {
  it('isLoading -> muestra spinner', () => {
    render(
      <QueryState query={baseQuery({ isLoading: true })}>
        {() => <div>contenido</div>}
      </QueryState>,
    );
    expect(screen.getByRole('status')).toBeDefined();
  });

  it('isError con ApiError -> muestra detail + correlationId', () => {
    const error = new ApiError({
      status: 503,
      detail: 'LDAP no responde',
      correlation_id: 'abc-123',
    });
    render(
      <QueryState query={baseQuery({ isError: true, error })}>
        {() => <div>contenido</div>}
      </QueryState>,
    );
    expect(screen.getByRole('alert').textContent).toContain('LDAP no responde');
    expect(screen.getByText('Referencia: abc-123')).toBeDefined();
  });

  it('isError sin ApiError -> sin línea de referencia', () => {
    render(
      <QueryState query={baseQuery({ isError: true, error: new Error('boom') })}>
        {() => <div>contenido</div>}
      </QueryState>,
    );
    expect(screen.getByRole('alert').textContent).toContain('boom');
    expect(screen.queryByText(/Referencia:/)).toBeNull();
  });

  it('data presente -> renderiza children(data)', () => {
    render(
      <QueryState query={baseQuery({ data: { valor: 42 } })}>
        {(data) => <div>valor: {data.valor}</div>}
      </QueryState>,
    );
    expect(screen.getByText('valor: 42')).toBeDefined();
  });

  it('emptyWhen true -> muestra emptyMessage en vez de children', () => {
    render(
      <QueryState
        query={baseQuery({ data: [] as number[] })}
        emptyWhen={(data) => data.length === 0}
        emptyMessage="Sin resultados"
      >
        {() => <div>no debería verse</div>}
      </QueryState>,
    );
    expect(screen.getByText('Sin resultados')).toBeDefined();
  });
});
