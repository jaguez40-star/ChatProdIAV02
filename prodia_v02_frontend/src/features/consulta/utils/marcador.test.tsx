import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { conMarcador } from './marcador';

describe('conMarcador (D6)', () => {
  it('pone en negrita lo marcado con ⟦…⟧', () => {
    render(<p>{conMarcador('Castilla va ⟦bien⟧ este mes')}</p>);
    expect(screen.getByText('bien').tagName).toBe('STRONG');
  });

  it('NO interpreta markdown', () => {
    // 🔑 D6: el intro lo escribe un LLM cuyo validador bloquea dígitos pero
    // no asteriscos. Interpretar `**` habría puesto en negrita un
    // "**Claro, Javier**" espontáneo del modelo.
    render(<p>{conMarcador('Esto **no** debe ir en negrita')}</p>);
    expect(screen.queryByText('no')).toBeNull();
    expect(screen.getByText(/\*\*no\*\*/)).toBeDefined();
  });

  it('un marcador sin cerrar no se come el resto del texto', () => {
    const { container } = render(<p>{conMarcador('Texto ⟦sin cerrar y más texto')}</p>);
    expect(container.querySelector('strong')).toBeNull();
    expect(container.textContent).toContain('y más texto');
  });

  it('admite varios marcadores en la misma línea', () => {
    render(<p>{conMarcador('⟦uno⟧ y ⟦dos⟧')}</p>);
    expect(screen.getByText('uno').tagName).toBe('STRONG');
    expect(screen.getByText('dos').tagName).toBe('STRONG');
  });

  it('texto sin marcadores pasa tal cual', () => {
    const { container } = render(<p>{conMarcador('sin marcas')}</p>);
    expect(container.textContent).toBe('sin marcas');
    expect(container.querySelector('strong')).toBeNull();
  });
});
