import { expect, test } from 'vitest';
import { apiProxy } from './apiProxy';

const proxied = (url: string) => Object.keys(apiProxy('http://api.test')).some((k) => new RegExp(k).test(url));

test('the exact API paths go to the API origin', () => {
  for (const url of ['/auth/verify', '/auth/request-link', '/auth/logout', '/me', '/me?x=1', '/admin', '/admin/', '/admin/sources/3', '/admin?q=1']) {
    expect(proxied(url), url).toBe(true);
  }
});

test('web routes, including the confirm page, stay on the web server', () => {
  for (const url of ['/', '/auth/confirm', '/auth/confirm?token=a', '/auth/verify/x', '/auth', '/meet', '/me/x', '/administrator', '/o/wfp-logistics', '/styleguide/components', '/fonts/google-figtree.css']) {
    expect(proxied(url), url).toBe(false);
  }
});

test('every route targets BK_API_ORIGIN', () => {
  expect(new Set(Object.values(apiProxy('http://api.test')).map((o) => o.target))).toEqual(new Set(['http://api.test']));
});
