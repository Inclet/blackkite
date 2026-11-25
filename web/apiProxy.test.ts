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
    '/api/sources',
    '/api/sources/3/mute',
    '/api/source-suggestions',
    '/api/unsubscribe',
    '/api/unsubscribe?token=a',
    '/auth/verify',
    '/auth/request-link',
    '/auth/logout',
    '/me',
    '/me?x=1',
    '/api/admin/sources',
    '/api/admin/sources/3',
    '/api/admin/sources/3/test-run',
    '/api/admin/sources/test-run',
    '/api/admin/source-suggestions?status=accepted',
    '/api/admin/users',
    '/api/admin/invites',
    '/api/admin/collector-types',
    '/api/admin/catalogue?needsReview=true',
  ]) {
    expect(proxied(url), url).toBe(true);
  }
});

test('web routes, including the confirm page, /shortlist, /profiles, /sources and the admin screens, stay on the web server', () => {
  for (const url of [
    '/',
    '/shortlist',
    '/shortlist?x=1',
    '/profiles',
    '/profiles/3f0c',
    '/profiles/new/personal',
    '/sources',
    '/sources?x=1',
    '/sources/3/mute',
    '/source-suggestions',
    '/auth/confirm',
    '/auth/confirm?token=a',
    // The unsubscribe page (decision 43); only POST /api/unsubscribe is the API.
    '/unsubscribe',
    '/unsubscribe?token=a',
    '/unsubscribe/',
    '/auth/verify/x',
    '/auth',
    '/meet',
    '/me/x',
    '/me/export',
    '/feed',
    '/digest-settings',
    '/opportunities/a',
    '/apiary',
    // The admin screens (the admin API is under /api/admin).
    '/admin',
    '/admin/',
    '/admin?q=1',
    '/admin/sources',
    '/admin/sources/new',
    '/admin/sources/3',
    '/admin/sources/3?x=1',
    '/admin/suggestions',
    '/admin/source-suggestions',
    '/admin/review',
    '/admin/users',
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
