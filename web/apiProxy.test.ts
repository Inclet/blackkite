import type { IncomingMessage } from 'node:http';
import { expect, test } from 'vitest';
import { apiProxy, wantsHtml } from './apiProxy';

const proxy = apiProxy('http://api.test');
const entry = (url: string) => Object.entries(proxy).find(([k]) => new RegExp(k).test(url))?.[1];
const proxied = (url: string) => entry(url) !== undefined;

const req = (accept?: string) => ({ headers: accept === undefined ? {} : { accept } }) as IncomingMessage;
const PAGE_LOAD = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8';

test('the exact API paths go to the API origin', () => {
  for (const url of [
    '/auth/verify',
    '/auth/request-link',
    '/auth/logout',
    '/me',
    '/me?x=1',
    '/me/export',
    '/feed',
    '/feed?stream=tender&profile=Ironji-Trade',
    '/digest-settings',
    '/shortlist',
    '/profiles',
    '/profiles/3f0c',
    '/opportunities/wfp-logistics',
    '/opportunities/wfp-logistics/state',
    '/opportunities/wfp-logistics/note',
    '/admin',
    '/admin/',
    '/admin/sources/3',
    '/admin?q=1',
  ]) {
    expect(proxied(url), url).toBe(true);
  }
});

test('web routes, including the confirm page, stay on the web server', () => {
  for (const url of [
    '/',
    '/auth/confirm',
    '/auth/confirm?token=a',
    '/auth/verify/x',
    '/auth',
    '/meet',
    '/me/x',
    '/me/exports',
    '/feeds',
    '/administrator',
    '/o/wfp-logistics',
    '/opportunities',
    '/opportunities/a/b',
    '/opportunities/a/statex',
    '/profiles/a/b',
    '/shortlists',
    '/settings/digest',
    '/account',
    '/sign-in',
    '/styleguide/components',
    '/fonts/google-figtree.css',
  ]) {
    expect(proxied(url), url).toBe(false);
  }
});

test('/shortlist and /profiles: a page load gets the app, the client fetch goes to the API', () => {
  for (const url of ['/shortlist', '/profiles', '/profiles/3f0c']) {
    const bypass = entry(url)!.bypass!;
    expect(bypass(req(PAGE_LOAD), undefined, {}), url).toBe('/index.html');
    expect(bypass(req('application/json'), undefined, {}), url).toBeUndefined();
    expect(bypass(req(), undefined, {}), url).toBeUndefined();
  }
});

test('only the shared paths bypass the proxy for page loads', () => {
  for (const url of ['/feed', '/me', '/me/export', '/digest-settings', '/opportunities/a', '/auth/verify', '/admin']) {
    expect(entry(url)!.bypass, url).toBeUndefined();
  }
});

test('wantsHtml reads the Accept header', () => {
  expect(wantsHtml(req(PAGE_LOAD))).toBe(true);
  expect(wantsHtml(req('application/json'))).toBe(false);
  expect(wantsHtml(req())).toBe(false);
});

test('every route targets BK_API_ORIGIN', () => {
  expect(new Set(Object.values(proxy).map((o) => o.target))).toEqual(new Set(['http://api.test']));
});
