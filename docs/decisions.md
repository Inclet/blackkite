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
