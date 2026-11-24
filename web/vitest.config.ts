import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  resolve: {
    alias: { '@design': fileURLToPath(new URL('../design', import.meta.url)) },
  },
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: { modules: { classNameStrategy: 'non-scoped' } },
  },
});
