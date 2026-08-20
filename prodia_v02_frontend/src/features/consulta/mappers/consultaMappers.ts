/**
 * snake_case del backend → camelCase de la vista.
 *
 * Mismo contrato que en Análisis: el backend no cambia sus nombres por
 * comodidad del frontend, y el frontend no consume snake_case. Este archivo es
 * el único punto donde conviven las dos convenciones.
 *
 * 🔑 **Aquí se valida el tipo de panel (Q5).** `datos` llega como `unknown`
 * porque su forma depende del tipo, así que la frontera de confianza está en
 * `aPanel`: si el `tipo` no es uno de los nueve conocidos, devuelve `null` en
 * vez de dejar pasar un objeto sin forma. El sistema viejo no hace esta
 * comprobación y pinta una tarjeta con campos ajenos.
 */

import type {
  AnalizaFocoScope,
  CapaResolutora,
  CuantKpi,
  CuantRank,
  CuantSerie,
  CuantVar,
  GrupoQ,
  JerarqArbol,
  JerarqOperador,
  JerarqRank,
  P50Vp,
  Panel,
  Producto,
  RespuestaQ,
  TipoPanel,
} from '../types/consultaTypes';

// ── Acceso seguro a datos de forma desconocida ───────────────────────────────

function campo(origen: unknown, clave: string): unknown {
  if (origen && typeof origen === 'object' && clave in origen) {
    return (origen as Record<string, unknown>)[clave];
  }
  return undefined;
}

function comoTexto(valor: unknown, porDefecto = ''): string {
  return typeof valor === 'string' ? valor : porDefecto;
}

/** Preserva `null`: en este dominio significa "no hay meta", que NO es cero. */
function comoNumeroONulo(valor: unknown): number | null {
  return typeof valor === 'number' && Number.isFinite(valor) ? valor : null;
}

function comoNumero(valor: unknown, porDefecto = 0): number {
  return typeof valor === 'number' && Number.isFinite(valor) ? valor : porDefecto;
}

function comoBooleano(valor: unknown): boolean {
  return valor === true;
}

function comoLista(valor: unknown): unknown[] {
  return Array.isArray(valor) ? valor : [];
}

function comoTextos(valor: unknown): string[] {
  return comoLista(valor).map((v) => comoTexto(v));
}

function comoProducto(valor: unknown): Producto {
  return valor === 'gas' || valor === 'blancos' ? valor : 'crudo';
}

// ── Q5: la frontera de confianza ─────────────────────────────────────────────

const TIPOS_CONOCIDOS: readonly TipoPanel[] = [
  'cuant_kpi',
  'cuant_serie',
  'cuant_var',
  'cuant_rank',
  'jerarq_arbol',
  'jerarq_operador',
  'jerarq_rank',
  'p50_vp',
  'analiza_foco',
];

function esTipoConocido(valor: unknown): valor is TipoPanel {
  return typeof valor === 'string' && (TIPOS_CONOCIDOS as readonly string[]).includes(valor);
}

function aCuantKpi(d: unknown): CuantKpi {
  const mes = campo(d, 'mes');
  return {
    entidadCualificada: comoTexto(campo(d, 'entidad_cualificada')),
    producto: comoProducto(campo(d, 'producto')),
    unidad: comoTexto(campo(d, 'unidad'), 'bbl'),
    real: comoNumero(campo(campo(d, 'resultado'), 'valor')),
    referenciaValor: comoNumeroONulo(campo(d, 'referencia_valor')),
    referenciaLabel: comoTexto(campo(d, 'referencia_label'), 'presupuesto'),
    // `null` = sin meta. Convertirlo a 0 diría "vas al 0 %", que es inventar
    // un incumplimiento (Q2).
    cumplimientoPct: comoNumeroONulo(campo(d, 'cumplimiento_pct')),
    estado: comoTexto(campo(d, 'estado')),
    mes: {
      nombre: comoTexto(campo(mes, 'nombre')),
      anio: comoNumero(campo(mes, 'anio')),
      completo: comoBooleano(campo(mes, 'completo')),
      diasConData: comoNumero(campo(mes, 'dias_con_data')),
      diasDelMes: comoNumero(campo(mes, 'dias_del_mes')),
    },
    avisos: comoTextos(campo(d, 'avisos')),
  };
}

