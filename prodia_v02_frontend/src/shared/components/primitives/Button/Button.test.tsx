import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';

import { Button } from './Button';

describe('Button', () => {
  it('renders children', () => {
    render(<Button>Guardar</Button>);
    expect(screen.getByRole('button', { name: 'Guardar' })).toBeDefined();
  });

  it('disabled cuando loading=true', () => {
    render(<Button loading>Cargando</Button>);
    expect(screen.getByRole('button')).toHaveProperty('disabled', true);
  });

  it('llama onClick al hacer click', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Click</Button>);
    await userEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('no llama onClick cuando disabled', async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Click
      </Button>,
    );
    await userEvent.click(screen.getByRole('button'));
    expect(onClick).not.toHaveBeenCalled();
  });

  it('aria-busy refleja el estado loading', () => {
    render(<Button loading>Cargando</Button>);
    expect(screen.getByRole('button').getAttribute('aria-busy')).toBe('true');
  });
});
