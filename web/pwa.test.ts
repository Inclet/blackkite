import { expect, test } from 'vitest';
import { NAVIGATE_FALLBACK_DENYLIST, referrerPolicyFor, workboxOptions } from './pwa';

/** Workbox's NavigationRoute tests the denylist against pathname + search. */
const denied = (url: string) => NAVIGATE_FALLBACK_DENYLIST.some((re) => re.test(url));

test('API navigations and the network-only pages never get the cached index.html', () => {
  for (const url of [
    '/api',
    '/api?x=1',
    '/api/calendar.ics?token=x',
    '/api/me/export',
    '/auth/verify',
    '/auth/request-link',
    '/auth/logout',
    '/auth/logout?next=/',
    '/me',
    '/me?x=1',
    '/auth/confirm',
    '/auth/confirm?token=abc',
    '/unsubscribe',
    '/unsubscribe?token=abc',
  ]) {
    expect(denied(url), url).toBe(true);
  }
});

test('every other route keeps the SPA fallback', () => {
  for (const url of [
    '/',
    '/shortlist',
    '/feed?stream=tender',
    '/o/wfp-logistics',
    '/calendar',
    '/settings/digest',
    '/profiles',
    '/sources',
    '/admin/sources',
    '/apiary',
    '/meetings',
    '/me/profile',
    '/auth/confirmed',
    '/unsubscribed',
    '/styleguide/foundations',
  ]) {
    expect(denied(url), url).toBe(false);
  }
});

test('the service worker has no runtime caching, so it never caches the API', () => {
  expect(workboxOptions).not.toHaveProperty('runtimeCaching');
  expect(workboxOptions.navigateFallback).toBe('index.html');
});

test('preview Referrer-Policy mirrors the edge server', () => {
  expect(referrerPolicyFor('/auth/confirm')).toBe('no-referrer');
  expect(referrerPolicyFor('/unsubscribe')).toBe('no-referrer');
  expect(referrerPolicyFor('/')).toBe('strict-origin-when-cross-origin');
  expect(referrerPolicyFor('/index.html')).toBe('strict-origin-when-cross-origin');
});
