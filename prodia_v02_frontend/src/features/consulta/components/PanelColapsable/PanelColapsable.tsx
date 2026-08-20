import { PanelLeftClose } from 'lucide-react';
import type { CSSProperties, ReactNode } from 'react';

import type { SeccionPrincipal } from '../../data/secciones';
import styles from './PanelColapsable.module.scss';

interface PanelColapsableProps {
  seccion: SeccionPrincipal;
  abierto: boolean;
  /** false cuando este es el único panel abierto: colapsarlo dejaría la
   *  página sin contenido, así que el botón se deshabilita. */
  puedeColapsar: boolean;
  /** Peso de reparto horizontal. Lo decide el acordeón, que es quien conoce
   *  la pareja abierta — ver AcordeonHorizontal.growDe(). Solo se aplica
   *  mientras el panel está abierto; colapsado tiene ancho fijo. */
  grow: number;
  onExpandir: () => void;
  onColapsar: () => void;
  /** Contenido del panel. F1a lo dejó vacío a propósito; lo llena F4. */
  children?: ReactNode;
}

export function PanelColapsable({
  seccion,
  abierto,
  puedeColapsar,
  grow,
  onExpandir,
  onColapsar,
  children,
}: PanelColapsableProps) {
  const Icono = seccion.icono;

  const clases = [styles.panel, abierto ? styles.abierto : styles.colapsado]
    .filter(Boolean)
    .join(' ');

  if (!abierto) {
    return (
      <div className={clases}>
        <button
          type="button"
          className={styles.tira}
          aria-expanded={false}
          aria-label={`Abrir ${seccion.titulo}`}
          onClick={onExpandir}
        >
          <span className={styles.tiraIcono}>
            <Icono size={18} aria-hidden />
          </span>
          <span className={styles.tiraTitulo}>{seccion.titulo}</span>
        </button>
      </div>
    );
  }

  return (
    <div className={clases} style={{ '--pv-panel-grow': grow } as CSSProperties}>
      <button
        type="button"
        className={styles.cabecera}
        aria-expanded
        aria-label={`Colapsar ${seccion.titulo}`}
        disabled={!puedeColapsar}
        title={puedeColapsar ? undefined : 'Debe quedar al menos un panel abierto'}
        onClick={onColapsar}
      >
        <span className={styles.num}>{seccion.num}</span>
        <span className={styles.titulos}>
          <span className={styles.titulo}>
            <Icono size={14} className={styles.tituloIcono} aria-hidden />
            {seccion.titulo}
          </span>
          <span className={styles.subtitulo}>{seccion.subtitulo}</span>
        </span>
        <span className={styles.colapsar} aria-hidden>
          <PanelLeftClose size={14} />
        </span>
      </button>

      {/* Cuerpo vacío a propósito: el contenido de cada panel llega en F4. */}
      <div className={styles.cuerpo}>{children}</div>
    </div>
  );
}
