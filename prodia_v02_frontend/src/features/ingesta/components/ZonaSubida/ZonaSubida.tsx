import { useCallback, useRef, useState } from 'react';
import { FileSpreadsheet, Upload } from 'lucide-react';

import styles from './ZonaSubida.module.scss';

interface ZonaSubidaProps {
  onArchivo: (archivo: File) => void;
  deshabilitada?: boolean;
}

const EXTENSIONES = '.xlsm,.xlsx';

/**
 * Zona para soltar o elegir el `.xlsm` del reporte.
 *
 * La validación real vive en el backend; aquí solo se filtra la extensión para no
 * hacerle subir 125 MB a alguien que arrastró el archivo equivocado. El requisito de la
 * fecha en el nombre se anuncia antes de subir, no como error después: es el rechazo más
 * frecuente y el usuario no tiene forma de adivinarlo.
 */
export function ZonaSubida({ onArchivo, deshabilitada = false }: ZonaSubidaProps) {
  const [encima, setEncima] = useState(false);
  const entradaRef = useRef<HTMLInputElement>(null);

  const aceptar = useCallback(
    (archivos: FileList | null) => {
      const archivo = archivos?.[0];
      if (archivo) onArchivo(archivo);
    },
    [onArchivo],
  );

  return (
    <div
      className={`${styles.zona} ${encima ? styles.encima : ''} ${
        deshabilitada ? styles.deshabilitada : ''
      }`}
      onDragOver={(evento) => {
        evento.preventDefault();
        if (!deshabilitada) setEncima(true);
      }}
      onDragLeave={() => setEncima(false)}
      onDrop={(evento) => {
        evento.preventDefault();
        setEncima(false);
        if (!deshabilitada) aceptar(evento.dataTransfer.files);
      }}
    >
      <input
        ref={entradaRef}
        type="file"
        accept={EXTENSIONES}
        className={styles.entrada}
        disabled={deshabilitada}
        onChange={(evento) => aceptar(evento.target.files)}
        aria-label="Archivo de reporte"
      />

      <FileSpreadsheet className={styles.icono} size={40} aria-hidden />
      <p className={styles.titulo}>Arrastra el reporte aquí</p>
      <p className={styles.ayuda}>
        Archivos <strong>.xlsm</strong> o <strong>.xlsx</strong>. El nombre debe incluir la
        fecha en formato <code>AAAAMMDD</code> — por ejemplo,{' '}
        <code>20260815_Reporte.xlsm</code>.
      </p>

      <button
        type="button"
        className={styles.boton}
        disabled={deshabilitada}
        onClick={() => entradaRef.current?.click()}
      >
        <Upload size={16} aria-hidden />
        Elegir archivo
      </button>
    </div>
  );
}
