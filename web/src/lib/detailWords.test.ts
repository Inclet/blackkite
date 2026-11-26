import { expect, test } from 'vitest';
import { changeSentence, detailLines, fieldLabel, formatAmount, formatWhen } from './detailWords';

test('dates and times in Kigali, with the year', () => {
  expect(formatWhen('2026-11-30T17:00:00+02:00')).toBe('30 Nov 2026, 5pm');
  expect(formatWhen('2026-11-30T15:30:00Z')).toBe('30 Nov 2026, 5:30pm');
  expect(formatWhen('2026-11-29T22:00:00Z')).toBe('30 Nov 2026');
  expect(formatWhen('2026-12-07')).toBe('7 Dec 2026');
  expect(formatWhen('next week')).toBe('next week');
});

test('amounts as the digest writes them', () => {
  expect(formatAmount(120000000)).toBe('FRW 120,000,000');
  expect(formatAmount(50000, 'USD')).toBe('USD 50,000');
});

test('details: fixed order, the currency joins the amount, requirements pair with their snippets', () => {
  const lines = detailLines([
    { name: 'location', value: 'Kigali' },
    { name: 'valueCurrency', value: 'USD', snippet: 'USD' },
    { name: 'valueAmount', value: 50000, snippet: 'up to USD 50,000' },
    { name: 'deadlineAt', value: '2026-12-07T17:00:00+02:00', snippet: 'Applications close 7 December 2026 at 5pm' },
    { name: 'requirements', value: ['Tax clearance', 'Two references'], snippets: ['a valid tax clearance'] },
    { name: 'someNewField', value: 'x' },
    { name: 'eligibility', value: '' },
  ]);
  expect(lines.map((l) => l.label)).toEqual(['Deadline', 'Value', 'Location', 'Requirements', 'Some new field']);
  expect(lines[0]!.values).toEqual([{ text: '7 Dec 2026, 5pm', quotes: ['Applications close 7 December 2026 at 5pm'] }]);
  expect(lines[1]!.values[0]!.text).toBe('USD 50,000');
  expect(lines[3]!.values).toEqual([
    { text: 'Tax clearance', quotes: ['a valid tax clearance'] },
    { text: 'Two references', quotes: [] },
  ]);
  expect(fieldLabel('submission_method')).toBe('How to apply');
});

test('changes in plain words', () => {
  expect(changeSentence({ field: 'deadline_at', old: '2026-11-28T17:00:00+02:00', new: '2026-11-30T17:00:00+02:00', at: '2026-11-20T06:00:00Z' })).toBe(
    '20 Nov 2026: the deadline moved from 28 Nov 2026, 5pm to 30 Nov 2026, 5pm.',
  );
  expect(changeSentence({ field: 'deadline_at', old: null, new: '2026-12-01', at: '2026-11-20T06:00:00Z' })).toBe('20 Nov 2026: a deadline was added: 1 Dec 2026.');
  expect(changeSentence({ field: 'status', old: 'open', new: 'closing_soon', at: '2026-11-21T06:00:00Z' })).toBe('21 Nov 2026: the status changed from open to closing soon.');
  expect(changeSentence({ field: 'visibility', old: 'private', new: 'public', at: '2026-11-24T08:00:00Z' })).toBe('24 Nov 2026: an admin made it public, with the owner’s consent.');
  // As the API records it (members never see *_by keys).
  expect(changeSentence({ field: 'visibility', old: { visibility: 'private' }, new: { visibility: 'public' }, at: '2026-11-24T08:00:00Z' })).toBe('24 Nov 2026: an admin made it public, with the owner’s consent.');
  expect(changeSentence({ field: 'title', old: 'A', new: 'B', at: '2026-11-24T08:00:00Z' })).toBe('24 Nov 2026: the title changed from A to B.');
});

test('the value line: the API display when sent, else the amount with separators and currency', () => {
  const line = (fields: Parameters<typeof detailLines>[0]) => detailLines(fields).find((l) => l.name === 'valueAmount')!.values[0]!.text;
  expect(line([{ name: 'valueAmount', value: '6000000.00', display: 'FRW 6,000,000' }])).toBe('FRW 6,000,000');
  // Before the API sends display: the decimal string or a number, formatted here.
  expect(line([{ name: 'valueAmount', value: '6000000.00' }, { name: 'valueCurrency', value: 'RWF' }])).toBe('FRW 6,000,000');
  expect(line([{ name: 'valueAmount', value: 6000000 }])).toBe('FRW 6,000,000');
  expect(line([{ name: 'valueAmount', value: '1250.50' }, { name: 'valueCurrency', value: 'USD' }])).toBe('USD 1,250.50');
  expect(line([{ name: 'valueAmount', value: '2000000.00' }, { name: 'valueCurrency', value: 'KES' }])).toBe('KES 2,000,000');
  expect(line([{ name: 'valueAmount', value: '6000000.00', display: '  ' }])).toBe('FRW 6,000,000');
  expect(changeSentence({ field: 'value_amount', old: '5000000.00', new: '6000000.00', at: '2026-11-20T06:00:00Z' })).toBe('20 Nov 2026: the value changed from FRW 5,000,000 to FRW 6,000,000.');
});
