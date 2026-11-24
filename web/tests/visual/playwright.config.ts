import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import { DEVICE_SCALE_FACTOR, LOCALE, TIMEZONE } from './contract';
import { reportsDir, webRoot } from './paths';

const PORT = 4317;

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  outputDir: path.join(reportsDir, '.playwright'),
  fullyParallel: true,
  forbidOnly: true,
  retries: 0,
  reporter: [['list']],
  globalSetup: './report-setup.ts',
  globalTeardown: './report-teardown.ts',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    deviceScaleFactor: DEVICE_SCALE_FACTOR,
    reducedMotion: 'reduce',
    timezoneId: TIMEZONE,
    locale: LOCALE,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
    // The PWA service worker must not cache or intercept anything under test.
    serviceWorkers: 'block',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // devices[] sets its own viewport and scale; the contract overrides them.
        deviceScaleFactor: DEVICE_SCALE_FACTOR,
      },
    },
  ],
  webServer: {
    // Always a fresh production build, served by vite preview.
    command: `npm run build && npx vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
    cwd: webRoot,
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
});
