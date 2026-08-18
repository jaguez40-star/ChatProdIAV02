import { useAuthStore } from '../../../app/store/authStore';
import { useSessionExpiry } from '../../../features/auth/hooks/useSessionExpiry';
import styles from './SessionExpiryBanner.module.scss';

/**
 * Banner de aviso cuando la sesión está próxima a expirar.
 * - Visible cuando minutesLeft <= WARNING_THRESHOLD_MIN (5 min).
 * - No descartable: desaparece solo cuando el backend renueva el token
 *   (sliding refresh).
 * - Posición: dentro de <main>, encima del <Outlet/>.
 */
export function SessionExpiryBanner() {
  const sessionExpiresAt = useAuthStore((s) => s.sessionExpiresAt);
  const { minutesLeft, isExpiringSoon } = useSessionExpiry(sessionExpiresAt);

  if (!isExpiringSoon || minutesLeft === null) return null;

  return (
    <div className={styles.banner} role="alert" aria-live="polite">
      <span className={styles.icon} aria-hidden="true">
        ⏱
      </span>
      <span className={styles.text}>
        Tu sesión expira en <strong>{minutesLeft} min</strong>. Guarda tu trabajo.
      </span>
    </div>
  );
}
