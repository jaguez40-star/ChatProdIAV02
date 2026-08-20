/**
 * Las secciones navegables de la aplicación — FUENTE ÚNICA.
 *
 * 🔑 Por qué existe este archivo. Tres veces seguidas se entregó una página
 * inalcanzable: F2 creó `/analisis`, F3 creó `/ingesta` y F5 creó `/test-clas`,
 * y ninguna quedó enlazada en el header. La página existía, pasaba sus tests y
 * solo se llegaba escribiendo la URL a mano.
 *
 * El test que debía atraparlo repetía la lista de rutas en su propio código, así
 * que una ruta nueva no lo rompía: verificaba lo que él mismo declaraba, no lo
 * que el router monta. Mientras la lista se escriba dos veces, el olvido puede
 * repetirse.
 *
 * Aquí se declara UNA vez. `router.tsx` monta estas rutas y `LayoutMain` pinta
 * estos enlaces, ambos leyendo de aquí.
 */

/** Permiso exigido para ver la sección. `null` = todo usuario autenticado. */
export type RequisitoSeccion = null | 'admin';

export interface Seccion {
  ruta: string;
  etiqueta: string;
  requiere: RequisitoSeccion;
}

export const SECCIONES: readonly Seccion[] = [
  { ruta: '/', etiqueta: 'Consulta', requiere: null },
  { ruta: '/analisis', etiqueta: 'Análisis', requiere: null },
  { ruta: '/ingesta', etiqueta: 'Ingesta', requiere: null },
  // Admin-only: el laboratorio del clasificador (F5). El backend es quien
  // decide de verdad (403); ocultar el enlace solo evita ofrecer una puerta
  // cerrada.
  { ruta: '/test-clas', etiqueta: 'Test Clas', requiere: 'admin' },
] as const;

/**
 * Las secciones que este usuario puede ver.
 *
 * Cierra la parte de navegación de DT-3/C4: el backend calcula `sections` y
 * `is_admin` desde F0, el dato viajaba hasta el store y **nadie lo leía**. Con
 * tres secciones abiertas era tolerable; con Test Clas deja de serlo, porque
 * un usuario sin permiso vería un enlace que solo le devuelve un 403.
 */
export function seccionesVisibles(esAdmin: boolean): readonly Seccion[] {
  return SECCIONES.filter((s) => s.requiere !== 'admin' || esAdmin);
}
