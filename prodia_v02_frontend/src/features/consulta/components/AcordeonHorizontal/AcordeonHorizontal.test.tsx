import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { AcordeonHorizontal } from './AcordeonHorizontal';

/** El grow vive en el estilo inline del panel (custom property), no en una
 *  clase — jsdom no resuelve @property, así que se lee del inline. */
function growDelPanel(boton: HTMLElement): string {
  const panel = boton.closest('div') as HTMLElement;
  return panel.style.getPropertyValue('--pv-panel-grow');
}

describe('AcordeonHorizontal', () => {
  it('arranca con Historial y Chat abiertos, Insights colapsado', () => {
    render(<AcordeonHorizontal />);

    expect(
      screen.getByRole('button', { name: 'Colapsar Historial' }).getAttribute('aria-expanded'),
    ).toBe('true');
    expect(
      screen.getByRole('button', { name: 'Colapsar Chat' }).getAttribute('aria-expanded'),
    ).toBe('true');
    expect(
      screen.getByRole('button', { name: 'Abrir Insights' }).getAttribute('aria-expanded'),
    ).toBe('false');
  });

  it('reparto Historial + Chat: 25 % / 75 % (grow 1 / 3)', () => {
    render(<AcordeonHorizontal />);

    expect(growDelPanel(screen.getByRole('button', { name: 'Colapsar Historial' }))).toBe('1');
    expect(growDelPanel(screen.getByRole('button', { name: 'Colapsar Chat' }))).toBe('3');
  });

  it('reparto Chat + Insights: 50 % / 50 % (grow 3 / 3)', async () => {
    const user = userEvent.setup();
    render(<AcordeonHorizontal />);

    // Cerrar Historial ya deja Chat + Insights abiertos (ver bloque de tests
    // dedicado más abajo) — un único clic basta.
    await user.click(screen.getByRole('button', { name: 'Colapsar Historial' }));

    expect(growDelPanel(screen.getByRole('button', { name: 'Colapsar Chat' }))).toBe('3');
    expect(growDelPanel(screen.getByRole('button', { name: 'Colapsar Insights' }))).toBe('3');
  });

  it('reparto Historial + Insights: 25 % / 75 % (grow 1 / 3)', async () => {
    const user = userEvent.setup();
    render(<AcordeonHorizontal />);

    // Se colapsa Chat primero: sin este paso, "Abrir Insights" produciría
    // Chat + Insights (Historial es el más antiguo del par inicial y sale
    // primero), no el par que este test necesita.
    await user.click(screen.getByRole('button', { name: 'Colapsar Chat' }));
    await user.click(screen.getByRole('button', { name: 'Abrir Insights' }));

    expect(growDelPanel(screen.getByRole('button', { name: 'Colapsar Historial' }))).toBe('1');
    expect(growDelPanel(screen.getByRole('button', { name: 'Colapsar Insights' }))).toBe('3');
  });

  it('al expandir un tercero, colapsa el más antiguo (máximo 2 abiertos)', async () => {
    const user = userEvent.setup();
    render(<AcordeonHorizontal />);

    await user.click(screen.getByRole('button', { name: 'Abrir Insights' }));

    // Insights entra; Historial, el más antiguo del par inicial, sale.
    expect(screen.getByRole('button', { name: 'Colapsar Insights' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Abrir Historial' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Colapsar Chat' })).toBeTruthy();
  });

  it('nunca deja cero paneles abiertos: el último queda deshabilitado', async () => {
    const user = userEvent.setup();
    render(<AcordeonHorizontal />);

    // Se cierra Chat, no Historial: cerrar Historial tiene su propia regla
    // (ver bloque siguiente) y ya no deja un único panel abierto.
    await user.click(screen.getByRole('button', { name: 'Colapsar Chat' }));

    const ultimo = screen.getByRole('button', { name: 'Colapsar Historial' }) as HTMLButtonElement;
    expect(ultimo.disabled).toBe(true);
    expect(ultimo.getAttribute('title')).toBe('Debe quedar al menos un panel abierto');

    // Y el clic sobre él no cambia nada.
    await user.click(ultimo);
    expect(screen.getByRole('button', { name: 'Colapsar Historial' })).toBeTruthy();
  });

  describe('cerrar Historial revela siempre el par de trabajo (Chat + Insights)', () => {
    it('desde Historial + Chat', async () => {
      const user = userEvent.setup();
      render(<AcordeonHorizontal />);

      await user.click(screen.getByRole('button', { name: 'Colapsar Historial' }));

      expect(screen.getByRole('button', { name: 'Abrir Historial' })).toBeTruthy();
      expect(
        screen.getByRole('button', { name: 'Colapsar Chat' }).getAttribute('aria-expanded'),
      ).toBe('true');
      expect(
        screen.getByRole('button', { name: 'Colapsar Insights' }).getAttribute('aria-expanded'),
      ).toBe('true');
    });

    it('desde Historial + Insights (Chat no estaba abierto)', async () => {
      const user = userEvent.setup();
      render(<AcordeonHorizontal />);

      // Llegar a Historial + Insights: cerrar Chat, luego abrir Insights.
      await user.click(screen.getByRole('button', { name: 'Colapsar Chat' }));
      await user.click(screen.getByRole('button', { name: 'Abrir Insights' }));

      await user.click(screen.getByRole('button', { name: 'Colapsar Historial' }));

      expect(screen.getByRole('button', { name: 'Abrir Historial' })).toBeTruthy();
      expect(
        screen.getByRole('button', { name: 'Colapsar Chat' }).getAttribute('aria-expanded'),
      ).toBe('true');
      expect(
        screen.getByRole('button', { name: 'Colapsar Insights' }).getAttribute('aria-expanded'),
      ).toBe('true');
    });
  });

  describe('abrir Historial siempre lo empareja con Chat', () => {
    it('desde Chat + Insights, Insights se colapsa', async () => {
      const user = userEvent.setup();
      render(<AcordeonHorizontal />);

      // Llegar a Chat + Insights (escenario exacto de la captura): cerrar
      // Historial, que por la regla anterior deja el par de trabajo abierto.
      await user.click(screen.getByRole('button', { name: 'Colapsar Historial' }));

      await user.click(screen.getByRole('button', { name: 'Abrir Historial' }));

      expect(
        screen.getByRole('button', { name: 'Colapsar Historial' }).getAttribute('aria-expanded'),
      ).toBe('true');
      expect(
        screen.getByRole('button', { name: 'Colapsar Chat' }).getAttribute('aria-expanded'),
      ).toBe('true');
      expect(screen.getByRole('button', { name: 'Abrir Insights' })).toBeTruthy();
    });

    it('desde Insights solo, Chat entra y acompaña a Historial', async () => {
      const user = userEvent.setup();
      render(<AcordeonHorizontal />);

      // Llegar a Insights solo: cerrar Historial (→ Chat+Insights), luego
      // cerrar Chat (→ Insights solo, el último no se puede cerrar más).
      await user.click(screen.getByRole('button', { name: 'Colapsar Historial' }));
      await user.click(screen.getByRole('button', { name: 'Colapsar Chat' }));

      await user.click(screen.getByRole('button', { name: 'Abrir Historial' }));

      expect(
        screen.getByRole('button', { name: 'Colapsar Historial' }).getAttribute('aria-expanded'),
      ).toBe('true');
      expect(
        screen.getByRole('button', { name: 'Colapsar Chat' }).getAttribute('aria-expanded'),
      ).toBe('true');
      expect(screen.getByRole('button', { name: 'Abrir Insights' })).toBeTruthy();
    });
  });

  describe('con Chat + Insights abiertos, cerrar uno deja el otro (comportamiento normal)', () => {
    async function abrirChatEInsights(user: ReturnType<typeof userEvent.setup>) {
      await user.click(screen.getByRole('button', { name: 'Colapsar Historial' }));
    }

    it('cerrar Chat deja Insights solo', async () => {
      const user = userEvent.setup();
      render(<AcordeonHorizontal />);
      await abrirChatEInsights(user);

      await user.click(screen.getByRole('button', { name: 'Colapsar Chat' }));

      expect(screen.getByRole('button', { name: 'Abrir Chat' })).toBeTruthy();
      const insights = screen.getByRole('button', {
        name: 'Colapsar Insights',
      }) as HTMLButtonElement;
      expect(insights.getAttribute('aria-expanded')).toBe('true');
      expect(insights.disabled).toBe(true);
    });

    it('cerrar Insights deja Chat solo', async () => {
      const user = userEvent.setup();
      render(<AcordeonHorizontal />);
      await abrirChatEInsights(user);

      await user.click(screen.getByRole('button', { name: 'Colapsar Insights' }));

      expect(screen.getByRole('button', { name: 'Abrir Insights' })).toBeTruthy();
      const chat = screen.getByRole('button', { name: 'Colapsar Chat' }) as HTMLButtonElement;
      expect(chat.getAttribute('aria-expanded')).toBe('true');
      expect(chat.disabled).toBe(true);
    });
  });
});
