import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, test } from 'vitest';
import { referenceItems } from '../../fixtures/reference';
import type { FeedItem } from '../../fixtures/types';
import { setNowForTests } from '../../lib/now';
import { DETAIL_COPY, DetailTop, showsProfile } from './parts';

beforeEach(() => setNowForTests('2026-11-24T14:00:00+02:00'));
afterEach(() => setNowForTests(null));

const item = (id: string, patch: Partial<FeedItem> = {}): FeedItem => ({ ...referenceItems().find((i) => i.id === id)!, ...patch });

function tags(i: FeedItem) {
  const { unmount } = render(<DetailTop item={i} tagGap={8} />);
  const out = {
    profile: screen.queryByText(i.detail.profile ?? '\u0000') !== null,
    provisional: screen.queryByText(DETAIL_COPY.provisional) !== null,
  };
  unmount();
  return out;
}

test('a scored tender or funding item shows its profile, and Provisional when the profile is', () => {
  expect(tags(item('wfp-logistics'))).toEqual({ profile: true, provisional: false });
  expect(tags(item('t2s-call', { provisional: true }))).toEqual({ profile: true, provisional: true });
});

test.each([null, 'not-scored'] as const)('tender or funding with fit %s: no profile tag, no Provisional (no match was made)', (fit) => {
  expect(tags(item('wfp-logistics', { fit }))).toEqual({ profile: false, provisional: false });
  expect(tags(item('t2s-call', { fit, provisional: true }))).toEqual({ profile: false, provisional: false });
});

test('events and investments (fit null by design) keep the profile the API sends', () => {
  expect(tags(item('abh-summit'))).toEqual({ profile: true, provisional: false });
  expect(tags(item('tbond-5y'))).toEqual({ profile: true, provisional: false });
  expect(tags(item('abh-summit', { provisional: true }))).toEqual({ profile: true, provisional: true });
});

test('no profile from the API: no tag either way', () => {
  const i = item('abh-summit');
  expect(showsProfile({ ...i, detail: { ...i.detail, profile: undefined } } as FeedItem)).toBe(false);
});
