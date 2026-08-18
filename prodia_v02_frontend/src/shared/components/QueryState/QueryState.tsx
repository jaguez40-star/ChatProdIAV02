import type { ReactNode } from 'react';
import type { UseQueryResult } from '@tanstack/react-query';

import { ApiError } from '../../services/apiClient';
import { Spinner } from '../primitives/Spinner/Spinner';
import styles from './QueryState.module.scss';

interface QueryStateProps<T> {
  query: Pick<UseQueryResult<T>, 'isLoading' | 'isError' | 'error' | 'data'>;
  skeleton?: ReactNode;
  emptyWhen?: (data: T) => boolean;
  emptyMessage?: string;
  children: (data: T) => ReactNode;
}

/**
 * Encapsula el triángulo loading/error/vacío (C5 — corrección sobre
 * Robustez V02, que lo repite como ternarios inline en cada página, p.ej.
 * `EbitdaRankPage.tsx:403-413`, con texto de error hardcodeado y sin
 * `correlation_id`). Aquí el error SIEMPRE muestra el `correlation_id`
 * cuando la causa es un `ApiError` (N6) — es lo que convierte un ticket de
 * soporte en 30 segundos de grep contra los logs del backend.
 */
export function QueryState<T>({
  query,
  skeleton,
  emptyWhen,
  emptyMessage = 'No hay datos para mostrar.',
  children,
}: QueryStateProps<T>) {
  if (query.isLoading) {
    return (
      <div className={styles.center}>{skeleton ?? <Spinner size="md" label="Cargando..." />}</div>
    );
  }

  if (query.isError) {
    const err = query.error;
    const correlationId = err instanceof ApiError ? err.correlationId : null;
    const detail = err instanceof Error ? err.message : 'Error al cargar los datos';
    return (
      <div className={styles.center} role="alert">
        <p className={styles.errorText}>{detail}</p>
        {correlationId ? (
          <p className={styles.correlationId}>Referencia: {correlationId}</p>
        ) : null}
      </div>
    );
  }

  if (query.data === undefined) {
    return <div className={styles.center}>{skeleton ?? <Spinner size="md" />}</div>;
  }

  if (emptyWhen?.(query.data)) {
    return (
      <div className={styles.center}>
        <p className={styles.emptyText}>{emptyMessage}</p>
      </div>
    );
  }

  return <>{children(query.data)}</>;
}
