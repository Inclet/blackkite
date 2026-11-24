# Phase 1 report: foundations

Date: 2026-11-24. Branch `claude/stoic-johnson-yofc7m` (merges b1e6f7e pipeline, d62d1cc UI). Reviewer: **signed off (code)**. Phase status: **open**, because exit check 2 (M0) is blocked.

## Exit checks

| Check | Result |
|---|---|
| Both styleguide routes ≤ 0.50% | **Pass**: foundations 0.00%, components 0.00% (0 of 1,440,000 px each). Built layout shift 0, stable. Confirmed by pixel-checker and reviewer separately. |
| M0 report written | **Not done.** Blocked: the owner's computer isn't shared with the session (decision 10), and this container's network refuses every seed source. |
| Schema migrations run clean | **Pass**: upgrade → downgrade base → upgrade, `alembic check` no drift. |
| Tests pass | **Pass**: api 57/57; web 73/73, typecheck and build clean; font-hash and harness-integrity specs pass. |

## Pixel-diff table (full suite, current state)

| Page | Viewport | Diff % | Result | Layout shift ref / built |
|---|---|---|---|---|
| foundations | 1440x1000 | 0.00 | pass | 0.0071 / 0 |
| components | 1440x1000 | 0.00 | pass | 0.0058 / 0 |
| feed-desktop | 1440x900 | 2.75 | fail (Phase 2 placeholder) | 0.0064 / 0 |
| feed-phone | 390x844 | 4.31 | fail (Phase 2 placeholder) | 0.0086 / 0 |
| opportunity-phone | 390x844 | 5.93 | fail (Phase 2 placeholder) | 0.0001 / 0 |
| digest-email | 640x1000 | 3.92 | fail (Phase 2 placeholder) | 0 / 0 |

## What was built

- **Web:** Vite/React 19/TS PWA shell; Figtree vendored byte-identical to Google's response (hash-checked); visual harness locked by CONTRACT.sha256; 18 components (Kite, KiteOrbit, Wordmark, Icon, Button, TextLink, FilterChip, Tag, Field, Switch, FitMeter, FitLine, Flag, DeadlinePill, TrustNote, FeedRow, StateCard, Card); both styleguide routes.
- **API:** full section 6 schema (17 tables incl. session and login_token), Alembic migration, magic-link sign-in, server-side sessions, member/admin roles, invites, deactivation, `bk bootstrap` (first admin + 7.1 profiles + digest setting), `bk seed-sources` (10 sources as `testing`), compose stack, `.env.example`.

## Unverified

- Docker image build and dev mail delivery to Mailpit (no Docker daemon here).
- pgvector was apt-installed in this container only; a fresh container needs it again.
- Project agents' path-guard hooks did not run (agent types registered only after they were created). The reviewer checked scope from git history: every agent stayed in its area.

## Reviewer findings (non-blocking)

1. Medium: `GET /auth/verify` spends the token, so mail link scanners can use up the link and receive a session. Must be fixed before any invite goes out; the fix needs a confirm screen (not designed).
2. Dockerfile trusts forwarded IPs from any peer, which weakens the per-IP limit behind a proxy.
3. Rate-limiter memory is never pruned.
4. TextLink hit area can be under 44 px wide for short labels; StateCard renders `href="#"` for click-only actions; Switch/Field let props override ARIA attributes.
5. Hex values hard-coded instead of `var(--bk-*)` (all match tokens today).
6. Stale comment in the frozen contract.ts about layout shift (value is correct).

Plan: items 2–5 fixed at the start of Phase 2; item 1 when the confirm screen is approved; item 6 needs the owner's OK because contract.ts is frozen.
