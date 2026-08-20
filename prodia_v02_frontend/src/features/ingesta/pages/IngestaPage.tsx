import { Loader2 } from 'lucide-react';

import { AvisoReingesta } from '../components/AvisoReingesta';
import { ProgresoIngesta } from '../components/ProgresoIngesta';
import { ZonaSubida } from '../components/ZonaSubida';
import { useIngesta } from '../hooks/useIngesta';
import styles from './IngestaPage.module.scss';

/**
 * Página de Ingesta: cargar un reporte `.xlsm` a la base de datos.
 *
 * El flujo tiene tres momentos y la página muestra **uno solo a la vez**: elegir el
 * archivo, confirmar (con el aviso de reingesta si la fecha ya existe) y procesar. Se
 * evita a propósito mostrarlos todos apilados: durante una carga de varios minutos, lo
 * único que importa es el progreso.
 */
export default function IngestaPage() {
  const { estado, seleccionarArchivo, procesar, reiniciar } = useIngesta();
  const { fase, archivo, subida, existente } = estado;

  const eligiendo = fase === 'inactiva' || fase === 'subiendo';
  const confirmando = fase === 'confirmando' && subida !== null;
  const mostrandoProgreso =
    fase === 'procesando' || fase === 'confirmada' || fase === 'revertida';

  return (
    <div className={styles.pagina}>
      <header className={styles.cabecera}>
        <h1 className={styles.titulo}>Ingesta de reportes</h1>
        <p className={styles.subtitulo}>
          Carga el reporte diario de producción a la base de datos. El archivo se procesa
          completo o no se procesa: si algo falla a mitad, no queda un reporte parcial.
        </p>
      </header>

      {eligiendo && (
        <>
          <ZonaSubida onArchivo={seleccionarArchivo} deshabilitada={fase === 'subiendo'} />
          {fase === 'subiendo' && (
            <p className={styles.subiendo} role="status">
              <Loader2 size={16} className={styles.girando} aria-hidden />
              Subiendo {archivo?.name}…
            </p>
          )}
        </>
      )}

      {confirmando && (
        <AvisoReingesta
          archivo={subida}
          existente={existente}
          onConfirmar={procesar}
          onCancelar={reiniciar}
        />
      )}

      {mostrandoProgreso && (
        <ProgresoIngesta
          fase={fase}
          hojas={estado.hojas}
          totalHojas={estado.totalHojas}
          resultado={estado.resultado}
          error={estado.error}
          hojaDelError={estado.hojaDelError}
          onReiniciar={reiniciar}
        />
      )}

      {/* Un fallo durante la subida ocurre antes de que haya progreso que mostrar. */}
      {fase === 'revertida' && !mostrandoProgreso && estado.error && (
        <p className={styles.errorSubida} role="alert">
          {estado.error}
        </p>
      )}
    </div>
  );
}
