/**
 * Estado de la libreta: carga, escaneo y calificación optimista.
 *
 * ## H4 — la corrección que da sentido a este hook
 *
 * El sistema viejo pintaba el veredicto **antes** del POST y descartaba el
 * error (`fetch(...).catch(function () {})`). Si la petición fallaba, la fila
 * quedaba "confirmada" en pantalla y `pendiente` en la base: el revisor creía
 * haberla juzgado. Sobre el dato que decide qué entra al golden, esa es la peor
 * mentira posible, porque nadie la ve.
 *
 * Aquí la respuesta sigue siendo instantánea —eso era bueno y se conserva— pero
 * `onError` **deshace** el cambio y avisa. Lo que se corrige no es la velocidad:
 * es que el fallo sea visible.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';

import {
  cargarLibreta,
  enviarVeredictosEnLote,
  escanearSenales,
} from '../services/testClasService';
import type {
  FilaLibreta,
  FiltroLibreta,
  GrupoQ,
  Libreta,
  VeredictoDeRevision,
} from '../types/testClasTypes';

const CLAVE = 'testclas-libreta';

/** Cómo quedaría una fila tras aplicarle un veredicto de revisión. */
function conVeredicto(fila: FilaLibreta, grupoCorrecto: GrupoQ | null): FilaLibreta {
  const confirma = grupoCorrecto === null || grupoCorrecto === fila.grupoAsignado;
  return {
    ...fila,
    veredicto: confirma ? 'confirmado_revision' : 'corregido_revision',
    grupoCorrecto: confirma ? null : grupoCorrecto,
    fuenteVeredicto: 'revision',
  };
}

export function useLibreta(filtro: FiltroLibreta) {
  const qc = useQueryClient();
  const [aviso, setAviso] = useState<string | null>(null);

  const consulta = useQuery({
    queryKey: [CLAVE, filtro],
    queryFn: () => cargarLibreta(filtro),
  });

  const calificar = useMutation({
    mutationFn: (items: VeredictoDeRevision[]) => enviarVeredictosEnLote(items),

    onMutate: async (items) => {
      // Sin esto, una recarga en vuelo podría aterrizar DESPUÉS del cambio
      // optimista y revivir el veredicto anterior.
      await qc.cancelQueries({ queryKey: [CLAVE, filtro] });
      const previo = qc.getQueryData<Libreta>([CLAVE, filtro]);

      const porId = new Map(items.map((i) => [i.logId, i.grupoCorrecto]));
      qc.setQueryData<Libreta>([CLAVE, filtro], (actual) =>
        actual === undefined
          ? actual
          : {
              ...actual,
              filas: actual.filas.map((f) =>
                porId.has(f.id) ? conVeredicto(f, porId.get(f.id) ?? null) : f,
              ),
            },
      );
      return { previo };
    },

    onError: (_error, items, contexto) => {
      // El rollback es lo que impide que la UI mienta.
      if (contexto?.previo !== undefined) {
        qc.setQueryData<Libreta>([CLAVE, filtro], contexto.previo);
      }
      setAviso(
        items.length === 1
          ? 'No se pudo guardar el veredicto. La fila sigue pendiente.'
          : `No se pudieron guardar los ${items.length} veredictos. Siguen pendientes.`,
      );
    },

    onSuccess: (resultado) => {
      // Un lote puede aplicarse a medias —un id que ya no existe, una
      // corrección sin grupo—. Callarlo dejaría al revisor creyendo que juzgó
      // más de lo que juzgó.
      setAviso(
        resultado.aplicados < resultado.total
          ? `Se guardaron ${resultado.aplicados} de ${resultado.total}. ` +
            'Los demás siguen pendientes.'
          : null,
      );
    },

    onSettled: () => {
      void qc.invalidateQueries({ queryKey: [CLAVE] });
    },
  });

  const escanear = useMutation({
    mutationFn: escanearSenales,
    onSuccess: (resultado) => {
      setAviso(
        resultado.sospechasNuevas > 0
          ? `${resultado.sospechasNuevas} caso(s) marcados como sospechosos ` +
            `sobre ${resultado.filasRevisadas} pendiente(s).`
          : null,
      );
      void qc.invalidateQueries({ queryKey: [CLAVE] });
    },
    onError: () => setAviso('No se pudo escanear en busca de señales.'),
  });

  const descartarAviso = useCallback(() => setAviso(null), []);

  /** Vuelve a leer la libreta sin ejecutar el Control 2 (H5). */
  const recargar = useCallback(() => {
    void qc.invalidateQueries({ queryKey: [CLAVE] });
  }, [qc]);

  return {
    /** Se expone el objeto entero para poder pasárselo a `QueryState` (C5). */
    consulta,
    libreta: consulta.data,
    aviso,
    descartarAviso,
    recargar,
    calificar: calificar.mutate,
    calificando: calificar.isPending,
    escanear: escanear.mutate,
    escaneando: escanear.isPending,
  };
}
