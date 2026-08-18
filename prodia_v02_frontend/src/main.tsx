import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import '@fontsource/inter/400.css';
import '@fontsource/inter/600.css';
import './shared/styles/index.scss';

import { App } from './app/App';
import { getPersistedAuth, useAuthStore } from './app/store/authStore';
import { getMe } from './features/auth/services/authService';
import { installSessionInterceptor } from './shared/services/sessionInterceptor';

// Antes de la primera petición: así el propio getMe() de la hidratación ya
// queda cubierto por el interceptor.
installSessionInterceptor();

async function hydrateAuth(): Promise<void> {
  const persisted = getPersistedAuth();
  if (!persisted) {
    useAuthStore.getState().setHydrated();
    return;
  }

  try {
    const session = await getMe();
    useAuthStore.getState().setSession(session.user, session.permissions);
  } catch {
    useAuthStore.getState().clearSession();
  } finally {
    useAuthStore.getState().setHydrated();
  }
}

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('Root element #root not found in index.html');
}

// React NO se monta hasta que la sesión está resuelta — por eso no hay
// flash de login para un usuario ya autenticado.
void hydrateAuth().then(() => {
  createRoot(rootEl).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
