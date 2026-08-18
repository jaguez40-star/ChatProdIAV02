import { BarChart3, CloudUpload, LayoutGrid, type LucideIcon } from 'lucide-react';

export interface SeccionPrincipal {
  id: 'ingesta' | 'control' | 'analisis';
  num: number;
  titulo: string;
  subtitulo: string;
  icono: LucideIcon;
}

/**
 * Los tres paneles de la página principal. El contenido de cada uno llega en
 * F1+ (ver §10 del CLAUDE.md); por ahora el cuerpo queda vacío a propósito —
 * lo que se valida aquí es la mecánica del acordeón, no el dato.
 */
export const SECCIONES: SeccionPrincipal[] = [
  {
    id: 'ingesta',
    num: 1,
    titulo: 'Ingesta',
    subtitulo: 'Carga y validación del reporte diario',
    icono: CloudUpload,
  },
  {
    id: 'control',
    num: 2,
    titulo: 'Control',
    subtitulo: 'Reportes disponibles y su estado',
    icono: LayoutGrid,
  },
  {
    id: 'analisis',
    num: 3,
    titulo: 'Análisis',
    subtitulo: 'Desempeño, brechas y consulta',
    icono: BarChart3,
  },
];

/** Estado inicial: Ingesta colapsada, Control y Análisis abiertos. */
export const ABIERTOS_INICIALES: SeccionPrincipal['id'][] = ['control', 'analisis'];

export const MAX_ABIERTOS_ESCRITORIO = 2;
export const MAX_ABIERTOS_MOVIL = 1;
