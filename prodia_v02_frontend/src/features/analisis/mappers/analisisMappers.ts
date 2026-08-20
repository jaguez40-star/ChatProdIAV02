/**
 * snake_case del backend → camelCase de la vista.
 *
 * El contrato de dos interceptores: el backend nunca cambia sus nombres por
 * comodidad del frontend, y el frontend nunca consume snake_case. Este archivo
 * es el único punto donde conviven ambas convenciones.
 *
 * Los endpoints del panel ejecutivo devuelven `dict` sin `response_model` (su
 * forma es demasiado dinámica para un DTO estable), así que aquí llegan como
 * `unknown` y se normalizan defensivamente: un campo ausente se convierte en
 * su valor neutro, nunca en `undefined` suelto que reviente un `.map()`.
 */

import type {
  Catalogo,
  Cobertura,
  Densidad,
  Desempeno,
  Diferidas,
  Ejecutivo,
  Huella,
  Mantenimientos,
  President,
  Waterfall,
} from '../types/analisisTypes';

/** Acceso seguro a un objeto de forma desconocida. */
function campo(origen: unknown, clave: string): unknown {
  if (origen && typeof origen === 'object' && clave in origen) {
    return (origen as Record<string, unknown>)[clave];
  }
  return undefined;
}

function comoLista(valor: unknown): unknown[] {
  return Array.isArray(valor) ? valor : [];
}

function comoTexto(valor: unknown, porDefecto = ''): string {
  return typeof valor === 'string' ? valor : porDefecto;
}

function comoNumero(valor: unknown, porDefecto = 0): number {
  return typeof valor === 'number' ? valor : porDefecto;
}

/** Preserva `null` como valor con significado: "sin dato", no "cero". */
function comoNumeroONulo(valor: unknown): number | null {
  return typeof valor === 'number' ? valor : null;
}

function comoBooleano(valor: unknown, porDefecto = false): boolean {
  return typeof valor === 'boolean' ? valor : porDefecto;
}

// ── Fundación de datos ──────────────────────────────────────────────────────

export function toCatalogo(dto: unknown): Catalogo {
  return {
    cardinalidad: comoLista(campo(dto, 'cardinalidad')).map((c) => ({
      nivel: comoTexto(campo(c, 'nivel')),
      n: comoNumero(campo(c, 'n')),
    })),
    productosValidos: comoLista(campo(dto, 'productos_validos')).map((p) => ({
      termino: comoTexto(campo(p, 'termino')),
      dim: comoTexto(campo(p, 'dim')),
    })),
    colisiones: comoLista(campo(dto, 'colisiones')).map((c) => ({
      nombre: comoTexto(campo(c, 'nombre')),
      niveles: comoLista(campo(c, 'niveles')).map((n) => comoTexto(n)),
      nNiveles: comoNumero(campo(c, 'n_niveles')),
      severidad: comoTexto(campo(c, 'severidad'), 'blanda') as Catalogo['colisiones'][number]['severidad'],
    })),
    resumenColisiones: {
      dura: comoNumero(campo(campo(dto, 'resumen_colisiones'), 'dura')),
      media: comoNumero(campo(campo(dto, 'resumen_colisiones'), 'media')),
      blanda: comoNumero(campo(campo(dto, 'resumen_colisiones'), 'blanda')),
      total: comoNumero(campo(campo(dto, 'resumen_colisiones'), 'total')),
    },
    filiales: comoLista(campo(dto, 'filiales')).map((f) => comoTexto(f)),
    entidadesPorNivel: (campo(dto, 'entidades_por_nivel') ?? {}) as Record<string, string[]>,
  };
}

