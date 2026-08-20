import { describe, expect, it } from 'vitest';

import { aPanel, aRespuestaQ } from './consultaMappers';

describe('aPanel — la frontera de confianza (Q5)', () => {
  it('rechaza un tipo que este frontend no conoce', () => {
    // 🔑 Q5: devolver `null` es lo que impide que un objeto sin forma llegue a
    // un componente y se pinte con campos ajenos, como hace el sistema viejo.
    expect(aPanel({ tipo: 'inventado', datos: {} })).toBeNull();
  });

  it('rechaza un panel sin datos', () => {
    expect(aPanel({ tipo: 'cuant_kpi' })).toBeNull();
  });

  it('rechaza null y valores que no son objeto', () => {
    expect(aPanel(null)).toBeNull();
    expect(aPanel('cuant_kpi')).toBeNull();
  });

  it('normaliza un KPI y preserva el null del cumplimiento', () => {
    // `null` = sin meta. Convertirlo a 0 diría "vas al 0 %", que inventaría un
    // incumplimiento (Q2).
    const panel = aPanel({
      tipo: 'cuant_kpi',
      datos: {
        entidad_cualificada: 'el Campo CASTILLA',
        producto: 'crudo',
        resultado: { valor: 1000 },
        cumplimiento_pct: null,
        mes: { nombre: 'Mayo', anio: 2026, completo: true },
      },
    });

    expect(panel?.tipo).toBe('cuant_kpi');
    if (panel?.tipo === 'cuant_kpi') {
      expect(panel.datos.cumplimientoPct).toBeNull();
      expect(panel.datos.real).toBe(1000);
      expect(panel.datos.entidadCualificada).toBe('el Campo CASTILLA');
    }
  });

  it('un producto desconocido cae a crudo, que es el default del catálogo', () => {
    const panel = aPanel({
      tipo: 'cuant_kpi',
      datos: { producto: 'helio', resultado: { valor: 1 }, mes: {} },
    });
    if (panel?.tipo === 'cuant_kpi') {
      expect(panel.datos.producto).toBe('crudo');
    }
  });

  it('el panel del P50 se marca con su propia escala', () => {
    // 🔑 A5: esa hoja NO está en la escala del fact (ratio ~29, no 1e6).
    // Aplicarle la conversión del gas mostraba "0,03" donde iban "33.453,2".
    const panel = aPanel({
      tipo: 'p50_vp',
      datos: { vice: 'GOR', producto: 'gas', real: 33453.2, p50: 30000 },
    });

    if (panel?.tipo === 'p50_vp') {
      expect(panel.datos.escala).toBe('p50_vp');
    }
  });

  it('una lista ausente se convierte en array vacío, no en undefined', () => {
    // Un `undefined` suelto reventaría el `.map()` del componente.
    const panel = aPanel({ tipo: 'cuant_serie', datos: {} });
    if (panel?.tipo === 'cuant_serie') {
      expect(panel.datos.serie).toEqual([]);
      expect(panel.datos.avisos).toEqual([]);
    }
  });

  it('el ranking conserva la semántica de orden (D3)', () => {
    const panel = aPanel({
      tipo: 'cuant_rank',
      datos: { metrica: 'gap', direccion: 'bottom', items: [] },
    });
    if (panel?.tipo === 'cuant_rank') {
      expect(panel.datos.metrica).toBe('gap');
      expect(panel.datos.direccion).toBe('bottom');
    }
  });
});

describe('aRespuestaQ', () => {
  it('normaliza la respuesta completa', () => {
    const r = aRespuestaQ({
      log_id: 42,
      texto_original: '¿cuánto produjo Castilla?',
      grupo: 'cuantificar',
      grupo_label: 'Cuantificar',
      capa_resolutora: 'regex',
      entidad_cruda: 'CASTILLA',
      patrones: ['PRODUCCION DE'],
      llm_diag: null,
      timestamp: '2026-08-20T12:00:00Z',
      mensaje: 'Ahí va.',
      panel: null,
      vp_ofrecida: null,
    });

    expect(r.logId).toBe(42);
    expect(r.grupo).toBe('cuantificar');
    expect(r.entidadCruda).toBe('CASTILLA');
    expect(r.panel).toBeNull();
  });

  it('un grupo desconocido degrada a "desconocido"', () => {
    expect(aRespuestaQ({ grupo: 'inventado' }).grupo).toBe('desconocido');
  });

  it('una respuesta vacía no revienta', () => {
    const r = aRespuestaQ({});
    expect(r.grupo).toBe('desconocido');
    expect(r.patrones).toEqual([]);
    expect(r.logId).toBeNull();
  });
});
