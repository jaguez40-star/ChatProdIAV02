import { Check, Flag, X } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';

import { useTecladoRevision } from '../../hooks/useTecladoRevision';
import {
  esPendiente,
  type FilaLibreta,
  type GrupoQ,
  type VeredictoDeRevision,
} from '../../types/testClasTypes';
import styles from './TablaLibreta.module.scss';

/** A partir de aquí, «confirmar todo» pide confirmación explícita (H6). */
export const TOPE_SIN_PREGUNTAR = 20;

const ETIQUETA: Record<GrupoQ, string> = {
  jerarquizar: 'Jerarquizar',
  cuantificar: 'Cuantificar',
  analizar: 'Analizar',
  desconocido: 'Desconocido',
};

const OTROS_GRUPOS: GrupoQ[] = ['jerarquizar', 'cuantificar', 'analizar', 'desconocido'];

interface Props {
  filas: FilaLibreta[];
  onCalificar: (items: VeredictoDeRevision[]) => void;
  deshabilitado: boolean;
}

export function TablaLibreta({ filas, onCalificar, deshabilitado }: Props) {
  const pendientes = useMemo(() => filas.filter((f) => esPendiente(f.veredicto)), [filas]);
  const [cursor, setCursor] = useState(0);
  const [visitadas, setVisitadas] = useState<Set<number>>(new Set());

  const filaActual = pendientes[cursor];

  const calificarActual = useCallback(
    (grupoCorrecto: GrupoQ | null) => {
      if (filaActual === undefined) return;
      setVisitadas((previas) => new Set(previas).add(filaActual.id));
      onCalificar([{ logId: filaActual.id, grupoCorrecto }]);
      // El cursor NO avanza a mano: la fila calificada sale de `pendientes` y
      // el índice actual pasa a apuntar a la siguiente por sí solo. Sumar uno
      // aquí saltaría un caso.
      setCursor((actual) => Math.min(actual, Math.max(0, pendientes.length - 2)));
    },
    [filaActual, onCalificar, pendientes.length],
  );

  const mover = useCallback(
    (delta: number) =>
      setCursor((actual) =>
        Math.max(0, Math.min(pendientes.length - 1, actual + delta)),
      ),
    [pendientes.length],
  );

  useTecladoRevision({
    calificar: calificarActual,
    mover,
    activo: !deshabilitado && pendientes.length > 0,
  });

  function confirmarTodas() {
    // H6 — El sistema viejo mandaba las 100 filas cargadas de un clic, sin
    // decir cuántas eran. `confirmado_revision` es la verdad final que alimenta
    // el golden: estampar eso sobre casos que nadie miró contamina el dato de
    // entrenamiento. Aquí se declara el número y, por encima del tope, se pide
    // confirmación explícita.
    if (pendientes.length > TOPE_SIN_PREGUNTAR) {
      const sigue = window.confirm(
        `Vas a marcar ${pendientes.length} clasificaciones como correctas sin ` +
          'revisarlas una a una. Esto alimenta el golden. ¿Seguro?',
      );
      if (!sigue) return;
    }
    onCalificar(pendientes.map((f) => ({ logId: f.id, grupoCorrecto: null })));
  }

  function confirmarVisitadas() {
    const items = pendientes
      .filter((f) => visitadas.has(f.id))
      .map((f) => ({ logId: f.id, grupoCorrecto: null }));
    if (items.length > 0) onCalificar(items);
  }

  const cuantasVisitadas = pendientes.filter((f) => visitadas.has(f.id)).length;

  return (
    <div className={styles.contenedor}>
      <div className={styles.acciones}>
        {pendientes.length > 0 ? (
          <>
            <button
              type="button"
              className={styles.botonPrincipal}
              onClick={confirmarTodas}
              disabled={deshabilitado}
            >
              <Check size={15} /> Confirmar {pendientes.length} pendiente
              {pendientes.length === 1 ? '' : 's'}
            </button>
            {cuantasVisitadas > 0 && (
              <button
                type="button"
                className={styles.boton}
                onClick={confirmarVisitadas}
                disabled={deshabilitado}
              >
                Confirmar las {cuantasVisitadas} visitadas
              </button>
            )}
            <span className={styles.ayudaTeclado}>
              <b>1</b> Jerarq · <b>2</b> Cuant · <b>3</b> Anal · <b>4</b> Descon ·{' '}
              <b>Enter</b> Correcta · <b>↑↓</b> mover
            </span>
          </>
        ) : (
          <span className={styles.ayudaTeclado}>No hay pendientes en esta vista.</span>
        )}
      </div>

      <div className={styles.scroll}>
        <table className={styles.tabla}>
          <thead>
            <tr>
              <th>Pregunta</th>
              <th>Decisión del motor</th>
              <th>Veredicto</th>
              <th>Fecha</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((fila) => (
              <Fila
                key={fila.id}
                fila={fila}
                esCursor={filaActual?.id === fila.id}
                deshabilitado={deshabilitado}
                onCalificar={(grupo) => {
                  setVisitadas((previas) => new Set(previas).add(fila.id));
                  onCalificar([{ logId: fila.id, grupoCorrecto: grupo }]);
                }}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface FilaProps {
  fila: FilaLibreta;
  esCursor: boolean;
  deshabilitado: boolean;
  onCalificar: (grupoCorrecto: GrupoQ | null) => void;
}

function Fila({ fila, esCursor, deshabilitado, onCalificar }: FilaProps) {
  const pendiente = esPendiente(fila.veredicto);
  const clases = [
    pendiente ? styles.filaPendiente : '',
    esCursor ? styles.filaCursor : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <tr className={clases} aria-current={esCursor ? 'true' : undefined}>
      <td className={styles.pregunta}>{fila.textoPregunta}</td>
      <td>
        <span className={styles.grupo}>{ETIQUETA[fila.grupoAsignado]}</span>
        <span className={styles.capa}>{fila.capaResolutora}</span>
        {fila.llmDiag !== null && <span className={styles.diag}>{fila.llmDiag}</span>}
      </td>
      <td>{pendiente ? (
        <CeldaCalificacion
          fila={fila}
          deshabilitado={deshabilitado}
          onCalificar={onCalificar}
        />
      ) : (
        <Insignia fila={fila} />
      )}</td>
      <td className={styles.fecha}>{(fila.ts ?? '').replace('T', ' ').slice(0, 16)}</td>
    </tr>
  );
}

function Insignia({ fila }: { fila: FilaLibreta }) {
  const fuente = fila.fuenteVeredicto === 'revision' ? 'revisión' : 'usuario';
  if (fila.veredicto.startsWith('confirmado')) {
    return (
      <span className={styles.ok}>
        <Check size={14} /> {fuente}
      </span>
    );
  }
  return (
    <span className={styles.no}>
      <X size={14} /> → {fila.grupoCorrecto ? ETIQUETA[fila.grupoCorrecto] : '—'} (
      {fuente})
    </span>
  );
}

function CeldaCalificacion({ fila, deshabilitado, onCalificar }: Omit<FilaProps, 'esCursor'>) {
  return (
    <div className={styles.calificar}>
      {/* «sospecha» NO es un veredicto: se pinta como pendiente con bandera de
          prioridad, para que el revisor sepa que sigue sin juzgar. */}
      <span className={fila.veredicto === 'sospecha' ? styles.sospecha : styles.pendiente}>
        {fila.veredicto === 'sospecha' && <Flag size={12} />} pendiente
        {fila.veredicto === 'sospecha' && ' (sospecha)'}
      </span>
      <span className={styles.chips}>
        <button
          type="button"
          className={styles.chipOk}
          onClick={() => onCalificar(null)}
          disabled={deshabilitado}
        >
          Correcta
        </button>
        {OTROS_GRUPOS.filter((g) => g !== fila.grupoAsignado).map((grupo) => (
          <button
            key={grupo}
            type="button"
            className={styles.chip}
            onClick={() => onCalificar(grupo)}
            disabled={deshabilitado}
          >
            {ETIQUETA[grupo]}
          </button>
        ))}
      </span>
    </div>
  );
}
