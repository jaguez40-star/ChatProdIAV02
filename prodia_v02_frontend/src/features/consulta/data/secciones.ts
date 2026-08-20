import { ChartColumn, MessageCircle, MessagesSquare, type LucideIcon } from 'lucide-react';

export interface SeccionPrincipal {
  id: 'historial' | 'chat' | 'insights';
  num: number;
  titulo: string;
  subtitulo: string;
  icono: LucideIcon;
}

/**
 * Los tres paneles de la página de Consulta. El contenido de cada uno llega
 * en F4 (Motor Q v2, ver §10 del CLAUDE.md); por ahora el cuerpo queda vacío
 * a propósito — lo que se valida aquí es la mecánica del acordeón, no el
 * dato.
 */
export const SECCIONES: SeccionPrincipal[] = [
  {
    id: 'historial',
    num: 1,
    titulo: 'Historial',
    subtitulo: 'Conversaciones anteriores',
    icono: MessagesSquare,
  },
  {
    id: 'chat',
    num: 2,
    titulo: 'Chat',
    subtitulo: 'Consulta en lenguaje natural',
    icono: MessageCircle,
  },
  {
    id: 'insights',
    num: 3,
    titulo: 'Insights',
    subtitulo: 'Gráficos de la respuesta',
    icono: ChartColumn,
  },
];

/** Estado inicial: Historial y Chat abiertos (reparto 25/75), Insights colapsado. */
export const ABIERTOS_INICIALES: SeccionPrincipal['id'][] = ['historial', 'chat'];

export const MAX_ABIERTOS_ESCRITORIO = 2;
export const MAX_ABIERTOS_MOVIL = 1;
