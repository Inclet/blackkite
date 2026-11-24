import { expect, test } from 'vitest';
import { edgeCases } from '../fixtures/edge-cases';
import { reference } from '../fixtures/reference';
import { rowSubtitle } from './subtitle';

const items = reference.feed.items;

test('desktop subtitles read word for word as feed-desktop.html', () => {
  expect(items.map((i) => rowSubtitle(i, 'desktop'))).toEqual([
    'Strong fit · World Food Programme',
    'Startups and investors · Kigali Convention Centre',
    'Possible fit · National Council for Science and Technology',
    'Possible fit · Horizon Logistics',
    'Good fit · needs matching funds',
    'National Bank of Rwanda · trading on the RSE',
  ]);
});

test('phone subtitles read word for word as feed-phone.html (develoPPP omitted, decision 4)', () => {
  expect(items.filter((i) => !i.hideOnPhone).map((i) => rowSubtitle(i, 'phone'))).toEqual([
    'Strong fit · World Food Programme',
    'Kigali Convention Centre',
    'Possible fit · NCST',
    'Possible fit · Horizon Logistics',
    'National Bank of Rwanda',
  ]);
});

test('not scored and closed rows', () => {
  expect(edgeCases.feed.items.map((i) => rowSubtitle(i, 'desktop'))).toEqual([
    'Possible fit · National Council for Science and Technology',
    'Possible fit · Horizon Logistics',
    'Not scored · develoPPP',
    'Aviation Travel and Logistics Holding',
  ]);
});
