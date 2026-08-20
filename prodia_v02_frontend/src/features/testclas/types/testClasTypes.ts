/**
 * Tipos de Test Clas — el laboratorio del clasificador.
 *
 * `FiltroLibreta` es una unión cerrada, igual que en el backend: el selector de
 * filtros no puede mandar un valor inválido ni compilando. En el sistema viejo
 * el filtro era texto libre y una errata devolvía la libreta entera mientras el
 * revisor creía estar viendo solo las sospechas.
 */

import type { components } from '../../../shared/types/api';

/**
 * Se toma del contrato de la API, no de `features/consulta` — un import
 * cross-feature violaría ADR-001. Además, así el tipo lo fija el backend: si
 * algún día apareciera un quinto grupo, este archivo lo hereda solo.
 */
export type GrupoQ = components['schemas']['FilaLibreta']['grupo_asignado'];

export type FiltroLibreta = 'todas' | 'pendientes' | 'sospecha' | 'corregidas';

/**
 * El estado de juicio de una fila.
 *
 * ⚠️ `sospecha` NO es un veredicto: es una bandera de prioridad que puso una
 * señal automática. Una fila sospechosa sigue **sin juzgar**, y por eso la UI la
 * pinta como pendiente (con distintivo), nunca como resuelta.
 */
export type Veredicto =
  | 'pendiente'
  | 'sospecha'
  | 'confirmado_usuario'
  | 'corregido_usuario'
  | 'confirmado_revision'
  | 'corregido_revision';

export interface FilaLibreta {
  id: number;
  ts: string | null;
  usuario: string | null;
  conversacionId: string | null;
  textoPregunta: string;
  grupoAsignado: GrupoQ;
  capaResolutora: string;
  entidadCruda: string | null;
  llmDiag: string | null;
  veredicto: Veredicto;
  grupoCorrecto: GrupoQ | null;
  fuenteVeredicto: string | null;
  notaRevision: string | null;
}

/** Los KPIs del ciclo de crecimiento del clasificador. */
export interface ResumenLibreta {
  total: number;
  porVeredicto: Record<string, number>;
  /**
   * % resuelto por la Capa 1 (regex pura). `null` cuando la libreta está vacía —
   * un 0 % afirmaría que la regex no resuelve nada, que es una conclusión muy
   * distinta de «aún no hay datos».
   *
   * Es el KPI que justifica la pantalla: por debajo del 50 %, el motor depende
   * demasiado del LLM y lo que toca es engordar patrones (regla A4).
   */
  pctCapa1: number | null;
}

export interface Libreta {
  filas: FilaLibreta[];
  resumen: ResumenLibreta;
  /** El backend devolvió tantas filas como caben: es probable que haya más. */
  truncado: boolean;
}

export interface ResultadoEscaneo {
  sospechasNuevas: number;
  filasRevisadas: number;
}

export interface ResultadoLote {
  aplicados: number;
  total: number;
}

/** Un juicio del Control 3. `null` en `grupoCorrecto` significa «confirmar». */
export interface VeredictoDeRevision {
  logId: number;
  grupoCorrecto: GrupoQ | null;
}

export function esPendiente(veredicto: Veredicto): boolean {
  return veredicto === 'pendiente' || veredicto === 'sospecha';
}
