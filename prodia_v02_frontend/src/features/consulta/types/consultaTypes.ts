/**
 * Tipos del chat de Consulta (Motor Q v2).
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 🔑 Q5 — un tipo de panel desconocido debe ROMPER EL BUILD.
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * En el sistema viejo el dispatcher es una cadena de ternarios que termina en
 * un fallback sin validar. Verificado: `cuant_kpi` —el tipo MÁS común, el de
 * toda pregunta "cuánto produjo X"— no aparece ni una vez en
 * `multitab_shell.js`, así que cae a ese fallback **por accidente**. Funciona
 * de casualidad, y cualquier tipo nuevo pintaría una tarjeta con campos
 * ajenos: anillo al 0 %, título vacío, "—". Estructuralmente válida,
 * semánticamente basura, sin ningún error visible.
 *
 * Aquí `Panel` es una unión discriminada y el dispatcher usa `never` en su
 * caso por defecto: si el backend añade un tipo y el frontend no lo registra,
 * `tsc` falla. El error aparece en el build, no en la pantalla del usuario.
 */

/** Los cuatro grupos del clasificador. */
export type GrupoQ = 'jerarquizar' | 'cuantificar' | 'analizar' | 'desconocido';

/** Cómo se resolvió la clasificación. Diagnóstico: no se muestra al usuario. */
export type CapaResolutora =
  | 'regex'
  | 'regex+filtro'
  | 'regex+llm'
  | 'regex+llm_fallo'
  | 'llm';

export type Producto = 'crudo' | 'gas' | 'blancos';

/**
 * ⚠️ A5 — la unidad NO es función del producto solamente.
 *
 * El gas del fact va en MSCF (÷1e6), pero la hoja del P50 tiene **ratio ~29**,
 * no 1e6: aplicarle la conversión del gas mostraba "0,03" donde iban
 * "33.453,2" — mil veces menor y sin error visible. Por eso la escala viaja
 * junto al valor y el formateador la respeta.
 */
export type EscalaValor = 'fact' | 'p50_vp';

// ── Los 9 paneles ────────────────────────────────────────────────────────────

export interface ItemRanking {
  pos: number;
  entidad: string;
  valor: number;
  gap: number;
  ppto: number;
  operador: string;
  /** Falso para campos operados por terceros. Se rotulan, no se ocultan. */
  esEcp: boolean;
}

export interface PuntoSerie {
  mes: string;
  valor: number;
}

export interface DeltaMes {
  de: string;
  a: string;
  delta: number;
  pct: number | null;
}

export interface CuantKpi {
  entidadCualificada: string;
  producto: Producto;
  unidad: string;
  real: number;
  referenciaValor: number | null;
  referenciaLabel: string;
  cumplimientoPct: number | null;
  estado: string;
  mes: {
    nombre: string;
    anio: number;
    completo: boolean;
    diasConData: number;
    diasDelMes: number;
  };
  avisos: string[];
}

export interface CuantSerie {
  entidadCualificada: string;
  producto: Producto;
  unidad: string;
  serie: PuntoSerie[];
  promedio: number | null;
  anio: number;
  /** Mes cuyo valor es proyección, no cierre. Se pinta distinto. */
  proyeccionMes: string | null;
  avisos: string[];
}

export interface CuantVar {
  entidadCualificada: string;
  producto: Producto;
  unidad: string;
  deltas: DeltaMes[];
  ultimo: DeltaMes;
  anio: number;
  proyeccionMes: string | null;
  avisos: string[];
}

export interface CuantRank {
  nivelRanking: 'campo' | 'activo';
  /** D3: el orden es (metrica, direccion), nunca (eje, asc/desc). */
  metrica: 'real' | 'gap';
  direccion: 'top' | 'bottom';
  producto: Producto;
  unidad: string;
  periodoLabel: string;
  esProyeccion: boolean;
  items: ItemRanking[];
  totalUniverso: number;
  /** D4: cuántos quedaron fuera por no tener registro (no por producir poco). */
  sinRegistro: number;
  concentracionPct: number | null;
}