export function toDensidad(dto: unknown): Densidad {
  const resumen = campo(dto, 'resumen');
  return {
    entidad: comoTexto(campo(dto, 'entidad')) || null,
    aplicaEcp: comoBooleano(campo(dto, 'aplica_ecp'), true),
    dias: comoLista(campo(dto, 'dias')).map((d) => ({
      fecha: comoTexto(campo(d, 'fecha')),
      filas: comoNumero(campo(d, 'filas')),
      fuentes: comoNumero(campo(d, 'fuentes')),
    })),
    porMes: comoLista(campo(dto, 'por_mes')).map((m) => ({
      anio: comoNumero(campo(m, 'anio')),
      mes: comoNumero(campo(m, 'mes')),
      mesNombre: comoTexto(campo(m, 'mes_nombre')),
      diasConData: comoNumero(campo(m, 'dias_con_data')),
      diasDelMes: comoNumero(campo(m, 'dias_del_mes')),
      huecos: comoNumero(campo(m, 'huecos')),
      rango: comoLista(campo(m, 'rango')).map((r) => comoTexto(r)),
    })),
    resumen: {
      totalDias: comoNumero(campo(resumen, 'total_dias')),
      rango: comoLista(campo(resumen, 'rango')).map((r) =>
        typeof r === 'string' ? r : null,
      ),
      huecosTotales: comoNumero(campo(resumen, 'huecos_totales')),
      rachaMaxima: comoNumero(campo(resumen, 'racha_maxima')),
    },
    semaforo: comoLista(campo(dto, 'semaforo')).map((s) => ({
      familia: comoTexto(campo(s, 'familia')),
      nivel: comoTexto(campo(s, 'nivel'), 'verde') as Densidad['semaforo'][number]['nivel'],
      necesitaContinuidad: comoBooleano(campo(s, 'necesita_continuidad')),
    })),
  };
}

export function toHuella(dto: unknown): Huella {
  return {
    entidad: comoTexto(campo(dto, 'entidad')) || null,
    encontrada: comoBooleano(campo(dto, 'encontrada'), true),
    series: comoLista(campo(dto, 'series')).map((s) => ({
      fuente: comoTexto(campo(s, 'fuente')),
      grupo: comoTexto(campo(s, 'grupo')),
      filas: comoNumero(campo(s, 'filas')),
      hoja: comoTexto(campo(s, 'hoja')),
    })),
  };
}

export function toCobertura(dto: unknown): Cobertura {
  return {
    entidad: comoTexto(campo(dto, 'entidad')) || null,
    totalHojas: comoNumero(campo(dto, 'total_hojas')),
    categorias: comoLista(campo(dto, 'categorias')).map((c) => ({
      categoria: comoTexto(campo(c, 'categoria')),
      hojas: comoLista(campo(c, 'hojas')).map((h) => ({
        hoja: comoTexto(campo(h, 'hoja')),
        categoria: comoTexto(campo(h, 'categoria')),
        reportesTotal: comoNumero(campo(h, 'reportes_total')),
        reportesEntidad: comoNumeroONulo(campo(h, 'reportes_entidad')),
      })),
    })),
    hojasConEntidad: comoNumeroONulo(campo(dto, 'hojas_con_entidad')),
  };
}

// ── Desempeño ───────────────────────────────────────────────────────────────

