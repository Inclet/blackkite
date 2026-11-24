import http from 'node:http';
import { expect, test } from '@playwright/test';
import { open } from './helpers';

interface Seen {
  method: string;
  url: string;
  contentType: string;
  body: string;
}

/** A stub API on BK_API_ORIGIN (the port the e2e config gave the preview server's proxy). */
function startStubApi(): Promise<{ seen: Seen[]; close: () => Promise<void> }> {
  const seen: Seen[] = [];
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (c: Buffer) => (body += c.toString()));
    req.on('end', () => {
      seen.push({ method: req.method ?? '', url: req.url ?? '', contentType: req.headers['content-type'] ?? '', body });
      if (req.method === 'POST' && req.url === '/auth/verify') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ redirect: '/shortlist' }));
        return;
      }
      res.writeHead(404).end();
    });
  });
  return new Promise((resolve, reject) => {
    server.on('error', reject);
    server.listen(Number(process.env.BK_E2E_API_PORT), '127.0.0.1', () =>
      resolve({ seen, close: () => new Promise((r) => server.close(() => r())) }),
    );
  });
}

test('sign-in link: the token goes through the proxy, leaves the address bar, and the redirect is followed', async ({ page }) => {
  const api = await startStubApi();
  try {
    await page.setViewportSize({ width: 390, height: 844 });
    await open(page, '/auth/confirm#token=abc');
    await expect(page.getByRole('heading', { level: 1, name: 'Sign in to Blackkite' })).toBeVisible();
    // The page itself is a web route, never proxied.
    expect(api.seen).toEqual([]);
    await expect.poll(() => page.url()).toMatch(/\/auth\/confirm$/);
    expect(page.url()).not.toContain('abc');
    await expect(page.locator('meta[name="referrer"]')).toHaveAttribute('content', 'no-referrer');

    await page.getByRole('button', { name: 'Continue to sign in' }).click();
    await expect.poll(() => new URL(page.url()).pathname).toBe('/shortlist');

    expect(api.seen).toHaveLength(1);
    const [req] = api.seen;
    expect(req!.method).toBe('POST');
    expect(req!.url).toBe('/auth/verify');
    expect(req!.contentType).toContain('application/json');
    expect(JSON.parse(req!.body)).toEqual({ token: 'abc' });
  } finally {
    await api.close();
  }
});
