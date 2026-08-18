import { Hand } from 'lucide-react';

import styles from './InactivitySessionModal.module.scss';

interface InactivitySessionModalProps {
  isOpen: boolean;
  onAccept: () => void;
  minutesInactive: number;
}

export function InactivitySessionModal({
  isOpen,
  onAccept,
  minutesInactive,
}: InactivitySessionModalProps) {
  if (!isOpen) return null;

  return (
    <div className={styles.overlay} role="none">
      <div
        className={styles.dialog}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="inactivity-modal-title"
        aria-describedby="inactivity-modal-desc"
      >
        <span className={styles.iconChip} aria-hidden="true">
          <Hand size={28} />
        </span>
        <h2 id="inactivity-modal-title" className={styles.title}>
          Sesión inactiva
        </h2>
        <p id="inactivity-modal-desc" className={styles.text}>
          No hemos detectado actividad en los últimos {minutesInactive} minutos, por
          seguridad cerraremos tu sesión.
        </p>
        <button type="button" className={styles.acceptBtn} onClick={onAccept}>
          Entendido
        </button>
      </div>
    </div>
  );
}