export function toDesempeno(dto: unknown): Desempeno {
  const mes = campo(dto, 'mes');
  const curva = campo(dto, 'curva');
  const ritmo = campo(dto, 'ritmo_mensual');

  return {
    entidad: comoTexto(campo(dto, 'entidad')) || null,
    encontrada: comoBooleano(campo(dto, 'encontrada'), true),
    sinDatos: comoBooleano(campo(dto, 'sin_datos')),
    aplicaDiario: comoBooleano(campo(dto, 'aplica_diario'), true),
    sinCierre: comoBooleano(campo(dto, 'sin_cierre')),
    periodoOk: comoBooleano(campo(dto, 'periodo_ok'), true),
    mes: mes
      ? {
          anio: comoNumero(campo(mes, 'anio')),
          mes: comoNumero(campo(mes, 'mes')),
          nombre: comoTexto(campo(mes, 'nombre')),
          diasConData: comoNumero(campo(mes, 'dias_con_data')),
          diasDelMes: comoNumero(campo(mes, 'dias_del_mes')),
          completo: comoBooleano(campo(mes, 'completo')),
        }
      : null,
    porProducto: comoLista(campo(dto, 'por_producto')).map((p) => ({
      producto: comoTexto(campo(p, 'producto')),
      real: comoNumero(campo(p, 'real')),
      ppto: comoNumero(campo(p, 'ppto')),
      // `null` se PRESERVA: sin meta no es 0 % de cumplimiento.
      cumplimiento: comoNumeroONulo(campo(p, 'cumplimiento')),
    })),
    camposSinMeta: comoLista(campo(dto, 'campos_sin_meta')).map((c) => ({
      campo: comoTexto(campo(c, 'campo')),
      producto: comoTexto(campo(c, 'producto')),
      real: comoNumero(campo(c, 'real')),
    })),
    curva: curva
      ? {
          fechas: comoLista(campo(curva, 'fechas')).map((f) => comoTexto(f)),
          series: (campo(curva, 'series') ?? {}) as Record<string, number[]>,
        }
      : null,
    ritmoMensual: ritmo
      ? {
          meses: comoLista(campo(ritmo, 'meses')).map((m) => comoTexto(m)),
          mesesNum: comoLista(campo(ritmo, 'meses_num')).map((m) => comoNumero(m)),
          series: (campo(ritmo, 'series') ?? {}) as Record<string, (number | null)[]>,
          promedioMes: (campo(ritmo, 'promedio_mes') ?? {}) as Record<string, number | null>,
          promedioDia: (campo(ritmo, 'promedio_dia') ?? {}) as Record<string, number | null>,
          mesActual: comoNumero(campo(ritmo, 'mes_actual')),
        }
      : null,
  };
}

// ── Ejecutivo ───────────────────────────────────────────────────────────────

function toTarjeta(t: unknown): Ejecutivo['tarjetas'][number] {
  const bopd = campo(t, 'bopd');
  return {
    producto: comoTexto(campo(t, 'producto')),
    unidad: comoTexto(campo(t, 'unidad')) || null,
    metaMes: comoNumero(campo(t, 'meta_mes')),
    proyectadoCierre: comoNumero(campo(t, 'proyectado_cierre')),
    brechaAbs: comoNumero(campo(t, 'brecha_abs')),
    rellenoPct: comoNumero(campo(t, 'relleno_pct')),
    alcanza: comoBooleano(campo(t, 'alcanza')),
    estado: comoTexto(campo(t, 'estado')),
    metaDePromedio: comoBooleano(campo(t, 'meta_de_promedio')),
    // `null` = la curva diaria no reconcilia; no se inventa una tasa.
    bopd: bopd
      ? {
          real: comoNumero(campo(bopd, 'real')),
          requerido: comoNumero(campo(bopd, 'requerido')),
          deltaPct: comoNumeroONulo(campo(bopd, 'delta_pct')),
        }
      : null,
    histProm: comoNumeroONulo(campo(t, 'hist_prom')),
  };
}

