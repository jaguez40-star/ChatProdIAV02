/**
 * Modelo de vista de Análisis — camelCase.
 *
 * El backend responde en snake_case; los mappers traducen. Estos tipos son lo
 * que consumen los componentes, así que describen lo que la UI necesita, no lo
 * que la BD guarda.
 */

/** Ámbito de una consulta: qué entidad, a qué nivel y de qué periodo. */
export interface Ambito {
  entidad?: string;
  nivel?: string;
  periodo?: string;
  /** `ecp` (por defecto) o `filiales`, que cambia fuente Y reglas. */
  segmento?: 'ecp' | 'filiales';
}

// ── Fundación de datos ──────────────────────────────────────────────────────

export type Severidad = 'dura' | 'media' | 'blanda';
export type NivelSemaforo = 'verde' | 'amarillo' | 'rojo';

export interface Cardinalidad {
  nivel: string;
  n: number;
}

export interface Colision {
  nombre: string;
  niveles: string[];
  nNiveles: number;
  /** `dura`/`media` hacen que el chat contrapregunte; `blanda` usa el default. */
  severidad: Severidad;
}

export interface Catalogo {
  cardinalidad: Cardinalidad[];
  productosValidos: { termino: string; dim: string }[];
  colisiones: Colision[];
  resumenColisiones: { dura: number; media: number; blanda: number; total: number };
  filiales: string[];
  entidadesPorNivel: Record<string, string[]>;
}

export interface DiaDensidad {
  fecha: string;
  filas: number;
  fuentes: number;
}

export interface MesDensidad {
  anio: number;
  mes: number;
  mesNombre: string;
  diasConData: number;
  diasDelMes: number;
  huecos: number;
  rango: string[];
}

export interface FamiliaSemaforo {
  familia: string;
  nivel: NivelSemaforo;
  /** Si depende de la racha de días continuos (tendencias, anomalías). */
  necesitaContinuidad: boolean;
}

export interface Densidad {
  entidad: string | null;
  /**
   * `false` NO es un error: las vicepresidencias y las filiales no tienen
   * grano diario ECP, así que su serie va vacía y la UI lo explica.
   */
  aplicaEcp: boolean;
  dias: DiaDensidad[];
  porMes: MesDensidad[];
  resumen: {
    totalDias: number;
    rango: (string | null)[];
    huecosTotales: number;
    rachaMaxima: number;
  };
  semaforo: FamiliaSemaforo[];
}

export interface SerieHuella {
  fuente: string;
  grupo: string;
  /** Cuenta FILAS, no barriles: es metadata de cobertura. */
  filas: number;
  hoja: string;
}

export interface Huella {
  entidad: string | null;
  encontrada: boolean;
  series: SerieHuella[];
}

export interface HojaCobertura {
  hoja: string;
  categoria: string;
  reportesTotal: number;
  reportesEntidad: number | null;
}

export interface Cobertura {
  entidad: string | null;
  totalHojas: number;
  categorias: { categoria: string; hojas: HojaCobertura[] }[];
  hojasConEntidad: number | null;
}

// ── Desempeño ───────────────────────────────────────────────────────────────

export interface ProductoDesempeno {
  producto: string;
  real: number;
  ppto: number;
  /** `null` = sin meta. **No es 0 %**: no hay con qué comparar. */
  cumplimiento: number | null;
}

export interface CampoSinMeta {
  campo: string;
  producto: string;
  real: number;
}

export interface Desempeno {
  entidad: string | null;
  encontrada: boolean;
  sinDatos: boolean;
  aplicaDiario: boolean;
  sinCierre: boolean;
  /** `false` = el periodo pedido no está soportado y se sirvió el default. */
  periodoOk: boolean;
  mes: {
    anio: number;
    mes: number;
    nombre: string;
    diasConData: number;
    diasDelMes: number;
    completo: boolean;
  } | null;
  porProducto: ProductoDesempeno[];
  camposSinMeta: CampoSinMeta[];
  curva: { fechas: string[]; series: Record<string, number[]> } | null;
  ritmoMensual: {
    meses: string[];
    mesesNum: number[];
    series: Record<string, (number | null)[]>;
    promedioMes: Record<string, number | null>;
    /** `null` cuando la curva diaria del producto no reconcilia con el mes. */
    promedioDia: Record<string, number | null>;
    mesActual: number;
  } | null;
}

// ── Ejecutivo ───────────────────────────────────────────────────────────────

