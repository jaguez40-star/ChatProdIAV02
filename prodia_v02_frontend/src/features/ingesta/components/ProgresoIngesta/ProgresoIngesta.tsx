import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  Loader2,
  MinusCircle,
  XCircle,
} from 'lucide-react';

import { formatBl } from '../../../../shared/utils/format';
import type {
  EstadoHoja,
  FaseIngesta,
  HojaEnProgreso,
  ResultadoIngesta,
} from '../../types/ingestaTypes';
import styles from './ProgresoIngesta.module.scss';

interface ProgresoIngestaProps {
  fase: FaseIngesta;
  hojas: HojaEnProgreso[];
  totalHojas: number;
  resultado: ResultadoIngesta | null;
  error: string | null;
  hojaDelError: string | null;
  onReiniciar: () => void;
}

const ICONOS: Record<EstadoHoja, typeof CheckCircle2> = {
  procesando: Loader2,
  procesada: CheckCircle2,
  vacia: MinusCircle,
  error: XCircle,
};

const ETIQUETAS: Record<EstadoHoja, string> = {
  procesando: 'Procesando',
  procesada: 'Procesada',
  vacia: 'Sin filas',
  error: 'Error',
};

function FilaHoja({ hoja }: { hoja: HojaEnProgreso }) {
  const Icono = ICONOS[hoja.estado];
  return (
    <li className={`${styles.hoja} ${styles[hoja.estado]}`}>
      <Icono
        size={16}
        className={hoja.estado === 'procesando' ? styles.girando : undefined}
        aria-hidden
      />
      <span className={styles.nombreHoja}>{hoja.hoja}</span>
      <span className={styles.estadoHoja}>{ETIQUETAS[hoja.estado]}</span>
      <span className={styles.filasHoja}>
        {hoja.filas !== null ? formatBl(hoja.filas) : ''}
      </span>
      {hoja.detalle && <p className={styles.detalleHoja}>{hoja.detalle}</p>}
    </li>
  );
}

/**
 * Panel de progreso y resultado.
 *
 * La distinción que sostiene todo el diseño: mientras corre, las hojas se muestran como
 * **procesadas**, no como guardadas. Hasta que llega el evento final, la transacción
 * puede revertirse entera y esas filas desaparecerían. Por eso el resumen de cierre es
 * explícito en ambos sentidos: confirma que los datos están, o avisa de que **nada** se
 * guardó pese a lo que se vio en verde.
 *
 * Las tablas vacías se listan aparte porque son la señal de un layout cambiado: el
 * extractor no falla, simplemente deja de encontrar datos, y sin mostrarlo eso pasaría
 * inadvertido.
 */
export function ProgresoIngesta({
  fase,
  hojas,
  totalHojas,
  resultado,
  error,
  hojaDelError,
  onReiniciar,
}: ProgresoIngestaProps) {
  const terminadas = hojas.filter((h) => h.estado !== 'procesando').length;
  const porcentaje = totalHojas > 0 ? Math.round((terminadas / totalHojas) * 100) : 0;
  const enCurso = fase === 'procesando';

  return (
    <div className={styles.panel}>
      {enCurso && (
        <>
          <div className={styles.cabecera}>
            <h3 className={styles.titulo}>
              <Loader2 size={18} className={styles.girando} aria-hidden />
              Procesando el reporte
            </h3>
            <span className={styles.contador}>
              {terminadas} de {totalHojas || '—'} hojas
            </span>
          </div>
          <div
            className={styles.barra}
            role="progressbar"
            aria-valuenow={porcentaje}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div className={styles.relleno} style={{ width: `${porcentaje}%` }} />
          </div>
          <p className={styles.pendiente}>
            <CircleDashed size={14} aria-hidden />
            Los datos aún <strong>no están guardados</strong>: se confirman al terminar.
          </p>
        </>
      )}

      {hojas.length > 0 && (
        <ul className={styles.listaHojas}>
          {hojas.map((hoja) => (
            <FilaHoja key={hoja.hoja} hoja={hoja} />
          ))}
        </ul>
      )}

      {fase === 'confirmada' && resultado && (
        <div className={`${styles.resumen} ${styles.exito}`} role="status">
          <h3 className={styles.tituloResumen}>
            <CheckCircle2 size={18} aria-hidden />
            Ingesta confirmada
          </h3>
          <dl className={styles.datos}>
            <div>
              <dt>Reporte</dt>
              <dd>#{resultado.reporteId}</dd>
            </div>
            <div>
              <dt>Fecha</dt>
              <dd>{resultado.fechaReporte ?? '—'}</dd>
            </div>
            <div>
              <dt>Tipo</dt>
              <dd>{resultado.tipoArchivo}</dd>
            </div>
            <div>
              <dt>Hojas</dt>
              <dd>{resultado.hojas.length}</dd>
            </div>
          </dl>

          {resultado.tablasVacias.length > 0 && (
            <details className={styles.vacias}>
              <summary>
                {resultado.tablasVacias.length} tabla
                {resultado.tablasVacias.length === 1 ? '' : 's'} sin filas
              </summary>
              <p className={styles.vaciasAyuda}>
                Puede ser normal si esa tabla viene vacía en el archivo. Si no lo es, suele
                indicar que el diseño de la hoja cambió y el extractor ya no la reconoce.
              </p>
              <ul>
                {resultado.tablasVacias.map((tabla) => (
                  <li key={tabla}>{tabla}</li>
                ))}
              </ul>
            </details>
          )}

          <button type="button" className={styles.boton} onClick={onReiniciar}>
            Cargar otro reporte
          </button>
        </div>
      )}

      {fase === 'revertida' && (
        <div className={`${styles.resumen} ${styles.fallo}`} role="alert">
          <h3 className={styles.tituloResumen}>
            <AlertCircle size={18} aria-hidden />
            No se guardó ningún dato
          </h3>
          <p className={styles.textoFallo}>
            {error ?? 'La ingesta no pudo completarse.'}
          </p>
          {hojaDelError && (
            <p className={styles.textoFallo}>
              Falló al procesar la hoja <strong>{hojaDelError}</strong>.
            </p>
          )}
          <p className={styles.notaFallo}>
            La carga se revirtió por completo: la base de datos quedó tal y como estaba
            antes, aunque algunas hojas se hubieran mostrado como procesadas.
          </p>
          <button type="button" className={styles.boton} onClick={onReiniciar}>
            Intentar de nuevo
          </button>
        </div>
      )}
    </div>
  );
}
