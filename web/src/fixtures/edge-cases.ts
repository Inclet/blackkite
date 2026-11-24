import { reference } from './reference';
import type { FeedItem, Fixture } from './types';

const noDetail = (state: FeedItem['detail']['trust']['state'], copy: string, url: string): FeedItem['detail'] => ({
  reasons: [],
  trust: { state, desktop: copy, phone: copy },
  originalUrl: url,
});

/**
 * ?fixture=edge-cases: the Components board's awkward rows in the feed: a long
 * title, a missing deadline, a not-scored item and a closed item. Titles come
 * from the Components board; the rest is not on any board.
 */
export const edgeCases: Fixture = {
  name: 'edge-cases',
  styleguide: reference.styleguide,
  feed: {
    ...reference.feed,
    items: [
      {
        id: 't2s-eoi',
        stream: 'funding',
        title:
          'Transition to Scale and Uptake of Research and Innovation: call for expressions of interest from eligible applicants',
        organisation: 'National Council for Science and Technology',
        organisationShort: 'NCST',
        fit: 'possible',
        deadline: '2026-12-07',
        isNew: true,
        detail: noDetail('confirmed', 'Matched to the call on NCST’s own site.', 'https://www.ncst.gov.rw/'),
      },
      {
        id: 'horizon-tyres-undated',
        stream: 'tender',
        title: 'Tenders for tyres and vehicle spare parts',
        organisation: 'Horizon Logistics',
        fit: 'possible',
        deadline: null,
        noDeadlineText: 'No deadline stated',
        detail: noDetail('unconfirmed', 'The notice gives no closing date. Ask Horizon Logistics before you act.', 'https://jobs.newtimes.co.rw/'),
      },
      {
        id: 'developpp-unscored',
        stream: 'funding',
        title: 'develoPPP Ventures, cohort 6',
        organisation: 'develoPPP',
        fit: 'not-scored',
        deadline: '2026-12-31',
        detail: noDetail('confirmed', 'Matched to the call on the programme’s own site.', 'https://www.developpp.de/'),
      },
      {
        id: 'atl-closed',
        stream: 'tender',
        title: 'Invitation for bids',
        organisation: 'Aviation Travel and Logistics Holding',
        fit: null,
        deadline: '2026-11-23', // Closed 23 Nov
        detail: noDetail('conflict', 'Two sources give different closing dates; the original says 23 Nov.', 'https://www.umucyo.gov.rw/'),
      },
    ],
  },
};
