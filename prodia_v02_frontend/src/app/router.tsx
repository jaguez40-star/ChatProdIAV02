import { lazy } from 'react';
import { createBrowserRouter } from 'react-router-dom';
import type { RouteObject } from 'react-router-dom';

import { ProtectedRoute } from '../shared/components/ProtectedRoute';
import { RutaAdmin } from '../shared/components/RutaAdmin';
import { withSuspense } from './withSuspense';

const LoginPage = lazy(() => import('../features/auth/pages/LoginPage'));
const ConsultaPage = lazy(() => import('../features/consulta/pages/ConsultaPage'));
const AnalisisPage = lazy(() => import('../features/analisis/pages/AnalisisPage'));
const IngestaPage = lazy(() => import('../features/ingesta/pages/IngestaPage'));
const TestClasPage = lazy(() => import('../features/testclas/pages/TestClasPage'));
const NotFoundPage = lazy(() => import('../shared/components/NotFoundPage/NotFoundPage'));
const LayoutMain = lazy(() =>
  import('./layouts/LayoutMain').then((m) => ({ default: m.LayoutMain })),
);

const routes: RouteObject[] = [
  { path: '/login', element: withSuspense(LoginPage) },
  {
    // Ruta pathless: el guard envuelve el layout, que hace <Outlet/>.
    element: (
      <ProtectedRoute>{withSuspense(LayoutMain)}</ProtectedRoute>
    ),
    children: [
      { path: '/', element: withSuspense(ConsultaPage) },
      // F2: por URL directa, sin entrada de menu (igual que /control).
      { path: '/analisis', element: withSuspense(AnalisisPage) },
      // F3: idem — la navegacion entre secciones sigue fuera de alcance.
      { path: '/ingesta', element: withSuspense(IngestaPage) },
      // F5: admin-only. La guarda va en el ELEMENTO, no en el ProtectedRoute de
      // arriba — aquél envuelve el layout entero y restringiría las otras tres
      // secciones. El backend es quien decide (403); esto solo evita ofrecer
      // una puerta cerrada.
      {
        path: '/test-clas',
        element: <RutaAdmin>{withSuspense(TestClasPage)}</RutaAdmin>,
      },
      { path: '*', element: withSuspense(NotFoundPage) },
    ],
  },
  { path: '*', element: withSuspense(NotFoundPage) },
];

export const router = createBrowserRouter(routes);
