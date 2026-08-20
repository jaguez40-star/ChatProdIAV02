import { ChevronDown, ChevronRight, X } from 'lucide-react';

import { useChatStore } from '../../store/chatStore';
import type { Panel } from '../../types/consultaTypes';
import { PanelDesconocido, PanelGenerico } from '../paneles';
import styles from './PilaResultados.module.scss';

/**
 * 🔑 **Q5 — el dispatcher agota los tipos con `never`.**
 *
 * El sistema viejo termina su cadena de ternarios en un fallback que **no
 * valida el tipo**, así que un tipo no registrado pinta una tarjeta con campos
 * ajenos sin ningún error visible. Verificado: `cuant_kpi` —el tipo más
 * común— no está registrado allí y funciona por accidente.
 *
 * Aquí el caso por defecto asigna a `never`: si el backend añade un tipo, el
 * build falla. Y si aun así llegara uno desconocido en tiempo de ejecución
 * —por ejemplo, un backend más nuevo que el frontend—, se muestra un aviso
 * explícito en vez de una tarjeta falsa.
 */
function cuerpoDePanel(panel: Panel) {
  switch (panel.tipo) {
    case 'cuant_kpi':
    case 'cuant_serie':
    case 'cuant_var':
    case 'cuant_rank':
    case 'jerarq_arbol':
    case 'jerarq_operador':
    case 'jerarq_rank':
    case 'p50_vp':
    case 'analiza_foco':
      return <PanelGenerico panel={panel} />;
    default: {
      // Si el backend añade un tipo y no se registra arriba, `tsc` falla aquí.
      const _exhaustivo: never = panel;
      void _exhaustivo;
      return <PanelDesconocido tipo={(panel as { tipo: string }).tipo} />;
    }
  }
}

/**
 * La pila de resultados: un bloque por respuesta con panel.
 *
 * A diferencia del original, los bloques **se pueden colapsar y cerrar**, y el
 * tope de la pila **se declara** en vez de descartar en silencio.
 */
export function PilaResultados() {
  const { pila, descartados, alternarBloque, cerrarBloque } = useChatStore();

  if (pila.length === 0) {
    return (
      <p className={styles.vacio}>
        Los resultados con gráfico o tabla aparecerán aquí, apilados por turno.
      </p>
    );
  }

  return (
    <div className={styles.pila}>
      {descartados > 0 && (
        <p className={styles.descartados}>
          Se ocultaron los {descartados} bloques más antiguos para no cargar la
          página.
        </p>
      )}

      {pila.map((bloque) => (
        <section key={bloque.n} className={styles.bloque}>
          <header className={styles.cabecera}>
            <button
              type="button"
              className={styles.alternar}
              onClick={() => alternarBloque(bloque.n)}
              aria-expanded={!bloque.colapsado}
              aria-label={
                bloque.colapsado
                  ? `Expandir el resultado ${bloque.n}`
                  : `Colapsar el resultado ${bloque.n}`
              }
            >
              {bloque.colapsado ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
            </button>

            <span className={styles.turno}>{bloque.n}</span>
            {/* La cabecera lleva la pregunta: es lo que el contenido no tiene
                y lo que permite ubicar de dónde salió el panel. */}
            <span className={styles.pregunta} title={bloque.pregunta}>
              {bloque.pregunta}
            </span>
            <span className={styles.hora}>{bloque.hora}</span>

            <button
              type="button"
              className={styles.cerrar}
              onClick={() => cerrarBloque(bloque.n)}
              aria-label={`Cerrar el resultado ${bloque.n}`}
            >
              <X size={14} />
            </button>
          </header>

          {!bloque.colapsado && (
            <div className={styles.cuerpo}>{cuerpoDePanel(bloque.panel)}</div>
          )}
        </section>
      ))}
    </div>
  );
}
