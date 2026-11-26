// End-to-end smoke test through the running proxy (deploy/smoke/run.sh starts the stack).
// Needs Playwright on the host: `require('playwright')` (any recent version).
//   BASE=http://localhost:8080 MAILPIT=http://127.0.0.1:8025 node deploy/smoke/browser.cjs
// Prints one "PASS|FAIL <check>: <evidence>" line per check; exit 1 if any failed.
// Writes the calendar link token to $SMOKE_OUT/calendar-token for the log checks.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const BASE = process.env.BASE || 'http://localhost:8080';
const MAILPIT = process.env.MAILPIT || 'http://127.0.0.1:8025';
const OUT = process.env.SMOKE_OUT || '.';
const EMAIL = process.env.SMOKE_EMAIL || 'owner@example.com';
const UNSUB_TOKEN = process.env.SMOKE_UNSUB_TOKEN || '';

let failed = 0;
function check(name, ok, evidence) {
  if (!ok) failed += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}: ${evidence}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function signInLink() {
  await fetch(`${MAILPIT}/api/v1/messages`, { method: 'DELETE' });
  const res = await fetch(`${BASE}/auth/request-link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL }),
  });
  check('request sign-in link through the proxy', res.status === 202, `POST /auth/request-link -> ${res.status}`);
  for (let i = 0; i < 30; i += 1) {
    const list = await (await fetch(`${MAILPIT}/api/v1/messages`)).json();
    const msg = (list.messages || []).find((m) => (m.To || []).some((t) => t.Address === EMAIL));
    if (msg) {
      const full = await (await fetch(`${MAILPIT}/api/v1/message/${msg.ID}`)).json();
      const m = /(https?:\/\/[^\s"<>]+\/auth\/confirm#token=[A-Za-z0-9_\-.~%]+)/.exec(full.Text || full.HTML || '');
      check('sign-in mail arrives in Mailpit', !!m, m ? `subject "${msg.Subject}", link ${m[1].replace(/token=.*/, 'token=…')}` : 'no confirm link in the mail');
      return m && m[1];
    }
    await sleep(500);
  }
  check('sign-in mail arrives in Mailpit', false, 'no mail after 15 s');
  return null;
}

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', (e) => consoleErrors.push(String(e)));

  // --- sign in --------------------------------------------------------------------
  const link = await signInLink();
  if (!link) throw new Error('cannot continue without a sign-in link');
  const confirm = await page.goto(link);
  check('/auth/confirm is the SPA with Referrer-Policy no-referrer',
    confirm.status() === 200 && confirm.headers()['referrer-policy'] === 'no-referrer',
    `status ${confirm.status()}, referrer-policy ${confirm.headers()['referrer-policy']}`);
  const cont = page.getByRole('button', { name: 'Continue to sign in' });
  await cont.waitFor({ timeout: 15000 });
  await page.waitForFunction(() => !location.href.includes('token='), null, { timeout: 5000 }).catch(() => {});
  check('token leaves the address bar before sign-in', !page.url().includes('token='), page.url());
  await cont.click();
  const rows = page.locator('[aria-label="Opportunities"] a');
  await rows.first().waitFor({ timeout: 20000 });
  const n = await rows.count();
  const texts = await rows.allInnerTexts();
  check('feed shows ranked demo items after sign-in', n > 0 && texts.some((t) => t.includes('[Demo]')),
    `${n} rows; first: ${JSON.stringify(texts[0].split('\n').slice(0, 2).join(' | '))}`);
  const cookies = await context.cookies();
  const session = cookies.find((c) => c.name === 'bk_session');
  check('session cookie is HttpOnly, SameSite set', !!session && session.httpOnly && !!session.sameSite,
    session ? `httpOnly=${session.httpOnly} sameSite=${session.sameSite} secure=${session.secure} (local http: secure off)` : 'no bk_session cookie');

  // --- API through the proxy, with the session --------------------------------------
  const me = await page.request.get(`${BASE}/me`);
  const meBody = await me.json();
  check('GET /me (proxied) as the bootstrap admin', me.status() === 200 && meBody.role === 'admin', `${me.status()} role=${meBody.role}`);
  const users = await page.request.get(`${BASE}/api/admin/users`);
  const usersBody = await users.json();
  check('GET /api/admin/users as admin', users.status() === 200 && Array.isArray(usersBody), `${users.status()}, ${usersBody.length} user(s)`);
  const anonAdmin = await fetch(`${BASE}/api/admin/users`);
  check('GET /api/admin/users without a session is refused', anonAdmin.status === 401, `${anonAdmin.status}`);

  // --- deep links load the SPA ------------------------------------------------------
  const feed = await (await page.request.get(`${BASE}/api/feed`)).json();
  const first = feed.items[0];
  const deep = await page.goto(`${BASE}/o/${first.id}`);
  await page.getByText(first.title, { exact: false }).first().waitFor({ timeout: 15000 });
  check('deep link /o/:id loads the SPA and the item', deep.status() === 200 && deep.headers()['content-type'].startsWith('text/html'),
    `${deep.status()} ${deep.headers()['content-type']}, shows "${first.title}"`);
  const adm = await page.goto(`${BASE}/admin/sources`);
  await page.getByRole('heading', { level: 1, name: 'Sources' }).waitFor({ timeout: 15000 });
  check('deep link /admin/sources loads the SPA admin screen', adm.status() === 200, `${adm.status()}, h1 "Sources"`);
  const cal = await page.goto(`${BASE}/calendar`);
  check('/calendar is the SPA', cal.status() === 200 && cal.headers()['content-type'].startsWith('text/html'), `${cal.status()} ${cal.headers()['content-type']}`);

  // --- calendar feed ------------------------------------------------------------------
  const saved = await page.request.put(`${BASE}/api/opportunities/${first.id}/state`, { data: { state: 'saved' } });
  const linkRes = await page.request.get(`${BASE}/api/calendar/feed-link`);
  const feedLink = await linkRes.json();
  const icsUrl = feedLink.url;
  check('calendar feed link offered', saved.ok() && linkRes.status() === 200 && /\/api\/calendar\.ics\?token=/.test(icsUrl || ''),
    `${linkRes.status()} ${String(icsUrl).replace(/token=.*/, 'token=…')}`);
  const token = new URL(icsUrl).searchParams.get('token');
  fs.writeFileSync(path.join(OUT, 'calendar-token'), token);
  const ics = await fetch(`${BASE}/api/calendar.ics?token=${encodeURIComponent(token)}`); // no cookies
  const icsBody = await ics.text();
  check('calendar .ics link works without a session', ics.status === 200 && ics.headers.get('content-type').startsWith('text/calendar') && icsBody.includes('BEGIN:VCALENDAR') && icsBody.includes('BEGIN:VEVENT'),
    `${ics.status} ${ics.headers.get('content-type')}, cache-control ${ics.headers.get('cache-control')}, ${icsBody.split('BEGIN:VEVENT').length - 1} VEVENT(s)`);
  const badIcs = await fetch(`${BASE}/api/calendar.ics?token=not-a-token`);
  check('bad calendar token is a JSON 404', badIcs.status === 404 && badIcs.headers.get('content-type').includes('application/json'), `${badIcs.status} ${badIcs.headers.get('content-type')}`);

  // --- unsubscribe page ------------------------------------------------------------------
  // A fresh browser (no service worker yet) sees the proxy's own headers.
  const fresh = await browser.newContext();
  const freshPage = await fresh.newPage();
  const unsubFresh = await freshPage.goto(`${BASE}/unsubscribe`);
  check('/unsubscribe is the SPA with Referrer-Policy no-referrer', unsubFresh.status() === 200 && unsubFresh.headers()['referrer-policy'] === 'no-referrer',
    `${unsubFresh.status()}, referrer-policy ${unsubFresh.headers()['referrer-policy']}`);
  await fresh.close();
  // Once the PWA's service worker controls the page it answers navigations from
  // its cached index.html (with that file's headers); the app's own
  // <meta name="referrer" content="no-referrer"> still applies.
  const unsub = await page.goto(`${BASE}/unsubscribe#token=${UNSUB_TOKEN}`);
  await page.getByRole('heading', { level: 1, name: 'Emails from Blackkite' }).waitFor({ timeout: 15000 });
  const meta = await page.evaluate(() => document.querySelector('meta[name="referrer"]')?.getAttribute('content'));
  const viaSw = unsub.fromServiceWorker();
  check('/unsubscribe keeps no-referrer under the service worker (meta tag)', meta === 'no-referrer',
    `served by service worker: ${viaSw}; header ${unsub.headers()['referrer-policy']}; meta referrer ${meta}`);
  if (UNSUB_TOKEN) {
    await page.getByRole('button', { name: 'Stop these emails' }).click();
    await page.getByText("You won't get these emails any more.").waitFor({ timeout: 15000 });
    check('unsubscribe page stops the digest (POST /api/unsubscribe via the proxy)', true, 'shows "You won\'t get these emails any more."');
  }
  const getUnsub = await fetch(`${BASE}/api/unsubscribe?token=x`);
  check('GET /api/unsubscribe changes nothing (405 JSON)', getUnsub.status === 405, `${getUnsub.status} ${getUnsub.headers.get('content-type')}`);

  // --- routing and headers ---------------------------------------------------------------
  for (const p of ['/api/does-not-exist', '/api', '/api/admin/nope']) {
    const r = await fetch(`${BASE}${p}`);
    check(`${p} is a JSON 404, not the SPA`, r.status === 404 && r.headers.get('content-type').includes('application/json'), `${r.status} ${r.headers.get('content-type')}`);
  }
  for (const p of ['/apiary', '/me/export', '/auth/confirm', '/unsubscribe', '/admin/users', '/sources']) {
    const r = await fetch(`${BASE}${p}`);
    check(`${p} is the SPA`, r.status === 200 && r.headers.get('content-type').startsWith('text/html'), `${r.status} ${r.headers.get('content-type')}`);
  }
  const index = await fetch(`${BASE}/`);
  const html = await index.text();
  const asset = /src="(\/assets\/[^"]+\.js)"/.exec(html)[1];
  const a = await fetch(`${BASE}${asset}`);
  check('hashed asset cached for a year, immutable', a.status === 200 && a.headers.get('cache-control') === 'public, max-age=31536000, immutable', `${asset}: ${a.headers.get('cache-control')}`);
  check('index.html revalidates', index.headers.get('cache-control') === 'no-cache', `/: ${index.headers.get('cache-control')}`);
  const sw = await fetch(`${BASE}/sw.js`);
  check('service worker revalidates', sw.status === 200 && sw.headers.get('cache-control') === 'no-cache', `/sw.js: ${sw.headers.get('cache-control')}`);
  const missing = await fetch(`${BASE}/assets/missing-0000.js`);
  check('missing bundle is a 404, not the SPA', missing.status === 404, `${missing.status}`);
  const h = index.headers;
  const csp = h.get('content-security-policy') || '';
  check('security headers on the SPA',
    csp.includes("default-src 'self'") && csp.includes("frame-ancestors 'none'") && !csp.includes('unsafe-inline') &&
      h.get('x-content-type-options') === 'nosniff' && h.get('referrer-policy') === 'strict-origin-when-cross-origin' &&
      !h.get('strict-transport-security') && !h.get('server'),
    `CSP "${csp}"; nosniff; referrer ${h.get('referrer-policy')}; HSTS ${h.get('strict-transport-security') || 'absent (plain HTTP)'}; server ${h.get('server') || 'absent'}`);
  const apiH = (await fetch(`${BASE}/me`)).headers;
  check('API responses carry the headers too, no server banner', apiH.get('x-content-type-options') === 'nosniff' && !apiH.get('server'), `server ${apiH.get('server') || 'absent'}`);
  const cspErrors = consoleErrors.filter((e) => /Content Security Policy|Refused to/i.test(e));
  check('no CSP violations while using the app', cspErrors.length === 0, cspErrors.length ? cspErrors.join(' || ') : `${consoleErrors.length} console error(s) in total, none from CSP`);

  await browser.close();
}

main().then(
  () => process.exit(failed ? 1 : 0),
  (e) => { console.log(`FAIL browser run: ${e.stack || e}`); process.exit(1); },
);
