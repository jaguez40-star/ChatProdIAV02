import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';

import { useAuthStore } from '../../app/store/authStore';
import { InactivitySessionModal } from '../../features/auth/components/InactivitySessionModal';
import { useInactivityLogout } from '../../features/auth/hooks/useInactivityLogout';
import { useLogout } from '../../features/auth/hooks/useLogout';
import { SessionExpiryBanner } from '../../shared/components/SessionExpiryBanner';
import { seccionesVisibles } from '../secciones';
import { MenuUsuario } from './components/MenuUsuario';
import styles from './LayoutMain.module.scss';

// Las secciones ya NO se declaran aquí: viven en `app/secciones.ts`, que es la
// fuente única que también alimenta al router. Repetir la lista en dos sitios
// es justo lo que dejó `/analisis`, `/ingesta` y `/test-clas` sin enlace en su
// momento. El layout sigue sin importar nada de las features (C10 intacta):
// `secciones.ts` es dato plano, rutas y etiquetas.

/**
 * Simplificado respecto de Robustez V02 (que además tiene drawer lateral y
 * ticker de KPIs, con el defecto documentado C10). Aquí el header es una
 * franja blanca con la navegación entre secciones a la izquierda y el avatar
 * como único otro control — sin marca ni lanzador de módulos (decisión del
 * usuario en F1a).
 */
export function LayoutMain() {
  const user = useAuthStore((s) => s.user);
  const logoutMutation = useLogout();
  const navigate = useNavigate();
  const inactivity = useInactivityLogout();
  const [menuAbierto, setMenuAbierto] = useState(false);
  const headerRef = useRef<HTMLElement>(null);

  // Cierre por clic fuera y por Escape: un popover que solo se cierra con su
  // propio botón atrapa al usuario que lo abrió por error.
  useEffect(() => {
    if (!menuAbierto) return;

    const alPresionarFuera = (e: MouseEvent) => {
      if (headerRef.current && !headerRef.current.contains(e.target as Node)) {
        setMenuAbierto(false);
      }
    };
    const alPresionarTecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuAbierto(false);
    };

    document.addEventListener('mousedown', alPresionarFuera);
    document.addEventListener('keydown', alPresionarTecla);
    return () => {
      document.removeEventListener('mousedown', alPresionarFuera);
      document.removeEventListener('keydown', alPresionarTecla);
    };
  }, [menuAbierto]);

  const handleLogout = () => {
    setMenuAbierto(false);
    logoutMutation.mutate(undefined, {
      onSettled: () => void navigate('/login'),
    });
  };

  const nombre = user?.fullName ?? user?.username ?? user?.email ?? 'Usuario';

  return (
    <div className={styles.layoutMain}>
      <InactivitySessionModal
        isOpen={inactivity.isModalOpen}
        minutesInactive={inactivity.minutesInactive}
        onAccept={inactivity.onAccept}
      />

      <header className={styles.header} ref={headerRef}>
        <nav className={styles.nav} aria-label="Secciones">
          {/* `user` es null durante el logout, mientras el layout aún está
              montado. Sin permiso conocido, se muestran solo las secciones
              abiertas: nunca una admin. */}
          {seccionesVisibles(user?.isAdmin ?? false).map(({ ruta, etiqueta }) => (
            <NavLink
              key={ruta}
              to={ruta}
              // `end` solo en la raíz: sin él, '/' quedaría activa también en
              // '/analisis', porque toda ruta empieza por '/'.
              end={ruta === '/'}
              className={({ isActive }) =>
                isActive ? `${styles.navLink} ${styles.navLinkActivo}` : styles.navLink
              }
            >
              {etiqueta}
            </NavLink>
          ))}
        </nav>

        <button
          type="button"
          className={styles.avatarBtn}
          onClick={() => setMenuAbierto((prev) => !prev)}
          aria-label="Menú de usuario"
          aria-expanded={menuAbierto}
          aria-haspopup="menu"
        >
          {nombre.charAt(0).toUpperCase()}
        </button>

        {menuAbierto && user && (
          <MenuUsuario
            username={user.username}
            fullName={user.fullName}
            email={user.email}
            isAdmin={user.isAdmin}
            onCerrar={() => setMenuAbierto(false)}
            onLogout={handleLogout}
          />
        )}
      </header>

      <main className={styles.mainContent}>
        <SessionExpiryBanner />
        <Outlet />
      </main>

      <footer className={styles.footer}>
        <span>© 2026 ECOPETROL S.A. — ProdIA V02 · v0.1.0</span>
      </footer>
    </div>
  );
}
