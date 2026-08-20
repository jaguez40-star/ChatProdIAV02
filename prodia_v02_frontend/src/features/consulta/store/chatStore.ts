/**
 * Estado del chat: mensajes, pila de paneles y turno en vuelo.
 *
 * Corrige cuatro defectos concretos del sistema viejo:
 *
 * 1. **Guarda datos, no HTML.** El original almacena strings ya renderizados,
 *    y por eso para marcar una burbuja como votada hace regex sobre el
 *    historial. Aquí se muta un campo y React repinta.
 * 2. **Bloquea el envío mientras hay una pregunta en vuelo.** El original no
 *    lo hace, así que N preguntas concurrentes pintan sus respuestas en orden
 *    de llegada, no de envío.
 * 3. **El tope de la pila se DECLARA.** El original descarta el bloque más
 *    antiguo en silencio al pasar de 100.
 * 4. **Los bloques se pueden cerrar y colapsar.** El original no ofrece
 *    ninguna de las dos cosas.
 */

import { create } from 'zustand';

import type { BloqueApilado, Mensaje, Panel } from '../types/consultaTypes';

/** Tope de la pila. Al superarlo se descarta el más antiguo, pero se avisa. */
const MAX_BLOQUES = 50;

interface ChatState {
  conversacionId: string;
  mensajes: Mensaje[];
  pila: BloqueApilado[];
  /** Cuántos bloques se descartaron por el tope. Se muestra, no se oculta. */
  descartados: number;
  enVuelo: boolean;
  turno: number;

  enviar: (texto: string) => void;
  responder: (texto: string, panel: Panel | null, logId: number | null, pregunta: string) => void;
  fallar: (texto: string, correlationId: string | null) => void;
  marcarVeredicto: (logId: number, veredicto: 'confirmado' | 'corregido') => void;
  alternarBloque: (n: number) => void;
  cerrarBloque: (n: number) => void;
  limpiar: () => void;
}

function nuevaConversacion(): string {
  return `cn-${Math.random().toString(36).slice(2, 11)}`;
}

function hora(): string {
  return new Date().toLocaleTimeString('es-CO', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export const useChatStore = create<ChatState>((set) => ({
  conversacionId: nuevaConversacion(),
  mensajes: [],
  pila: [],
  descartados: 0,
  enVuelo: false,
  turno: 0,

  enviar: (texto) =>
    set((s) => ({
      mensajes: [...s.mensajes, { rol: 'usuario', texto, ts: Date.now() }],
      // Bloquea el input hasta que llegue la respuesta: sin esto, dos
      // preguntas seguidas se pintan en orden de llegada.
      enVuelo: true,
      turno: s.turno + 1,
    })),

  responder: (texto, panel, logId, pregunta) =>
    set((s) => {
      const mensajes: Mensaje[] = [
        ...s.mensajes,
        { rol: 'asistente', texto, panel, logId, veredicto: null, ts: Date.now() },
      ];

      if (!panel) return { mensajes, enVuelo: false };

      const bloque: BloqueApilado = {
        n: s.turno,
        pregunta,
        panel,
        hora: hora(),
        colapsado: false,
      };
      const pila = [...s.pila, bloque];

      // El tope se declara: `descartados` viaja al componente, que lo dice.
      const excedente = Math.max(0, pila.length - MAX_BLOQUES);
      return {
        mensajes,
        pila: excedente ? pila.slice(excedente) : pila,
        descartados: s.descartados + excedente,
        enVuelo: false,
      };
    }),

  fallar: (texto, correlationId) =>
    set((s) => ({
      mensajes: [...s.mensajes, { rol: 'error', texto, correlationId, ts: Date.now() }],
      enVuelo: false,
    })),

  marcarVeredicto: (logId, veredicto) =>
    set((s) => ({
      // Se muta el dato y React repinta. El original tenía que reescribir el
      // HTML guardado con una regex.
      mensajes: s.mensajes.map((m) =>
        m.rol === 'asistente' && m.logId === logId ? { ...m, veredicto } : m,
      ),
    })),

  alternarBloque: (n) =>
    set((s) => ({
      pila: s.pila.map((b) => (b.n === n ? { ...b, colapsado: !b.colapsado } : b)),
    })),

  cerrarBloque: (n) => set((s) => ({ pila: s.pila.filter((b) => b.n !== n) })),

  limpiar: () =>
    set({
      conversacionId: nuevaConversacion(),
      mensajes: [],
      pila: [],
      descartados: 0,
      enVuelo: false,
      turno: 0,
    }),
}));
