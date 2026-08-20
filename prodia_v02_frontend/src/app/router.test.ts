import type { RouteObject } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { routes } from './router';
import { SECCIONES } from './secciones';

/**
 * 🔑 El guardián contra la página inalcanzable.
 *
 * Ha ocurrido TRES veces: F2 montó `/analisis`, F3 montó `/ingesta` y F5 montó
 * `/test-clas` sin enlazarlas. La página existía, pasaba sus propios tests, y
 * solo se llegaba escribiendo la URL a mano.
 *
 * El test que debía atraparlo vivía en `LayoutMain.test.tsx` y comparaba el
 * header contra una lista escrita en el propio test: verificaba lo que él mismo
 * declaraba, no lo que la aplicación monta. Por eso no atrapó ninguna de las
 * tres.
 *
 * Este sí, porque compara las dos fuentes REALES entre sí: las rutas que monta
 * `router.tsx` y las secciones que declara `secciones.ts` (de donde sale el
 * header). Si divergen, falla.
 */

/** Rutas navegables del router, sin comodines ni rutas técnicas. */
function rutasMontadas(nodos: readonly RouteObject[]): string[] {
  const encontradas: string[] = [];

  const recorrer = (lista: readonly RouteObject[]) => {
    for (const nodo of lista) {
      if (nodo.path && nodo.path !== '*') encontradas.push(nodo.path);
      if (nodo.children) recorrer(nodo.children);
    }
  };

  recorrer(nodos);
  return encontradas;
}

// `/login` es la única ruta navegable que NO es una sección: se llega a ella
// por expulsión, no por el menú, y enlazarla en el header no tendría sentido.
const FUERA_DEL_MENU = new Set(['/login']);

describe('router — toda ruta navegable es una sección declarada', () => {
  it('ninguna ruta montada se queda sin su entrada en secciones.ts', () => {
    const declaradas = new Set(SECCIONES.map((s) => s.ruta));

    const huerfanas = rutasMontadas(routes).filter(
      (ruta) => !FUERA_DEL_MENU.has(ruta) && !declaradas.has(ruta),
    );

    // Si esto falla: añadiste una ruta al router y olvidaste declararla en
    // `secciones.ts`. La página sería inalcanzable desde el menú.
    expect(huerfanas).toEqual([]);
  });

  it('ninguna sección declarada se queda sin ruta en el router', () => {
    const montadas = new Set(rutasMontadas(routes));

    // El descuido inverso: una entrada en el menú que lleva a un 404.
    const rotas = SECCIONES.filter((s) => !montadas.has(s.ruta)).map((s) => s.ruta);

    expect(rotas).toEqual([]);
  });
});
