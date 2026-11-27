# Blackkite

Rwanda opportunity platform. Named after the black kite, the bird that circles over Kigali scanning from above.

Spec for a multi-user platform that finds, ranks and tracks opportunities in Rwanda, with a managed registry of information sources. Written to be handed to Claude Code. Draft 7, 2026-11-24.

Changes from draft 1: multi-user from the start (sections 1, 5, 6, 7, 8); sources are data managed in the system, visible to users and extendable without redeploying (section 4).

## 1. Purpose

Surface opportunities in Rwanda that are relevant to each user before their deadlines pass, in four streams:

| Stream | What counts |
|---|---|
| `tender` | Public, UN/NGO and corporate tenders, EOIs, RFPs, supplier pre-qualification rounds |
| `investment` | Treasury bond/bill issuances, RSE listings and new products, corporate bonds, announced deals open to retail investors |
| `funding` | Grants, non-dilutive funding, accelerators, competitions |
| `event` | Conferences, summits, networking and industry events in Kigali/Rwanda |

The platform has two halves:

- **Shared**: sources, collection, the opportunity catalogue. Collected and extracted once, for everyone.
- **Per user**: profiles, scores, saved/dismissed state, notes, digests. Private to each user.

Success test for v1: for the first user, a weekly digest where at least half the top 10 items are ones they would act on or want to have known about, and no relevant item is first seen after its deadline. Then the same test for a second user with a different profile, without code changes.

### Decisions (confirmed by the owner, 2026-11-24)

- Accounts are individuals, invite-only at first. No shared company workspaces in v1.
- Sources are added by admins only. Any member can see the source list and suggest a source.
- Free for now. No billing in v1.
- First user's digest goes by email.
- Hosting: a VPS.
- AI lab tenders are scored in v1, alongside Ironji and personal.

Still an assumption: one user can hold several profiles (for example a trucking company, an AI consultancy, personal investing), and opportunities are scored against each.

### Non-goals (v1)

- No automatic bidding, applying, registering or buying. The tool informs; the user acts.
- No investment advice or buy/sell signals. The `investment` stream reports facts (issuer, tenor, coupon, dates, minimums, where the prospectus is).
- No career/jobs stream.
- No billing, public sign-up, or team/organisation accounts with shared workspaces. The schema should not block these later.

## 2. What the sample run showed (2026-11-24)

A manual run across the four streams found usable items in every stream, and exposed these constraints. Design around them.

1. **The best tender sources resist plain HTTP fetching.** The New Times jobs/tenders portal returned client errors, Job in Rwanda and Umucyo did not serve robots.txt to the fetcher, and the BNR site is a JavaScript app with no content in the raw HTML. These were tested from a cloud environment only; re-test each from the real host before choosing a collection method.
2. **Search-engine results still expose these sites' listings** (title, organisation, published date, deadline), so a search-API collector is a workable fallback.
3. **Aggregators are unreliable as a record.** Their listing pages run notices together so it is unclear which deadline belongs to which tender, and they paywall the documents. Treat them as discovery only; take dates from the original notice.
4. **Listing titles are often uninformative** ("Invitation for Bids", "Tenders for various items"). Relevance cannot be judged without the detail page or the PDF.
5. **Undated and stale pages are common in events.** A Norrsken "25 November" event page with no year was from an earlier year. Every date needs a year and a sanity check.
6. **Official data is rich where it is reachable.** Umucyo publishes procurement plans (tenders before they are advertised) and awarded contracts with every bidder's price. BNR publishes prospectuses and auction results as PDFs.
7. **Things were already missed.** Africa Fintech Summit Kigali ran 18-20 Nov; several tenders closed 23-24 Nov. Lead time is the product.

## 3. Roles

| Role | Can do |
|---|---|
| `member` | Manage own profiles and digest settings; browse the catalogue; save, dismiss, annotate; add private manual items; view the source list; mute sources for themselves; suggest a source |
| `admin` | Everything a member can, plus: add, test, edit, pause and retire sources; review source suggestions; review items flagged `needs_review`; invite and deactivate users |

The first user is an admin. Role checks are enforced on the server, not only in the UI.

## 4. Source registry

Sources are rows in the database, not code constants. This is what lets the platform grow: most new sources are added through the admin screen with no deploy.

