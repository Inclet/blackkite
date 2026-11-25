import { expect, test } from 'vitest';
import { fieldSnippets, fieldValueText } from './detail';

test('field values: text, numbers and lists (requirements) all read as one line', () => {
  expect(fieldValueText('Kigali')).toBe('Kigali');
  expect(fieldValueText(5000000)).toBe('5000000');
  expect(fieldValueText(['Tax clearance', 'Owned fleet'])).toBe('Tax clearance; Owned fleet');
});

test('snippets: a list (requirements) or a single snippet, or none', () => {
  expect(fieldSnippets({ name: 'requirements', value: ['a', 'b'], snippets: ['s1', 's2'] })).toEqual(['s1', 's2']);
  expect(fieldSnippets({ name: 'deadlineAt', value: '2026-11-30', snippet: 'Closing 30 November 2026' })).toEqual(['Closing 30 November 2026']);
  expect(fieldSnippets({ name: 'location', value: 'Kigali' })).toEqual([]);
});
