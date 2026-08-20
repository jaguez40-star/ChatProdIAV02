import { AcordeonHorizontal } from '../components/AcordeonHorizontal';
import { PanelChat } from '../components/PanelChat/PanelChat';
import { PanelHistorial } from '../components/PanelHistorial/PanelHistorial';
import { PilaResultados } from '../components/PilaResultados/PilaResultados';

/**
 * Página de Consulta: tres paneles colapsables (Historial, Chat, Insights).
 *
 * El cascarón y su mecánica son de F1a —ya verificados en navegador— y no se
 * tocan: F4 solo llena los cuerpos.
 */
export default function ConsultaPage() {
  return (
    <AcordeonHorizontal
      cuerpos={{
        historial: <PanelHistorial />,
        chat: <PanelChat />,
        insights: <PilaResultados />,
      }}
    />
  );
}
