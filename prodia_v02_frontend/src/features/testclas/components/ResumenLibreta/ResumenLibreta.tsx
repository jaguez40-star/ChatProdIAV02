import type { ResumenLibreta as Resumen } from '../../types/testClasTypes';
import styles from './ResumenLibreta.module.scss';

interface Props {
  resumen: Resumen;
}

/** Umbral de la regla A4: por debajo, el motor depende demasiado del LLM. */
const UMBRAL_CAPA1 = 50;

/**
 * Los tres KPIs del ciclo de crecimiento del clasificador.
 *
 * El destacado es **% resuelto por Capa 1**, y no es decorativo: es el número
 * que decide si hay que engordar patrones (regla A4). Por debajo del 50 % el
 * motor se apoya demasiado en el LLM, que es más lento, no determinista y no
 * auditable — así que se marca visualmente en vez de dejarlo como un dato más.
 */
export function ResumenLibreta({ resumen }: Props) {
  const sinVeredicto =
    (resumen.porVeredicto.pendiente ?? 0) + (resumen.porVeredicto.sospecha ?? 0);
  const bajo = resumen.pctCapa1 !== null && resumen.pctCapa1 < UMBRAL_CAPA1;

  return (
    <dl className={styles.resumen}>
      <div className={styles.kpi}>
        <dt>Clasificadas</dt>
        <dd>{resumen.total.toLocaleString('es-CO')}</dd>
      </div>

      <div className={styles.kpi}>
        <dt>Sin veredicto</dt>
        <dd>{sinVeredicto.toLocaleString('es-CO')}</dd>
      </div>

      <div className={`${styles.kpi} ${styles.destacado} ${bajo ? styles.alerta : ''}`}>
        <dt>Resueltas por regex (Capa 1)</dt>
        <dd>
          {/* `null` es "aún no hay datos", muy distinto de un 0 % que afirmaría
              que la regex no resuelve nada. */}
          {resumen.pctCapa1 === null ? '—' : `${resumen.pctCapa1}%`}
        </dd>
        {bajo && (
          <p className={styles.nota}>
            Por debajo del {UMBRAL_CAPA1}%: conviene engordar patrones antes que
            depender del modelo.
          </p>
        )}
      </div>
    </dl>
  );
}
