import { AlertTriangle, CheckCircle2, Info } from 'lucide-react';

import type { ArchivoAceptado, ReporteExistente } from '../../types/ingestaTypes';
import styles from './AvisoReingesta.module.scss';

interface AvisoReingestaProps {
  archivo: ArchivoAceptado;
  existente: ReporteExistente | null;
  onConfirmar: () => void;
  onCancelar: () => void;
}

function formatearFecha(iso: string | null): string {
  if (!iso) return '—';
  const fecha = new Date(iso);
  return Number.isNaN(fecha.getTime()) ? iso : fecha.toLocaleDateString('es-CO');
}

/**
 * Confirmación previa a procesar, con el aviso de reingesta cuando aplica.
 *
 * Reingerir es seguro —el ETL es idempotente y sustituye el reporte de esa fecha—, así
 * que esto no es una advertencia de peligro: es información para que nadie sobrescriba
 * sin saberlo. Por eso se distinguen tres casos, y el más tranquilizador (mismo archivo)
 * se muestra como tal en vez de como alerta.
 */
export function AvisoReingesta({
  archivo,
  existente,
  onConfirmar,
  onCancelar,
}: AvisoReingestaProps) {
  const yaExiste = existente?.existe ?? false;
  const esElMismo = existente?.mismoContenido === true;

  return (
    <div className={styles.aviso}>
      <header className={styles.cabecera}>
        <h3 className={styles.titulo}>Listo para procesar</h3>
        <p className={styles.archivo}>{archivo.archivo}</p>
        <p className={styles.meta}>
          Fecha del reporte: <strong>{archivo.fechaReporte}</strong>
        </p>
      </header>

      {yaExiste && esElMismo && (
        <div className={`${styles.nota} ${styles.info}`} role="status">
          <Info size={18} aria-hidden />
          <div>
            <p className={styles.notaTitulo}>Este archivo ya se ingirió</p>
            <p className={styles.notaTexto}>
              El contenido es idéntico al que se cargó el{' '}
              {formatearFecha(existente?.ingeridoEn ?? null)}. Procesarlo de nuevo dejará
              los datos igual que están.
            </p>
          </div>
        </div>
      )}

      {yaExiste && !esElMismo && (
        <div className={`${styles.nota} ${styles.alerta}`} role="alert">
          <AlertTriangle size={18} aria-hidden />
          <div>
            <p className={styles.notaTitulo}>Ya hay un reporte de esta fecha</p>
            <p className={styles.notaTexto}>
              Se cargó <strong>{existente?.archivo}</strong> el{' '}
              {formatearFecha(existente?.ingeridoEn ?? null)}. Al continuar, los datos de
              esa fecha se reemplazarán por los de este archivo.
            </p>
          </div>
        </div>
      )}

      {!yaExiste && (
        <div className={`${styles.nota} ${styles.ok}`} role="status">
          <CheckCircle2 size={18} aria-hidden />
          <div>
            <p className={styles.notaTitulo}>Reporte nuevo</p>
            <p className={styles.notaTexto}>
              No hay ningún reporte cargado con esta fecha.
            </p>
          </div>
        </div>
      )}

      <div className={styles.acciones}>
        <button type="button" className={styles.secundario} onClick={onCancelar}>
          Cancelar
        </button>
        <button type="button" className={styles.primario} onClick={onConfirmar}>
          {yaExiste ? 'Reemplazar y procesar' : 'Procesar'}
        </button>
      </div>
    </div>
  );
}
