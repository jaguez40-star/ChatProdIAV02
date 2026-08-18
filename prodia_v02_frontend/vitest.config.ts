import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Umbrales de cobertura forzados (L7) — esto sostiene la estabilidad, no
// los tests en sí. Los exclude evitan inflar la cobertura con barriles y
// tipos generados.
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup/vitest.setup.ts'],
    pool: 'forks',
    poolOptions: {
      forks: { singleFork: true, execArgv: ['--max-old-space-size=8192'] },
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.d.ts',
        'src/main.tsx',
        'src/shared/types/**',
        'src/**/index.{ts,tsx}',
      ],
      thresholds: { lines: 80, branches: 80, functions: 80, statements: 80 },
    },
  },
});
