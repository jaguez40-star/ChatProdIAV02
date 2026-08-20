/**
 * Modelo de vista de Control (F1) — camelCase.
 *
 * Contrato de dos interceptores: el backend habla snake_case (Pydantic) y `mappers/`
 * es la única frontera donde cambia. Ninguna vista consume snake_case.
 */

export interface DiaArbol {
  dia: number;
  reporteId: number;
  tipo: string | null;
  archivo: string | null;
}

export interface MesArbol {
  mes: number;
  mesNombre: string;
  dias: DiaArbol[];
}

export interface AnioArbol {
  anio: number;
  meses: MesArbol[];
}

export interface TablaLogica {
  tablaIdx: number;
  tablaLabel: string | null;
  filas: number;
}

export interface HojaReporte {
  hoja: string;
  tablas: TablaLogica[];
}

export interface HojasReporte {
  reporteId: number;
  hojas: HojaReporte[];
}

/**
 * Los tres modos del visor. Es una unión cerrada a propósito: el dispatcher valida el
 * modo recibido y nunca cae a un fallback silencioso (Q5 — en el sistema viejo, un tipo
 * de panel no reconocido pintaba una tarjeta con campos ajenos sin ningún error visible).
 */
export type ModoTabla = 'fechas' | 'matriz' | 'texto';

/**
 * `dims` viene de una columna JSONB: puede traer texto, números o booleanos según la
 * hoja. El visor solo los muestra, no opera con ellos.
 */
export interface FilaTabla {
  dims: Record<string, unknown>;
  valores: Array<number | string | null>;
}

export interface TablaDatos {
  modo: ModoTabla;
  vacia: boolean;
  dimensiones: string[];
  meses: string[];
  filas: FilaTabla[];
  totalFilas: number;
}

/** Identifica una tabla concreta dentro de un reporte — la selección del visor. */
export interface SeleccionTabla {
  reporteId: number;
  hoja: string;
  tablaIdx: number;
  etiqueta: string;
}
