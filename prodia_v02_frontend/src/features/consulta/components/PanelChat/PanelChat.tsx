import { Send } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { ApiError } from '../../../../shared/services/apiClient';
import { preguntar } from '../../services/consultaService';
import { useChatStore } from '../../store/chatStore';
import { conMarcador } from '../../utils/marcador';
import styles from './PanelChat.module.scss';

/**
 * El chat: historial de burbujas + input.
 *
 * **Dos fases de espera, por latencia** (idea del origen que sí merece
 * conservarse): la Capa 1 resuelve por regex en milisegundos, así que si a los
 * 900 ms la petición sigue viva es que escaló al LLM. La segunda etiqueta lo
 * dice con honestidad. No hay streaming: la latencia misma es la señal.
 *
 * **El input se bloquea mientras hay una pregunta en vuelo.** El original no
 * lo hace, y por eso N preguntas concurrentes pintan sus respuestas en orden
 * de llegada en vez de en orden de envío.
 */
export function PanelChat() {
  const { conversacionId, mensajes, enVuelo, enviar, responder, fallar } = useChatStore();
  const [texto, setTexto] = useState('');
  const [faseLarga, setFaseLarga] = useState(false);
  const finRef = useRef<HTMLDivElement>(null);

  // Autoscroll SOLO si el usuario ya estaba al final: el original lo hace
  // siempre y arrastra la vista mientras alguien lee algo más arriba.
  useEffect(() => {
    const contenedor = finRef.current?.parentElement;
    if (!contenedor) return;
    const alFinal =
      contenedor.scrollHeight - contenedor.scrollTop - contenedor.clientHeight < 120;
    if (alFinal) finRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [mensajes.length]);

  useEffect(() => {
    if (!enVuelo) {
      setFaseLarga(false);
      return;
    }
    const t = window.setTimeout(() => setFaseLarga(true), 900);
    return () => window.clearTimeout(t);
  }, [enVuelo]);

  const preguntarAhora = async () => {
    const pregunta = texto.trim();
    if (!pregunta || enVuelo) return;

    setTexto('');
    enviar(pregunta);

    try {
      const respuesta = await preguntar(pregunta, conversacionId);
      responder(respuesta.mensaje, respuesta.panel, respuesta.logId, pregunta);
    } catch (error) {
      // El correlationId viaja al usuario: es la referencia con la que puede
      // reportar el problema y alguien hacer grep en los logs (C2/N6).
      const api = error instanceof ApiError ? error : null;
      fallar(
        api?.message ?? 'No se pudo procesar la pregunta.',
        api?.correlationId ?? null,
      );
    }
  };

  return (
    <div className={styles.chat}>
      <div className={styles.historial}>
        {mensajes.length === 0 && (
          <p className={styles.saludo}>
            Puedo responder sobre <strong>estructura</strong> (qué campos tiene un
            activo), <strong>cifras</strong> (cuánto produjo un campo) y{' '}
            <strong>análisis</strong> (por qué vamos cortos). ¿Qué necesitas?
          </p>
        )}

        {mensajes.map((m) => {
          if (m.rol === 'usuario') {
            return (
              <div key={m.ts} className={styles.burbujaUsuario}>
                {m.texto}
              </div>
            );
          }
          if (m.rol === 'error') {
            return (
              <div key={m.ts} className={styles.burbujaError}>
                <p>{m.texto}</p>
                {m.correlationId && (
                  <p className={styles.referencia}>Referencia: {m.correlationId}</p>
                )}
              </div>
            );
          }
          return (
            <div key={m.ts} className={styles.burbujaBot}>
              {/* El marcador ⟦…⟧ produce nodos, no HTML (D6). */}
              {conMarcador(m.texto)}
            </div>
          );
        })}

        {enVuelo && (
          <div className={styles.pensando} role="status">
            {faseLarga
              ? 'Consultando con la IA… puede tardar un momento'
              : 'Entendiendo tu pregunta'}
            <span className={styles.puntos}>…</span>
          </div>
        )}

        <div ref={finRef} />
      </div>

      <div className={styles.entrada}>
        <input
          type="text"
          value={texto}
          disabled={enVuelo}
          placeholder="Escribe tu pregunta de producción…"
          aria-label="Pregunta de producción"
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void preguntarAhora();
            }
          }}
        />
        <button
          type="button"
          onClick={() => void preguntarAhora()}
          disabled={enVuelo || !texto.trim()}
          aria-label="Enviar pregunta"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
