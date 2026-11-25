# Phase 4 report: make it personal (M2)

Date: 2026-11-25. Branch `claude/stoic-johnson-yofc7m`, head b34a177. Reviewer: **signed off** on the third pass (after two fix rounds). Phase status: **code complete; the real-data exit item is open**, like Phase 3's, because no real source runs yet.

## Exit check

| Check | Result |
|---|---|
| The seeded account sees a ranked feed from real data | **Not done.** No real sources (M0 not run, no keys, no network to the sites). Verified instead on `bk demo-seed` fictional data in two live runs by the reviewer: real sign-in, ranked feed with fit words and escalating deadline pills, save/dismiss/notes persisted, profile edits re-ranked by the worker, digest settings, account export/delete. |
| The digest renders correctly from it | **On demo data, yes**: `bk digest --dry-run` gives full dates, value lines, ≤ 3 investments and ≤ 3 events, the "Closing in 7 days" block for saved items, "(provisional)" labels, links to /settings/digest; a second send is refused as already sent. Real data pending. |
| Visual checks still pass on fixtures | **Pass**: all six at 0.00%. |
| All tests pass | **Pass**: api 718; web 377 unit, 148 e2e, typecheck, build; contract test against the API's own schemas. |

## Pixel-diff table (head b34a177)

| Page | Viewport | Diff % | Built layout shift |
|---|---|---|---|
| foundations | 1440x1000 | 0.00 | 0 |
| components | 1440x1000 | 0.00 | 0 |
| feed-desktop | 1440x900 | 0.00 | 0 |
| feed-phone | 390x844 | 0.00 | 0 |
| opportunity-phone | 390x844 | 0.00 | 0 |
| digest-email | 640x1000 | 0.00 | 0 |

## What was built

- **Scoring** (spec 7): hard filters (outside Rwanda, deadline passed, stream not selected, muted sources only, explicit ineligibility, Ironji's FRW 5M minimum when stated); a cheap shortlist (tags + embeddings, no model); one Claude judgement per shortlisted tender/funding pair whose reason must quote the notice; the spec weights; the 7.1 consequences as flags with quotes (Umucyo registration, owned fleet — kept and flagged when the partner network covers the number, transport licence, value unknown, check capacity); AI lab provisional; investments and events ranked on time, verification and source kind without the model; fit words per decision 32; cost guard (call cap, reuse keyed on the profile's data).
- **Member API** under `/api`: feed (closing soonest first), opportunity detail (fields with snippets, visible sources, document names, change history, note), state and note, shortlist, profiles, digest settings, name, export, delete; admin catalogue with review. Isolation tested: no access to other users' private items or to testing-only items.
- **Re-scoring in the worker**: after each source run, after profile edits and mutes (debounced), on reactivation; backoff and a per-tick cap.
- **Digest and urgent alert** (spec 8): weekly on Monday 07:00 Kigali, capped and deduplicated week to week; alerts by fit word (decision 34), once per item; HTML + plain text with the inline logo; console/Mailpit only.
- **Web**: live data on the feed and opportunity screens with optimistic updates; sign-in; Shortlist; Profiles list and editor; Digest settings; Account; dismiss reasons; saved state visible; Provisional tag. All undesigned pieces are in docs/design-review.md.
- **`bk demo-seed`**: ten fictional items for local development only.

## Unverified

- Anything with real data, real model calls (Claude, Voyage) or real email clients.
- The Docker stack and Mailpit delivery (no Docker daemon here).
- Production reverse proxy: must forward exactly `/api/*`, `/auth/verify`, `/auth/request-link`, `/auth/logout`, `/me` and `/admin/*` to the API, and nothing else.

## Known limits (non-blocking, recorded)

- `bk score`/`bk backfill` leave a profile's future backoff retry queued; the worker repeats one backfill (harmless).
- For at most one worker tick after an unmute, an item that would fail the eligibility or minimum-value filter shows as unscored (no fit word, so it can't alert).
- Events and investments never trigger alerts (no fit word) — owner decision pending.
- The FilterChip action variant isn't on the styleguide (it would change the components board).

## Decisions waiting for the owner

See the end of this phase's chat report; recorded as they're answered in docs/decisions.md.

## Stop

Per the kickoff, work stops after Phase 4. Sources UI (M3), admin screens and the remaining streams come after the owner's review.
