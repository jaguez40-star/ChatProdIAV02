import { ListOrdered, Send } from 'lucide-react';
import { useState } from 'react';

import apiClient, { toApiError } from '../../../../shared/services/apiClient';
import styles from './ChatPrueba.module.scss';

interface Clasificacion {
  texto: string;
  grupo: string;
  capa: string;
  entidad: string | null;
}

interface Props {
  /** Se llama tras cada clasificación para que la libreta se recargue. */
  onClasificado: () => void;
}

const ETIQUETA: Record<string, string> = {
  jerarquizar: 'Jerarquizar',
  cuantificar: 'Cuantificar',
  analizar: 'Analizar',
  desconocido: 'Desconocido',
};

/** Quita duplicados conservando el orden en que se escribieron. */
function lineasUnicas(texto: string): string[] {
  const vistas = new Set<string>();
  const salida: string[] = [];
  for (const linea of texto.split('\n')) {
    const limpia = linea.trim();
    const clave = limpia.toLowerCase();
    if (limpia !== '' && !vistas.has(clave)) {
      vistas.add(clave);
      salida.push(limpia);
    }
  }
  return salida;
}

/**
 * El chat del laboratorio: clasifica preguntas sueltas o por lote.
 *
 * **La traza de capa se muestra aquí y solo aquí.** Saber si resolvió la regex o
 * el LLM es información de diagnóstico: al usuario del chat de Consulta no le
 * dice nada sobre su respuesta y solo ensucia la pantalla. En el laboratorio es
 * justo lo que se viene a ver.
 *
 * **El lote se clasifica UNA POR UNA, en serie.** Es la decisión del sistema
 * viejo y se conserva por su razón original: si una pregunta tropieza con el
 * modelo frío, solo falla esa. Un lote atómico las perdería todas.
 */
export function ChatPrueba({ onClasificado }: Props) {
  const [texto, setTexto] = useState('');
  const [lote, setLote] = useState('');
  const [historial, setHistorial] = useState<Clasificacion[]>([]);
  const [enVuelo, setEnVuelo] = useState(false);
  const [progreso, setProgreso] = useState<{ hechas: number; total: number } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  const conversacionId = `tc-${Math.floor(Math.random() * 1e9)}`;

  async function clasificar(pregunta: string): Promise<Clasificacion | null> {
    const { data, error: fallo } = await apiClient.POST('/api/v1/consulta/preguntar', {
      body: { texto: pregunta, conversacion_id: conversacionId },
    });
    if (fallo || data === undefined) {
      throw toApiError(fallo, 'No se pudo clasificar');
    }
    return {
      texto: pregunta,
      grupo: data.grupo,
      capa: data.capa_resolutora,
      entidad: data.entidad_cruda ?? null,
    };
  }

  async function enviarUna() {
    const pregunta = texto.trim();
    if (pregunta === '' || enVuelo) return;
    setEnVuelo(true);
    setError(null);
    try {
      const resultado = await clasificar(pregunta);
      if (resultado !== null) setHistorial((previo) => [...previo, resultado]);
      setTexto('');
      onClasificado();
    } catch {
      setError('No se pudo clasificar la pregunta.');
    } finally {
      setEnVuelo(false);
    }
  }

  async function enviarLote() {
    const preguntas = lineasUnicas(lote);
    if (preguntas.length === 0 || enVuelo) return;
    setEnVuelo(true);
    setError(null);
    setLote('');
    let fallidas = 0;

    for (const [indice, pregunta] of preguntas.entries()) {
      setProgreso({ hechas: indice, total: preguntas.length });
      try {
        const resultado = await clasificar(pregunta);
        if (resultado !== null) setHistorial((previo) => [...previo, resultado]);
      } catch {
        fallidas += 1;
      }
    }

    setProgreso(null);
    setEnVuelo(false);
    if (fallidas > 0) setError(`${fallidas} pregunta(s) no se pudieron clasificar.`);
    onClasificado();
  }

  const cuantasEnLote = lineasUnicas(lote).length;

  return (
    <div className={styles.panel}>
      <ul className={styles.historial}>
        {historial.length === 0 && (
          <li className={styles.vacio}>
            Escribe una pregunta y te digo cómo la clasifico: <b>Jerarquizar</b>{' '}
            (estructura), <b>Cuantificar</b> (cifras) o <b>Analizar</b> (causas). Cada
            clasificación queda en la libreta, lista para calificar.
          </li>
        )}
        {historial.map((item, indice) => (
          <li key={`${item.texto}-${indice}`} className={styles.item}>
            <p className={styles.pregunta}>{item.texto}</p>
            <p className={styles.resultado}>
              <span className={styles.grupo}>
                {ETIQUETA[item.grupo] ?? item.grupo}
              </span>
              <span className={styles.capa}>vía {item.capa}</span>
              {item.entidad !== null && (
                <span className={styles.entidad}>{item.entidad}</span>
              )}
            </p>
          </li>
        ))}
      </ul>

      {progreso !== null && (
        <p className={styles.progreso}>
          Clasificando {progreso.hechas + 1} de {progreso.total}…
        </p>
      )}
      {error !== null && <p className={styles.error}>{error}</p>}

      <div className={styles.entrada}>
        <input
          type="text"
          value={texto}
          onChange={(evento) => setTexto(evento.target.value)}
          onKeyDown={(evento) => {
            if (evento.key === 'Enter' && !evento.shiftKey) {
              evento.preventDefault();
              void enviarUna();
            }
          }}
          placeholder="Escribe una pregunta para clasificar…"
          aria-label="Pregunta para clasificar"
          disabled={enVuelo}
        />
        <button
          type="button"
          onClick={() => void enviarUna()}
          disabled={enVuelo || texto.trim() === ''}
          aria-label="Clasificar"
        >
          <Send size={16} />
        </button>
      </div>

      <details className={styles.lote}>
        <summary>
          <ListOrdered size={14} /> Cargar un lote de preguntas
        </summary>
        <textarea
          value={lote}
          onChange={(evento) => setLote(evento.target.value)}
          rows={5}
          placeholder={'Una pregunta por línea…\ncuánto crudo en Rubiales\npor qué cayó Caño Limón'}
          aria-label="Lote de preguntas"
          disabled={enVuelo}
        />
        <div className={styles.barraLote}>
          <span>
            {cuantasEnLote} pregunta{cuantasEnLote === 1 ? '' : 's'}
          </span>
          <button
            type="button"
            onClick={() => void enviarLote()}
            disabled={enVuelo || cuantasEnLote === 0}
          >
            Clasificar lote
          </button>
        </div>
      </details>
    </div>
  );
}
