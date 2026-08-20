import { useMemo } from 'react';

import { Grafico } from '../../../../shared/components/Grafico';
import type { DatosGrafico } from '../../../../shared/components/Grafico';
import { QueryState } from '../../../../shared/components/QueryState';
import { formatBbl, formatMscf, formatPct } from '../../../../shared/utils/format';
import { useDesempeno } from '../../hooks/useAnalisis';
import type { Ambito, Desempeno } from '../../types/analisisTypes';
import styles from './PanelDesempeno.module.scss';

interface PanelDesempenoProps {
  ambito: Ambito;
}

/** Un color por producto, estable en todos los gráficos de la sección. */
const COLOR_PRODUCTO: Record<string, string> = {
  CRUDO: '#004236',
  GAS: '#6cd300',
  BLANCOS: '#00214d',
};

/**
 * A5 — cada producto con SU formateador. El gas va en MSCF; usar el de crudo
 * mostró "0,03" donde debía decir "33.453,2": mil veces menor, sin error
 * visible.
 */
function formatearVolumen(producto: string, valor: number): string {
  return producto === 'GAS' ? formatMscf(valor) : formatBbl(valor);
}

export function PanelDesempeno({ ambito }: PanelDesempenoProps) {
  const query = useDesempeno(ambito);

  return (
    <QueryState query={query}>
      {(desempeno) => {
        if (!desempeno.encontrada) {
          return (
            <p className={styles.aviso}>
              No se encontró <strong>{ambito.entidad}</strong> en el catálogo.
              Revisa el nombre o el nivel seleccionado.
            </p>
          );
        }
        if (desempeno.sinDatos) {
          return (
            <p className={styles.aviso}>
              La entidad existe pero no tiene datos de producción en el periodo.
            </p>
          );
        }

        return (
          <section className={styles.panel}>
            <Encabezado desempeno={desempeno} />
            <KpisPorProducto desempeno={desempeno} />
            {desempeno.camposSinMeta.length > 0 && (
              <CamposSinMeta desempeno={desempeno} />
            )}
            {desempeno.curva && desempeno.curva.fechas.length > 0 && (
              <CurvaDiaria desempeno={desempeno} />
            )}
            {desempeno.ritmoMensual && desempeno.ritmoMensual.meses.length > 0 && (
              <RitmoMensual desempeno={desempeno} />
            )}
          </section>
        );
      }}
    </QueryState>
  );
}

function Encabezado({ desempeno }: { desempeno: Desempeno }) {
  const mes = desempeno.mes;
  return (
    <header className={styles.encabezado}>
      <h2 className={styles.titulo}>
        {desempeno.entidad ?? 'Global (toda la producción)'}
        {mes && (
          <span className={styles.periodo}>
            {' '}
            · {mes.nombre} {mes.anio} · corte {mes.diasConData}/{mes.diasDelMes}
          </span>
        )}
      </h2>

      {/* El backend DECLARA cuando no pudo honrar el periodo, en vez de servir
          otro en silencio. */}
      {!desempeno.periodoOk && (
        <p className={styles.avisoLinea}>
          El periodo solicitado no está soportado (solo meses). Se muestra el
          último mes con datos.
        </p>
      )}
      {desempeno.sinCierre && (
        <p className={styles.avisoLinea}>
          Sin cifras mensuales de cierre para este periodo.
        </p>
      )}
      {!desempeno.aplicaDiario && (
        <p className={styles.avisoLinea}>
          Sin grano diario: esta entidad solo reporta a nivel mensual.
        </p>
      )}
    </header>
  );
}

function KpisPorProducto({ desempeno }: { desempeno: Desempeno }) {
  return (
    <div className={styles.kpis}>
      {desempeno.porProducto.map((p) => (
        <article key={p.producto} className={styles.kpi}>
          <header className={styles.kpiCabecera}>
            <span
              className={styles.kpiPunto}
              style={{ background: COLOR_PRODUCTO[p.producto] }}
              aria-hidden="true"
            />
            <h3 className={styles.kpiNombre}>{p.producto}</h3>
          </header>

          <p className={styles.kpiValor}>{formatearVolumen(p.producto, p.real)}</p>

          {/* `null` NO es 0 %: significa que no hay meta con la que comparar. */}
          {p.cumplimiento === null ? (
            <p className={styles.kpiSinMeta}>Sin meta en el periodo</p>
          ) : (
            <p className={styles.kpiMeta}>
              {formatPct(p.cumplimiento)} de {formatearVolumen(p.producto, p.ppto)}
            </p>
          )}
        </article>
      ))}
    </div>
  );
}

