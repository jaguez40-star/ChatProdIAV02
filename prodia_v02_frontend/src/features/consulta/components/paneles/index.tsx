/**
 * Los componentes de panel de la pila de resultados.
 *
 * **Son SVG y CSS, no Plotly**, y no es una preferencia estética: el sistema
 * de origen ya lo hace así deliberadamente —sus paneles de resultado son
 * funciones puras que devuelven SVG— y solo el acordeón analítico pesado usa
 * la librería. Importar Plotly aquí metería 4,7 MB en el bundle de una página
 * que se abre siempre.
 */

import { formatBl, formatMscf, formatPct } from '../../../../shared/utils/format';
import type { Panel, Producto } from '../../types/consultaTypes';
import styles from './paneles.module.scss';

/**
 * ⚠️ A5 — la unidad NO es función del producto solamente.
 *
 * El gas del fact va en MSCF, pero la hoja del P50 está en otra escala
 * (ratio ~29, no 1e6): aplicarle la conversión del gas mostraba "0,03" donde
 * iban "33.453,2". Por eso la escala viaja como parámetro.
 */
function formatearVolumen(
  valor: number,
  producto: Producto,
  escala: 'fact' | 'p50_vp' = 'fact',
): string {
  if (escala === 'p50_vp') {
    // Tal cual: esta hoja no está en la escala del fact.
    return formatBl(valor, { maximumFractionDigits: 1 });
  }
  return producto === 'gas' ? formatMscf(valor) : `${formatBl(valor)} bbl`;
}

/** Aviso explícito cuando llega un tipo que este frontend no conoce (Q5). */
export function PanelDesconocido({ tipo }: { tipo: string }) {
  return (
    <div className={styles.desconocido} role="alert">
      <strong>No puedo mostrar este resultado.</strong>
      <p>
        El servidor devolvió un panel de tipo «{tipo}», que esta versión de la
        aplicación no sabe pintar. Es probable que el backend sea más reciente
        que el frontend.
      </p>
    </div>
  );
}

function Avisos({ avisos }: { avisos: string[] }) {
  if (avisos.length === 0) return null;
  return (
    <ul className={styles.avisos}>
      {avisos.map((a) => (
        <li key={a}>⚠️ {a}</li>
      ))}
    </ul>
  );
}

/**
 * Dispatcher de contenido por tipo.
 *
 * Se agrupan aquí los nueve porque cada uno es una tabla o una lista corta;
 * separarlos en nueve archivos daría nueve módulos triviales.
 */
