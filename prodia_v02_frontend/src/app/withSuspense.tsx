import { Suspense } from 'react';
import type { ComponentType, ReactElement } from 'react';

import { PageLoader } from '../shared/components/PageLoader';

/**
 * Corrección C7 sobre Robustez V02: su `router.tsx` envuelve cada ruta a
 * mano en `<Suspense fallback={<PageLoader/>}>...</Suspense>`, repetido
 * ~20 veces. Este helper produce lo mismo en una línea por ruta.
 */
export function withSuspense(Component: ComponentType): ReactElement {
  return (
    <Suspense fallback={<PageLoader />}>
      <Component />
    </Suspense>
  );
}
