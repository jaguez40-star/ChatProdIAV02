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

export function AcordeonHorizontal() {
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
    setAbiertos((prev) => (prev.includes(id) ? prev : [...prev, id].slice(-maxAbiertos)));

  const colapsar = (id: IdSeccion) =>
    setAbiertos((prev) => (prev.length <= 1 ? prev : prev.filter((x) => x !== id)));

  return (
    <div className={styles.acordeon}>
      {SECCIONES.map((seccion) => (
        <PanelColapsable
          key={seccion.id}
          seccion={seccion}
          abierto={abiertos.includes(seccion.id)}
          puedeColapsar={puedeColapsar}
          onExpandir={() => expandir(seccion.id)}
          onColapsar={() => colapsar(seccion.id)}
        />
      ))}
    </div>
  );
}