export function PanelGenerico({ panel }: { panel: Panel }) {
  switch (panel.tipo) {
    case 'cuant_kpi': {
      const d = panel.datos;
      return (
        <div className={styles.kpi}>
          <p className={styles.entidad}>{d.entidadCualificada}</p>
          <p className={styles.valor}>
            {formatearVolumen(d.real, d.producto)}
          </p>
          <p className={styles.meta}>
            {/* `null` = sin meta. No se muestra "0 %": eso inventaría un
                incumplimiento (Q2). */}
            {d.cumplimientoPct === null
              ? 'Sin meta definida en el periodo'
              : `${formatPct(d.cumplimientoPct)} del ${d.referenciaLabel} · ${d.estado}`}
          </p>
          <p className={styles.corte}>
            {d.mes.nombre} {d.mes.anio} ·{' '}
            {d.mes.completo
              ? 'mes cerrado'
              : `proyección · ${d.mes.diasConData}/${d.mes.diasDelMes} días`}
          </p>
          <Avisos avisos={d.avisos} />
        </div>
      );
    }

    case 'cuant_serie': {
      const d = panel.datos;
      return (
        <div>
          <p className={styles.entidad}>
            {d.entidadCualificada} · {d.producto} · {d.anio}
          </p>
          <table className={styles.tabla}>
            <thead>
              <tr>
                <th>Mes</th>
                <th>Volumen ({d.unidad})</th>
              </tr>
            </thead>
            <tbody>
              {d.serie.map((p) => (
                <tr key={p.mes}>
                  <td>
                    {p.mes}
                    {/* El mes proyectado se marca: pintarlo igual daría por
                        cerrado lo que no lo está. */}
                    {p.mes === d.proyeccionMes && (
                      <span className={styles.proy}> (proyección)</span>
                    )}
                  </td>
                  <td>{formatearVolumen(p.valor, d.producto)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Avisos avisos={d.avisos} />
        </div>
      );
    }

    case 'cuant_var': {
      const d = panel.datos;
      return (
        <div>
          <p className={styles.entidad}>
            {d.entidadCualificada} · {d.producto}
          </p>
          <table className={styles.tabla}>
            <thead>
              <tr>
                <th>De</th>
                <th>A</th>
                <th>Cambio ({d.unidad})</th>
              </tr>
            </thead>
            <tbody>
              {d.deltas.map((x) => (
                <tr key={`${x.de}-${x.a}`}>
                  <td>{x.de}</td>
                  <td>{x.a}</td>
                  <td className={x.delta >= 0 ? styles.sube : styles.baja}>
                    {x.delta >= 0 ? '+' : '−'}
                    {formatearVolumen(Math.abs(x.delta), d.producto)}
                    {x.pct !== null && ` (${formatPct(x.pct)})`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Avisos avisos={d.avisos} />
        </div>
      );
    }

    case 'cuant_rank': {
      const d = panel.datos;
      const esGap = d.metrica === 'gap';
      return (
        <div>
          <p className={styles.entidad}>
            {d.periodoLabel} · {d.producto}
            {d.esProyeccion && <span className={styles.proy}> (proyección)</span>}
          </p>
          <table className={styles.tabla}>
            <thead>
              <tr>
                <th>#</th>
                <th>Entidad</th>
                <th>{esGap ? `Gap (${d.unidad})` : `Volumen (${d.unidad})`}</th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((i) => (
                <tr key={i.entidad}>
                  <td>{i.pos}</td>
                  <td>
                    {i.entidad}
                    {/* Los terceros se rotulan, no se ocultan: esconderlos
                        daría un ranking falso. */}
                    {!i.esEcp && i.operador && (
                      <span className={styles.tercero}> · {i.operador}</span>
                    )}
                  </td>
                  <td className={esGap && i.gap < 0 ? styles.baja : undefined}>
                    {formatearVolumen(esGap ? i.gap : i.valor, d.producto)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className={styles.pie}>
            Sobre {d.totalUniverso} {d.nivelRanking === 'activo' ? 'activos' : 'campos'}{' '}
            con producción registrada.
            {/* D4: los ceros se declaran, no se cuelan como "poca producción". */}
            {d.sinRegistro > 0 && ` ${d.sinRegistro} sin registro en el periodo.`}
            {d.concentracionPct !== null &&
              ` Concentran el ${formatPct(d.concentracionPct)} del total.`}
          </p>
        </div>
      );
    }

    case 'jerarq_arbol': {
      const d = panel.datos;
      return (
        <div>
          <p className={styles.entidad}>
            {d.entidad}
            {/* R2: se rotula el nivel REAL cuando la fuente lo tiene mal. */}
            <span className={styles.nivel}>
              {' '}
              · {d.puente ? 'vicepresidencia' : d.nivel}
            </span>
          </p>
          {d.padres.map((p) => (
            <p key={p.nivel} className={styles.linea}>
              <strong>{p.nivel}:</strong> {p.items.join(', ')}
            </p>
          ))}
          {d.hijosGrupos.map((g) => (
            <p key={g.nivel} className={styles.linea}>
              <strong>{g.nivel}:</strong> {g.items.join(', ')}
              {/* El tope se declara en vez de recortar en silencio. */}
              {g.truncado && ` … (${g.total} en total)`}
            </p>
          ))}
          {d.pozos !== null && (
            <p className={styles.linea}>
              <strong>Pozos:</strong> {formatBl(d.pozos)}
            </p>
          )}
        </div>
      );
    }

    case 'jerarq_operador': {
      const d = panel.datos;
      return (
        <div>
          <p className={styles.entidad}>{d.entidad}</p>
          <p className={styles.linea}>{d.campos.join(', ')}</p>
          <p className={styles.pie}>
            {d.total} campos{d.truncado && ' (lista recortada)'}
          </p>
        </div>
      );
    }

    case 'jerarq_rank': {
      const d = panel.datos;
      return (
        <div>
          <p className={styles.entidad}>{d.subject}</p>
          <table className={styles.tabla}>
            <thead>
              <tr>
                <th>#</th>
                <th>Entidad</th>
                <th>{d.conteo}</th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((i) => (
                <tr key={i.entidad}>
                  <td>{i.pos}</td>
                  <td>{i.entidad}</td>
                  <td>{formatBl(i.n)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className={styles.pie}>Sobre {d.total} entidades.</p>
        </div>
      );
    }

    case 'p50_vp': {
      const d = panel.datos;
      return (
        <div className={styles.kpi}>
          <p className={styles.entidad}>
            {d.vice} · {d.producto} · {d.mesReal}
          </p>
          <p className={styles.valor}>
            {/* ⚠️ Escala propia: NO se le aplica la conversión del gas. */}
            {formatearVolumen(d.real, d.producto, d.escala)} {d.unidad}
          </p>
          <p className={styles.meta}>
            P50: {formatearVolumen(d.p50, d.producto, d.escala)} {d.unidad}
            {d.pct !== null && ` · ${formatPct(d.pct)}`}
          </p>
        </div>
      );
    }

    case 'analiza_foco': {
      const d = panel.datos;
      return (
        <div>
          <p className={styles.entidad}>
            {d.entidad}
            {d.nivel && <span className={styles.nivel}> · {d.nivel}</span>}
          </p>
          <p className={styles.linea}>
            Análisis de{' '}
            {d.productos.length ? d.productos.join(', ') : 'los tres productos'}.
            Ábrelo en la sección Análisis para ver el detalle.
          </p>
        </div>
      );
    }

    default: {
      const _exhaustivo: never = panel;
      void _exhaustivo;
      return <PanelDesconocido tipo={(panel as { tipo: string }).tipo} />;
    }
  }
}