export interface GrupoHijos {
  nivel: string;
  items: string[];
  total: number;
  /** El tope se DECLARA, no se recorta en silencio. */
  truncado: boolean;
}

export interface JerarqArbol {
  entidad: string;
  nivel: string;
  /** R2: el valor es en realidad una vicepresidencia mal nombrada. */
  puente: boolean;
  padres: { nivel: string; items: string[] }[];
  hijosGrupos: GrupoHijos[];
  pozos: number | null;
  operador: string | null;
  fueraEstructura: boolean;
}

export interface JerarqOperador {
  entidad: string;
  campos: string[];
  total: number;
  truncado: boolean;
}

export interface JerarqRank {
  subject: string;
  conteo: string;
  asc: boolean;
  items: { pos: number; entidad: string; n: number }[];
  total: number;
}

export interface P50Vp {
  vice: string;
  producto: Producto;
  unidad: string;
  /** ⚠️ Siempre `'p50_vp'`: esta hoja NO está en la escala del fact. */
  escala: EscalaValor;
  real: number;
  p50: number;
  pct: number | null;
  gap: number | null;
  mesReal: string;
  serie: { fecha: string; p50: number | null; real: number | null }[];
}

/**
 * El panel de análisis lleva SOLO el alcance, no los datos.
 *
 * El frontend los pide por su cuenta con sus propias cachés (regla A7 del
 * origen): el tablero puede estar mostrando otra entidad, y reusar su estado
 * daría cifras cruzadas.
 */
export interface AnalizaFocoScope {
  entidad: string;
  nivel: string | null;
  segmento: string;
  periodo: string | null;
  /** Vacío = ninguno nombrado, y el panel muestra los tres. */
  productos: Producto[];
}

/** Los 9 tipos. El dispatcher los agota con `never`. */
export type Panel =
  | { tipo: 'cuant_kpi'; datos: CuantKpi }
  | { tipo: 'cuant_serie'; datos: CuantSerie }
  | { tipo: 'cuant_var'; datos: CuantVar }
  | { tipo: 'cuant_rank'; datos: CuantRank }
  | { tipo: 'jerarq_arbol'; datos: JerarqArbol }
  | { tipo: 'jerarq_operador'; datos: JerarqOperador }
  | { tipo: 'jerarq_rank'; datos: JerarqRank }
  | { tipo: 'p50_vp'; datos: P50Vp }
  | { tipo: 'analiza_foco'; datos: AnalizaFocoScope };

export type TipoPanel = Panel['tipo'];

// ── Respuesta y mensajes ─────────────────────────────────────────────────────

export interface RespuestaQ {
  logId: number | null;
  textoOriginal: string;
  grupo: GrupoQ;
  grupoLabel: string;
  /** Diagnóstico: NO se muestra en el chat, solo en Test Clas (F5). */
  capaResolutora: CapaResolutora;
  entidadCruda: string | null;
  patrones: string[];
  llmDiag: string | null;
  timestamp: string;
  mensaje: string;
  panel: Panel | null;
  vpOfrecida: string | null;
  continuacion: boolean | null;
}

/**
 * Un mensaje del historial.
 *
 * 🔑 Guarda **datos, no HTML**. El sistema viejo almacena strings de HTML ya
 * renderizado, y por eso para cambiar una burbuja pintada tiene que hacer
 * regex sobre el historial —con la advertencia de que la franja de veredicto
 * no puede contener `<div>` anidados—. Con datos, el render es una función
 * pura y ese mecanismo entero desaparece.
 */
export type Mensaje =
  | { rol: 'usuario'; texto: string; ts: number }
  | {
      rol: 'asistente';
      texto: string;
      panel: Panel | null;
      logId: number | null;
      /** El veredicto que ya dio el usuario, si lo dio. */
      veredicto: 'confirmado' | 'corregido' | null;
      ts: number;
    }
  | { rol: 'error'; texto: string; correlationId: string | null; ts: number };

export interface BloqueApilado {
  /** Número de turno, para que el usuario ubique de qué pregunta salió. */
  n: number;
  pregunta: string;
  panel: Panel;
  hora: string;
  colapsado: boolean;
}
