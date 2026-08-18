import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PageLoader } from './PageLoader';

describe('PageLoader', () => {
  it('renderiza un status de carga', () => {
    render(<PageLoader />);
    expect(screen.getByRole('status')).toBeDefined();
  });
});
