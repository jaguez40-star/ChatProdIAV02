import { useMemo, useState } from 'react';

import { QueryState } from '../../../../shared/components/QueryState';
import { Grafico } from '../../../../shared/components/Grafico';
import type { DatosGrafico } from '../../../../shared/components/Grafico';
import { formatBl, formatPct } from '../../../../shared/utils/format';
import { useCatalogo, useCobertura, useDensidad } from '../../hooks/useAnalisis';
import type { Densidad } from '../../types/analisisTypes';
import styles from './PanelFundacion.module.scss';

interface PanelFundacionProps {
  entidad?: string;
}

type Vista = 'catalogo' | 'densidad' | 'cobertura';

const VISTAS: { id: Vista; etiqueta: string }[] = [
  { id: 'catalogo', etiqueta: 'Catálogo de entidades' },
  { id: 'densidad', etiqueta: 'Densidad temporal' },
  { id: 'cobertura', etiqueta: 'Cobertura del reporte' },
];

const COLOR_SEMAFORO: Record<string, string> = {
  verde: '#2a7a50',
  amarillo: '#d98324',
  rojo: '#e24b4a',
};

/**
 * Fundación de datos: qué entidades existen, con qué continuidad y en qué
 * hojas viven. Responde "¿puedo confiar en lo que voy a analizar?" antes de
 * analizarlo.
 */
export function PanelFundacion({ entidad }: PanelFundacionProps) {
  const [vista, setVista] = useState<Vista>('catalogo');

  return (
    <section className={styles.panel}>
      <div className={styles.pestanas} role="tablist" aria-label="Fundación de datos">
        {VISTAS.map((v) => (
          <button
            key={v.id}
            type="button"
            role="tab"
            aria-selected={vista === v.id}
            className={vista === v.id ? styles.pestanaActiva : styles.pestana}
            onClick={() => setVista(v.id)}
          >
            {v.etiqueta}
          </button>
        ))}
      </div>

      {vista === 'catalogo' && <VistaCatalogo />}
      {vista === 'densidad' && <VistaDensidad entidad={entidad} />}
      {vista === 'cobertura' && <VistaCobertura entidad={entidad} />}
    </section>
  );
}

