import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

import styles from './ErrorBoundary.module.scss';

interface Props {
  children: ReactNode;
}
interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  private handleReload = () => {
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className={styles.container} role="alert">
          <div className={styles.card}>
            <span className={styles.icon} aria-hidden="true">
              ⚠
            </span>
            <h1 className={styles.title}>Error inesperado</h1>
            <p className={styles.message}>
              Ocurrió un problema al cargar esta sección. Intenta recargar la página.
            </p>
            <button className={styles.btn} onClick={this.handleReload}>
              Volver al inicio
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
