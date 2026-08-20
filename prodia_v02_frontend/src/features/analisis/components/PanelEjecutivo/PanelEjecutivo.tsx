import { QueryState } from '../../../../shared/components/QueryState';
import { formatBl, formatMscf, formatPct } from '../../../../shared/utils/format';
import { useEjecutivo } from '../../hooks/useAnalisis';
import type { Ambito, Ejecutivo, Foco, TarjetaKpi } from '../../types/analisisTypes';
import { AcordeonFoco } from '../AcordeonFoco';
import styles from './PanelEjecutivo.module.scss';

interface PanelEjecutivoProps {
  ambito: Ambito;
}

function formatearVolumen(producto: string, valor: number): string {
  return producto === 'GAS' ? formatMscf(valor) : formatBl(valor);
}

export function PanelEjecutivo({ ambito }: PanelEjecutivoProps) {
  const query = useEjecutivo(ambito);

  return (
    <QueryState query={query}>
      {(ejecutivo) => {
        if (!ejecutivo.encontrada || ejecutivo.sinDatos) {
          return (
            <p className={styles.aviso}>
              Sin análisis disponible para este ámbito.
            </p>
          );
        }

        return (
          <section className={styles.panel}>
            <header className={styles.encabezado}>
              <h2 className={styles.titulo}>{ejecutivo.meta.scope}</h2>
              <p className={styles.subtitulo}>
                {ejecutivo.meta.periodo} · corte {ejecutivo.meta.corte}
                {/* Transparencia sobre el origen del texto: el composer
                    determinista es el default, el LLM es pulido opcional. */}
                {ejecutivo.meta.generadoPor === 'llm' && (
                  <span className={styles.insignia}>prosa asistida</span>
                )}
              </p>
            </header>

            <div className={styles.tarjetas}>
              {ejecutivo.tarjetas.map((t) => (
                <TarjetaCierre key={t.producto} tarjeta={t} />
              ))}
            </div>

            {ejecutivo.secciones && <Secciones ejecutivo={ejecutivo} />}

            <div className={styles.focos}>
              <h3 className={styles.tituloSeccion}>Focos por producto</h3>
              {ejecutivo.focos.map((f) => (
                <AcordeonFoco key={f.producto} foco={f} ambito={ambito} />
              ))}
              {ejecutivo.sinFoco && (
                <p className={styles.nota}>{ejecutivo.sinFoco}</p>
              )}
            </div>
          </section>
        );
      }}
    </QueryState>
  );
}

/**
 * Tarjeta de cierre por producto.
 *
 * El `estado` lo decide el BACKEND, no el frontend: derivarlo de
 * "proyectado < meta" marcaría en rojo un 94 % que la banda ámbar considera
 * "ajustado".
 */
function TarjetaCierre({ tarjeta }: { tarjeta: TarjetaKpi }) {
  const claseEstado = tarjeta.estado
    ? styles[`estado_${tarjeta.estado}`]
    : styles.estado_neutro;

  return (
    <article className={`${styles.tarjeta} ${claseEstado}`}>
      <header className={styles.tarjetaCabecera}>
        <h3 className={styles.tarjetaNombre}>{tarjeta.producto}</h3>
        {tarjeta.estado && (
          <span className={styles.chip}>{etiquetaEstado(tarjeta.estado)}</span>
        )}
      </header>

      <p className={styles.tarjetaValor}>
        {formatearVolumen(tarjeta.producto, tarjeta.proyectadoCierre)}
        <span className={styles.tarjetaUnidad}> {tarjeta.unidad ?? ''}/mes</span>
      </p>

      {tarjeta.metaMes > 0 ? (
        <>
          <div className={styles.barra}>
            {/* El relleno topa en 100 % para no desbordar; el texto muestra el
                porcentaje real, así que un 108 % sigue siendo visible. */}
            <span style={{ width: `${Math.min(tarjeta.rellenoPct, 100)}%` }} />
          </div>
          <p className={styles.tarjetaMeta}>
            {formatPct((tarjeta.proyectadoCierre / tarjeta.metaMes) * 100)} de{' '}
            {formatearVolumen(tarjeta.producto, tarjeta.metaMes)}
            {tarjeta.metaDePromedio && (
              <span className={styles.nota}> (promedio del año)</span>
            )}
          </p>
        </>
      ) : (
        <p className={styles.tarjetaSinMeta}>Sin meta definida</p>
      )}

      {/* Solo se muestra si la curva diaria reconcilia con el mensual. */}
      {tarjeta.bopd && (
        <p className={styles.tarjetaRitmo}>
          Ritmo {formatBl(tarjeta.bopd.real)} · requerido{' '}
          {formatBl(tarjeta.bopd.requerido)}
          {tarjeta.bopd.deltaPct !== null && (
            <span className={styles.nota}> ({formatPct(tarjeta.bopd.deltaPct)})</span>
          )}
        </p>
      )}
    </article>
  );
}

function etiquetaEstado(estado: string): string {
  const etiquetas: Record<string, string> = {
    alineado: 'Alineado',
    ajustado: 'Ajustado',
    actuar: 'Actuar',
  };
  return etiquetas[estado] ?? estado;
}

function Secciones({ ejecutivo }: { ejecutivo: Ejecutivo }) {
  const secciones = ejecutivo.secciones;
  if (!secciones) return null;

  const bloques: { titulo: string; frases: string[] }[] = [
    { titulo: 'Hallazgos', frases: secciones.insights },
    { titulo: 'Oportunidades', frases: secciones.oportunidades },
    { titulo: 'Puntos de atención', frases: secciones.puntosAtencion },
    { titulo: 'Decisiones', frases: secciones.decisiones },
  ];

  return (
    <div className={styles.secciones}>
      {bloques.map((b) => (
        <div key={b.titulo} className={styles.seccion}>
          <h3 className={styles.tituloSeccion}>{b.titulo}</h3>
          <ul className={styles.listaFrases}>
            {b.frases.map((frase) => (
              <li key={frase}>{frase}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export type { Foco };
