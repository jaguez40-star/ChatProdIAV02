import type { ReactNode } from 'react';

import { useEffect, useState } from 'react';

import { useIsMobile } from '../../../../shared/hooks/useIsMobile';
import {
  ABIERTOS_INICIALES,
  MAX_ABIERTOS_ESCRITORIO,
  MAX_ABIERTOS_MOVIL,
  SECCIONES,
  type SeccionPrincipal,
} from '../../data/secciones';
import { PanelColapsable } from '../PanelColapsable';
import styles from './AcordeonHorizontal.module.scss';

type IdSeccion = SeccionPrincipal['id'];

interface AcordeonHorizontalProps {
  /** Contenido de cada panel, por id. F1a los dejó vacíos; los llena F4. */
  cuerpos?: Partial<Record<IdSeccion, ReactNode>>;
}

export function AcordeonHorizontal({ cuerpos }: AcordeonHorizontalProps = {}) {
  const esMovil = useIsMobile();
  const maxAbiertos = esMovil ? MAX_ABIERTOS_MOVIL : MAX_ABIERTOS_ESCRITORIO;
  const [abiertos, setAbiertos] = useState<IdSeccion[]>(ABIERTOS_INICIALES);

  // Al encoger a móvil el máximo baja a 1: se conservan los últimos abiertos,
  // que son los que el usuario tocó más recientemente.
  useEffect(() => {
    setAbiertos((prev) => (prev.length > maxAbiertos ? prev.slice(-maxAbiertos) : prev));
  }, [maxAbiertos]);

  const puedeColapsar = abiertos.length > 1;

  const expandir = (id: IdSeccion) =>
    setAbiertos((prev) => {
      if (prev.includes(id)) return prev;

      // Simétrico a colapsar(): abrir Historial siempre lo empareja con Chat
      // (25/75), sin importar qué estuviera abierto antes — si Insights
      // estaba abierto, se colapsa. 'historial' va al final del array para
      // que sobreviva el slice(-maxAbiertos) también en móvil (max 1).
      if (id === 'historial') {
        return (['chat', 'historial'] as IdSeccion[]).slice(-maxAbiertos);
      }

      return [...prev, id].slice(-maxAbiertos);
    });

  const colapsar = (id: IdSeccion) =>
    setAbiertos((prev) => {
      if (prev.length <= 1) return prev;

      // Historial es un panel de apoyo, no de trabajo: cerrarlo siempre
      // revela el par de trabajo completo (Chat + Insights), sin importar
      // cuál de los dos estuviera abierto antes. Cerrar Chat o Insights, en
      // cambio, se comporta de forma normal — queda el otro solo.
      if (id === 'historial') {
        return (['chat', 'insights'] as IdSeccion[]).slice(-maxAbiertos);
      }

      return prev.filter((x) => x !== id);
    });

  /**
   * El ancho depende de la PAREJA abierta, no del panel: Chat ocupa 75 % junto
   * a Historial y 50 % junto a Insights. Historial es el único angosto.
   */
  const growDe = (id: IdSeccion) => (id === 'historial' ? 1 : 3);

  return (
    <div className={styles.acordeon}>
      {SECCIONES.map((seccion) => (
        <PanelColapsable
          key={seccion.id}
          seccion={seccion}
          abierto={abiertos.includes(seccion.id)}
          puedeColapsar={puedeColapsar}
          grow={growDe(seccion.id)}
          onExpandir={() => expandir(seccion.id)}
          onColapsar={() => colapsar(seccion.id)}
        >
          {cuerpos?.[seccion.id]}
        </PanelColapsable>
      ))}
    </div>
  );
}