export function toEjecutivo(dto: unknown): Ejecutivo {
  const meta = campo(dto, 'meta');
  const valle = campo(dto, 'valle');
  const pace = campo(dto, 'pace_crudo');
  const secciones = campo(dto, 'secciones');

  return {
    entidad: comoTexto(campo(dto, 'entidad')) || null,
    encontrada: comoBooleano(campo(dto, 'encontrada'), true),
    sinDatos: comoBooleano(campo(dto, 'sin_datos')),
    meta: {
      scope: comoTexto(campo(meta, 'scope')),
      periodo: comoTexto(campo(meta, 'periodo')),
      corte: comoTexto(campo(meta, 'corte')),
      generadoPor: comoTexto(campo(meta, 'generado_por'), 'fallback'),
    },
    titular: comoLista(campo(dto, 'titular')).map((t) => ({
      producto: comoTexto(campo(t, 'producto')),
      valorPct: comoNumeroONulo(campo(t, 'valor_pct')),
      estado: comoTexto(campo(t, 'estado')),
      texto: comoTexto(campo(t, 'texto')),
    })),
    tarjetas: comoLista(campo(dto, 'tarjetas')).map(toTarjeta),
    valle: valle
      ? {
          desde: comoTexto(campo(valle, 'desde')),
          hasta: comoTexto(campo(valle, 'hasta')),
          minFecha: comoTexto(campo(valle, 'min_fecha')),
          minValor: comoNumero(campo(valle, 'min_valor')),
          magnitudPct: comoNumeroONulo(campo(valle, 'magnitud_pct')),
          dias: comoNumero(campo(valle, 'dias')),
        }
      : null,
    pace: pace
      ? {
          mtd: comoNumero(campo(pace, 'mtd')),
          dias: comoNumero(campo(pace, 'dias')),
          restantes: comoNumero(campo(pace, 'restantes')),
          promedioDia: comoNumero(campo(pace, 'promedio_dia')),
          requeridoDia: comoNumero(campo(pace, 'requerido_dia')),
          deltaPct: comoNumeroONulo(campo(pace, 'delta_pct')),
        }
      : null,
    secciones: secciones
      ? {
          insights: comoLista(campo(secciones, 'insights')).map((s) => comoTexto(s)),
          oportunidades: comoLista(campo(secciones, 'oportunidades')).map((s) => comoTexto(s)),
          puntosAtencion: comoLista(campo(secciones, 'puntos_atencion')).map((s) => comoTexto(s)),
          decisiones: comoLista(campo(secciones, 'decisiones')).map((s) => comoTexto(s)),
        }
      : null,
    focos: comoLista(campo(dto, 'focos')).map((f) => {
      const causa = campo(f, 'causa');
      return {
        producto: comoTexto(campo(f, 'producto')),
        entidades: comoLista(campo(f, 'entidades')).map((e) => comoTexto(e)),
        faltanteAbs: comoNumeroONulo(campo(f, 'faltante_abs')),
        pesoRelativoPct: comoNumeroONulo(campo(f, 'peso_relativo_pct')),
        esOk: comoBooleano(campo(f, 'es_ok')),
        estadoLabel: comoTexto(campo(f, 'estado_label')),
        sinProduccion: comoBooleano(campo(f, 'sin_produccion')),
        titulo: comoTexto(campo(f, 'titulo')),
        causa: {
          texto: comoTexto(campo(causa, 'texto')),
          cobertura: comoTexto(campo(causa, 'cobertura')),
          detalle: comoLista(campo(causa, 'detalle')).map((d) => comoTexto(d)),
          eventos: comoLista(campo(causa, 'eventos')).map((e) => ({
            campo: comoTexto(campo(e, 'campo')),
            fecha: comoTexto(campo(e, 'fecha')),
            texto: comoTexto(campo(e, 'texto')),
          })),
        },
        accion: comoTexto(campo(f, 'accion')),
        tipo: comoTexto(campo(f, 'tipo')),
        rank: comoNumero(campo(f, 'rank')),
        extremos: comoLista(campo(f, 'extremos')).map((e) => ({
          campo: comoTexto(campo(e, 'campo')),
          real: comoNumero(campo(e, 'real')),
          meta: comoNumero(campo(e, 'meta')),
        })),
      };
    }),
    sinFoco: comoTexto(campo(dto, 'sin_foco')),
    porFilial: comoLista(campo(dto, 'por_filial')).map((f) => ({
      empresa: comoTexto(campo(f, 'empresa')),
      periodo: comoTexto(campo(f, 'periodo')),
      tarjetas: comoLista(campo(f, 'tarjetas')).map(toTarjeta),
    })),
  };
}

// ── Pills ───────────────────────────────────────────────────────────────────

export function toWaterfall(dto: unknown): Waterfall {
  const meta = campo(dto, 'meta');
  return {
    components: comoLista(campo(dto, 'components')).map((c) => ({
      key: comoTexto(campo(c, 'key')),
      label: comoTexto(campo(c, 'label')),
      valueKusd: comoNumero(campo(c, 'value_kusd')),
      valueUsdBl: comoNumero(campo(c, 'value_usd_bl')),
      type: comoTexto(campo(c, 'type'), 'delta') as Waterfall['components'][number]['type'],
    })),
    totalBls: comoNumero(campo(dto, 'total_bls')),
    meta: {
      year: comoNumero(campo(meta, 'year')),
      month: comoNumero(campo(meta, 'month')),
      nivel: comoTexto(campo(meta, 'nivel'), 'global'),
      entidad: comoTexto(campo(meta, 'entidad')) || null,
    },
  };
}

