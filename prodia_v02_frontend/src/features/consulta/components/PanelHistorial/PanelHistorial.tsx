import { MessageSquare, Plus } from 'lucide-react';

import { useChatStore } from '../../store/chatStore';
import styles from './PanelHistorial.module.scss';

/**
 * Historial de la conversación en curso.
 *
 * **Alcance de F4**: lista los turnos de ESTA conversación y permite empezar
 * una nueva. La persistencia entre sesiones necesita la migración `0004` (ya
 * creada) más endpoints de listado y carga, que son alcance de F5 junto con el
 * resto de la libreta.
 *
 * Aun así ya corrige el defecto de raíz del original, que guardaba HTML
 * renderizado: aquí son datos, así que persistirlos será serializarlos.
 */
export function PanelHistorial() {
  const { mensajes, limpiar } = useChatStore();

  const preguntas = mensajes.filter((m) => m.rol === 'usuario');

  return (
    <div className={styles.historial}>
      <button type="button" className={styles.nueva} onClick={limpiar}>
        <Plus size={14} />
        Nueva conversación
      </button>

      {preguntas.length === 0 ? (
        <p className={styles.vacio}>Aún no has preguntado nada.</p>
      ) : (
        <ul className={styles.lista}>
          {preguntas.map((m, i) => (
            <li key={m.ts} className={styles.item}>
              <MessageSquare size={12} />
              <span className={styles.turno}>{i + 1}</span>
              <span className={styles.texto} title={m.texto}>
                {m.texto}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
