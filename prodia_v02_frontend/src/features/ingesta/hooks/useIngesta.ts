/**
 * Orquesta el flujo completo de una ingesta: subir → avisar de reingesta → procesar.
 *
 * El progreso llega por `EventSource`. Dos cuidados que no son opcionales:
 *
 * 1. **La conexión se cierra siempre**, tanto al terminar como al desmontar el
 *    componente. Un `EventSource` huérfano reintenta conectarse solo, de forma
 *    indefinida, y volvería a lanzar el ETL en el servidor.
 * 2. **El estado final solo se fija con el evento `fin`.** Que lleguen hojas en verde no
 *    significa que los datos estén guardados: hasta el commit, la transacción puede
 *    revertirse entera (G2).
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError } from '../../../shared/services/apiClient';
import {
  aCodigoError,
  aEstadoFinal,
  aHojaEnProgreso,
  aResultadoIngesta,
  type EventoFinApi,
  type EventoHojaApi,
  type EventoInicioApi,
} from '../mappers/ingestaMappers';
import {
  calcularHash,
  consultarReporteExistente,
  fechaDelNombre,
  rutaDeProgreso,
  subirArchivo,
} from '../services/ingestaService';
import type {
  ArchivoAceptado,
  CodigoError,
  FaseIngesta,
  HojaEnProgreso,
  ReporteExistente,
  ResultadoIngesta,
} from '../types/ingestaTypes';

interface EstadoIngesta {
  fase: FaseIngesta;
  archivo: File | null;
  subida: ArchivoAceptado | null;
  existente: ReporteExistente | null;
  hojas: HojaEnProgreso[];
  totalHojas: number;
  resultado: ResultadoIngesta | null;
  error: string | null;
  codigoError: CodigoError | null;
  hojaDelError: string | null;
}

const ESTADO_INICIAL: EstadoIngesta = {
  fase: 'inactiva',
  archivo: null,
  subida: null,
  existente: null,
  hojas: [],
  totalHojas: 0,
  resultado: null,
  error: null,
  codigoError: null,
  hojaDelError: null,
};

export function useIngesta() {
  const [estado, setEstado] = useState<EstadoIngesta>(ESTADO_INICIAL);
  const fuenteRef = useRef<EventSource | null>(null);

  const cerrarConexion = useCallback(() => {
    fuenteRef.current?.close();
    fuenteRef.current = null;
  }, []);

  // Al desmontar: cerrar la conexión. Sin esto, el EventSource seguiría reintentando
  // y relanzaría el ETL en el servidor.
  useEffect(() => cerrarConexion, [cerrarConexion]);

  const reiniciar = useCallback(() => {
    cerrarConexion();
    setEstado(ESTADO_INICIAL);
  }, [cerrarConexion]);

  /** Sube el archivo y comprueba si su fecha ya fue ingerida. */
  const seleccionarArchivo = useCallback(async (archivo: File) => {
    setEstado({ ...ESTADO_INICIAL, fase: 'subiendo', archivo });
    try {
      const subida = await subirArchivo(archivo);
      const fecha = fechaDelNombre(archivo.name);
      let existente: ReporteExistente | null = null;
      if (fecha) {
        const hash = await calcularHash(archivo);
        existente = await consultarReporteExistente(fecha, hash);
      }
      setEstado((previo) => ({
        ...previo,
        fase: 'confirmando',
        subida,
        existente,
      }));
    } catch (error) {
      setEstado((previo) => ({
        ...previo,
        fase: 'revertida',
        error: error instanceof Error ? error.message : 'No se pudo subir el archivo',
        codigoError: error instanceof ApiError ? aCodigoError(error.code) : null,
      }));
    }
  }, []);

  /** Lanza el ETL y sigue su progreso. */
  const procesar = useCallback(() => {
    const subida = estado.subida;
    if (!subida) return;

    setEstado((previo) => ({ ...previo, fase: 'procesando', hojas: [] }));
    const fuente = new EventSource(rutaDeProgreso(subida.id), {
      withCredentials: true,
    });
    fuenteRef.current = fuente;

    fuente.addEventListener('inicio', (evento) => {
      const datos = JSON.parse((evento as MessageEvent<string>).data) as EventoInicioApi;
      setEstado((previo) => ({ ...previo, totalHojas: datos.total }));
    });

    fuente.addEventListener('hoja', (evento) => {
      const datos = JSON.parse((evento as MessageEvent<string>).data) as EventoHojaApi;
      const hoja = aHojaEnProgreso(datos);
      setEstado((previo) => {
        // Una hoja pasa por varios estados: se reemplaza en su sitio para que la lista
        // no crezca ni se reordene mientras el usuario la mira.
        const indice = previo.hojas.findIndex((h) => h.hoja === hoja.hoja);
        if (indice === -1) return { ...previo, hojas: [...previo.hojas, hoja] };
        const hojas = [...previo.hojas];
        hojas[indice] = hoja;
        return { ...previo, hojas };
      });
    });

    fuente.addEventListener('fin', (evento) => {
      const datos = JSON.parse((evento as MessageEvent<string>).data) as EventoFinApi;
      cerrarConexion();
      const estadoFinal = aEstadoFinal(datos.estado);
      setEstado((previo) => ({
        ...previo,
        fase: estadoFinal === 'confirmado' ? 'confirmada' : 'revertida',
        resultado: datos.resultado ? aResultadoIngesta(datos.resultado) : null,
        error: datos.detalle ?? null,
        codigoError: aCodigoError(datos.code),
        hojaDelError: datos.hoja ?? null,
      }));
    });

    fuente.onerror = () => {
      // El navegador reintenta solo; si el flujo ya terminó no hay nada que hacer.
      if (fuenteRef.current === null) return;
      cerrarConexion();
      setEstado((previo) =>
        previo.fase === 'procesando'
          ? {
              ...previo,
              fase: 'revertida',
              error:
                'Se perdió la conexión con el servidor durante la ingesta. No hay ' +
                'garantía de que los datos se hayan guardado.',
              codigoError: 'ERROR_INTERNO',
            }
          : previo,
      );
    };
  }, [estado.subida, cerrarConexion]);

  return { estado, seleccionarArchivo, procesar, reiniciar };
}