function CamposSinMeta({ desempeno }: { desempeno: Desempeno }) {
  return (
    <div className={styles.avisoBloque}>
      <h3 className={styles.subtitulo}>Campos que producen sin meta asignada</h3>
      <p className={styles.nota}>
        Su producción SÍ suma al total, pero no tienen presupuesto en el
        periodo. Se declaran en vez de inventarles una meta: compararlos contra
        un presupuesto que no los cubre inflaría el cumplimiento del activo.
      </p>
      <ul className={styles.listaCampos}>
        {desempeno.camposSinMeta.map((c) => (
          <li key={`${c.campo}-${c.producto}`}>
            <strong>{c.campo}</strong> · {c.producto} ·{' '}
            {formatearVolumen(c.producto, c.real)}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Curva diaria por producto.
 *
 * R2: `data` depende SOLO de `desempeno.curva`. No hay estado de selección ni
 * de hover en este componente, así que no puede entrar en las dependencias.
 */
function CurvaDiaria({ desempeno }: { desempeno: Desempeno }) {
  const curva = desempeno.curva;

  const datos = useMemo<DatosGrafico>(() => {
    if (!curva) return [];
    return Object.entries(curva.series)
      .filter(([, valores]) => valores.some((v) => v > 0))
      .map(([producto, valores]) => ({
        type: 'scatter',
        mode: 'lines',
        name: producto,
        x: curva.fechas,
        y: valores,
        line: { color: COLOR_PRODUCTO[producto], width: 2 },
      }));
  }, [curva]);

  const diseno = useMemo(
    () => ({
      title: { text: 'Producción diaria' },
      xaxis: { title: { text: 'Día' } },
      yaxis: { title: { text: 'Volumen' }, rangemode: 'tozero' as const },
      legend: { orientation: 'h' as const, y: -0.2 },
      hovermode: 'x unified' as const,
    }),
    [],
  );

  if (datos.length === 0) return null;
  return (
    <Grafico data={datos} layout={diseno} descripcion="Curva de producción diaria" />
  );
}

/**
 * Producción mensual del año: barras por mes + línea de promedio.
 *
 * Sale del MISMO fact mensual que las tarjetas, así que las cifras reconcilian
 * exacto. R2: depende solo de `ritmoMensual`.
 */
function RitmoMensual({ desempeno }: { desempeno: Desempeno }) {
  const ritmo = desempeno.ritmoMensual;

  const datos = useMemo<DatosGrafico>(() => {
    if (!ritmo) return [];
    const barras: DatosGrafico = Object.entries(ritmo.series)
      .filter(([, valores]) => valores.some((v) => v !== null))
      .map(([producto, valores]) => ({
        type: 'bar',
        name: producto,
        x: ritmo.meses,
        y: valores,
        marker: { color: COLOR_PRODUCTO[producto] },
      }));

    // Línea de promedio: solo para los productos que tienen meses cerrados.
    const lineas: DatosGrafico = Object.entries(ritmo.promedioMes)
      .filter(([, promedio]) => promedio !== null)
      .map(([producto, promedio]) => ({
        type: 'scatter',
        mode: 'lines',
        name: `Promedio ${producto}`,
        x: ritmo.meses,
        y: ritmo.meses.map(() => promedio as number),
        line: { color: COLOR_PRODUCTO[producto], width: 1, dash: 'dot' as const },
        // El orden de los tokens importa para los tipos de Plotly: `y+name`
        // es válido, `name+y` no.
        hoverinfo: 'y+name' as const,
      }));

    return [...barras, ...lineas];
  }, [ritmo]);

  const diseno = useMemo(
    () => ({
      title: { text: 'Producción mensual del año' },
      barmode: 'group' as const,
      yaxis: { title: { text: 'Volumen' }, rangemode: 'tozero' as const },
      legend: { orientation: 'h' as const, y: -0.2 },
    }),
    [],
  );

  if (datos.length === 0) return null;
  return (
    <Grafico
      data={datos}
      layout={diseno}
      descripcion="Producción mensual del año con su promedio"
    />
  );
}
