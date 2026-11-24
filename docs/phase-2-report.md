# Phase 2 report: screens on fixtures

Date: 2026-11-24. Branch `claude/stoic-johnson-yofc7m`, head cddeb16. Reviewer: **signed off** (second pass, after one blocking fix round). Two small follow-up fixes landed after sign-off (keyboard race, config alias); all suites re-run on the merged head.

## Exit checks

| Check | Result |
|---|---|
| All six references ≤ 0.50% | **Pass**: all six at 0.00% (table below) |
| Keyboard J, K, S, X | **Pass**: desktop and phone list; keyboard e2e passed 250/250 repeated runs |
| Reflow at 360, 768, 1024, 1440, 1920 | **Pass**: 8 routes incl. /auth/confirm; no horizontal scroll, no overlap, every control ≥ 44 px or covered by its hit area |
| Tests pass | **Pass**: web 187 unit, 63 e2e, typecheck, build; api 154 |

## Pixel-diff table (merged head cddeb16)

| Page | Viewport | Diff % | Built layout shift |
|---|---|---|---|
| foundations | 1440x1000 | 0.00 | 0 |
| components | 1440x1000 | 0.00 | 0 |
| feed-desktop | 1440x900 | 0.00 | 0 |
| feed-phone | 390x844 | 0.00 | 0 |
| opportunity-phone | 390x844 | 0.00 | 0 |
| digest-email | 640x1000 | 0.00 | 0 |

## What was built

- **Web:** desktop feed (list + detail pane, /o/:id selects), phone feed, phone opportunity page, all component-board states on fixtures (?state=checking | nothing-new | first-visit | source-down, ?fixture=edge-cases), J/K/S/X, drop-in once, phone layout below 792 px, subtitles and event pills from rules 23–24, sign-in confirm page, dev/preview proxy for the exact API paths.
- **API:** sign-in confirm (POST /auth/verify JSON only, GET 405, token in the URL fragment), digest schedule weekly/off on Monday, save/dismiss state per (user, opportunity) with scores per profile (migrations 0002, 0003), digest email template (tables, inline styles, PNG logo, plain-text part, http/https links only) and the generated preview, forwarded-IP trust limited to a configured proxy, bounded rate-limiter memory, BK_WEB_BASE_URL only.
- **Verified for real:** sign-in end to end (request link → console mail → confirm page → signed in as admin → reused link refused), run by the reviewer against a throwaway database.

## Unverified

- Docker image build, the compose stack, and Mailpit delivery (no Docker daemon here).
- The production reverse proxy does not exist yet. It must forward exactly /auth/verify, /auth/request-link, /auth/logout, /me and /admin/* to the API and must NOT forward /auth/confirm.
- Real email clients: the sendable digest is not sent anywhere; the mail transport still sends plain text only.

## Carried to Phase 4

- Digest: "closing in 7 days" block for saved items, the value field, HTML + inline-logo sending, email provider.
- App-layer check that a user can't act on another user's private opportunity.
- BK_FORWARDED_ALLOW_IPS set to the proxy's address at deploy (until then the per-IP limit acts as one shared limit, failing safe).

## Housekeeping

- `ruff` reports 7 warnings and `ruff format` would reformat 28 files in api/; none in code changed this phase. Proposed as one tidy-up commit at the start of Phase 3.
- Undesigned items: docs/design-review.md. Token/reference mismatches: docs/token-mismatches.md.
