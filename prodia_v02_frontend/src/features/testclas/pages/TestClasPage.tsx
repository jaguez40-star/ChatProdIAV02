import { Cpu, RefreshCw } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { QueryState } from '../../../shared/components/QueryState';
import { ChatPrueba } from '../components/ChatPrueba/ChatPrueba';
import { ResumenLibreta } from '../components/ResumenLibreta/ResumenLibreta';
import { TablaLibreta } from '../components/TablaLibreta/TablaLibreta';
import { useLibreta } from '../hooks/useLibreta';
import type { FiltroLibreta } from '../types/testClasTypes';
import styles from './TestClasPage.module.scss';

const FILTROS: { valor: FiltroLibreta; etiqueta: string }[] = [
  { valor: 'todas', etiqueta: 'Todas' },
  { valor: 'pendientes', etiqueta: 'Pendientes' },
  { valor: 'sospecha', etiqueta: 'Sospecha' },
  { valor: 'corregidas', etiqueta: 'Corregidas' },
];

/**
 * Test Clas — el laboratorio del clasificador. **Admin-only.**
 *
 * Dos columnas: a la izquierda se prueba el motor, a la derecha se juzga lo que
 * decidió. El valor de la pantalla no es la tabla, es el ciclo que sostiene:
 * solo los casos VERIFICADOS alimentan el crecimiento de patrones y del golden.
 */
export default function TestClasPage() {
  const [filtro, setFiltro] = useState<FiltroLibreta>('todas');
  const {
    consulta,
    aviso,
    descartarAviso,
    recargar,
    calificar,
    calificando,
    escanear,
    escaneando,
  } = useLibreta(filtro);

  // El escaneo de señales corre UNA VEZ al abrir, no en cada lectura (H5). El
  // sistema viejo lo llamaba dentro del GET de la libreta, así que cada clic en
  // un chip de filtro recorría todos los pendientes con dos consultas por fila.
  //
  // ⚠️ `escanear` viene de `useMutation` y TanStack lo recrea en cada render, así
  // que ponerlo en las dependencias vuelve a disparar el efecto — el guardia de
  // `useRef` no basta porque el propio escaneo provoca un render. Se guarda en
  // una ref y el efecto se queda SIN dependencias: eso es lo que hace que sea
  // «una vez al montar» de verdad.
  const escanearRef = useRef(escanear);
  escanearRef.current = escanear;
  useEffect(() => {
    escanearRef.current();
  }, []);

  return (
    <div className={styles.pagina}>
      <header className={styles.cabecera}>
        <h1 className={styles.titulo}>
          <Cpu size={18} /> Test Clas · laboratorio del clasificador
        </h1>
        <button
          type="button"
          className={styles.botonEscanear}
          onClick={() => escanear()}
          disabled={escaneando}
        >
          <RefreshCw size={14} className={escaneando ? styles.girando : undefined} />
          Buscar señales
        </button>
      </header>

      {aviso !== null && (
        <div className={styles.aviso} role="status">
          <span>{aviso}</span>
          <button type="button" onClick={descartarAviso} aria-label="Descartar aviso">
            ×
          </button>
        </div>
      )}

      <div className={styles.columnas}>
        <section className={styles.izquierda} aria-label="Chat de prueba">
          {/* Recargar la libreta, NO escanear: una clasificación recién hecha
              no puede tener señales todavía (la reformulación necesita una
              segunda pregunta y el abandono, 600 s). Escanear aquí repetiría el
              recorrido completo de pendientes por cada pregunta escrita — el
              mismo derroche que H5 corrige. */}
          <ChatPrueba onClasificado={recargar} />
        </section>

        <section className={styles.derecha} aria-label="Libreta de clasificación">
          <QueryState query={consulta}>
            {(libreta) => (
              <>
                <ResumenLibreta resumen={libreta.resumen} />

                <div className={styles.filtros} role="group" aria-label="Filtros">
                  {FILTROS.map(({ valor, etiqueta }) => (
                    <button
                      key={valor}
                      type="button"
                      className={valor === filtro ? styles.chipActivo : styles.chip}
                      onClick={() => setFiltro(valor)}
                      aria-pressed={valor === filtro}
                    >
                      {etiqueta}
                    </button>
                  ))}
                </div>

                {libreta.truncado && (
                  <p className={styles.truncado}>
                    Se muestran las primeras {libreta.filas.length} filas; hay más en
                    la libreta.
                  </p>
                )}

                <TablaLibreta
                  filas={libreta.filas}
                  onCalificar={calificar}
                  deshabilitado={calificando}
                />
              </>
            )}
          </QueryState>
        </section>
      </div>
    </div>
  );
}
