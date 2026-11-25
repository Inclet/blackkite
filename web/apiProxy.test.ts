import { expect, test } from 'vitest';
import { apiProxy } from './apiProxy';

const proxy = apiProxy('http://api.test');
const entry = (url: string) => Object.entries(proxy).find(([k]) => new RegExp(k).test(url))?.[1];
const proxied = (url: string) => entry(url) !== undefined;

test('/api and the earlier API paths go to the API origin', () => {
  for (const url of [
    '/api',
    '/api/feed',
    '/api/feed?stream=tender&profile=Ironji-Trade',
    '/api/shortlist',
    '/api/profiles',
    '/api/profiles/3f0c',
    '/api/opportunities/wfp-logistics',
    '/api/opportunities/wfp-logistics/state',
    '/api/opportunities/wfp-logistics/note',
    '/api/digest-settings',
    '/api/me',
    '/api/me/export',
    '/api/admin/catalogue',
    '/auth/verify',
    '/auth/request-link',
    '/auth/logout',
    '/me',
    '/me?x=1',
    '/admin',
    '/admin/',
    '/admin/sources/3',
    '/admin/source-suggestions',
    '/admin?q=1',
    '/sources/3/mute',
    '/source-suggestions',
    '/source-suggestions?x=1',
  ]) {
    expect(proxied(url), url).toBe(true);
  }
});

test('web routes, including the confirm page, /shortlist and /profiles, stay on the web server', () => {
  for (const url of [
    '/',
    '/shortlist',
    '/shortlist?x=1',
    '/profiles',
    '/profiles/3f0c',
    '/profiles/new/personal',
    '/sources',
    '/sources?x=1',
    '/auth/confirm',
    '/auth/confirm?token=a',
    '/auth/verify/x',
    '/auth',
    '/meet',
    '/me/x',
    '/me/export',
    '/feed',
    '/digest-settings',
    '/opportunities/a',
    '/apiary',
    '/administrator',
    '/o/wfp-logistics',
    '/settings/digest',
    '/account',
    '/sign-in',
    '/styleguide/components',
    '/fonts/google-figtree.css',
  ]) {
    expect(proxied(url), url).toBe(false);
  }
});

test('nothing bypasses the proxy by Accept header any more', () => {
  for (const options of Object.values(proxy)) expect(options.bypass).toBeUndefined();
});

test('every route targets BK_API_ORIGIN', () => {
  expect(new Set(Object.values(proxy).map((o) => o.target))).toEqual(new Set(['http://api.test']));
});