### 4.1 Source record

- `name`, `home_url`, `publisher` (the organisation behind it)
- `streams` it feeds (one or more)
- `kind`: `original` (the issuer itself, e.g. Umucyo, BNR), `publisher` (a portal that carries notices, e.g. a jobs/tenders board), `aggregator`, `news`, `community`
- `collector_type` and `config` (see 4.2)
- `schedule` (how often to run), `rate_limit`
- `access_note` (robots/terms position, login needed, what was tested and when)
- `status`: `suggested` -> `testing` -> `active` -> `paused` / `retired`
- `added_by`, `created_at`, `updated_at`

### 4.2 Collector types

A collector type is code; a source is a configuration of one. Adding a source of an existing type needs no code.

| Type | Config | Use for |
|---|---|---|
| `rss` | feed URL | News sections, blogs, any site with a feed |
| `html_list` | list URL, pagination pattern, selectors for item/title/date/link, optional detail-page selectors | Server-rendered listing pages |
| `browser_list` | same as `html_list`, rendered with a headless browser | JavaScript apps |
| `json_api` | endpoint, params, field mapping | Sites whose front end calls a JSON API |
| `search_query` | list of queries, domain restriction, recency window | Sites that cannot be fetched directly |
| `email_ingest` | sender address/pattern for a shared inbox | Newsletters and alert emails |
| `custom` | name of a Python collector class | Anything that does not fit the above |

Every collector implements the same interface: `fetch(source) -> list[RawItem]`. One failing must not stop the run.

### 4.3 Adding a source (admin flow)

1. Fill in the source record and choose a collector type.
2. **Test run**: the system fetches once and shows the first items it parsed, with nothing written to the catalogue. Fix the config until the preview is right.
3. Save as `testing`. It runs on schedule; its items are stored but hidden from members.
4. After it has produced sane items across at least two runs, promote to `active`.

Members can **suggest a source** (URL, what it covers, why it is useful). Suggestions land in an admin queue as `suggested`.

### 4.4 What users see

- **Sources page**: every active source with publisher, kind, streams, last successful run, items found in the last 30 days, and health (ok / degraded / failing). Members can mute a source for themselves.
- **On every opportunity**: all sources that carried it, which one is the original, when each first and last saw it, and a link out. Aggregator-only items are labelled as such.
- **Admin source screen**: run history, error log, config editor, test run, pause/retire.

### 4.5 Seed sources

Load these as rows with status `testing`. Promote each only after the access test in milestone M0.

| Source | Kind | Streams | Likely collector | Access notes from the sample run |
|---|---|---|---|---|
| Umucyo e-procurement (umucyo.gov.rw) | original | tender | `html_list` or `browser_list` | Tender notices, procurement plans, awarded contracts with bidder prices. Fetch blocked from cloud; test from host. Low request rate. |
| Job in Rwanda, tenders (jobinrwanda.com/jobs/tender) | publisher | tender | `html_list`, else `email_ingest` / `search_query` | Same access caveat. Check for email alerts first. |
| The New Times jobs & tenders (jobs.newtimes.co.rw) | publisher | tender | `html_list`, else `search_query` | Same access caveat. |
| UNGM (ungm.org) | original | tender | `html_list` or `json_api` | Public notice pages with stable IDs; filter by beneficiary country. |
| BNR (bnr.rw) | original | investment | `browser_list` or `json_api` | JS front end; documents are PDFs. |
| RSE (rse.rw) | original | investment | `html_list` | Bond market table was reachable. |
| The New Times, KT Press business sections | news | funding, investment, event | `rss`, else `search_query` | |
| Eventbrite Kigali, 10times Kigali | publisher | event | `html_list` | JSON-LD event data on listing pages. |

Candidates for later: CMA Rwanda, RDB, NCST calls, Impact Hub Kigali, Norrsken House Kigali, VC4A (Rwanda), Opportunities for Africans (Rwanda tag), World Bank and AfDB procurement notices for Rwanda, district websites.

Not sourceable: WhatsApp groups, notice boards, word-of-mouth deals, private land offers. Covered by private manual items (section 6).

## 5. Pipeline

```
shared:    collect -> normalise -> dedupe -> enrich -> extract -> validate -> catalogue
per user:  match -> score -> deliver
```

