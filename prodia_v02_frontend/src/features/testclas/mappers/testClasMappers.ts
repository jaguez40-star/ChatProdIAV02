/**
 * Mappers de Test Clas — `snake_case` del backend a `camelCase` del frontend.
 *
 * **Degradación segura**: un veredicto que el frontend no conozca se trata como
 * `pendiente`, no se pinta como resuelto. Es la dirección correcta del error: en
 * el peor caso el revisor vuelve a mirar algo ya juzgado; al revés, un caso sin
 * juzgar desaparecería de la cola y nadie lo sabría.
 */

import type { components } from '../../../shared/types/api';
import type {
  FilaLibreta,
  Libreta,
  ResultadoEscaneo,
  ResultadoLote,
  ResumenLibreta,
  Veredicto,
} from '../types/testClasTypes';

type FilaApi = components['schemas']['FilaLibreta'];
type LibretaApi = components['schemas']['LibretaOut'];
type ResumenApi = components['schemas']['ResumenLibretaOut'];
type EscaneoApi = components['schemas']['EscaneoOut'];
type LoteApi = components['schemas']['VeredictoLoteOut'];

const VEREDICTOS_CONOCIDOS = new Set<Veredicto>([
  'pendiente',
  'sospecha',
  'confirmado_usuario',
  'corregido_usuario',
  'confirmado_revision',
  'corregido_revision',
]);

function aVeredicto(valor: string): Veredicto {
  return VEREDICTOS_CONOCIDOS.has(valor as Veredicto)
    ? (valor as Veredicto)
    : 'pendiente';
}

export function aFilaLibreta(api: FilaApi): FilaLibreta {
  return {
    id: api.id,
    ts: api.ts ?? null,
    usuario: api.usuario ?? null,
    conversacionId: api.conversacion_id ?? null,
    textoPregunta: api.texto_pregunta,
    grupoAsignado: api.grupo_asignado,
    capaResolutora: api.capa_resolutora,
    entidadCruda: api.entidad_cruda ?? null,
    llmDiag: api.llm_diag ?? null,
    veredicto: aVeredicto(api.veredicto),
    grupoCorrecto: api.grupo_correcto ?? null,
    fuenteVeredicto: api.fuente_veredicto ?? null,
    notaRevision: api.nota_revision ?? null,
  };
}

export function aResumenLibreta(api: ResumenApi): ResumenLibreta {
  return {
    total: api.total,
    porVeredicto: api.por_veredicto,
    pctCapa1: api.pct_capa1 ?? null,
  };
}

export function aLibreta(api: LibretaApi): Libreta {
  return {
    filas: api.filas.map(aFilaLibreta),
    resumen: aResumenLibreta(api.resumen),
    truncado: api.truncado,
  };
}

export function aResultadoEscaneo(api: EscaneoApi): ResultadoEscaneo {
  return {
    sospechasNuevas: api.sospechas_nuevas,
    filasRevisadas: api.filas_revisadas,
  };
}

export function aResultadoLote(api: LoteApi): ResultadoLote {
  return { aplicados: api.aplicados, total: api.total };
}
