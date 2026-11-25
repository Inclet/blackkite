import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, devices } from '@playwright/test';

const here = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(here, '../..');
const PORT = 4318;

/** A free local port. */
function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address() as net.AddressInfo;
      srv.close(() => resolve(port));
    });
  });
}

// The preview server proxies the API paths here; globalSetup starts the stub API on it (stubApi.ts).
// Chosen once in the main process; workers inherit it through the environment.
process.env.BK_E2E_API_PORT ??= String(await freePort());
export const API_ORIGIN = `http://127.0.0.1:${process.env.BK_E2E_API_PORT}`;

/** End-to-end checks (keyboard, reflow, focus, contrast, motion). Separate from the frozen visual harness. */
export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  globalSetup: path.join(here, 'globalSetup.ts'),
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
    env: { ...(process.env as Record<string, string>), BK_API_ORIGIN: API_ORIGIN },
  },
});