**Shared stages** (run once per item, cost independent of user count)

1. **Collect.** Scheduler runs each `active` and `testing` source per its schedule; writes a `source_run` row.
2. **Normalise.** Canonical URL, cleaned title, raw text, source, fetch time.
3. **Dedupe.** The same tender appears on several sites. Key on normalised (organisation, title) similarity plus overlapping deadline; keep every source on one record and mark the original.
4. **Enrich.** Follow to the detail page; download attached PDFs; extract text.
5. **Extract.** LLM turns text into the structured record in section 6. Structured output only; every extracted field carries its supporting snippet. Absent fields stay null. Also produce a set of tags (sector, service type, required capabilities) and an embedding for matching.
6. **Validate.** Dates must parse with an explicit year and lie in a plausible window. Deadline passed -> `expired`. Conflicting deadlines across sources -> keep the original's, else the earliest, and set `needs_review`. No original source -> `aggregator_only`.

**Per-user stages**

7. **Match.** Cheap shortlist per profile: hard filters, tag overlap, embedding similarity. No LLM call. This keeps cost from growing as users x opportunities.
8. **Score.** Rules plus one LLM judgement, only for shortlisted (profile, opportunity) pairs. See section 7.
9. **Deliver.** Per-user digest and alerts; dashboard reads the same data.

A new user or an edited profile triggers a backfill of match and score over currently open opportunities.

## 6. Data model

All per-user tables carry `user_id` and are filtered by it in every query.

**Identity**
- `user` (id, email, name, role, status, created_at)
- `invite` (email, invited_by, token, expires_at, accepted_at)
- `profile` (id, user_id, name, type: business | personal, data json, version, active): a user has one or more
- `digest_setting` (user_id, channel, address, frequency, day, alert_threshold, streams)

**Sources**
- `source` (see 4.1)
- `source_run` (source_id, started_at, finished_at, status, items_found, items_new, error)
- `source_suggestion` (user_id, url, note, status, reviewed_by)
- `user_source_mute` (user_id, source_id)

**Catalogue (shared)**
- `opportunity`: `id`, `stream`, `subtype`, `title`, `organisation`, `summary` (2 sentences, own words), `published_at`, `deadline_at`, `event_start`, `event_end`, `value_amount`, `value_currency`, `value_note`, `location`, `eligibility`, `requirements` (list), `submission_method`, `fees`, `tags`, `embedding`, `status` (open | closing_soon | expired | awarded | cancelled), `verification` (verified_original | aggregator_only | unverified), `needs_review`, `visibility` (public | private), `owner_user_id` (set for private manual items), timestamps
- `opportunity_source` (opportunity_id, source_id, url, is_original, first_seen, last_seen)
- `document` (opportunity_id, url, file path, extracted text)
- `change_event` (opportunity_id, field, old, new, at)
- `award` (tender ref, entity, bidders, prices, winner, period): from Umucyo awarded lists, for price benchmarking

**Per user**
- `user_opportunity` (user_id, opportunity_id, profile_id, score, score_breakdown json, score_reason, state: unseen | saved | dismissed | acting | done, dismiss_reason, note, updated_at)
- `digest_log` (user_id, sent_at, opportunity_ids)

Manual items a user adds are `visibility = private` and never appear to anyone else. An admin can promote one to public only with the owner's consent.

## 7. Scoring

Rules first, LLM second, so results stay explainable and cost stays bounded.

**Profile** (edited in the app; one or more per user):
- Business profile: services offered, capacity (for example fleet size and tonnage), locations, registrations and certificates held, minimum contract size worth pursuing, sectors
- Personal profile: instruments of interest, ticket range, horizon; event topics, availability, budget
- Exclusions: organisations, sectors, keywords
- Streams the profile cares about

**Hard filters**: outside Rwanda, deadline passed, stream not selected, muted source only, explicit eligibility the profile cannot meet (NGO-only calls, capacity thresholds above what the profile states).

**Score components** (0-100, weights configurable globally, later per user):
- Fit to the profile's services/interests (40)
- Eligibility confidence (20)
- Value relative to profile thresholds (15)
- Time left to act: penalise too little preparation time and unknown deadlines (15)
- Source kind and verification (10)

