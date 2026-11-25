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
