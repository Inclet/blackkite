# Owner decisions

Answers to the Phase 0 questions, 2026-11-24. Conflict numbers refer to `PLAN.md` section 7.

| # | Topic | Decision |
|---|---|---|
| 1 | Event deadline pill (C1) | Follow the boards. Events get their own urgency rule counted from `event_start`. **Exact rule still to be stated by the owner.** |
| 2 | Tap targets under 44 px (C2) | Extend the hit area with an invisible layer; visible pixels match the boards. |
| 3 | Fonts in visual tests | Vendor the exact Figtree woff2 bytes Google serves, check hashes, route reference font requests to them; tests run offline. |
| 4 | Phone feed rows / Events chip (C6) | Match the board: 5 rows, develoPPP omitted on purpose. Events chip added at the end of the scroll row, off-screen. |
| 5 | Row subtitles (C7, C8) | Short-name field per organisation plus a per-stream subtitle template (long on desktop, short on phone). **Template wording still to be confirmed by the owner.** |
| 6 | Layout switch (C10) | Phone layout below 792 px. Widths 792–1024 listed for design review. |
| 7 | Digest email build (C5) | Email-safe tables tuned to match the board in Chromium; logo as PNG. |
| 8 | Bold in email (C4) | Keep 700 in the email as on the board; logged as an exception to the 600 rule. |
| 9 | Motion (C3) | The board's motion appears only on `/styleguide/foundations`. The app uses token durations and easing; new items drop once. |
| 10 | M0 host | Run from the owner's computer, attached to the session through Remote Control. |
| 11 | Search API | Brave Search. Key requested when Phase 3 starts. |
| 12 | Embeddings | **Voyage AI** (owner's choice over the local model). Needs `VOYAGE_API_KEY`; item text is sent to Voyage. |
| 13 | Production email | Pluggable transport now; provider chosen before Phase 4. Dev mail goes to Mailpit only. |
| 14 | Models | `claude-haiku-5-5` for extraction and scoring; **`claude-opus-5-5` for digest write-ups**. Names in config. |
| 15 | First admin | The owner's Claude account email. Kept out of the repo: the seed reads `BK_FIRST_ADMIN_EMAIL` from the environment. |
| 16 | Layout shift in the visual harness | Only the built page must have zero layout shift. The reference pages shift slightly when Google's Figtree swaps in (font-display: swap); that value is reported, not judged. Threshold, viewports and pass mark unchanged. |
| 17 | Sign-in confirm page | Yes. The emailed link opens a "Continue to sign in" page; only its POST spends the token and sets the session. Built from existing components; listed for design review. |
| 18 | Digest schedule | Weekly on Monday by default, or off. No other frequencies or weekdays in v1. |
| 19 | Save/dismiss scope | State applies across all of a user's profiles, per (user, opportunity). Scores stay per profile. |
| 20 | Admins deactivating admins | Allowed. An admin still cannot deactivate themselves. |
| 21 | Status values | users: active / deactivated; source runs: running / succeeded / failed; source suggestions: suggested / accepted / rejected. |
| 22 | Contract comment | Comment in contract.ts and the report header updated to match ruling 16. Text only (b57650a). |
| 23 | Event date pills (resolves 1) | Counted from `event_start`: over 14 days quiet; 7–14 outlined; 6 or fewer solid; the day before or the day of, alert red. |
| 24 | Row subtitles (resolves 5) | Tender and funding: fit word · organisation, or fit word · top flag when there is one. Event: topic · venue on desktop, venue on phone. Investment: issuer · note on desktop, issuer on phone. Phone uses the short organisation name. |
| 25 | Retired sources | Their items are hidden from members unless an active or paused source also carries them. |
| 26 | Deadline conflict window | Sources' deadlines up to 14 days apart are one notice ("sources disagree"); further apart, separate notices. |
| 27 | Editing an active source | Changing collector type or config sends it back to testing; two good runs needed again. Other fields don't change status. |
| 28 | `bk run-source` on retired | Refused; move the source back to testing first. |
| 29 | Items with no original source | `aggregator_only` only when every carrying source is an aggregator; publisher/news-only items are `unverified`. Both display as "Not yet confirmed at the source". (Refines spec 5.6.) |
| 30 | Voyage model | `voyage-3.5`, 1024 dimensions. |
| 31 | Bot contact URL | Owner will provide it later; required before any real collection. Until then the worker logs a warning. |
| 32 | Fit word rule (confirmed by the owner 2026-11-25) | Strong: fit ≥ 0.7 and eligibility ≥ 0.7, flags allowed. Good: fit ≥ 0.6 and eligibility ≥ 0.5. Possible: fit ≥ 0.4. Otherwise no word. Thresholds in config (`BK_SCORE_FIT_WORD`). Matches the boards (WFP is Strong with a "To check" note). |
| 33 | Row subtitle top flag (orchestrator) | The top flag replaces the organisation only on Good items (develoPPP on the boards); Strong items show the organisation. Refines 24. |
| 34 | Urgent alert level (confirmed by the owner 2026-11-25) | Chosen as a fit word ("Strong fits only" / "Strong and good fits"), compared against the best active profile's fit word, never the numeric score. Replaces spec 6 `alert_threshold` with `alert_min_fit`. Default: off until the owner chooses. Events and investments carry no fit word, so they never alert (confirmed, decision 40). |
| 35 | Feed order | Closing soonest first, score as tie-break (feed boards: "Closing soonest first"). Ranking by score applies to the digest. |
| 36 | Re-scoring off the request path | Profile edits and mutes queue a backfill for the worker (debounced 60 s; an unmute is due on the next tick). Renames and pauses re-judge nothing; reactivating always catches up. Failed backfills back off (1, 5, 15, 60 min, then hourly) and stop after 6 attempts until the next edit; at most 5 profiles per worker tick, after collection. |
| 37 | NGO-only calls | A business profile with no organisation type is treated as not an NGO, so an explicit NGO-only call is filtered. |
| 38 | Dismiss reasons | Optional, one of: not my sector, too small, can't meet the requirements, already knew about it, other. |
| 39 | Member API paths | Phase 4 member routes and member source routes live under `/api`; `/auth/*`, `GET /me` and `/admin/sources*` stay. |
| 40 | Alerts for events and investments | None; they appear in the weekly digest only. |
| 41 | Tenders and funding with no fit word | Hidden from the feed (and shortlist suggestions); the digest already leaves them out. A saved item stays on the shortlist. |
| 42 | Testing-source items for admins | Admin catalogue only; an admin's feed and digest show what members see. |
| 43 | Unsubscribe | One-click: a signed link in every digest and alert turns that email off without signing in, plus List-Unsubscribe and List-Unsubscribe-Post headers. |
| 44 | Where collection runs | The VPS. Nothing is deployed without the owner's go-ahead. |
| 45 | Email provider | Resend. No real email is sent until the owner gives the go-ahead and the key is provided through the secure form. |
| 46 | Headless browser isolation | `browser_list` collection and its test runs run in a separate container with no secrets (no database credentials, no API keys), reaching the network only through the guarded path; the API and worker call it over an internal channel. |
| 47 | Role change | Kept: admins can switch another user between member and admin (never themselves, never leaving no active admin). Extends spec 3. |
| 48 | Robots on JavaScript sites | Robots.txt is also checked for pages a site redirects or navigates us to; a disallowed page is stopped. |
| 49 | Emails with no usable link | Skipped, and each skipped email is recorded in the run's error log (sender, subject, date) so an admin can see what was missed. |
