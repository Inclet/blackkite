import { afterEach, expect, test } from 'vitest';
import { now, setNowForTests } from './now';

afterEach(() => setNowForTests(null));

test('now() can be frozen and unfrozen', () => {
  setNowForTests('2026-11-24T14:00:00+02:00');
  expect(now().toISOString()).toBe('2026-11-24T12:00:00.000Z');
  setNowForTests(null);
  expect(Math.abs(now().getTime() - Date.now())).toBeLessThan(1000);
});
