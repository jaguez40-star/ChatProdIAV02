import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';

import { Toast } from './Toast';

describe('Toast', () => {
  it('muestra el mensaje', () => {
    render(<Toast message="Sesión cerrada" />);
    expect(screen.getByRole('alert').textContent).toContain('Sesión cerrada');
  });

  it('llama onClose al hacer click en cerrar', async () => {
    const onClose = vi.fn();
    render(<Toast message="Error" variant="error" onClose={onClose} />);
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar notificación' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('sin onClose no muestra botón de cerrar', () => {
    render(<Toast message="Info" />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('con duration=0 no se auto-cierra', () => {
    vi.useFakeTimers();
    const onClose = vi.fn();
    render(<Toast message="Persistente" duration={0} onClose={onClose} />);
    vi.advanceTimersByTime(10_000);
    expect(onClose).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});
