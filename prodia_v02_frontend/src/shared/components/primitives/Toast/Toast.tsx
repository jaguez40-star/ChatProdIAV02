import { useEffect } from 'react';

import styles from './Toast.module.scss';

type ToastVariant = 'info' | 'success' | 'warning' | 'error';

interface ToastProps {
  message: string;
  variant?: ToastVariant;
  duration?: number; // ms; 0 = no auto-cierre
  onClose?: () => void;
}

export function Toast({ message, variant = 'info', duration = 4000, onClose }: ToastProps) {
  useEffect(() => {
    if (!duration || !onClose) return;
    const timer = setTimeout(onClose, duration);
    return () => clearTimeout(timer);
  }, [duration, onClose]);

  return (
    <div
      className={`${styles.toast} ${styles[variant]}`}
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
    >
      <p className={styles.message}>{message}</p>
      {onClose ? (
        <button
          type="button"
          className={styles.closeBtn}
          onClick={onClose}
          aria-label="Cerrar notificación"
        >
          ×
        </button>
      ) : null}
    </div>
  );
}
