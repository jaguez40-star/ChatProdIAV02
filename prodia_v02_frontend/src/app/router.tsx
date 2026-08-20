import { lazy } from 'react';
import { createBrowserRouter } from 'react-router-dom';
import type { RouteObject } from 'react-router-dom';

import { ProtectedRoute } from '../shared/components/ProtectedRoute';
import { RutaAdmin } from '../shared/components/RutaAdmin';
import { SECCIONES } from './secciones';
import { withSuspense } from './withSuspense';

/** Ruta de una sección, por su etiqueta. Falla ruidosamente si no existe. */
function ruta(etiqueta: string): string {
  const seccion = SECCIONES.find((s) => s.etiqueta === etiqueta);
  if (!seccion) {
    throw new Error(
      `No hay ninguna sección con la etiqueta «${etiqueta}» en secciones.ts`,
    );
  }
  return seccion.ruta;
}

const LoginPage = lazy(() => import('../features/auth/pages/LoginPage'));
const ConsultaPage = lazy(() => import('../features/consulta/pages/ConsultaPage'));
const AnalisisPage = lazy(() => import('../features/analisis/pages/AnalisisPage'));
const IngestaPage = lazy(() => import('../features/ingesta/pages/IngestaPage'));
const TestClasPage = lazy(() => import('../features/testclas/pages/TestClasPage'));
const NotFoundPage = lazy(() => import('../shared/components/NotFoundPage/NotFoundPage'));
const LayoutMain = lazy(() =>
  import('./layouts/LayoutMain').then((m) => ({ default: m.LayoutMain })),
);

// Exportado para que `router.test.ts` pueda recorrer las rutas montadas y
// compararlas con `secciones.ts`. Es lo que convierte «se me olvidó enlazar la
// página» en un fallo de build.
export const routes: RouteObject[] = [
  { path: '/login', element: withSuspense(LoginPage) },
  {
    // Ruta pathless: el guard envuelve el layout, que hace <Outlet/>.
    element: (
      <ProtectedRoute>{withSuspense(LayoutMain)}</ProtectedRoute>
    ),
    children: [
      // Las rutas de sección se declaran en `app/secciones.ts`, que es también
      // la fuente del header. `LayoutMain.test.tsx` recorre esa lista y exige
      // que cada una tenga su enlace: añadir una sección sin enlazarla rompe el
      // build, que es lo que no ocurrió con /analisis, /ingesta ni /test-clas.
      { path: ruta('Consulta'), element: withSuspense(ConsultaPage) },
      { path: ruta('Análisis'), element: withSuspense(AnalisisPage) },
      { path: ruta('Ingesta'), element: withSuspense(IngestaPage) },
      // F5: admin-only. La guarda va en el ELEMENTO, no en el ProtectedRoute de
      // arriba — aquél envuelve el layout entero y restringiría las otras tres
      // secciones. El backend es quien decide (403); esto solo evita ofrecer
      // una puerta cerrada.
      {
        path: ruta('Test Clas'),
        element: <RutaAdmin>{withSuspense(TestClasPage)}</RutaAdmin>,
      },
      { path: '*', element: withSuspense(NotFoundPage) },
    ],
  },
  { path: '*', element: withSuspense(NotFoundPage) },
];

export const router = createBrowserRouter(routes);
