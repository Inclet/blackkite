import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const designDir = fileURLToPath(new URL('../design', import.meta.url));

export default defineConfig({
  resolve: {
    alias: { '@design': designDir },
  },
  server: {
    // Components read path data from design/assets (e.g. kite-full.svg?raw).
    fs: { allow: ['.', designDir] },
  },
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}', 'apiProxy.test.ts', 'pwa.test.ts', 'tests/contract/**/*.test.ts'],
    css: { modules: { classNameStrategy: 'non-scoped' } },
  },
});