export function toDiferidas(dto: unknown): Diferidas {
  const meta = campo(dto, 'meta');
  return {
    sinDatos: comoBooleano(campo(dto, 'sin_datos')),
    motivo: comoTexto(campo(dto, 'motivo')) || null,
    pareto: comoLista(campo(dto, 'pareto')).map((p) => ({
      grupo: comoTexto(campo(p, 'grupo')),
      total: comoNumero(campo(p, 'total')),
      pct: comoNumero(campo(p, 'pct')),
      anios: (campo(p, 'anios') ?? {}) as Record<string, number>,
    })),
    tendencia: comoLista(campo(dto, 'tendencia')).map((t) => ({
      causa: comoTexto(campo(t, 'causa')),
      pct: (campo(t, 'pct') ?? {}) as Record<string, number>,
      tendencia: comoTexto(campo(t, 'tendencia')),
    })),
    pozosPorGrupo: comoLista(campo(dto, 'pozos_por_grupo')).map((p) => ({
      grupo: comoTexto(campo(p, 'grupo')),
      pozos: comoNumero(campo(p, 'pozos')),
    })),
    impacto: (campo(dto, 'impacto') ?? {}) as Diferidas['impacto'],
    meta: {
      scopeLabel: comoTexto(campo(meta, 'scope_label')),
      rango: comoTexto(campo(meta, 'rango')),
      totalIncidentes: comoNumero(campo(meta, 'total_incidentes')),
      pozosTotal: comoNumero(campo(meta, 'pozos_total')),
    },
  };
}

export function toMantenimientos(dto: unknown): Mantenimientos {
  const meta = campo(dto, 'meta');
  return {
    sinDatos: comoBooleano(campo(dto, 'sin_datos')),
    motivo: comoTexto(campo(dto, 'motivo')) || null,
    eventos: comoLista(campo(dto, 'eventos')).map((e) => ({
      pozo: comoTexto(campo(e, 'pozo')),
      tipo: comoTexto(campo(e, 'tipo')),
      estado: comoTexto(campo(e, 'estado'), 'cerrado') as Mantenimientos['eventos'][number]['estado'],
      inicio: comoTexto(campo(e, 'inicio')),
      fin: comoTexto(campo(e, 'fin')),
    })),
    meta: {
      scopeLabel: comoTexto(campo(meta, 'scope_label')),
      periodo: comoTexto(campo(meta, 'periodo')),
      total: comoNumero(campo(meta, 'total')),
      mostrados: comoNumero(campo(meta, 'mostrados')),
      abiertos: comoNumero(campo(meta, 'abiertos')),
    },
  };
}

export function toPresident(dto: unknown): President {
  const toTarjetaP50 = (t: unknown): President['productos'][number] => ({
    entidad: comoTexto(campo(t, 'entidad')),
    realMes: comoNumeroONulo(campo(t, 'real_mes')),
    proyMes: comoNumeroONulo(campo(t, 'proy_mes')),
    baseP50: comoNumeroONulo(campo(t, 'base_p50')),
    compromiso: comoNumeroONulo(campo(t, 'compromiso')),
    cumplP50: comoNumeroONulo(campo(t, 'cumpl_p50')),
    compromisoDifiere: comoBooleano(campo(t, 'compromiso_difiere')),
  });

  return {
    encontrada: comoBooleano(campo(dto, 'encontrada')),
    corte: comoTexto(campo(dto, 'corte')) || null,
    unidad: comoTexto(campo(dto, 'unidad'), 'kbpe'),
    productos: comoLista(campo(dto, 'productos')).map(toTarjetaP50),
    totales: comoLista(campo(dto, 'totales')).map(toTarjetaP50),
  };
}
