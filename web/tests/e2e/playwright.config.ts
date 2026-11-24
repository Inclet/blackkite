import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, devices } from '@playwright/test';

const here = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(here, '../..');
const PORT = 4318;

/** End-to-end checks (keyboard, reflow, focus, contrast, motion). Separate from the frozen visual harness. */
export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  outputDir: path.join(webRoot, 'test-results/e2e'),
  fullyParallel: true,
  forbidOnly: true,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    deviceScaleFactor: 1,
    timezoneId: 'Africa/Kigali',
    locale: 'en-GB',
    reducedMotion: 'reduce',
    trace: 'off',
    screenshot: 'off',
    video: 'off',
    serviceWorkers: 'block',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], deviceScaleFactor: 1 } }],
  webServer: {
    command: `npm run build && npx vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
    cwd: webRoot,
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
});
