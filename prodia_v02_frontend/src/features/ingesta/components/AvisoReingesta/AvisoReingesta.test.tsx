/**
 * Tests del aviso previo a procesar.
 *
 * Los tres casos —reporte nuevo, misma fecha con otro archivo, y mismo archivo— tienen
 * consecuencias distintas para el usuario, así que deben distinguirse en pantalla.
 * Reemplazar datos sin saberlo es lo que este componente existe para evitar.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ArchivoAceptado, ReporteExistente } from '../../types/ingestaTypes';
import { AvisoReingesta } from './AvisoReingesta';

const ARCHIVO: ArchivoAceptado = {
  id: 'abc',
  archivo: '20260815_Reporte.xlsm',
  hash: 'deadbeef',
  fechaReporte: '2026-08-15',
};

const YA_EXISTE: ReporteExistente = {
  existe: true,
  reporteId: 7,
  archivo: 'anterior.xlsm',
  tipoArchivo: 'NEW',
  ingeridoEn: '2026-08-15T10:00:00',
  mismoContenido: false,
};

function renderizar(existente: ReporteExistente | null, onConfirmar = vi.fn()) {
  render(
    <AvisoReingesta
      archivo={ARCHIVO}
      existente={existente}
      onConfirmar={onConfirmar}
      onCancelar={vi.fn()}
    />,
  );
  return onConfirmar;
}

describe('reporte nuevo', () => {
  it('confirma que no hay nada que reemplazar', () => {
    renderizar({ ...YA_EXISTE, existe: false });

    expect(screen.getByText(/reporte nuevo/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Procesar' })).toBeTruthy();
  });

  it('funciona aunque no se haya podido comprobar', () => {
    renderizar(null);

    expect(screen.getByText(/reporte nuevo/i)).toBeTruthy();
  });
});

describe('la fecha ya fue ingerida', () => {
  it('advierte de que los datos se reemplazarán', () => {
    renderizar(YA_EXISTE);

    expect(screen.getByRole('alert').textContent).toMatch(/se reemplazarán/i);
    expect(screen.getByText('anterior.xlsm')).toBeTruthy();
  });

  it('cambia la acción para que el usuario sepa lo que hace', () => {
    renderizar(YA_EXISTE);

    expect(
      screen.getByRole('button', { name: /reemplazar y procesar/i }),
    ).toBeTruthy();
  });
});

describe('es exactamente el mismo archivo', () => {
  it('lo informa sin alarmar', () => {
    // Reingerir lo mismo deja los datos igual: no es una advertencia, es información.
    renderizar({ ...YA_EXISTE, mismoContenido: true });

    expect(screen.getByRole('status').textContent).toMatch(/ya se ingirió/i);
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('acciones', () => {
  it('confirma al pulsar procesar', async () => {
    const usuario = userEvent.setup();
    const onConfirmar = renderizar(null);

    await usuario.click(screen.getByRole('button', { name: 'Procesar' }));

    expect(onConfirmar).toHaveBeenCalledOnce();
  });

  it('muestra el archivo y su fecha', () => {
    renderizar(null);

    expect(screen.getByText('20260815_Reporte.xlsm')).toBeTruthy();
    expect(screen.getByText('2026-08-15')).toBeTruthy();
  });
});