function aCuantSerie(d: unknown): CuantSerie {
  return {
    entidadCualificada: comoTexto(campo(d, 'entidad_cualificada')),
    producto: comoProducto(campo(d, 'producto')),
    unidad: comoTexto(campo(d, 'unidad'), 'bbl'),
    serie: comoLista(campo(d, 'serie')).map((p) => ({
      mes: comoTexto(campo(p, 'mes')),
      valor: comoNumero(campo(p, 'valor')),
    })),
    promedio: comoNumeroONulo(campo(d, 'promedio')),
    anio: comoNumero(campo(d, 'anio')),
    proyeccionMes: campo(d, 'proyeccion_mes') === null ? null : comoTexto(campo(d, 'proyeccion_mes')) || null,
    avisos: comoTextos(campo(d, 'avisos')),
  };
}

function aDelta(v: unknown) {
  return {
    de: comoTexto(campo(v, 'de')),
    a: comoTexto(campo(v, 'a')),
    delta: comoNumero(campo(v, 'delta')),
    pct: comoNumeroONulo(campo(v, 'pct')),
  };
}

function aCuantVar(d: unknown): CuantVar {
  const deltas = comoLista(campo(d, 'deltas')).map(aDelta);
  return {
    entidadCualificada: comoTexto(campo(d, 'entidad_cualificada')),
    producto: comoProducto(campo(d, 'producto')),
    unidad: comoTexto(campo(d, 'unidad'), 'bbl'),
    deltas,
    ultimo: aDelta(campo(d, 'ultimo')),
    anio: comoNumero(campo(d, 'anio')),
    proyeccionMes: campo(d, 'proyeccion_mes') === null ? null : comoTexto(campo(d, 'proyeccion_mes')) || null,
    avisos: comoTextos(campo(d, 'avisos')),
  };
}

function aCuantRank(d: unknown): CuantRank {
  const nivel = campo(d, 'nivel_ranking');
  const metrica = campo(d, 'metrica');
  const direccion = campo(d, 'direccion');
  return {
    nivelRanking: nivel === 'activo' ? 'activo' : 'campo',
    metrica: metrica === 'gap' ? 'gap' : 'real',
    direccion: direccion === 'bottom' ? 'bottom' : 'top',
    producto: comoProducto(campo(d, 'producto')),
    unidad: comoTexto(campo(d, 'unidad'), 'bbl'),
    periodoLabel: comoTexto(campo(d, 'periodo_label')),
    esProyeccion: comoBooleano(campo(d, 'es_proyeccion')),
    items: comoLista(campo(d, 'items')).map((i) => ({
      pos: comoNumero(campo(i, 'pos')),
      entidad: comoTexto(campo(i, 'entidad')),
      valor: comoNumero(campo(i, 'valor')),
      gap: comoNumero(campo(i, 'gap')),
      ppto: comoNumero(campo(i, 'ppto')),
      operador: comoTexto(campo(i, 'operador')),
      esEcp: comoBooleano(campo(i, 'es_ecp')),
    })),
    totalUniverso: comoNumero(campo(d, 'total_universo')),
    sinRegistro: comoNumero(campo(d, 'sin_registro')),
    concentracionPct: comoNumeroONulo(campo(d, 'concentracion_pct')),
  };
}

function aJerarqArbol(d: unknown): JerarqArbol {
  return {
    entidad: comoTexto(campo(d, 'entidad')),
    nivel: comoTexto(campo(d, 'nivel')),
    puente: comoBooleano(campo(d, 'puente')),
    padres: comoLista(campo(d, 'padres')).map((p) => ({
      nivel: comoTexto(campo(p, 'nivel')),
      items: comoTextos(campo(p, 'items')),
    })),
    hijosGrupos: comoLista(campo(d, 'hijos_grupos')).map((g) => ({
      nivel: comoTexto(campo(g, 'nivel')),
      items: comoTextos(campo(g, 'items')),
      total: comoNumero(campo(g, 'total')),
      truncado: comoBooleano(campo(g, 'truncado')),
    })),
    pozos: comoNumeroONulo(campo(d, 'pozos')),
    operador: campo(d, 'operador') ? comoTexto(campo(d, 'operador')) : null,
    fueraEstructura: comoBooleano(campo(d, 'fuera_estructura')),
  };
}

function aJerarqOperador(d: unknown): JerarqOperador {
  return {
    entidad: comoTexto(campo(d, 'entidad')),
    campos: comoTextos(campo(d, 'campos')),
    total: comoNumero(campo(d, 'total')),
    truncado: comoBooleano(campo(d, 'truncado')),
  };
}

function aJerarqRank(d: unknown): JerarqRank {
  return {
    subject: comoTexto(campo(d, 'subject')),
    conteo: comoTexto(campo(d, 'conteo')),
    asc: comoBooleano(campo(d, 'asc')),
    items: comoLista(campo(d, 'items')).map((i) => ({
      pos: comoNumero(campo(i, 'pos')),
      entidad: comoTexto(campo(i, 'entidad')),
      n: comoNumero(campo(i, 'n')),
    })),
    total: comoNumero(campo(d, 'total')),
  };
}

