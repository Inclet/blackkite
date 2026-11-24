import { afterEach, beforeEach, expect, test } from 'vitest';
import { edgeCases } from '../fixtures/edge-cases';
import { reference } from '../fixtures/reference';
import { detailMeta, feedSummary, greeting, nextDigest, sortClosingSoonest } from './feed';
import { setNowForTests } from './now';

beforeEach(() => setNowForTests('2026-11-24T14:00:00+02:00'));
afterEach(() => setNowForTests(null));

const items = reference.feed.items;

test('closing soonest first keeps the board order', () => {
  expect(sortClosingSoonest([...items].reverse()).map((i) => i.id)).toEqual(items.map((i) => i.id));
});

test('closed items go last', () => {
  const sorted = sortClosingSoonest(edgeCases.feed.items);
  expect(sorted.at(-1)!.id).toBe('atl-closed');
  expect(sorted.at(-2)!.id).toBe('horizon-tyres-undated');
});

test('the greeting line reads as the boards', () => {
  expect(greeting('Clet')).toBe('Good afternoon, Clet');
  expect(feedSummary(items)).toBe('Six things worth a look. One closes in 6 days.');
  expect(feedSummary(items.slice(1))).toBe('Five things worth a look.');
  expect(feedSummary([])).toBe('Nothing to look at right now.');
  setNowForTests('2026-11-24T08:00:00+02:00');
  expect(greeting('Clet')).toBe('Good morning, Clet');
});

test('next digest is the coming Monday', () => {
  expect(nextDigest('email')).toBe('Monday 30 November, by email');
  setNowForTests('2026-11-30T09:00:00+02:00');
  expect(nextDigest('email')).toBe('Monday 7 December, by email');
});

test('detail meta line', () => {
  expect(detailMeta(items[0]!)).toBe('World Food Programme · Kigali · closes 30 Nov');
});
