import { HelpCircle, LogOut, Settings, ShieldCheck } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import styles from './MenuUsuario.module.scss';

interface MenuUsuarioProps {
  username: string;
  fullName: string | null;
  email: string;
  isAdmin: boolean;
  onCerrar: () => void;
  onLogout: () => void;
}

const ACCESOS = [
  { icono: ShieldCheck, etiqueta: 'Admin', ruta: '/admin', color: '#004236', soloAdmin: true },
  { icono: Settings, etiqueta: 'Configuración', ruta: '/settings', color: '#6b7280', soloAdmin: false },
  { icono: HelpCircle, etiqueta: 'Ayuda', ruta: '/help', color: '#7c3aed', soloAdmin: false },
] as const;

export function MenuUsuario({
  username,
  fullName,
  email,
  isAdmin,
  onCerrar,
  onLogout,
}: MenuUsuarioProps) {
  const navigate = useNavigate();
  const nombre = fullName ?? username;
  const visibles = ACCESOS.filter((a) => !a.soloAdmin || isAdmin);

  const irA = (ruta: string) => {
    void navigate(ruta);
    onCerrar();
  };

  return (
    <div className={styles.menu} role="menu" aria-label="Menú de usuario">
      <div className={styles.usuario}>
        <div className={styles.avatar}>{nombre.charAt(0).toUpperCase()}</div>
        <div className={styles.datos}>
          <div className={styles.filaNombre}>
            <span className={styles.nombre}>{nombre}</span>
            {isAdmin && <span className={styles.insignia}>ADMIN</span>}
          </div>
          <div className={styles.email}>{email}</div>
        </div>
      </div>

      <div className={styles.separador} />

      <nav
        className={styles.accesos}
        style={{ gridTemplateColumns: `repeat(${visibles.length}, 1fr)` }}
      >
        {visibles.map((acceso) => (
          <button
            key={acceso.ruta}
            type="button"
            className={styles.acceso}
            role="menuitem"
            onClick={() => irA(acceso.ruta)}
          >
            <acceso.icono size={22} color={acceso.color} aria-hidden />
            <span className={styles.accesoEtiqueta}>{acceso.etiqueta}</span>
          </button>
        ))}
      </nav>

      <div className={styles.separador} />

      <button type="button" className={`${styles.item} ${styles.salir}`} role="menuitem" onClick={onLogout}>
        <LogOut size={16} aria-hidden />
        <span>Cerrar sesión</span>
      </button>
    </div>
  );
}