function VistaCatalogo() {
  const query = useCatalogo();

  return (
    <QueryState query={query}>
      {(catalogo) => (
        <div className={styles.contenido}>
          <div className={styles.tarjetas}>
            {catalogo.cardinalidad.map((c) => (
              <div key={c.nivel} className={styles.tarjeta}>
                <span className={styles.tarjetaValor}>{formatBl(c.n)}</span>
                <span className={styles.tarjetaNivel}>{c.nivel}</span>
              </div>
            ))}
          </div>

          <p className={styles.nota}>
            Jerarquía ECP: vicepresidencia → gerencia → activo → área → campo →
            fuente. Filiales aparte: {catalogo.filiales.join(', ')}.
          </p>

          <h3 className={styles.subtitulo}>
            Colisiones de nombre ({catalogo.resumenColisiones.total})
          </h3>
          <p className={styles.nota}>
            Un mismo nombre que existe en varios niveles. Las{' '}
            <strong>duras</strong> y <strong>medias</strong> obligan a
            contrapreguntar; las blandas usan el nivel por defecto.
          </p>

          <table className={styles.tabla}>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Severidad</th>
                <th>Niveles</th>
              </tr>
            </thead>
            <tbody>
              {catalogo.colisiones
                .filter((c) => c.severidad !== 'blanda')
                .slice(0, 40)
                .map((c) => (
                  <tr key={c.nombre}>
                    <td>
                      <strong>{c.nombre}</strong>
                    </td>
                    <td>
                      <span className={styles[`sev_${c.severidad}`]}>{c.severidad}</span>
                    </td>
                    <td className={styles.celdaTenue}>{c.niveles.join(', ')}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </QueryState>
  );
}

function VistaDensidad({ entidad }: { entidad?: string }) {
  const query = useDensidad(entidad);

  return (
    <QueryState query={query}>
      {(densidad) =>
        !densidad.aplicaEcp ? (
          <p className={styles.aviso}>
            <strong>{densidad.entidad ?? 'La entidad'}</strong> no tiene datos a
            grano diario ECP. Puede aparecer en hojas derivadas o de filiales —
            revísalo en <em>Cobertura del reporte</em>. No es un error.
          </p>
        ) : (
          <div className={styles.contenido}>
            <div className={styles.resumenLinea}>
              <span>
                Días con dato: <strong>{formatBl(densidad.resumen.totalDias)}</strong>
              </span>
              <span>
                Rango: {densidad.resumen.rango[0] ?? '—'} →{' '}
                {densidad.resumen.rango[1] ?? '—'}
              </span>
              <span>
                Huecos: <strong>{formatBl(densidad.resumen.huecosTotales)}</strong>
              </span>
              <span>
                Racha máxima: <strong>{densidad.resumen.rachaMaxima}</strong> días
              </span>
            </div>

            <HeatmapDensidad densidad={densidad} />

            <h3 className={styles.subtitulo}>Qué análisis soporta este dato</h3>
            <ul className={styles.listaSemaforo}>
              {densidad.semaforo.map((f) => (
                <li key={f.familia}>
                  <span
                    className={styles.punto}
                    style={{ background: COLOR_SEMAFORO[f.nivel] }}
                    aria-hidden="true"
                  />
                  {f.familia}
                  {f.necesitaContinuidad && (
                    <em className={styles.celdaTenue}> (requiere días continuos)</em>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )
      }
    </QueryState>
  );
}

/**
 * Heatmap mes × día. El color es el nº de fuentes que reportaron ese día; una
 * celda vacía es un hueco.
 *
 * R2: `data` y `layout` se memoizan SOLO contra `densidad`. Este componente no
 * tiene estado de selección ni de hover, así que no puede colarse en las
 * dependencias.
 */
function HeatmapDensidad({ densidad }: { densidad: Densidad }) {
  const datos = useMemo<DatosGrafico>(() => {
    const porFecha = new Map(densidad.dias.map((d) => [d.fecha, d.fuentes]));
    const etiquetasY = densidad.porMes.map((m) => `${m.mesNombre} ${m.anio}`);
    const dias = Array.from({ length: 31 }, (_, i) => i + 1);

    const z = densidad.porMes.map((m) =>
      dias.map((dia) => {
        const clave = `${m.anio}-${String(m.mes).padStart(2, '0')}-${String(dia).padStart(2, '0')}`;
        return porFecha.get(clave) ?? null;
      }),
    );

    return [
      {
        type: 'heatmap',
        x: dias,
        y: etiquetasY,
        z,
        colorscale: [
          [0, '#e8f0ea'],
          [1, '#004236'],
        ],
        hovertemplate: 'Día %{x} · %{y}<br>%{z} fuentes<extra></extra>',
        showscale: false,
      },
    ];
  }, [densidad]);

  const diseno = useMemo(
    () => ({
      xaxis: { title: { text: 'Día del mes' }, dtick: 2 },
      yaxis: { automargin: true },
      margin: { t: 8, r: 8, b: 40, l: 8 },
    }),
    [],
  );

  return (
    <Grafico
      data={datos}
      layout={diseno}
      alto={Math.max(160, densidad.porMes.length * 28 + 60)}
      descripcion="Mapa de calor de días con dato por mes"
    />
  );
}

function VistaCobertura({ entidad }: { entidad?: string }) {
  const query = useCobertura(entidad);

  return (
    <QueryState query={query}>
      {(cobertura) => (
        <div className={styles.contenido}>
          <p className={styles.nota}>
            {cobertura.totalHojas} hojas del reporte, agrupadas por categoría. La
            métrica es el número de <strong>reportes</strong> donde aparece cada
            hoja.
            {cobertura.hojasConEntidad !== null && (
              <>
                {' '}
                <strong>{cobertura.hojasConEntidad}</strong> contienen a{' '}
                {cobertura.entidad}.
              </>
            )}
          </p>

          {cobertura.categorias.map((cat) => (
            <div key={cat.categoria}>
              <h3 className={styles.subtitulo}>{cat.categoria}</h3>
              <table className={styles.tabla}>
                <thead>
                  <tr>
                    <th>Hoja</th>
                    <th>Reportes</th>
                    {cobertura.entidad && <th>Con la entidad</th>}
                  </tr>
                </thead>
                <tbody>
                  {cat.hojas.map((h) => (
                    <tr key={h.hoja}>
                      <td>{h.hoja}</td>
                      <td>{formatBl(h.reportesTotal)}</td>
                      {cobertura.entidad && (
                        <td>
                          {h.reportesEntidad ?? 0}
                          {h.reportesTotal > 0 && (
                            <span className={styles.celdaTenue}>
                              {' '}
                              (
                              {formatPct(
                                ((h.reportesEntidad ?? 0) / h.reportesTotal) * 100,
                              )}
                              )
                            </span>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </QueryState>
  );
}
