import { expect, test } from 'vitest';
import { httpUrl } from './externalUrl';

test('http and https pass through', () => {
  expect(httpUrl('https://www.ungm.org/Public/Notice/1')).toBe('https://www.ungm.org/Public/Notice/1');
  expect(httpUrl('http://example.rw/a?b=1')).toBe('http://example.rw/a?b=1');
  expect(httpUrl('HTTPS://EXAMPLE.RW/')).toBe('https://example.rw/');
});

test('anything else is no link', () => {
  for (const u of ['javascript:alert(1)', ' javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'data:text/html,hi', 'vbscript:x', 'file:///etc/passwd', 'mailto:a@b.rw', '/relative', '//evil.test/x', 'not a url', '', null, undefined]) {
    expect(httpUrl(u), String(u)).toBeNull();
  }
});
