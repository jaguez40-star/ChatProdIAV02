/**
 * Modelo de vista de Ingesta (F3) — camelCase.
 *
 * El vocabulario de estados es el que corrige la mentira del sistema viejo: allí cada
 * hoja se marcaba «ok» aunque la transacción pudiera revertirse después. Aquí una hoja
 * queda `procesada` —insertada, pendiente de confirmar— y solo el evento final dice si
 * los datos se guardaron de verdad.
 */

/** Estado de una hoja mientras se procesa. */
export type EstadoHoja = 'procesando' | 'procesada' | 'vacia' | 'error';

/**
 * Cómo terminó la ingesta.
 *
 * - `confirmado`: la transacción hizo commit; lo que se vio en pantalla está en la base.
 * - `revertido`: hubo rollback. **Nada** se guardó, aunque varias hojas se hubieran
 *   mostrado como procesadas.
 */
export type EstadoFinal = 'confirmado' | 'revertido';

/** Códigos de error del backend, para poder decirle al usuario qué hacer. */
export type CodigoError =
  | 'ARCHIVO_INVALIDO'
  | 'FECHA_AUSENTE'
  | 'ARCHIVO_DEMASIADO_GRANDE'
  | 'HOJA_ILEGIBLE'
  | 'BD_NO_DISPONIBLE'
  | 'ERROR_INTERNO';

export interface TablaIngerida {
  tablaIdx: number;
  tablaLabel: string;
  filas: number;
}

export interface HojaIngerida {
  hoja: string;
  destino: string;
  filas: number;
  tablas: TablaIngerida[];
}

export interface ResultadoIngesta {
  archivo: string;
  reporteId: number;
  fechaReporte: string | null;
  tipoArchivo: 'NEW' | 'STD';
  tieneRaw: boolean;
  filasPorDestino: Record<string, number>;
  hojas: HojaIngerida[];
  /** Tablas declaradas que no produjeron ninguna fila — señal de un layout cambiado. */
  tablasVacias: string[];
}

/** Una hoja tal y como se muestra en el panel de progreso. */
export interface HojaEnProgreso {
  hoja: string;
  estado: EstadoHoja;
  destino: string | null;
  filas: number | null;
  tablas: TablaIngerida[];
  detalle: string | null;
}

/** Lo que devuelve la subida, antes de procesar nada. */
export interface ArchivoAceptado {
  id: string;
  archivo: string;
  hash: string;
  fechaReporte: string;
}

/** Aviso de que ya existe un reporte para esa fecha. */
export interface ReporteExistente {
  existe: boolean;
  reporteId: number | null;
  archivo: string | null;
  tipoArchivo: string | null;
  ingeridoEn: string | null;
  /** `true` si el archivo que se va a subir es idéntico al ya ingerido. */
  mismoContenido: boolean | null;
}

/** Fase del flujo completo, de principio a fin. */
export type FaseIngesta =
  | 'inactiva'
  | 'subiendo'
  | 'confirmando'
  | 'procesando'
  | 'confirmada'
  | 'revertida';