function aP50Vp(d: unknown): P50Vp {
  return {
    vice: comoTexto(campo(d, 'vice')),
    producto: comoProducto(campo(d, 'producto')),
    unidad: comoTexto(campo(d, 'unidad'), 'bpd'),
    // ⚠️ A5: esta hoja NO está en la escala del fact (ratio ~29, no 1e6).
    escala: 'p50_vp',
    real: comoNumero(campo(d, 'real')),
    p50: comoNumero(campo(d, 'p50')),
    pct: comoNumeroONulo(campo(d, 'pct')),
    gap: comoNumeroONulo(campo(d, 'gap')),
    mesReal: comoTexto(campo(d, 'mes_real')),
    serie: comoLista(campo(d, 'serie')).map((p) => ({
      fecha: comoTexto(campo(p, 'fecha')),
      p50: comoNumeroONulo(campo(p, 'p50')),
      real: comoNumeroONulo(campo(p, 'real')),
    })),
  };
}

function aAnalizaFoco(d: unknown): AnalizaFocoScope {
  return {
    entidad: comoTexto(campo(d, 'entidad')),
    nivel: campo(d, 'nivel') ? comoTexto(campo(d, 'nivel')) : null,
    segmento: comoTexto(campo(d, 'segmento'), 'ecp'),
    periodo: campo(d, 'periodo') ? comoTexto(campo(d, 'periodo')) : null,
    productos: comoLista(campo(d, 'productos')).map(comoProducto),
  };
}

/**
 * Normaliza el panel, o devuelve `null` si su tipo no es conocido.
 *
 * 🔑 Q5: aquí es donde se corta. Un tipo nuevo del backend llega como `null`
 * —y la vista muestra un aviso explícito— en vez de colarse hasta un
 * componente que lo pintaría con campos ajenos.
 */
export function aPanel(bruto: unknown): Panel | null {
  const tipo = campo(bruto, 'tipo');
  const datos = campo(bruto, 'datos');
  if (!esTipoConocido(tipo) || !datos) return null;

  switch (tipo) {
    case 'cuant_kpi':
      return { tipo, datos: aCuantKpi(datos) };
    case 'cuant_serie':
      return { tipo, datos: aCuantSerie(datos) };
    case 'cuant_var':
      return { tipo, datos: aCuantVar(datos) };
    case 'cuant_rank':
      return { tipo, datos: aCuantRank(datos) };
    case 'jerarq_arbol':
      return { tipo, datos: aJerarqArbol(datos) };
    case 'jerarq_operador':
      return { tipo, datos: aJerarqOperador(datos) };
    case 'jerarq_rank':
      return { tipo, datos: aJerarqRank(datos) };
    case 'p50_vp':
      return { tipo, datos: aP50Vp(datos) };
    case 'analiza_foco':
      return { tipo, datos: aAnalizaFoco(datos) };
    default: {
      // Si el backend añade un tipo y no se registra arriba, `tsc` falla aquí.
      const _exhaustivo: never = tipo;
      return _exhaustivo;
    }
  }
}

const GRUPOS: readonly GrupoQ[] = ['jerarquizar', 'cuantificar', 'analizar', 'desconocido'];

function aGrupo(valor: unknown): GrupoQ {
  return GRUPOS.includes(valor as GrupoQ) ? (valor as GrupoQ) : 'desconocido';
}

export function aRespuestaQ(bruto: unknown): RespuestaQ {
  return {
    logId: comoNumeroONulo(campo(bruto, 'log_id')),
    textoOriginal: comoTexto(campo(bruto, 'texto_original')),
    grupo: aGrupo(campo(bruto, 'grupo')),
    grupoLabel: comoTexto(campo(bruto, 'grupo_label')),
    capaResolutora: comoTexto(campo(bruto, 'capa_resolutora'), 'regex') as CapaResolutora,
    entidadCruda: campo(bruto, 'entidad_cruda') ? comoTexto(campo(bruto, 'entidad_cruda')) : null,
    patrones: comoTextos(campo(bruto, 'patrones')),
    llmDiag: campo(bruto, 'llm_diag') ? comoTexto(campo(bruto, 'llm_diag')) : null,
    timestamp: comoTexto(campo(bruto, 'timestamp')),
    mensaje: comoTexto(campo(bruto, 'mensaje')),
    panel: aPanel(campo(bruto, 'panel')),
    vpOfrecida: campo(bruto, 'vp_ofrecida') ? comoTexto(campo(bruto, 'vp_ofrecida')) : null,
    continuacion: campo(bruto, 'continuacion') === true ? true : null,
  };
}
