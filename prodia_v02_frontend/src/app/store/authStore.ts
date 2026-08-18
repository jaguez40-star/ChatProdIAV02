import { create } from 'zustand';

import type { AuthPermissions, AuthUser } from '../../features/auth/types/authTypes';

const STORAGE_KEY = 'prodia_auth';

interface PersistedAuth {
  userId: number;
  username: string;
  email: string;
  isAdmin: boolean;
}

interface AuthState {
  user: AuthUser | null;
  permissions: AuthPermissions | null;
  isAuthenticated: boolean;
  isHydrated: boolean;
  sessionExpiresAt: string | null; // ISO UTC desde header X-Session-Expires
  /** La sesión se cerró por vencimiento, no por acción del usuario. Lo lee
   *  ProtectedRoute para avisarle a LoginPage por qué lo mandaron ahí. */
  sessionExpired: boolean;

  setSession: (user: AuthUser, permissions: AuthPermissions) => void;
  clearSession: () => void;
  setHydrated: () => void;
  setSessionExpiry: (expiresAt: string | null) => void;
  markSessionExpired: () => void;
}

function persistToStorage(user: AuthUser): void {
  const data: PersistedAuth = {
    userId: user.id,
    username: user.username,
    email: user.email,
    isAdmin: user.isAdmin,
  };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    // localStorage puede fallar en modo privado
  }
}

function clearStorage(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // silencioso
  }
}

export function getPersistedAuth(): PersistedAuth | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PersistedAuth;
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthState>()((set) => ({
  user: null,
  permissions: null,
  isAuthenticated: false,
  isHydrated: false,
  sessionExpiresAt: null,
  sessionExpired: false,

  setSession: (user, permissions) => {
    persistToStorage(user);
    set({ user, permissions, isAuthenticated: true, sessionExpired: false });
  },

  clearSession: () => {
    clearStorage();
    set({
      user: null,
      permissions: null,
      isAuthenticated: false,
      sessionExpiresAt: null,
      sessionExpired: false,
    });
  },

  // Igual que clearSession pero dejando dicho POR QUÉ se cerró. El logout
  // voluntario usa clearSession y no debe mostrar el aviso de vencimiento.
  markSessionExpired: () => {
    clearStorage();
    set({
      user: null,
      permissions: null,
      isAuthenticated: false,
      sessionExpiresAt: null,
      sessionExpired: true,
    });
  },

  setHydrated: () => {
    set({ isHydrated: true });
  },

  setSessionExpiry: (expiresAt) => {
    set({ sessionExpiresAt: expiresAt });
  },
}));
