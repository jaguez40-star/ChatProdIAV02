import { useMemo } from 'react';

import { useCatalogo } from '../../hooks/useAnalisis';
import type { Ambito } from '../../types/analisisTypes';
import styles from './SelectorAmbito.module.scss';

interface SelectorAmbitoProps {
  ambito: Ambito;
  onCambio: (ambito: Ambito) => void;
}

/** Niveles en orden de agregación, de mayor a menor. */
const NIVELES = [
  { valor: '', etiqueta: 'Sin nivel (unión)' },
  { valor: 'vicepresidencia', etiqueta: 'Vicepresidencia' },
  { valor: 'gerencia', etiqueta: 'Gerencia' },
  { valor: 'activo', etiqueta: 'Activo' },
  { valor: 'campo', etiqueta: 'Campo' },
  { valor: 'fuente', etiqueta: 'Fuente' },
];

/**
 * Selector de ámbito: entidad, nivel, periodo y segmento.
 *
 * Las entidades salen del catálogo real, no de una lista escrita a mano: si
 * mañana entra un campo nuevo aparece solo. El `nivel` importa porque la misma
 * palabra puede existir en varios niveles a la vez (por eso el catálogo reporta
 * "colisiones"), y sin él la resolución cae a una unión que puede agregar de
 * más.
 */
export function SelectorAmbito({ ambito, onCambio }: SelectorAmbitoProps) {
  const catalogo = useCatalogo();

  // Solo depende del catálogo y del nivel elegido: nunca de la entidad
  // seleccionada, para no recalcular la lista en cada tecla.
  const entidades = useMemo(() => {
    if (!catalogo.data) return [];
    const nivel = ambito.nivel?.trim();
    if (nivel && catalogo.data.entidadesPorNivel[nivel]) {
      // 🔑 Se deduplica también aquí, no solo en el caso de abajo: un mismo
      // nombre puede repetirse DENTRO de un nivel (dos campos homónimos bajo
      // activos distintos — las 151 colisiones que reporta Fundación).
      return [...new Set(catalogo.data.entidadesPorNivel[nivel])];
    }
    // 🔑 Sin el Set, este `.flat()` de TODOS los niveles garantiza duplicados,
    // y con ellos una consola llena de "Encountered two children with the same
    // key" (VIGIA, YAGUARA, YARIGUI-CANTAGALLO…) que React advierte que puede
    // duplicar u omitir hijos. Solo aparece con el catálogo real del 139: con
    // datos de prueba la lista es corta y no colisiona.
    return [...new Set(Object.values(catalogo.data.entidadesPorNivel).flat())].sort();
  }, [catalogo.data, ambito.nivel]);

  return (
    <div className={styles.selector}>
      <label className={styles.campo}>
        <span className={styles.etiqueta}>Segmento</span>
        <select
          className={styles.control}
          value={ambito.segmento ?? 'ecp'}
          onChange={(e) =>
            onCambio({ ...ambito, segmento: e.target.value as Ambito['segmento'] })
          }
        >
          <option value="ecp">Producción ECP</option>
          <option value="filiales">Filiales</option>
        </select>
      </label>

      <label className={styles.campo}>
        <span className={styles.etiqueta}>Nivel</span>
        <select
          className={styles.control}
          value={ambito.nivel ?? ''}
          // Al cambiar de nivel se limpia la entidad: la anterior puede no
          // existir en el nivel nuevo, y dejarla daría "no encontrada".
          onChange={(e) => onCambio({ ...ambito, nivel: e.target.value, entidad: '' })}
          disabled={ambito.segmento === 'filiales'}
        >
          {NIVELES.map((n) => (
            <option key={n.valor} value={n.valor}>
              {n.etiqueta}
            </option>
          ))}
        </select>
      </label>

      <label className={styles.campo}>
        <span className={styles.etiqueta}>Entidad</span>
        <input
          className={styles.control}
          list="entidades-analisis"
          value={ambito.entidad ?? ''}
          placeholder="Global (toda la producción)"
          onChange={(e) => onCambio({ ...ambito, entidad: e.target.value })}
          disabled={ambito.segmento === 'filiales'}
        />
        <datalist id="entidades-analisis">
          {/* 🔑 Se deduplica ANTES de pintar. El catálogo real del 139 trae el
              mismo nombre más de una vez —VIGIA, YAGUARA, YARIGUI-CANTAGALLO…—
              porque un campo puede colgar de dos activos distintos (las 151
              colisiones que ya reporta el panel Fundación).

              Con `key={e}` eso daba una consola llena de "Encountered two
              children with the same key", y React avisa de que puede duplicar u
              omitir hijos. Como sugerencia de un datalist, dos entradas
              idénticas no aportan nada: el usuario escribe un nombre, no elige
              un activo. */}
          {[...new Set(entidades)].slice(0, 500).map((e) => (
            <option key={e} value={e} />
          ))}
        </datalist>
      </label>

      <label className={styles.campo}>
        <span className={styles.etiqueta}>Periodo</span>
        <input
          className={styles.control}
          value={ambito.periodo ?? ''}
          placeholder="Último mes con dato"
          onChange={(e) => onCambio({ ...ambito, periodo: e.target.value })}
        />
      </label>
    </div>
  );
}
