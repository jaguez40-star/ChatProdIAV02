/**
 * La tabla de la libreta: teclado (H7), confirmación acotada (H6) y el trato de
 * la sospecha como «pendiente con bandera», no como resuelta.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { TablaLibreta, TOPE_SIN_PREGUNTAR } from './TablaLibreta';
import type { FilaLibreta, Veredicto } from '../../types/testClasTypes';

function fila(id: number, extra: Partial<FilaLibreta> = {}): FilaLibreta {
  return {
    id,
    ts: '2026-08-20T09:00:00',
    usuario: 'javier',
    conversacionId: 'c1',
    textoPregunta: `pregunta ${id}`,
    grupoAsignado: 'cuantificar',
    capaResolutora: 'regex',
    entidadCruda: null,
    llmDiag: null,
    veredicto: 'pendiente' as Veredicto,
    grupoCorrecto: null,
    fuenteVeredicto: null,
    notaRevision: null,
    ...extra,
  };
}

describe('TablaLibreta', () => {
  let onCalificar: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onCalificar = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('pinta una fila por registro', () => {
    render(
      <TablaLibreta
        filas={[fila(1), fila(2)]}
        onCalificar={onCalificar}
        deshabilitado={false}
      />,
    );

    expect(screen.getByText('pregunta 1')).toBeTruthy();
    expect(screen.getByText('pregunta 2')).toBeTruthy();
  });

  // ── Teclado (AP-4) ─────────────────────────────────────────────────────────

  it('Enter confirma la clasificación del motor', async () => {
    const usuario = userEvent.setup();
    render(
      <TablaLibreta filas={[fila(1)]} onCalificar={onCalificar} deshabilitado={false} />,
    );

    await usuario.keyboard('{Enter}');

    expect(onCalificar).toHaveBeenCalledWith([{ logId: 1, grupoCorrecto: null }]);
  });

  it.each([
    ['1', 'jerarquizar'],
    ['2', 'cuantificar'],
    ['3', 'analizar'],
    ['4', 'desconocido'],
  ])('la tecla %s corrige a %s', async (tecla, grupo) => {
    const usuario = userEvent.setup();
    render(
      <TablaLibreta filas={[fila(1)]} onCalificar={onCalificar} deshabilitado={false} />,
    );

    await usuario.keyboard(tecla);

    expect(onCalificar).toHaveBeenCalledWith([{ logId: 1, grupoCorrecto: grupo }]);
  });

  it('las flechas mueven el cursor entre pendientes', async () => {
    const usuario = userEvent.setup();
    render(
      <TablaLibreta
        filas={[fila(1), fila(2)]}
        onCalificar={onCalificar}
        deshabilitado={false}
      />,
    );

    await usuario.keyboard('{ArrowDown}');
    await usuario.keyboard('{Enter}');

    expect(onCalificar).toHaveBeenCalledWith([{ logId: 2, grupoCorrecto: null }]);
  });

  it('no califica mientras se escribe en un campo de texto', async () => {
    const usuario = userEvent.setup();
    render(
      <>
        <input aria-label="buscador" />
        <TablaLibreta
          filas={[fila(1)]}
          onCalificar={onCalificar}
          deshabilitado={false}
        />
      </>,
    );

    await usuario.click(screen.getByLabelText('buscador'));
    await usuario.keyboard('3');

    expect(onCalificar).not.toHaveBeenCalled();
  });

  it('el atajo se retira al desmontar (H7)', async () => {
    const usuario = userEvent.setup();
    const { unmount } = render(
      <TablaLibreta filas={[fila(1)]} onCalificar={onCalificar} deshabilitado={false} />,
    );

    unmount();
    await usuario.keyboard('{Enter}');

    // Sin el cleanup, pulsar Enter en OTRA página seguiría calificando filas.
    expect(onCalificar).not.toHaveBeenCalled();
  });

  // ── Confirmación masiva acotada (H6) ───────────────────────────────────────

  it('con pocos pendientes confirma directo, sin preguntar', async () => {
    const usuario = userEvent.setup();
    const confirmar = vi.spyOn(window, 'confirm');
    render(
      <TablaLibreta
        filas={[fila(1), fila(2)]}
        onCalificar={onCalificar}
        deshabilitado={false}
      />,
    );

    await usuario.click(screen.getByRole('button', { name: /Confirmar 2 pendientes/ }));

    expect(confirmar).not.toHaveBeenCalled();
    expect(onCalificar).toHaveBeenCalledWith([
      { logId: 1, grupoCorrecto: null },
      { logId: 2, grupoCorrecto: null },
    ]);
  });

  it('por encima del tope PIDE confirmación y dice cuántas son (H6)', async () => {
    const usuario = userEvent.setup();
    const confirmar = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const muchas = Array.from({ length: TOPE_SIN_PREGUNTAR + 5 }, (_, i) => fila(i + 1));

    render(
      <TablaLibreta filas={muchas} onCalificar={onCalificar} deshabilitado={false} />,
    );
    await usuario.click(screen.getByRole('button', { name: /Confirmar 25 pendientes/ }));

    expect(confirmar).toHaveBeenCalledWith(expect.stringContaining('25'));
    expect(onCalificar).toHaveBeenCalled();
  });

  it('si el revisor cancela el diálogo, no se confirma nada', async () => {
    const usuario = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const muchas = Array.from({ length: TOPE_SIN_PREGUNTAR + 5 }, (_, i) => fila(i + 1));

    render(
      <TablaLibreta filas={muchas} onCalificar={onCalificar} deshabilitado={false} />,
    );
    await usuario.click(screen.getByRole('button', { name: /Confirmar 25 pendientes/ }));

    expect(onCalificar).not.toHaveBeenCalled();
  });

  // ── La sospecha no es un veredicto ─────────────────────────────────────────

  it('una sospecha se muestra como pendiente, no como resuelta', () => {
    render(
      <TablaLibreta
        filas={[fila(1, { veredicto: 'sospecha' })]}
        onCalificar={onCalificar}
        deshabilitado={false}
      />,
    );

    // La bandera la distingue, pero el estado sigue siendo «sin juzgar».
    expect(screen.getByText(/pendiente \(sospecha\)/)).toBeTruthy();
    // Y por eso ofrece los mismos botones que cualquier pendiente...
    expect(screen.getByRole('button', { name: 'Correcta' })).toBeTruthy();
    // ...y cuenta para la confirmación masiva.
    expect(screen.getByRole('button', { name: /Confirmar 1 pendiente/ })).toBeTruthy();
  });

  it('lo ya juzgado no ofrece botones de calificación', () => {
    render(
      <TablaLibreta
        filas={[fila(1, { veredicto: 'confirmado_revision', fuenteVeredicto: 'revision' })]}
        onCalificar={onCalificar}
        deshabilitado={false}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Correcta' })).toBeNull();
    expect(screen.getByText(/No hay pendientes/)).toBeTruthy();
  });

  it('durante una calificación en vuelo los botones quedan bloqueados', () => {
    render(
      <TablaLibreta filas={[fila(1)]} onCalificar={onCalificar} deshabilitado={true} />,
    );

    expect(screen.getByRole('button', { name: 'Correcta' }).hasAttribute('disabled')).toBe(
      true,
    );
  });
});
