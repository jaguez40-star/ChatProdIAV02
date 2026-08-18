import { RouterProvider } from 'react-router-dom';

import { ErrorBoundary } from '../shared/components/ErrorBoundary';
import { Providers } from './providers';
import { router } from './router';

export function App() {
  return (
    <ErrorBoundary>
      <Providers>
        <RouterProvider router={router} />
      </Providers>
    </ErrorBoundary>
  );
}
