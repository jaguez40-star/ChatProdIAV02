/**
 * Hooks de Análisis — uno por endpoint.
 *
 * **Carga perezosa (`enabled`)**: las pills del acordeón solo consultan cuando
 * se muestran. Sin eso, abrir un foco dispararía 4 peticiones caras de golpe
 * —una de ellas al EBITDA, que cruza tres tablas— aunque el usuario solo mire
 * la primera pestaña.
 *
 * **`staleTime` alto**: el backend ya cachea estos paneles 15 minutos (regla
 * A4) porque el reporte de producción cambia una vez al día. Refrescar en
 * cada foco del navegador solo gastaría red para recibir lo mismo.
 */

import { useQuery } from '@tanstack/react-query';

import {
  getCatalogo,
  getCobertura,
  getDensidad,
  getDesempeno,
  getDiferidas,
  getEjecutivo,
  getHuella,
  getMantenimientos,
  getPresident,
  getWaterfall,
} from '../services/analisisService';
import type { Ambito } from '../types/analisisTypes';

/** 15 min: el mismo TTL que la caché del backend. */
const FRESCURA_MS = 15 * 60 * 1000;

/** Raíz de todas las claves, para poder invalidar la sección entera. */
const RAIZ = ['analisis'] as const;

export function useCatalogo() {
  return useQuery({
    queryKey: [...RAIZ, 'catalogo'],
    queryFn: getCatalogo,
    staleTime: FRESCURA_MS,
  });
}

export function useDensidad(entidad?: string) {
  return useQuery({
    queryKey: [...RAIZ, 'densidad', entidad ?? null],
    queryFn: () => getDensidad(entidad),
    staleTime: FRESCURA_MS,
  });
}

export function useHuella(entidad?: string) {
  return useQuery({
    queryKey: [...RAIZ, 'huella', entidad ?? null],
    queryFn: () => getHuella(entidad),
    staleTime: FRESCURA_MS,
  });
}

export function useCobertura(entidad?: string) {
  return useQuery({
    queryKey: [...RAIZ, 'cobertura', entidad ?? null],
    queryFn: () => getCobertura(entidad),
    staleTime: FRESCURA_MS,
  });
}

export function useDesempeno(ambito: Ambito) {
  return useQuery({
    queryKey: [...RAIZ, 'desempeno', ambito],
    queryFn: () => getDesempeno(ambito),
    staleTime: FRESCURA_MS,
  });
}

export function useEjecutivo(ambito: Ambito) {
  return useQuery({
    queryKey: [...RAIZ, 'ejecutivo', ambito],
    queryFn: () => getEjecutivo(ambito),
    staleTime: FRESCURA_MS,
  });
}

export function usePresident(periodo?: string) {
  return useQuery({
    queryKey: [...RAIZ, 'president', periodo ?? null],
    queryFn: () => getPresident(periodo),
    staleTime: FRESCURA_MS,
  });
}

// ── Pills del acordeón: solo consultan si están visibles ────────────────────

export function useWaterfall(entidad?: string, nivel?: string, activa = false) {
  return useQuery({
    queryKey: [...RAIZ, 'ebitda', entidad ?? null, nivel ?? null],
    queryFn: () => getWaterfall(entidad, nivel),
    staleTime: FRESCURA_MS,
    enabled: activa,
  });
}

export function useDiferidas(entidad?: string, nivel?: string, activa = false) {
  return useQuery({
    queryKey: [...RAIZ, 'diferidas', entidad ?? null, nivel ?? null],
    queryFn: () => getDiferidas(entidad, nivel),
    // Los datos son históricos y estáticos (ene-2023 → jul-2025): una vez
    // cargados no cambian mientras dure la sesión.
    staleTime: Infinity,
    enabled: activa,
  });
}

export function useMantenimientos(
  entidad?: string,
  nivel?: string,
  periodo?: string,
  activa = false,
) {
  return useQuery({
    queryKey: [...RAIZ, 'mantenimientos', entidad ?? null, nivel ?? null, periodo ?? null],
    queryFn: () => getMantenimientos(entidad, nivel, periodo),
    staleTime: FRESCURA_MS,
    enabled: activa,
  });
}
