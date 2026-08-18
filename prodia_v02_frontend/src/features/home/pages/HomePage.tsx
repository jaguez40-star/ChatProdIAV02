import { AcordeonHorizontal } from '../components/AcordeonHorizontal';

/**
 * Página principal: tres paneles colapsables en horizontal (Ingesta, Control,
 * Análisis). Los cuerpos están vacíos a propósito — cada uno se llena con su
 * feature en F1+ (ver §10 del CLAUDE.md).
 */
export default function HomePage() {
  return <AcordeonHorizontal />;
}
