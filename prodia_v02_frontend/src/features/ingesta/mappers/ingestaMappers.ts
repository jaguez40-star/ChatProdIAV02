/**
 * Frontera snake_case (API) → camelCase (vista) de Ingesta.
 *
 * Los eventos SSE llegan como JSON suelto, no por `apiClient`, así que aquí se valida
 * además su forma: un evento con un estado desconocido se degrada a algo seguro en vez
 * de propagar un valor que ningún componente sabe pintar (espíritu de Q5).
 */

import type {
  ArchivoAceptado,
  CodigoError,
  EstadoFinal,
  EstadoHoja,
  HojaEnProgreso,
  HojaIngerida,
  ReporteExistente,
  ResultadoIngesta,
  TablaIngerida,
} from '../types/ingestaTypes';

// ── Formas crudas del backend ────────────────────────────────────────────────

interface TablaApi {
  tabla_idx: number;
  tabla_label: string;
  filas: number;
}

interface HojaApi {
  hoja: string;
  destino: string;
  filas: number;
  tablas?: TablaApi[];
}

interface ResultadoApi {
  archivo: string;
  reporte_id: number;
  fecha_reporte?: string | null;
  tipo_archivo: 'NEW' | 'STD';
  tiene_raw: boolean;
  filas_por_destino?: Record<string, number>;
  hojas?: HojaApi[];
  tablas_vacias?: string[];
}

export interface EventoHojaApi {
  tipo: 'hoja';
  hoja: string;
  estado: string;
  destino?: string | null;
  filas?: number | null;
  tablas?: TablaApi[];
  detalle?: string | null;
}

export interface EventoInicioApi {
  tipo: 'inicio';
  archivo: string;
  tipo_archivo: 'NEW' | 'STD';
  hojas: string[];
  total: number;
}

export interface EventoAvanceApi {
  tipo: 'avance';
  hoja: string;
  destino: string;
  filas: number;
}

export interface EventoFinApi {
  tipo: 'fin';
  estado: string;
  resultado?: ResultadoApi | null;
  code?: string | null;
  hoja?: string | null;
  detalle?: string | null;
}

const ESTADOS_HOJA: readonly EstadoHoja[] = ['procesando', 'procesada', 'vacia', 'error'];

const CODIGOS: readonly CodigoError[] = [
  'ARCHIVO_INVALIDO',
  'FECHA_AUSENTE',
  'ARCHIVO_DEMASIADO_GRANDE',
  'HOJA_ILEGIBLE',
  'BD_NO_DISPONIBLE',
  'ERROR_INTERNO',
];

/**
 * Un estado desconocido se trata como `error`, nunca como éxito: ante la duda, es
 * preferible que el usuario revise una hoja de más a que dé por buena una que falló.
 */
export function aEstadoHoja(valor: string): EstadoHoja {
  return ESTADOS_HOJA.includes(valor as EstadoHoja) ? (valor as EstadoHoja) : 'error';
}

/**
 * Un estado final desconocido se trata como `revertido`. Es la degradación segura: dar
 * por confirmada una ingesta que no lo está haría creer al usuario que tiene datos.
 */
export function aEstadoFinal(valor: string): EstadoFinal {
  return valor === 'confirmado' ? 'confirmado' : 'revertido';
}

export function aCodigoError(valor: string | null | undefined): CodigoError | null {
  if (!valor) return null;
  return CODIGOS.includes(valor as CodigoError) ? (valor as CodigoError) : 'ERROR_INTERNO';
}

function aTablas(tablas: TablaApi[] | undefined): TablaIngerida[] {
  return (tablas ?? []).map((tabla) => ({
    tablaIdx: tabla.tabla_idx,
    tablaLabel: tabla.tabla_label,
    filas: tabla.filas,
  }));
}

export function aHojaEnProgreso(evento: EventoHojaApi): HojaEnProgreso {
  return {
    hoja: evento.hoja,
    estado: aEstadoHoja(evento.estado),
    destino: evento.destino ?? null,
    filas: evento.filas ?? null,
    tablas: aTablas(evento.tablas),
    detalle: evento.detalle ?? null,
  };
}

function aHojaIngerida(hoja: HojaApi): HojaIngerida {
  return {
    hoja: hoja.hoja,
    destino: hoja.destino,
    filas: hoja.filas,
    tablas: aTablas(hoja.tablas),
  };
}

export function aResultadoIngesta(datos: ResultadoApi): ResultadoIngesta {
  return {
    archivo: datos.archivo,
    reporteId: datos.reporte_id,
    fechaReporte: datos.fecha_reporte ?? null,
    tipoArchivo: datos.tipo_archivo,
    tieneRaw: datos.tiene_raw,
    filasPorDestino: datos.filas_por_destino ?? {},
    hojas: (datos.hojas ?? []).map(aHojaIngerida),
    tablasVacias: datos.tablas_vacias ?? [],
  };
}

export function aArchivoAceptado(datos: {
  id: string;
  archivo: string;
  hash: string;
  fecha_reporte: string;
}): ArchivoAceptado {
  return {
    id: datos.id,
    archivo: datos.archivo,
    hash: datos.hash,
    fechaReporte: datos.fecha_reporte,
  };
}

export function aReporteExistente(datos: {
  existe: boolean;
  reporte_id?: number | null;
  archivo?: string | null;
  tipo_archivo?: string | null;
  ingerido_en?: string | null;
  mismo_contenido?: boolean | null;
}): ReporteExistente {
  return {
    existe: datos.existe,
    reporteId: datos.reporte_id ?? null,
    archivo: datos.archivo ?? null,
    tipoArchivo: datos.tipo_archivo ?? null,
    ingeridoEn: datos.ingerido_en ?? null,
    mismoContenido: datos.mismo_contenido ?? null,
  };
}

/** Total de filas escritas, para el resumen final. */
export function totalDeFilas(resultado: ResultadoIngesta): number {
  return Object.values(resultado.filasPorDestino).reduce((suma, n) => suma + n, 0);
}
