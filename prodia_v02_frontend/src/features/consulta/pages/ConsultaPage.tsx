import { AcordeonHorizontal } from '../components/AcordeonHorizontal';

/**
 * Página de Consulta: tres paneles colapsables en horizontal (Historial,
 * Chat, Insights). Los cuerpos están vacíos a propósito — el Motor Q v2 que
 * los llena es F4 (ver §10 del CLAUDE.md); esto es solo el cascarón.
 */
export default function ConsultaPage() {
  return <AcordeonHorizontal />;
}
