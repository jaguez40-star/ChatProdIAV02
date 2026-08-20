/**
 * Tests de la zona de subida.
 *
 * El requisito de la fecha en el nombre se anuncia antes de subir: es el rechazo más
 * frecuente del backend y el usuario no tiene forma de adivinarlo.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ZonaSubida } from './ZonaSubida';

function archivoDePrueba(nombre = '20260815_r.xlsm') {
  return new File(['contenido'], nombre, { type: 'application/vnd.ms-excel' });
}

describe('ZonaSubida', () => {
  it('explica el formato de nombre que exige el backend', () => {
    render(<ZonaSubida onArchivo={vi.fn()} />);

    expect(screen.getByText(/AAAAMMDD/)).toBeTruthy();
    expect(screen.getByText(/20260815_Reporte.xlsm/)).toBeTruthy();
  });

  it('entrega el archivo elegido desde el diálogo', async () => {
    const onArchivo = vi.fn();
    const usuario = userEvent.setup();
    render(<ZonaSubida onArchivo={onArchivo} />);

    await usuario.upload(
      screen.getByLabelText('Archivo de reporte'),
      archivoDePrueba(),
    );

    expect(onArchivo).toHaveBeenCalledOnce();
    expect(onArchivo.mock.calls[0][0].name).toBe('20260815_r.xlsm');
  });

  it('entrega el archivo soltado sobre la zona', () => {
    const onArchivo = vi.fn();
    const { container } = render(<ZonaSubida onArchivo={onArchivo} />);
    const zona = container.firstElementChild as HTMLElement;

    fireEvent.drop(zona, { dataTransfer: { files: [archivoDePrueba()] } });

    expect(onArchivo).toHaveBeenCalledOnce();
  });

  it('no acepta nada mientras está deshabilitada', () => {
    const onArchivo = vi.fn();
    const { container } = render(<ZonaSubida onArchivo={onArchivo} deshabilitada />);
    const zona = container.firstElementChild as HTMLElement;

    fireEvent.drop(zona, { dataTransfer: { files: [archivoDePrueba()] } });

    expect(onArchivo).not.toHaveBeenCalled();
    const entrada = screen.getByLabelText('Archivo de reporte') as HTMLInputElement;
    expect(entrada.disabled).toBe(true);
  });

  it('ignora un soltar sin archivos', () => {
    const onArchivo = vi.fn();
    const { container } = render(<ZonaSubida onArchivo={onArchivo} />);

    fireEvent.drop(container.firstElementChild as HTMLElement, {
      dataTransfer: { files: [] },
    });

    expect(onArchivo).not.toHaveBeenCalled();
  });
});
