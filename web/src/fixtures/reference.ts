import type { FeedItem, Fixture } from './types';

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
  feed: {
    user: { name: 'Clet' },
    sources: { checked: 8, when: 'this morning' },
    digest: { channel: 'email' },
    items: referenceItems(),
  },
};

/**
 * The six items on feed-desktop.html, in board order. Row text and the WFP
 * detail pane are word for word from the boards; detail content for the other
 * five items is not on any board (listed for design review).
 */
export function referenceItems(): FeedItem[] {
  return [
    {
      id: 'wfp-logistics',
      stream: 'tender',
      title: 'Logistics, transport and warehousing support',
      organisation: 'World Food Programme',
      fit: 'strong',
      deadline: '2026-11-30', // 6 days left
      detail: {
        profile: 'Ironji-Trade',
        location: 'Kigali',
        reasons: [
          'It asks for transport, warehousing and logistics support, which you offer.',
          'It is in Rwanda, where your network of more than 1,000 trucks operates.',
        ],
        toCheck: "To check: WFP's transport call in May asked for vehicle logbooks, so this one may require an owned fleet.",
        trust: {
          state: 'unconfirmed',
          desktop:
            "Found on Job in Rwanda, posted 9 Nov. We have not matched it to a notice on WFP's own site yet, so check the date there before you act.",
          phone: "Found on Job in Rwanda, posted 9 Nov. Check the date on WFP's own site before you act.",
        },
        originalUrl: 'https://www.jobinrwanda.com/jobs/tender',
      },
    },
    {
      id: 'abh-summit',
      stream: 'event',
      title: 'ABH Summit and Grand Finale',
      organisation: "Africa's Business Heroes",
      fit: null,
      topic: 'Startups and investors',
      venue: 'Kigali Convention Centre',
      deadline: null,
      eventDates: { start: '2026-12-01', end: '2026-12-02' }, // "1 to 2 Dec", outlined (decision 23)
      detail: {
        profile: 'Personal',
        location: 'Kigali Convention Centre',
        reasons: ['It is about startups and investors, one of your event topics.'],
        trust: {
          state: 'confirmed',
          desktop: 'Dates and venue match the organiser’s own event page.',
          phone: 'Dates and venue match the organiser’s own page.',
        },
        originalUrl: 'https://africabusinessheroes.org/',
      },
    },
    {
      id: 't2s-call',
      stream: 'funding',
      title: 'Transition to Scale research and innovation call',
      organisation: 'National Council for Science and Technology',
      organisationShort: 'NCST',
      fit: 'possible',
      deadline: '2026-12-07', // 13 days left
      detail: {
        profile: 'AI lab',
        location: 'Kigali',
        reasons: ['It funds applied research and innovation, which may cover AI and data work.'],
        toCheck: 'To check: the call may be open only to research institutions.',
        trust: {
          state: 'confirmed',
          desktop: 'Matched to the call on NCST’s own site.',
          phone: 'Matched to the call on NCST’s own site.',
        },
        originalUrl: 'https://www.ncst.gov.rw/',
      },
    },
    {
      id: 'horizon-tyres',
      stream: 'tender',
      title: 'Tenders for tyres and vehicle spare parts',
      organisation: 'Horizon Logistics',
      fit: 'possible',
      deadline: '2026-12-23', // 29 days left
      detail: {
        profile: 'Ironji-Trade',
        location: 'Kigali',
        reasons: ['It is a transport buyer, but it asks for supplies rather than freight services.'],
        trust: {
          state: 'unconfirmed',
          desktop: 'Found on The New Times jobs and tenders. We have not matched it to a notice from Horizon Logistics yet.',
          phone: 'Found on The New Times jobs and tenders. Check with Horizon Logistics before you act.',
        },
        originalUrl: 'https://jobs.newtimes.co.rw/',
      },
    },
    {
      id: 'developpp-6',
      stream: 'funding',
      title: 'develoPPP Ventures, cohort 6',
      organisation: 'develoPPP',
      fit: 'good',
      topFlag: 'Needs matching funds',
      deadline: '2026-12-31', // 37 days left
      hideOnPhone: true, // decision 4
      detail: {
        profile: 'Ironji-Trade',
        location: 'Rwanda',
        reasons: ['It backs growing companies in Africa that want to scale a proven business.'],
        toCheck: 'To check: it needs matching funds from your side.',
        trust: {
          state: 'confirmed',
          desktop: 'Matched to the call on the programme’s own site.',
          phone: 'Matched to the call on the programme’s own site.',
        },
        originalUrl: 'https://www.developpp.de/',
      },
    },
    {
      id: 'tbond-5y',
      stream: 'investment',
      title: 'Five-year treasury bond',
      organisation: 'National Bank of Rwanda',
      fit: null,
      note: 'trading on the RSE',
      deadline: null,
      noDeadlineText: 'No deadline',
      detail: {
        profile: 'Personal',
        location: 'Rwanda Stock Exchange',
        reasons: [],
        trust: {
          state: 'confirmed',
          desktop: 'Listed in the bond market table on the RSE’s own site.',
          phone: 'Listed on the RSE’s own site.',
        },
        originalUrl: 'https://www.rse.rw/',
      },
    },
  ];
}
