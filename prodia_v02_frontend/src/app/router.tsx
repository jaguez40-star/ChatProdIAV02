import { lazy } from 'react';
import { createBrowserRouter } from 'react-router-dom';
import type { RouteObject } from 'react-router-dom';

import { ProtectedRoute } from '../shared/components/ProtectedRoute';
import { withSuspense } from './withSuspense';

const LoginPage = lazy(() => import('../features/auth/pages/LoginPage'));
const HomePage = lazy(() => import('../features/home/pages/HomePage'));
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
      { path: '/', element: withSuspense(HomePage) },
      { path: '*', element: withSuspense(NotFoundPage) },
    ],
  },
  { path: '*', element: withSuspense(NotFoundPage) },
];

export const router = createBrowserRouter(routes);