The LLM assigns fit and eligibility confidence with a one-sentence reason that quotes the requirement behind it. `saved` / `dismissed` actions are logged as labelled data for tuning later; no learning loop in v1.

**Missing profile data never hard-filters.** If a profile field is null, the matching requirement lowers eligibility confidence and adds a flag on the item (for example "check capacity", "needs Umucyo supplier registration") instead of dropping it.

### 7.1 Seed profiles for the first user (owner's answers, 2026-11-24)

Load these when the first admin account is created. `null` means not yet provided.

```yaml
profiles:
  - name: Ironji-Trade
    type: business
    streams: [tender, funding, event]
    location: Kigali, Rwanda
    services: [dry freight, cold chain, last-mile distribution]
    registrations_held:
      - RDB company registration
      - RRA tax clearance
      - RSSB clearance
    registrations_not_held:
      - Umucyo supplier account      # planned; owner will create it later
      - transport operator licence   # owner's position: not needed for Ironji's model
    capacity:
      model: partner network         # trucks are a network, not an owned fleet
      trucks_in_network: 1000        # "more than 1,000"
      refrigerated_in_network: 100   # "around 100"
      owned_trucks: null
      tonnage: null
    min_contract_rwf: 5000000

  - name: AI lab
    type: business
    streams: [tender, funding, event]
    services: [software development, AI/ML, data, digital consulting]   # default set, confirmed as provisional
    provisional: true
    registrations_held: null
    min_contract_rwf: null

  - name: Personal
    type: personal
    streams: [investment, event]
    instruments:
      - treasury bonds and bills
      - RSE shares
      - corporate bonds
      - real estate and land
      - private deals and startups
    ticket_range_rwf: null           # owner chose not to filter by size
    event_topics:
      - AI and tech
      - logistics and trade
      - startups and investors
      - finance and fintech
      - agriculture and food
      - general networking

digest:
  channel: email
  frequency: weekly
```

Consequences for scoring:

- Every investment instrument and every event topic is selected, so profile fit will barely separate items in those two streams. Until dismiss reasons accumulate, rank them mainly on time left, verification and source kind, and cap each at a few items per digest.
- Ironji tenders under FRW 5M are filtered out when the value is stated; when no value is stated, keep the item and flag "value unknown".
- Tenders published on Umucyo need a supplier account to bid. Show them with a "needs Umucyo supplier registration" flag until the profile lists an account.
- Ironji's capacity is a partner network, not an owned fleet. Volume requirements are met; ownership requirements may not be. When a tender asks for proof of owned vehicles (logbooks, registration cards in the bidder's name) or a transport operator licence, keep the item and flag "requires owned fleet" or "requires transport licence" with the quoted requirement, so the owner can judge whether subcontracting or a joint bid is allowed.
- AI lab matches use the default service set and are labelled provisional until the owner replaces it.

## 8. Delivery

**Digest (per user).**
- Weekly: top items across the user's profiles, capped at about 12, each with title, organisation, deadline, value, one-line reason, which profile it matched, and the source it came from with a link to the original. A "closing in 7 days" block for saved items.
- Urgent alert: an item above the user's threshold with a deadline under 5 days, sent the day it is found.
- Channel per user: email first; Telegram as a second channel.

**App.**
- Feed with filters: stream, profile, status, deadline window, score, source, verification.
- Opportunity page: extracted fields with supporting snippets, all sources, documents, change history, the user's notes.
- Actions: save, dismiss (with reason), mark acting/done, add private manual item.
- Calendar of deadlines and events.
- Profiles and digest settings.
- Sources page (4.4) and suggest-a-source form.
- Benchmarks: awarded tender prices by category.
- Admin: source management, suggestion queue, review queue, users and invites.

## 9. Stack

- Python pipeline and API (collectors, extraction, scoring, scheduler)
- PostgreSQL with pgvector for embeddings
- TypeScript web app (PWA)
- Authentication: email magic link or OAuth sign-in; no passwords stored by the app. Sessions server-side.
- Docker Compose on a single VPS to start
- Claude API for extraction and scoring, model names in config; a smaller model for extraction and scoring, a larger one only for digest write-ups
- Playwright only for `browser_list` sources

## 10. Guardrails

