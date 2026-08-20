/**
 * Frontera snake_case (API) → camelCase (vista) de Control.
 *
 * Es el único sitio del feature donde aparece snake_case. Los mappers son funciones
 * puras y sin dependencias, así que se testean solos.
 */

import type {
  AnioArbol,
  FilaTabla,
  HojasReporte,
  ModoTabla,
  TablaDatos,
} from '../types/controlTypes';

/** Forma cruda que devuelve el backend (Pydantic, snake_case). */
interface DiaArbolApi {
  dia: number;
  reporte_id: number;
  tipo?: string | null;
  archivo?: string | null;
}

interface MesArbolApi {
  mes: number;
  mes_nombre: string;
  dias: DiaArbolApi[];
}

interface AnioArbolApi {
  anio: number;
  meses: MesArbolApi[];
}

interface TablaLogicaApi {
  tabla_idx: number;
  tabla_label?: string | null;
  filas: number;
}

interface HojaReporteApi {
  hoja: string;
  tablas: TablaLogicaApi[];
}

interface HojasReporteApi {
  reporte_id: number;
  hojas: HojaReporteApi[];
}

interface FilaTablaApi {
  dims: Record<string, unknown>;
  valores: Array<number | string | null>;
}

interface TablaDatosApi {
  modo?: string;
  vacia?: boolean;
  dimensiones: string[];
  meses: string[];
  filas: FilaTablaApi[];
  total_filas?: number;
}

const MODOS_VALIDOS: readonly ModoTabla[] = ['fechas', 'matriz', 'texto'];

/**
 * Valida el modo en la frontera, no en el render (Q5). Si el backend enviara un modo
 * desconocido, se degrada a `fechas` —el más genérico— en vez de dejar que un
 * dispatcher pinte una tabla con la estructura equivocada sin avisar.
 */
function aModo(valor: string | undefined): ModoTabla {
  return MODOS_VALIDOS.includes(valor as ModoTabla) ? (valor as ModoTabla) : 'fechas';
}

export function aArbol(datos: AnioArbolApi[]): AnioArbol[] {
  return datos.map((anio) => ({
    anio: anio.anio,
    meses: anio.meses.map((mes) => ({
      mes: mes.mes,
      mesNombre: mes.mes_nombre,
      dias: mes.dias.map((dia) => ({
        dia: dia.dia,
        reporteId: dia.reporte_id,
        tipo: dia.tipo ?? null,
        archivo: dia.archivo ?? null,
      })),
    })),
  }));
}

export function aHojasReporte(datos: HojasReporteApi): HojasReporte {
  return {
    reporteId: datos.reporte_id,
    hojas: datos.hojas.map((hoja) => ({
      hoja: hoja.hoja,
      tablas: hoja.tablas.map((tabla) => ({
        tablaIdx: tabla.tabla_idx,
        tablaLabel: tabla.tabla_label ?? null,
        filas: tabla.filas,
      })),
    })),
  };
}

export function aFilaTabla(fila: FilaTablaApi): FilaTabla {
  return { dims: fila.dims, valores: fila.valores };
}

export function aTablaDatos(datos: TablaDatosApi): TablaDatos {
  return {
    modo: aModo(datos.modo),
    vacia: datos.vacia ?? false,
    dimensiones: datos.dimensiones,
    meses: datos.meses,
    filas: datos.filas.map(aFilaTabla),
    totalFilas: datos.total_filas ?? 0,
  };
}
