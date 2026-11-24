import type { FeedItem } from '../fixtures/types';

export type SubtitleLayout = 'desktop' | 'phone';

const FIT_WORDS = { strong: 'Strong fit', good: 'Good fit', possible: 'Possible fit', 'not-scored': 'Not scored' } as const;

function lowerFirst(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}

/**
 * Row subtitles (owner decision 24):
 * - tender, funding: fit word · organisation, or fit word · top flag when the item has one;
 * - event: topic · venue on desktop, venue only on phone;
 * - investment: issuer · note on desktop, issuer only on phone (unscored);
 * - the phone uses the organisation's short name.
 */
export function rowSubtitle(item: FeedItem, layout: SubtitleLayout): string {
  const org = layout === 'phone' ? (item.organisationShort ?? item.organisation) : item.organisation;
  const parts: (string | undefined)[] = [];
  switch (item.stream) {
    case 'event':
      parts.push(layout === 'desktop' ? item.topic : undefined, item.venue ?? org);
      break;
    case 'investment':
      parts.push(org, layout === 'desktop' ? item.note : undefined);
      break;
    default:
      parts.push(item.fit ? FIT_WORDS[item.fit] : undefined, item.topFlag ? lowerFirst(item.topFlag) : org);
  }
  return parts.filter(Boolean).join(' · ');
}
