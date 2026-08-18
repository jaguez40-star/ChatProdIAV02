import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '../../../app/store/authStore';
import { SessionExpiryBanner } from './SessionExpiryBanner';

describe('SessionExpiryBanner', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-18T12:00:00Z'));
    useAuthStore.setState({ sessionExpiresAt: null });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('sin sessionExpiresAt no renderiza nada', () => {
    const { container } = render(<SessionExpiryBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('expira en 30 min: no se muestra (fuera del umbral de 5 min)', () => {
    useAuthStore.setState({
      sessionExpiresAt: new Date('2026-08-18T12:30:00Z').toISOString(),
    });
    const { container } = render(<SessionExpiryBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('expira en 3 min: se muestra el aviso', () => {
    useAuthStore.setState({
      sessionExpiresAt: new Date(Date.now() + 3 * 60_000).toISOString(),
    });
    render(<SessionExpiryBanner />);
    expect(screen.getByRole('alert').textContent).toContain('3 min');
  });
});