export interface TarjetaKpi {
  producto: string;
  unidad: string | null;
  metaMes: number;
  proyectadoCierre: number;
  brechaAbs: number;
  rellenoPct: number;
  alcanza: boolean;
  /** `alineado` | `ajustado` | `actuar` | `''` (sin meta). Lo decide el backend. */
  estado: string;
  /** `true` = la meta es el promedio del año, no un presupuesto. */
  metaDePromedio: boolean;
  /** `null` cuando la curva diaria no reconcilia: no se inventa una tasa. */
  bopd: { real: number; requerido: number; deltaPct: number | null } | null;
  histProm: number | null;
}

export interface Foco {
  producto: string;
  entidades: string[];
  faltanteAbs: number | null;
  pesoRelativoPct: number | null;
  esOk: boolean;
  estadoLabel: string;
  sinProduccion: boolean;
  titulo: string;
  causa: {
    texto: string;
    cobertura: string;
    detalle: string[];
    eventos?: { campo: string; fecha: string; texto: string }[];
  };
  accion: string;
  tipo: string;
  rank: number;
  extremos?: { campo: string; real: number; meta: number }[];
}

export interface Valle {
  desde: string;
  hasta: string;
  minFecha: string;
  minValor: number;
  magnitudPct?: number | null;
  dias?: number;
}

export interface Pace {
  mtd: number;
  dias: number;
  restantes: number;
  promedioDia: number;
  requeridoDia: number;
  deltaPct: number | null;
}

export interface SeccionesEjecutivas {
  insights: string[];
  oportunidades: string[];
  puntosAtencion: string[];
  decisiones: string[];
}

export interface Ejecutivo {
  entidad: string | null;
  encontrada: boolean;
  sinDatos: boolean;
  meta: {
    scope: string;
    periodo: string;
    corte: string;
    /** `fallback` = composer determinista · `llm` = prosa pulida · `error`. */
    generadoPor: string;
  };
  titular: { producto: string; valorPct: number | null; estado: string; texto: string }[];
  tarjetas: TarjetaKpi[];
  valle: Valle | null;
  pace: Pace | null;
  secciones: SeccionesEjecutivas | null;
  focos: Foco[];
  sinFoco: string;
  porFilial?: { empresa: string; periodo: string; tarjetas: TarjetaKpi[] }[];
}

// ── Pills del acordeón ──────────────────────────────────────────────────────

export interface ComponenteWaterfall {
  key: string;
  label: string;
  valueKusd: number;
  valueUsdBl: number;
  /** `total` arranca desde cero; `delta` desde donde quedó el anterior. */
  type: 'total' | 'delta';
}

export interface Waterfall {
  components: ComponenteWaterfall[];
  totalBls: number;
  meta: { year: number; month: number; nivel: string; entidad: string | null };
}

export interface GrupoPareto {
  grupo: string;
  total: number;
  pct: number;
  anios: Record<string, number>;
}

export interface Diferidas {
  sinDatos: boolean;
  motivo?: string | null;
  pareto: GrupoPareto[];
  /** Solo los tipos que EMPEORARON: la tarjeta muestra el deterioro. */
  tendencia: { causa: string; pct: Record<string, number>; tendencia: string }[];
  pozosPorGrupo: { grupo: string; pozos: number }[];
  impacto: Record<string, { total: number; causas: { causa: string; vol: number; pct: number }[] }>;
  meta: { scopeLabel: string; rango?: string; totalIncidentes?: number; pozosTotal?: number };
}

export interface EventoMantenimiento {
  pozo: string;
  tipo: string;
  /** `abierto` = sin fecha de cierre; sigue corriendo. */
  estado: 'abierto' | 'cerrado';
  inicio: string;
  fin: string;
}

export interface Mantenimientos {
  sinDatos: boolean;
  motivo?: string | null;
  eventos: EventoMantenimiento[];
  meta: {
    scopeLabel: string;
    periodo?: string;
    total?: number;
    mostrados?: number;
    abiertos?: number;
  };
}

// ── President ───────────────────────────────────────────────────────────────

export interface TarjetaP50 {
  entidad: string;
  realMes: number | null;
  proyMes: number | null;
  baseP50: number | null;
  compromiso: number | null;
  cumplP50: number | null;
  /** `true` cuando el Reto difiere del P50: la UI rotula distinto. */
  compromisoDifiere: boolean;
}

export interface President {
  encontrada: boolean;
  corte: string | null;
  /** Escala corporativa kbpe — NO la del fact diario (A5). */
  unidad: string;
  productos: TarjetaP50[];
  totales: TarjetaP50[];
}
