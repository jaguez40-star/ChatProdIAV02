import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Puertos por env (N2 — una sola fuente): front 6033 / back 6034 por
// defecto, para no chocar con Robustez V02 (6023/6024).
const FRONT_PORT = parseInt(process.env.VITE_PORT || '6033', 10);
const BACK_PORT = parseInt(process.env.VITE_BACKEND_PORT || '6034', 10);

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: FRONT_PORT,
    strictPort: true,
    proxy: {
      '/api': { target: `http://localhost:${BACK_PORT}`, changeOrigin: true },
    },
  },
});
