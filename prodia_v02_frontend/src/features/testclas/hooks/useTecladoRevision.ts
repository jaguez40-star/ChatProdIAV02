/**
 * Atajos de teclado para calificar sin soltar las manos del teclado.
 *
 * ## H7 — por qué este hook existe en vez de un `addEventListener` suelto
 *
 * El sistema viejo registraba el manejador en `document` y **nunca lo quitaba**;
 * se protegía comprobando la pestaña activa dentro del propio manejador. En una
 * SPA eso significa que el atajo sigue vivo en todas las demás páginas: pulsar
 * «3» en Análisis calificaría una fila de la libreta.
 *
 * Aquí el `useEffect` devuelve su `removeEventListener`, así que el atajo existe
 * exactamente mientras la pantalla está montada.
 *
 * Las teclas son las mismas que las del CLI y las del sistema viejo, porque el
 * revisor ya las tiene en los dedos.
 */

import { useEffect } from 'react';

import type { GrupoQ } from '../types/testClasTypes';

const POR_TECLA: Record<string, GrupoQ> = {
  '1': 'jerarquizar',
  '2': 'cuantificar',
  '3': 'analizar',
  '4': 'desconocido',
};

interface Acciones {
  /** `null` = confirmar la clasificación del motor. */
  calificar: (grupoCorrecto: GrupoQ | null) => void;
  mover: (delta: number) => void;
  activo: boolean;
}

/** ¿El foco está en un control donde el usuario está escribiendo? */
function escribiendo(destino: EventTarget | null): boolean {
  if (!(destino instanceof HTMLElement)) return false;
  return (
    destino.tagName === 'INPUT' ||
    destino.tagName === 'TEXTAREA' ||
    destino.isContentEditable
  );
}

export function useTecladoRevision({ calificar, mover, activo }: Acciones): void {
  useEffect(() => {
    if (!activo) return;

    function alPulsar(evento: KeyboardEvent) {
      // Sin esta guarda, escribir «3» en el buscador calificaría una fila.
      if (escribiendo(evento.target)) return;
      // Un atajo con modificador pertenece al navegador o al sistema.
      if (evento.ctrlKey || evento.altKey || evento.metaKey) return;

      const grupo = POR_TECLA[evento.key];
      if (grupo !== undefined) {
        evento.preventDefault();
        calificar(grupo);
        return;
      }
      if (evento.key === 'Enter') {
        evento.preventDefault();
        calificar(null);
        return;
      }
      if (evento.key === 'ArrowDown') {
        evento.preventDefault();
        mover(1);
        return;
      }
      if (evento.key === 'ArrowUp') {
        evento.preventDefault();
        mover(-1);
      }
    }

    document.addEventListener('keydown', alPulsar);
    // 🔑 El cleanup ES la corrección (H7).
    return () => document.removeEventListener('keydown', alPulsar);
  }, [calificar, mover, activo]);
}

export const TECLAS_DE_GRUPO = POR_TECLA;
