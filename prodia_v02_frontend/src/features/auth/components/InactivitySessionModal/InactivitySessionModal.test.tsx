import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { InactivitySessionModal } from './InactivitySessionModal';

describe('InactivitySessionModal', () => {
  it('isOpen=false no renderiza nada', () => {
    const { container } = render(
      <InactivitySessionModal isOpen={false} onAccept={vi.fn()} minutesInactive={30} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('isOpen=true muestra el diálogo con los minutos', () => {
    render(
      <InactivitySessionModal isOpen onAccept={vi.fn()} minutesInactive={30} />,
    );
    expect(screen.getByRole('alertdialog')).toBeDefined();
    expect(screen.getByText(/30 minutos/)).toBeDefined();
  });

  it('llama onAccept al hacer click en Entendido', async () => {
    const onAccept = vi.fn();
    render(<InactivitySessionModal isOpen onAccept={onAccept} minutesInactive={30} />);
    await userEvent.click(screen.getByRole('button', { name: 'Entendido' }));
    expect(onAccept).toHaveBeenCalledTimes(1);
  });
});
