import { useState } from 'react';

import { AcordeonFoco } from '../components/AcordeonFoco';
import { PanelDesempeno } from '../components/PanelDesempeno';
import { PanelEjecutivo } from '../components/PanelEjecutivo';
import { PanelFundacion } from '../components/PanelFundacion';
import { SelectorAmbito } from '../components/SelectorAmbito';
import type { Ambito } from '../types/analisisTypes';
import styles from './AnalisisPage.module.scss';

type Seccion = 'desempeno' | 'ejecutivo' | 'fundacion';

const SECCIONES: { id: Seccion; etiqueta: string; descripcion: string }[] = [
  {
    id: 'desempeno',
    etiqueta: 'Desempeño',
    descripcion: 'Cómo va el mes contra su meta',
  },
  {
    id: 'ejecutivo',
    etiqueta: 'Análisis ejecutivo',
    descripcion: 'Qué explica el resultado y qué hacer',
  },
  {
    id: 'fundacion',
    etiqueta: 'Fundación de datos',
    descripcion: 'Qué dato hay y si se puede confiar en él',
  },
];

/**
 * Sección de Análisis (F2).
 *
 * Se accede por URL directa (`/analisis`), sin entrada de menú: la navegación
 * entre secciones se resolverá cuando existan tres o cuatro, no antes.
 *
 * El orden de las secciones es deliberado: primero el resultado, luego su
 * explicación, y al final la trazabilidad del dato. Quien entra a mirar el mes
 * no debería tener que pasar por la auditoría de cobertura para llegar.
 */
export default function AnalisisPage() {
  const [ambito, setAmbito] = useState<Ambito>({ segmento: 'ecp' });
  const [seccion, setSeccion] = useState<Seccion>('desempeno');

  return (
    <div className={styles.pagina}>
      <header className={styles.encabezado}>
        <h1 className={styles.titulo}>Análisis de producción</h1>
        <p className={styles.subtitulo}>
          Desempeño del mes, sus causas y la economía asociada.
        </p>
      </header>

      <SelectorAmbito ambito={ambito} onCambio={setAmbito} />

      <nav className={styles.secciones} aria-label="Secciones de análisis">
        {SECCIONES.map((s) => (
          <button
            key={s.id}
            type="button"
            aria-current={seccion === s.id}
            className={seccion === s.id ? styles.seccionActiva : styles.seccion}
            onClick={() => setSeccion(s.id)}
          >
            <span className={styles.seccionEtiqueta}>{s.etiqueta}</span>
            <span className={styles.seccionDescripcion}>{s.descripcion}</span>
          </button>
        ))}
      </nav>

      <main className={styles.contenido}>
        {seccion === 'desempeno' && <PanelDesempeno ambito={ambito} />}
        {seccion === 'ejecutivo' && <PanelEjecutivo ambito={ambito} />}
        {seccion === 'fundacion' && <PanelFundacion entidad={ambito.entidad} />}
      </main>
    </div>
  );
}

export { AcordeonFoco };
