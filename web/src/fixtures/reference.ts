import type { Fixture } from './types';

/**
 * Reference content, word for word from design/reference/*.html.
 * Dates are chosen so that, at the contract's frozen time (Tuesday 24 Nov 2026,
 * Kigali), they read exactly as the boards do.
 */
export const reference: Fixture = {
  name: 'reference',
  styleguide: {
    // 32 days left, 12 days left, 6 days left, Closes tomorrow
    urgencyDeadlines: ['2026-12-26', '2026-12-06', '2026-11-30', '2026-11-25'],
    droppedItem: 'New this morning: WFP logistics roster',
    feedRows: [
      {
        stream: 'tender',
        title: 'Logistics, transport and warehousing support',
        subtitle: 'World Food Programme · matches your dry freight and cold chain',
        fit: 'strong',
        deadline: { deadline: '2026-11-30' }, // 6 days left
      },
      {
        stream: 'funding',
        title: 'Transition to Scale and Uptake of Research and Innovation: call for expressions of interest from eligible applicants',
        subtitle: 'National Council for Science and Technology · long titles cut at one line',
        fit: 'possible',
        deadline: { deadline: '2026-12-07' }, // 13 days left
      },
      {
        stream: 'investment',
        title: 'Five-year treasury bond',
        subtitle: 'National Bank of Rwanda · trading on the RSE',
        fit: 'not-scored',
        deadline: { deadline: null, emptyText: 'No deadline stated' },
      },
      {
        stream: 'tender',
        title: 'Invitation for bids',
        subtitle: 'Aviation Travel and Logistics Holding · closed items fade and lose their colour',
        fit: null,
        deadline: { deadline: '2026-11-23' }, // Closed 23 Nov
        closed: true,
      },
    ],
    fitLines: [
      { level: 'strong', reason: 'services and eligibility both match' },
      { level: 'good', reason: 'matches, with something to check' },
      { level: 'possible', reason: 'eligibility unclear' },
    ],
    flags: ['May require owned fleet', 'Needs Umucyo account', 'Needs matching funds'],
    profileTag: 'Ironji-Trade',
    fields: {
      amount: { label: 'Smallest contract worth bidding', value: 'FRW 5,000,000' },
      trucks: { label: 'Refrigerated trucks', value: 'about a hundred', error: 'Use a number, such as 100.' },
      alerts: { label: 'Urgent alerts', description: 'Email me the day a strong fit closes within 5 days.' },
    },
    states: [
      {
        kind: 'checking',
        title: 'Checking 8 sources',
        body: "Usually under a minute. Yesterday's list stays on screen meanwhile.",
      },
      {
        kind: 'nothing-new',
        title: 'Nothing new since yesterday',
        body: 'All 8 sources were checked this morning. Your shortlist has 2 items closing this month.',
        action: { label: 'Open shortlist', href: '#' },
      },
      {
        kind: 'first-visit',
        title: 'Tell Blackkite what you do',
        body: 'Three questions about your business or interests. Until then you see everything, unranked.',
        action: { label: 'Set up a profile' },
      },
      {
        kind: 'source-down',
        title: 'We could not reach BNR today',
        body: 'Bond notices may be a day behind. The other 7 sources are up to date.',
        action: { label: 'See all sources', href: '#' },
      },
    ],
  },
};
