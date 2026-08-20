import { useMemo, useState } from 'react';

import { Grafico } from '../../../../shared/components/Grafico';
import type { DatosGrafico } from '../../../../shared/components/Grafico';
import { QueryState } from '../../../../shared/components/QueryState';
import { formatBl, formatKUSD, formatPct } from '../../../../shared/utils/format';
import {
  useDiferidas,
  useMantenimientos,
  useWaterfall,
} from '../../hooks/useAnalisis';
import type { Ambito, Foco } from '../../types/analisisTypes';
import styles from './AcordeonFoco.module.scss';

interface AcordeonFocoProps {
  foco: Foco;
  ambito: Ambito;
}

type Pill = 'comportamiento' | 'diferidas' | 'mantenimientos' | 'ebitda';

const PILLS: { id: Pill; etiqueta: string }[] = [
  { id: 'comportamiento', etiqueta: 'Comportamiento' },
  { id: 'diferidas', etiqueta: 'Diferidas' },
  { id: 'mantenimientos', etiqueta: 'Mantenimientos' },
  { id: 'ebitda', etiqueta: 'EBITDA-NOPAT' },
];

/**
 * Foco de un producto, con sus 4 pills de detalle.
 *
 * **Carga perezosa**: cada pill solo consulta cuando está visible. Sin eso,
 * abrir un foco dispararía 4 peticiones caras de golpe.
 *
 * **Scope por props, nunca global**: la entidad y el nivel llegan desde el
 * llamador. En el sistema viejo las pills leían el estado global del tablero,
 * así que abrir el foco de "Rubiales" podía mostrar las diferidas de
 * "Castilla".
 */