- Respect robots.txt and site terms. Where a site disallows automated access, use its alerts via `email_ingest` or the `search_query` type. Record the position in the source's `access_note`.
- Show other people's content as a short summary in our own words plus a link to the original. Do not republish full notices or documents to users; keep stored documents for extraction and the owner's reference only. Showing third-party content to many users raises terms-of-use questions a single-user tool does not; check each source's terms before promoting it to `active`.
- Identify the client honestly, rate-limit, cache, never retry aggressively.
- Never present an aggregator-only item as confirmed.
- Store the supporting snippet for every extracted deadline and amount.
- Investment items are factual listings with a link to the prospectus. No recommendations in generated text. If the platform later opens to the public, get advice on whether presenting investment listings to users is a regulated activity.
- Privacy: profiles, scores, states, notes and private items are visible only to their owner. Admins manage sources and users, not other users' profiles. Collect the minimum personal data; allow account export and deletion.
- Admin-entered source config (URLs, selectors) is untrusted input: validate URLs, block internal network addresses, sandbox the test run.
- Secrets in environment variables; nothing committed.

## 11. Milestones

1. **M0, access test (half a day).** From the real host, test each seed source: plain fetch, headless fetch, RSS, email alerts. Record results in each source's `access_note`.
2. **M1, foundations.** Full multi-user schema, auth, roles, invites. Source registry with `source_run`, two collector types (`html_list`, `search_query`), two working tender sources. Shared pipeline through validation. CLI and a bare catalogue page.
3. **M2, profiles + scoring + digest.** Profile editor, match and score, weekly digest and urgent alert for the first user.
4. **M3, source management UI.** Sources page, admin add/test/pause flow, remaining collector types, suggestions queue. Add investment, funding and event sources through the UI as the test of the design.
5. **M4, app.** Feed, opportunity page, actions, calendar, private manual items.
6. **M5, second user.** Invite a user with a different profile; fix whatever breaks. Benchmarks and procurement plans.

Review after M2: if the digest fails the success test in section 1, fix sources and scoring before building more.

## 12. Design

The interface is designed. Direction: v1 "Calm" (neutral base, one colour per stream, Figtree). Everything needed to build it is in `design/`:

- `design/tokens.css`: colour, type, space, shape, focus and motion tokens
- `design/assets/`: the kite mark (full and small) and exact icon path data
- `design/reference/*.html`: the six approved boards as plain HTML. These are the source of truth for layout and exact values.

| Reference | Viewport | What it is |
|---|---|---|
| `foundations.html` | 1440 x 1000 | Logo, signature motion, colour, type, space, motion, voice |
| `components.html` | 1440 x 1000 | Buttons, filters, tags, fields, feed rows, fit, flags, states |
| `feed-desktop.html` | 1440 x 900 | Feed with detail pane |
| `feed-phone.html` | 390 x 844 | Feed on a phone |
| `opportunity-phone.html` | 390 x 844 | Opportunity detail on a phone |
| `digest-email.html` | 640 x 1000 | Weekly digest email |

Rules that follow from the design:

- The list shows a fit word (Strong, Good, Possible) with a reason, never a bare score. The numeric score stays internal.
- Every opportunity shows one of three trust states: confirmed at the source, not yet confirmed, sources disagree. These map to `verification` in section 6.
- Deadlines escalate by weight: over 14 days quiet, 14 or fewer outlined, 7 or fewer solid graphite, last day alert red.
- Loading uses the circling kite, not a spinner. New items drop in once.
- The digest email uses system fonts and full dates.
- Not yet designed: Sources, Profiles, Shortlist, Calendar, admin screens, and full evening mode. Build these from existing components only and mark them for design review.

## 13. Open decisions (owner)

1. AI lab profile: real services, registrations, minimum contract size (default set in use until then).
2. Ironji: tonnage range, and whether any trucks are owned.
3. Domain and public-facing spelling of the name (see the naming note below).

Naming note: "Black Kite" is already the name of a US cyber-risk software company, plus a few smaller firms. Fine for a free, invite-only tool. Before any public launch, pick a distinct domain and get the name checked for trademark conflicts.

Revisit if the platform opens to public sign-up or becomes paid: terms-of-use checks on sources and the investment-listing question in section 10.

@OCTANT.md
