import { beforeEach, describe, expect, it } from 'vitest';

import type { Panel } from '../types/consultaTypes';
import { useChatStore } from './chatStore';

const PANEL: Panel = {
  tipo: 'jerarq_operador',
  datos: { entidad: 'ECOPETROL', campos: ['CASTILLA'], total: 1, truncado: false },
};

beforeEach(() => {
  useChatStore.getState().limpiar();
});

describe('chatStore', () => {
  it('bloquea el envío mientras hay una pregunta en vuelo', () => {
    // Sin esto, N preguntas concurrentes pintan sus respuestas en orden de
    // llegada y no de envío — el defecto del sistema viejo.
    const s = useChatStore.getState();
    s.enviar('¿cuánto produjo Castilla?');

    expect(useChatStore.getState().enVuelo).toBe(true);

    useChatStore.getState().responder('Ahí va.', null, 1, '¿cuánto?');
    expect(useChatStore.getState().enVuelo).toBe(false);
  });

  it('guarda datos, no HTML', () => {
    // El original almacena strings ya renderizados, y por eso tiene que hacer
    // regex sobre el historial para marcar una burbuja como votada.
    useChatStore.getState().enviar('pregunta');
    useChatStore.getState().responder('respuesta', null, 7, 'pregunta');

    const [pregunta, respuesta] = useChatStore.getState().mensajes;
    expect(pregunta).toMatchObject({ rol: 'usuario', texto: 'pregunta' });
    expect(respuesta).toMatchObject({ rol: 'asistente', logId: 7, veredicto: null });
  });

  it('marcar un veredicto muta el dato, sin tocar los demás mensajes', () => {
    useChatStore.getState().enviar('a');
    useChatStore.getState().responder('r1', null, 1, 'a');
    useChatStore.getState().enviar('b');
    useChatStore.getState().responder('r2', null, 2, 'b');

    useChatStore.getState().marcarVeredicto(1, 'confirmado');

    const asistentes = useChatStore
      .getState()
      .mensajes.filter((m) => m.rol === 'asistente');
    expect(asistentes[0]).toMatchObject({ logId: 1, veredicto: 'confirmado' });
    expect(asistentes[1]).toMatchObject({ logId: 2, veredicto: null });
  });

  it('solo apila los mensajes que traen panel', () => {
    useChatStore.getState().enviar('sin panel');
    useChatStore.getState().responder('texto', null, 1, 'sin panel');
    expect(useChatStore.getState().pila).toHaveLength(0);

    useChatStore.getState().enviar('con panel');
    useChatStore.getState().responder('texto', PANEL, 2, 'con panel');
    expect(useChatStore.getState().pila).toHaveLength(1);
  });

  it('un error deja de bloquear el input y conserva la referencia', () => {
    useChatStore.getState().enviar('pregunta');
    useChatStore.getState().fallar('No se pudo procesar.', 'abc-123');

    const s = useChatStore.getState();
    expect(s.enVuelo).toBe(false);
    expect(s.mensajes.at(-1)).toMatchObject({
      rol: 'error',
      correlationId: 'abc-123',
    });
  });

  it('el tope de la pila descarta los más antiguos y lo DECLARA', () => {
    // El original descarta en silencio al pasar de 100.
    for (let i = 0; i < 55; i += 1) {
      useChatStore.getState().enviar(`p${i}`);
      useChatStore.getState().responder('r', PANEL, i, `p${i}`);
    }

    const s = useChatStore.getState();
    expect(s.pila).toHaveLength(50);
    expect(s.descartados).toBe(5);
  });

  it('cerrar y colapsar bloques', () => {
    useChatStore.getState().enviar('p');
    useChatStore.getState().responder('r', PANEL, 1, 'p');
    const n = useChatStore.getState().pila[0].n;

    useChatStore.getState().alternarBloque(n);
    expect(useChatStore.getState().pila[0].colapsado).toBe(true);

    useChatStore.getState().cerrarBloque(n);
    expect(useChatStore.getState().pila).toHaveLength(0);
  });

  it('limpiar arranca una conversación nueva', () => {
    const antes = useChatStore.getState().conversacionId;
    useChatStore.getState().enviar('p');
    useChatStore.getState().limpiar();

    const s = useChatStore.getState();
    expect(s.conversacionId).not.toBe(antes);
    expect(s.mensajes).toHaveLength(0);
    expect(s.turno).toBe(0);
  });
});
