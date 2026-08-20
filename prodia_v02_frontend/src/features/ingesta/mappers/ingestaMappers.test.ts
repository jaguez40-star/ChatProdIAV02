/**
 * Tests de los mappers de Ingesta.
 *
 * Lo que se fija aquí es la **degradación segura**: los eventos SSE llegan como JSON
 * suelto, sin pasar por el cliente tipado, así que un valor inesperado no debe convertirse
 * en un estado que ningún componente sabe pintar — ni, peor, en un falso «confirmado».
 */

import { describe, expect, it } from 'vitest';

import {
  aArchivoAceptado,
  aCodigoError,
  aEstadoFinal,
  aEstadoHoja,
  aHojaEnProgreso,
  aReporteExistente,
  aResultadoIngesta,
  totalDeFilas,
} from './ingestaMappers';

describe('aEstadoHoja', () => {
  it.each(['procesando', 'procesada', 'vacia', 'error'] as const)(
    'conserva el estado conocido "%s"',
    (estado) => {
      expect(aEstadoHoja(estado)).toBe(estado);
    },
  );

  it('degrada un estado desconocido a error, no a éxito', () => {
    // Ante la duda es preferible que el usuario revise una hoja de más a que dé por
    // buena una que falló.
    expect(aEstadoHoja('ok')).toBe('error');
    expect(aEstadoHoja('')).toBe('error');
  });
});

describe('aEstadoFinal', () => {
  it('reconoce el commit', () => {
    expect(aEstadoFinal('confirmado')).toBe('confirmado');
  });

  it('trata cualquier otro valor como revertido', () => {
    // Dar por confirmada una ingesta que no lo está haría creer al usuario que tiene
    // datos que no existen.
    expect(aEstadoFinal('revertido')).toBe('revertido');
    expect(aEstadoFinal('lo-que-sea')).toBe('revertido');
  });
});

describe('aCodigoError', () => {
  it('conserva los códigos conocidos', () => {
    expect(aCodigoError('BD_NO_DISPONIBLE')).toBe('BD_NO_DISPONIBLE');
    expect(aCodigoError('FECHA_AUSENTE')).toBe('FECHA_AUSENTE');
  });

  it('mapea un código desconocido a error interno', () => {
    expect(aCodigoError('INVENTADO')).toBe('ERROR_INTERNO');
  });

  it('devuelve null cuando no hay código', () => {
    expect(aCodigoError(null)).toBeNull();
    expect(aCodigoError(undefined)).toBeNull();
  });
});

describe('aHojaEnProgreso', () => {
  it('convierte el evento a camelCase con sus tablas', () => {
    const hoja = aHojaEnProgreso({
      tipo: 'hoja',
      hoja: 'NEW MES-AÑO',
      estado: 'procesada',
      destino: 'core.fact_tabla_hoja',
      filas: 1646,
      tablas: [{ tabla_idx: 1, tabla_label: 'T1', filas: 100 }],
    });

    expect(hoja.hoja).toBe('NEW MES-AÑO');
    expect(hoja.estado).toBe('procesada');
    expect(hoja.filas).toBe(1646);
    expect(hoja.tablas[0]).toEqual({ tablaIdx: 1, tablaLabel: 'T1', filas: 100 });
  });

  it('tolera los campos opcionales ausentes', () => {
    const hoja = aHojaEnProgreso({ tipo: 'hoja', hoja: 'INICIO', estado: 'procesando' });

    expect(hoja.destino).toBeNull();
    expect(hoja.filas).toBeNull();
    expect(hoja.tablas).toEqual([]);
    expect(hoja.detalle).toBeNull();
  });
});

describe('aResultadoIngesta', () => {
  it('convierte el resultado completo', () => {
    const resultado = aResultadoIngesta({
      archivo: '20260815_r.xlsm',
      reporte_id: 1042,
      fecha_reporte: '2026-08-15',
      tipo_archivo: 'NEW',
      tiene_raw: true,
      filas_por_destino: { 'bronze.bdp_datos_dia': 40236 },
      hojas: [
        { hoja: 'INICIO', destino: 'core.fact_tabla_hoja', filas: 80, tablas: [] },
      ],
      tablas_vacias: ['REPORTE_PRESIDENT → Tabla 1'],
    });

    expect(resultado.reporteId).toBe(1042);
    expect(resultado.tipoArchivo).toBe('NEW');
    expect(resultado.hojas[0].hoja).toBe('INICIO');
    expect(resultado.tablasVacias).toHaveLength(1);
  });

  it('rellena con valores vacíos lo que el backend omita', () => {
    const resultado = aResultadoIngesta({
      archivo: 'r.xlsm',
      reporte_id: 1,
      tipo_archivo: 'STD',
      tiene_raw: false,
    });

    expect(resultado.fechaReporte).toBeNull();
    expect(resultado.filasPorDestino).toEqual({});
    expect(resultado.hojas).toEqual([]);
    expect(resultado.tablasVacias).toEqual([]);
  });
});

describe('totalDeFilas', () => {
  it('suma todos los destinos', () => {
    const resultado = aResultadoIngesta({
      archivo: 'r.xlsm',
      reporte_id: 1,
      tipo_archivo: 'NEW',
      tiene_raw: true,
      filas_por_destino: { a: 100, b: 250 },
    });

    expect(totalDeFilas(resultado)).toBe(350);
  });

  it('devuelve cero si no se escribió nada', () => {
    const resultado = aResultadoIngesta({
      archivo: 'r.xlsm',
      reporte_id: 1,
      tipo_archivo: 'STD',
      tiene_raw: false,
    });

    expect(totalDeFilas(resultado)).toBe(0);
  });
});

describe('aArchivoAceptado y aReporteExistente', () => {
  it('convierte la respuesta de subida', () => {
    const aceptado = aArchivoAceptado({
      id: 'abc',
      archivo: '20260815_r.xlsm',
      hash: 'deadbeef',
      fecha_reporte: '2026-08-15',
    });

    expect(aceptado.fechaReporte).toBe('2026-08-15');
  });

  it('convierte un reporte ya existente', () => {
    const existente = aReporteExistente({
      existe: true,
      reporte_id: 7,
      archivo: 'previo.xlsm',
      tipo_archivo: 'NEW',
      ingerido_en: '2026-08-15T10:00:00',
      mismo_contenido: true,
    });

    expect(existente.existe).toBe(true);
    expect(existente.reporteId).toBe(7);
    expect(existente.mismoContenido).toBe(true);
  });

  it('deja en null lo que no se informó', () => {
    const existente = aReporteExistente({ existe: false });

    expect(existente.reporteId).toBeNull();
    expect(existente.mismoContenido).toBeNull();
  });
});
