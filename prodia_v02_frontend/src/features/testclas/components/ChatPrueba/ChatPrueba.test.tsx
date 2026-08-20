/**
 * El chat del laboratorio. Lo que se fija aquí: la traza de capa SÍ se muestra
 * (es lo que se viene a ver), el lote va en serie y deduplica, y un fallo del
 * modelo no se traga las demás preguntas.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ChatPrueba } from './ChatPrueba';
import apiClient from '../../../../shared/services/apiClient';

vi.mock('../../../../shared/services/apiClient', () => ({
  default: { POST: vi.fn() },
  toApiError: (_e: unknown, mensaje: string) => new Error(mensaje),
}));

function respuestaOk(grupo = 'cuantificar', capa = 'regex') {
  return {
    data: {
      grupo,
      capa_resolutora: capa,
      entidad_cruda: null,
      log_id: 1,
      texto_original: 'x',
      grupo_label: grupo,
      timestamp: '2026-08-20T09:00:00',
      mensaje: 'ok',
    },
    error: undefined,
  };
}

describe('ChatPrueba', () => {
  let onClasificado: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onClasificado = vi.fn();
    vi.mocked(apiClient.POST).mockReset();
  });

  it('arranca explicando para qué sirve', () => {
    render(<ChatPrueba onClasificado={onClasificado} />);

    expect(screen.getByText(/Escribe una pregunta y te digo cómo la clasifico/)).toBeTruthy();
  });

  it('clasifica una pregunta y MUESTRA la traza de capa', async () => {
    const usuario = userEvent.setup();
    vi.mocked(apiClient.POST).mockResolvedValue(respuestaOk('analizar', 'llm') as never);
    render(<ChatPrueba onClasificado={onClasificado} />);

    await usuario.type(
      screen.getByLabelText('Pregunta para clasificar'),
      'por qué cayó Castilla{Enter}',
    );

    await waitFor(() => expect(screen.getByText('Analizar')).toBeTruthy());
    // La traza es diagnóstico: aquí SÍ se enseña, en el chat de Consulta no.
    expect(screen.getByText('vía llm')).toBeTruthy();
    expect(onClasificado).toHaveBeenCalled();
  });

  it('el input se bloquea mientras hay una pregunta en vuelo', async () => {
    const usuario = userEvent.setup();
    vi.mocked(apiClient.POST).mockReturnValue(new Promise(() => {}) as never);
    render(<ChatPrueba onClasificado={onClasificado} />);

    const campo = screen.getByLabelText('Pregunta para clasificar');
    await usuario.type(campo, 'algo{Enter}');

    await waitFor(() => expect(campo.hasAttribute('disabled')).toBe(true));
  });

  it('un fallo se declara en vez de perderse', async () => {
    const usuario = userEvent.setup();
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: undefined,
      error: { detail: 'boom' },
    } as never);
    render(<ChatPrueba onClasificado={onClasificado} />);

    await usuario.type(screen.getByLabelText('Pregunta para clasificar'), 'algo{Enter}');

    await waitFor(() =>
      expect(screen.getByText('No se pudo clasificar la pregunta.')).toBeTruthy(),
    );
  });

  it('el lote deduplica preguntas conservando el orden', async () => {
    const usuario = userEvent.setup();
    render(<ChatPrueba onClasificado={onClasificado} />);

    await usuario.click(screen.getByText(/Cargar un lote/));
    await usuario.type(
      screen.getByLabelText('Lote de preguntas'),
      'una{enter}otra{enter}UNA',
    );

    // «una» y «UNA» son la misma pregunta.
    expect(screen.getByText('2 preguntas')).toBeTruthy();
  });

  it('el lote se clasifica UNA POR UNA y una que falla no tumba el resto', async () => {
    const usuario = userEvent.setup();
    vi.mocked(apiClient.POST)
      .mockResolvedValueOnce(respuestaOk() as never)
      .mockResolvedValueOnce({ data: undefined, error: { detail: 'x' } } as never)
      .mockResolvedValueOnce(respuestaOk('analizar', 'llm') as never);

    render(<ChatPrueba onClasificado={onClasificado} />);
    await usuario.click(screen.getByText(/Cargar un lote/));
    await usuario.type(
      screen.getByLabelText('Lote de preguntas'),
      'p1{enter}p2{enter}p3',
    );
    await usuario.click(screen.getByRole('button', { name: 'Clasificar lote' }));

    // Las tres se intentaron —en serie— y solo se perdió la del medio.
    await waitFor(() => expect(apiClient.POST).toHaveBeenCalledTimes(3));
    await waitFor(() =>
      expect(screen.getByText(/1 pregunta\(s\) no se pudieron clasificar/)).toBeTruthy(),
    );
    expect(screen.getByText('p1')).toBeTruthy();
    expect(screen.getByText('p3')).toBeTruthy();
  });
});
