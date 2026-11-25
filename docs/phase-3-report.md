# Phase 3 report: pipeline (M1, offline part)

Date: 2026-11-25. Branch `claude/stoic-johnson-yofc7m`. Reviewer: **signed off (code)** on the second pass. One small fix round followed sign-off (past-date guard, same-day times, gzip members, PDF memory cap, owner rulings 27–28); all suites re-run on the merged head. Phase status: **open**, because the real-sources part of the exit check can't run yet.

## Exit check

| Check | Result |
|---|---|
| A scheduled run fills the catalogue from real sources | **Not done.** Blocked by: M0 not run (the owner's folder isn't served to cloud sessions), no API keys (Brave, Anthropic, Voyage), no bot contact URL (decision 31), and this container's network refuses every seed source. |
| Tests for dedupe, date validation and the three trust states | **Pass.** Plus end-to-end runs of an `html_list` source (listing, detail pages, a PDF) and a `search_query` source through the real pipeline, on synthetic pages and fake model clients. |
| All tests pass | **Pass**: api 487; ruff check and format clean; migrations 0001–0006 round trip with no drift. Web unchanged since Phase 2. |

## What was built

- **Source registry** (spec 4): admin create/edit/status/test-run/run history, suggestions queue, member sources page with health, mute, suggest. Promotion to active only after two successful runs with items since the last config change. Editing an active source's config sends it back to testing (27).
- **Untrusted config safety** (spec 10): http/https only, private and internal addresses refused (incl. disguised IPv4 forms and IPv6 that embeds IPv4), re-checked at connect time and on every redirect hop, size caps, timeouts, bounded decompression, config size limit, selectors as data only. Test runs write nothing.
- **Polite HTTP client**: honest User-Agent, robots.txt obeyed (unreachable or 429 = stay away), at least 1 s between requests to a host, one retry only on connect errors/5xx, conditional GET cache.
- **Collectors**: `html_list` and Brave `search_query`; the other five types fail cleanly as not implemented.
- **Runner and worker**: source runs recorded with found/new/failed counts, one source failing never stops others, per-source locks, stuck runs closed after 2 h, daily status refresh at 00:05 Kigali, `bk sources`, `bk run-source` (refuses retired, 28), `bk test-source`, `bk worker`.
- **Shared pipeline** (spec 5, stages 2–6): normalise, dedupe (URL, then title + organisation similarity with compatible deadlines; never across streams), enrich (detail pages and PDFs through the same guarded client; PDF text in a separate process with time and memory limits), extract (Claude with a quoted snippet for every field; unsupported fields dropped; investment no-advice guard), embeddings (Voyage `voyage-3.5`), validate (explicit years only, plausible windows, expiry, conflicting deadlines, deadline extensions, past-date changes flagged and ignored), the three trust states, change history.
- **Visibility**: members see an item only while an active or paused source carries it (25). Not yet used by any route; the first member listing arrives in Phase 4.

## Unverified

- Everything that touches a real site or a real API: the Brave response fields and rate limit are from memory; the Claude and Voyage clients have only run against fakes.
- The Docker stack (no Docker daemon here).
- Behaviour of the seed sites (M0).

## Known limits, carried forward

- Search results carry no organisation or deadline, so a repost under a different title becomes its own record.
- A public item with no source row is hidden from members; promoting a private manual item to public (spec 6) will need an exception.
- Verification recompute and dedupe candidate scoring are one query or one Python pass per item. Fine at v1 volume; revisit with real data.
- The admin review route must clear `evidence["_review"]` when it clears `needs_review` (route not built yet).
- Trust values were renamed with no data migration; there is no production data.

## To finish Phase 3

1. Run M0 from a host that can reach the sites, and fill each seed source's `access_note` and config.
2. Provide `BRAVE_API_KEY`, `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY` (secure form) and `BK_BOT_CONTACT_URL`.
3. Run the worker where the sites are reachable; promote two tender sources after two good runs each.
