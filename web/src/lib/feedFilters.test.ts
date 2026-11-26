import { expect, test } from 'vitest';
import { filterQuery, filterWord, readFilters } from './feedFilters';

test('only values the API accepts are read from the URL', () => {
  const f = readFilters(new URLSearchParams('fit=good&window=14&status=nope&verification=conflict&profile=p1&source=src-jir&fixture=x&stream=tender'));
  expect(f).toEqual({ fit: 'good', window: '14', verification: 'conflict', profile: 'p1', source: 'src-jir' });
  expect(readFilters(new URLSearchParams('fit=72&profile=../x'))).toEqual({});
});

test('a fixed order for the resource key', () => {
  expect(filterQuery({ verification: 'confirmed', fit: 'strong' })).toBe('fit=strong&verification=confirmed');
  expect(filterQuery({})).toBe('');
});

test('values in words', () => {
  const names = { profiles: { p1: 'Ironji-Trade' }, sources: {} };
  expect(filterWord('profile', 'p1', names)).toBe('Ironji-Trade');
  expect(filterWord('source', 'x', names)).toBe('A source');
  expect(filterWord('window', '7', names)).toBe('This week');
  expect(filterWord('fit', 'good', names)).toBe('Good and up');
});
