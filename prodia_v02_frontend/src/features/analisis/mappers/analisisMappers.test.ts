import { describe, expect, it } from 'vitest';

import {
  toCatalogo,
  toDesempeno,
  toDiferidas,
  toEjecutivo,
  toMantenimientos,
  toPresident,
  toWaterfall,
} from './analisisMappers';

/**
 * Lo que se protege aquí es el contrato de dos interceptores: el backend habla
 * snake_case, la vista camelCase, y `null` conserva su significado.
 */

describe('toDesempeno', () => {
  it('preserva `null` en cumplimiento: sin meta NO es 0 %', () => {
    const resultado = toDesempeno({
      por_producto: [
        { producto: 'CRUDO', real: 100, ppto: 0, cumplimiento: null },
        { producto: 'GAS', real: 95, ppto: 100, cumplimiento: 95.0 },
      ],
    });

    expect(resultado.porProducto[0].cumplimiento).toBeNull();
    expect(resultado.porProducto[1].cumplimiento).toBe(95.0);
  });

  it('traduce snake_case a camelCase', () => {
    const resultado = toDesempeno({
      aplica_diario: false,
      sin_cierre: true,
      periodo_ok: false,
      campos_sin_meta: [{ campo: 'SURIA', producto: 'CRUDO', real: 500 }],
    });

    expect(resultado.aplicaDiario).toBe(false);
    expect(resultado.sinCierre).toBe(true);
    expect(resultado.periodoOk).toBe(false);
    expect(resultado.camposSinMeta[0].campo).toBe('SURIA');
  });

  it('sobrevive a una respuesta incompleta sin reventar', () => {
    const resultado = toDesempeno({});
    expect(resultado.porProducto).toEqual([]);
    expect(resultado.mes).toBeNull();
    expect(resultado.curva).toBeNull();
  });
});

describe('toEjecutivo', () => {
  it('preserva `bopd: null` cuando la curva diaria no reconcilia', () => {
    const resultado = toEjecutivo({
      tarjetas: [
        { producto: 'CRUDO', bopd: { real: 100, requerido: 120, delta_pct: 20 } },
        { producto: 'BLANCOS', bopd: null },
      ],
    });

    expect(resultado.tarjetas[0].bopd).toEqual({
      real: 100,
      requerido: 120,
      deltaPct: 20,
    });
    expect(resultado.tarjetas[1].bopd).toBeNull();
  });

  it('declara el origen de la prosa', () => {
    const conLlm = toEjecutivo({ meta: { generado_por: 'llm' } });
    const sinLlm = toEjecutivo({ meta: {} });

    expect(conLlm.meta.generadoPor).toBe('llm');
    expect(sinLlm.meta.generadoPor).toBe('fallback');
  });

  it('mapea los focos con su causa y detalle', () => {
    const resultado = toEjecutivo({
      focos: [
        {
          producto: 'GAS',
          entidades: ['CUSIANA', 'CUPIAGUA'],
          es_ok: false,
          estado_label: 'Foco',
          peso_relativo_pct: 88.2,
          causa: { texto: 'x', cobertura: 'con_evento', detalle: ['a', 'b'] },
        },
      ],
    });

    const foco = resultado.focos[0];
    expect(foco.entidades).toEqual(['CUSIANA', 'CUPIAGUA']);
    expect(foco.pesoRelativoPct).toBe(88.2);
    expect(foco.causa.detalle).toHaveLength(2);
  });
});

describe('toCatalogo', () => {
  it('mapea colisiones con su severidad', () => {
    const resultado = toCatalogo({
      colisiones: [
        { nombre: 'RUBIALES', niveles: ['activo', 'campo'], n_niveles: 2, severidad: 'dura' },
      ],
      resumen_colisiones: { dura: 1, media: 0, blanda: 0, total: 1 },
    });

    expect(resultado.colisiones[0].severidad).toBe('dura');
    expect(resultado.colisiones[0].nNiveles).toBe(2);
    expect(resultado.resumenColisiones.total).toBe(1);
  });
});

describe('toWaterfall', () => {
  it('distingue totales de deltas', () => {
    const resultado = toWaterfall({
      components: [
        { key: 'ingresos', label: 'Ingresos', value_kusd: 1000, value_usd_bl: 20, type: 'total' },
        { key: 'energia', label: 'Energía', value_kusd: -50, value_usd_bl: -1, type: 'delta' },
      ],
      total_bls: 500,
    });

    expect(resultado.components[0].type).toBe('total');
    expect(resultado.components[1].valueKusd).toBe(-50);
    expect(resultado.totalBls).toBe(500);
  });
});

describe('toDiferidas y toMantenimientos', () => {
  it('propagan la degradación con su motivo', () => {
    const diferidas = toDiferidas({
      sin_datos: true,
      motivo: 'BD no disponible',
      meta: { scope_label: 'CASTILLA' },
    });

    expect(diferidas.sinDatos).toBe(true);
    expect(diferidas.motivo).toBe('BD no disponible');
    expect(diferidas.pareto).toEqual([]);
  });

  it('mapea el estado abierto de un mantenimiento', () => {
    const resultado = toMantenimientos({
      sin_datos: false,
      eventos: [{ pozo: 'P-1', tipo: 'Workover', estado: 'abierto', inicio: '5 May', fin: '—' }],
      meta: { scope_label: 'CASTILLA', abiertos: 1 },
    });

    expect(resultado.eventos[0].estado).toBe('abierto');
    expect(resultado.meta.abiertos).toBe(1);
  });
});

describe('toPresident', () => {
  it('preserva `null` en las medidas ausentes', () => {
    const resultado = toPresident({
      encontrada: true,
      unidad: 'kbpe',
      productos: [
        { entidad: 'Crudo', real_mes: 484, base_p50: 500, cumpl_p50: 96.8, compromiso_difiere: false },
        { entidad: 'Gas', real_mes: null, base_p50: null, cumpl_p50: null },
      ],
    });

    expect(resultado.productos[0].cumplP50).toBe(96.8);
    expect(resultado.productos[1].cumplP50).toBeNull();
    expect(resultado.unidad).toBe('kbpe');
  });
});
