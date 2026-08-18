import styles from './Spinner.module.scss';

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  label?: string;
}

export function Spinner({ size = 'md', label = 'Cargando...' }: SpinnerProps) {
  return (
    <span className={`${styles.spinner} ${styles[size]}`} role="status" aria-label={label}>
      <span className={styles.circle} aria-hidden="true" />
    </span>
  );
}