export function AcordeonFoco({ foco, ambito }: AcordeonFocoProps) {
  const [abierto, setAbierto] = useState(false);
  const [pill, setPill] = useState<Pill>('comportamiento');

  // Los campos nombrados por el foco acotan las pills; si no hay, se usa la
  // entidad del ámbito.
  const entidadPill = foco.entidades.length
    ? foco.entidades.join('|')
    : ambito.entidad;
  const nivelPill = foco.entidades.length ? 'campo' : ambito.nivel;

  return (
    <article className={styles.foco}>
      <button
        type="button"
        className={styles.cabecera}
        aria-expanded={abierto}
        onClick={() => setAbierto((previo) => !previo)}
      >
        <span className={styles.producto}>{foco.producto}</span>
        {foco.entidades.length > 0 && (
          <span className={styles.entidades}>{foco.entidades.join(' + ')}</span>
        )}
        <span className={foco.esOk ? styles.etiquetaOk : styles.etiquetaFoco}>
          {foco.estadoLabel}
        </span>
        {foco.titulo && <span className={styles.tituloFoco}>{foco.titulo}</span>}
        <span className={styles.flecha} aria-hidden="true">
          {abierto ? '▾' : '▸'}
        </span>
      </button>

      {abierto && (
        <div className={styles.cuerpo}>
          {foco.causa.texto && (
            <p className={styles.causa}>{foco.causa.texto}</p>
          )}
          {foco.causa.detalle.length > 0 && (
            <ul className={styles.detalle}>
              {foco.causa.detalle.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          )}
          {foco.accion && <p className={styles.accion}>{foco.accion}</p>}

          <div className={styles.pills} role="tablist" aria-label="Detalle del foco">
            {PILLS.map((p) => (
              <button
                key={p.id}
                type="button"
                role="tab"
                aria-selected={pill === p.id}
                className={pill === p.id ? styles.pillActiva : styles.pill}
                onClick={() => setPill(p.id)}
              >
                {p.etiqueta}
              </button>
            ))}
          </div>

          <div className={styles.contenidoPill}>
            {pill === 'comportamiento' && <PillComportamiento foco={foco} />}
            {pill === 'diferidas' && (
              <PillDiferidas entidad={entidadPill} nivel={nivelPill} activa />
            )}
            {pill === 'mantenimientos' && (
              <PillMantenimientos entidad={entidadPill} nivel={nivelPill} activa />
            )}
            {pill === 'ebitda' && (
              <PillEbitda
                producto={foco.producto}
                entidad={entidadPill}
                nivel={nivelPill}
                activa
              />
            )}
          </div>
        </div>
      )}
    </article>
  );
}

function PillComportamiento({ foco }: { foco: Foco }) {
  if (foco.extremos && foco.extremos.length > 0) {
    return (
      <table className={styles.tabla}>
        <thead>
          <tr>
            <th>Campo</th>
            <th>Real</th>
            <th>Meta</th>
          </tr>
        </thead>
        <tbody>
          {foco.extremos.map((e) => (
            <tr key={e.campo}>
              <td>{e.campo}</td>
              <td>{formatBl(e.real)}</td>
              <td>{formatBl(e.meta)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (foco.causa.eventos && foco.causa.eventos.length > 0) {
    return (
      <ul className={styles.eventos}>
        {foco.causa.eventos.map((e) => (
          <li key={`${e.campo}-${e.fecha}`}>
            <strong>{e.campo}</strong> <span className={styles.tenue}>{e.fecha}</span>
            <p className={styles.textoEvento}>{e.texto}</p>
          </li>
        ))}
      </ul>
    );
  }

  return <p className={styles.vacio}>Sin detalle adicional para este producto.</p>;
}

function PillDiferidas({
  entidad,
  nivel,
  activa,
}: {
  entidad?: string;
  nivel?: string;
  activa: boolean;
}) {
  const query = useDiferidas(entidad, nivel, activa);

  return (
    <QueryState query={query}>
      {(diferidas) => {
        if (diferidas.sinDatos) {
          return (
            <p className={styles.vacio}>
              {diferidas.motivo ?? 'Sin diferidas registradas para este ámbito.'}
            </p>
          );
        }
        return <ParetoDiferidas pareto={diferidas.pareto} />;
      }}
    </QueryState>
  );
}

/** R2: `data` depende SOLO del pareto recibido. */
function ParetoDiferidas({
  pareto,
}: {
  pareto: { grupo: string; total: number; pct: number }[];
}) {
  const datos = useMemo<DatosGrafico>(
    () => [
      {
        type: 'bar',
        orientation: 'h',
        x: pareto.map((p) => p.pct).reverse(),
        y: pareto.map((p) => p.grupo).reverse(),
        marker: { color: '#004236' },
        hovertemplate: '%{y}: %{x}%<extra></extra>',
      },
    ],
    [pareto],
  );

  const diseno = useMemo(
    () => ({
      xaxis: { title: { text: '% de incidentes' } },
      yaxis: { automargin: true },
      margin: { t: 8, r: 16, b: 40, l: 8 },
    }),
    [],
  );

  return (
    <Grafico
      data={datos}
      layout={diseno}
      alto={Math.max(180, pareto.length * 28 + 60)}
      descripcion="Pareto de causas de producción diferida"
    />
  );
}

function PillMantenimientos({
  entidad,
  nivel,
  activa,
}: {
  entidad?: string;
  nivel?: string;
  activa: boolean;
}) {
  const query = useMantenimientos(entidad, nivel, undefined, activa);

  return (
    <QueryState query={query}>
      {(mantenimientos) => {
        if (mantenimientos.sinDatos) {
          return (
            <p className={styles.vacio}>
              {mantenimientos.motivo ??
                'Sin eventos de mantenimiento en el periodo.'}
            </p>
          );
        }
        return (
          <>
            <p className={styles.tenue}>
              {mantenimientos.meta.total} eventos ·{' '}
              <strong>{mantenimientos.meta.abiertos} abiertos</strong> ·{' '}
              {mantenimientos.meta.periodo}
            </p>
            <table className={styles.tabla}>
              <thead>
                <tr>
                  <th>Pozo</th>
                  <th>Tipo</th>
                  <th>Estado</th>
                  <th>Inicio</th>
                  <th>Fin</th>
                </tr>
              </thead>
              <tbody>
                {mantenimientos.eventos.map((e) => (
                  <tr key={`${e.pozo}-${e.inicio}`}>
                    <td>{e.pozo}</td>
                    <td>{e.tipo}</td>
                    <td>
                      <span
                        className={
                          e.estado === 'abierto' ? styles.abierto : styles.cerrado
                        }
                      >
                        {e.estado}
                      </span>
                    </td>
                    <td>{e.inicio}</td>
                    <td>{e.fin}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        );
      }}
    </QueryState>
  );
}

function PillEbitda({
  producto,
  entidad,
  nivel,
  activa,
}: {
  producto: string;
  entidad?: string;
  nivel?: string;
  activa: boolean;
}) {
  // El waterfall económico solo aplica a crudo (variante `_a` de la BD
  // operacional): pedirlo para gas o blancos daría cifras que no le
  // corresponden.
  const esCrudo = producto === 'CRUDO';
  const query = useWaterfall(entidad, nivel, activa && esCrudo);

  if (!esCrudo) {
    return <p className={styles.vacio}>El EBITDA-NOPAT solo aplica a crudo.</p>;
  }

  return (
    <QueryState query={query}>
      {(waterfall) => <WaterfallEbitda componentes={waterfall.components} />}
    </QueryState>
  );
}

/** R2: `data` depende SOLO de los componentes recibidos. */
function WaterfallEbitda({
  componentes,
}: {
  componentes: { key: string; label: string; valueKusd: number; type: string }[];
}) {
  const datos = useMemo<DatosGrafico>(
    () => [
      {
        type: 'waterfall',
        orientation: 'v',
        x: componentes.map((c) => c.label),
        y: componentes.map((c) => c.valueKusd),
        // `total` arranca desde cero; `relative` continúa desde el anterior.
        measure: componentes.map((c) =>
          c.type === 'total' ? 'total' : 'relative',
        ),
        increasing: { marker: { color: '#2a7a50' } },
        decreasing: { marker: { color: '#e24b4a' } },
        totals: { marker: { color: '#004236' } },
        hovertemplate: '%{x}: %{y:,.0f} kUSD<extra></extra>',
      } as DatosGrafico[number],
    ],
    [componentes],
  );

  const diseno = useMemo(
    () => ({
      yaxis: { title: { text: 'kUSD' } },
      xaxis: { automargin: true, tickangle: -45 },
      margin: { t: 8, r: 16, b: 120, l: 64 },
    }),
    [],
  );

  const nopat = componentes.find((c) => c.key === 'util_neta');

  return (
    <>
      <Grafico
        data={datos}
        layout={diseno}
        alto={380}
        descripcion="Waterfall económico de Ingresos a NOPAT"
      />
      {nopat && (
        <p className={styles.tenue}>
          Utilidad neta: <strong>{formatKUSD(nopat.valueKusd)}</strong>
        </p>
      )}
    </>
  );
}

export { formatPct };
