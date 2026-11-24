# Blackkite: Phase 0 plan

Status: **awaiting owner approval**. No application code has been written.
Inputs read in full: `CLAUDE.md` (draft 7), `design/tokens.css`, `design/assets/*`, all six `design/reference/*.html`.

---

## 1. Repository layout

```
blackkite/
├── CLAUDE.md, KICKOFF_PROMPT.md        spec and brief (unchanged)
├── design/                             approved design; read-only, never edited
├── docs/
│   ├── PLAN.md                         this file
│   ├── decisions.md                    owner answers, recorded as they come
│   ├── token-mismatches.md             every token vs reference disagreement
│   ├── design-review.md                every undesigned screen, "needs design review"
│   ├── m0-access-report.md             source-scout output
│   └── phase-N-report.md               end-of-phase reports (pixel table, unverified, questions)
├── .claude/agents/                     the five subagents (section 3)
├── web/                                React + TS + Vite PWA
│   ├── public/fonts/                   Figtree 400/500/600 woff2, self-hosted
│   ├── src/styles/                     global.css (imports ../../design/tokens.css directly, no copy)
│   ├── src/components/                 one folder per component: X.tsx + X.module.css + X.test.tsx
│   ├── src/screens/                    Feed, Opportunity, Styleguide{Foundations,Components}, undesigned screens
│   ├── src/fixtures/                   reference fixtures, word for word from the boards
│   ├── src/api/                        typed client for the FastAPI backend
│   └── tests/
│       ├── visual/                     Playwright + pixelmatch harness, one spec per reference
│       ├── e2e/                        keyboard (J/K/S/X), reflow 360–1920, a11y checks
│       └── reports/                    generated: diff PNGs + visual-report.md (git-ignored except the .md)
├── api/                                Python 3.13, uv-managed
│   ├── blackkite/
│   │   ├── config.py                   settings from env (models, keys, rate limits)
│   │   ├── db/                         SQLAlchemy 2 models, session, Alembic migrations
│   │   ├── auth/                       magic link, server-side sessions, roles, invites
│   │   ├── sources/                    registry, URL safety, test-run sandbox
│   │   ├── collectors/                 base.py (fetch(source) -> list[RawItem]), html_list, search_query, …
│   │   ├── pipeline/                   normalise, dedupe, enrich, extract, validate
│   │   ├── scoring/                    match, score, fit word, flags
│   │   ├── delivery/                   digest + alert builders, Jinja email templates, mail transports
│   │   ├── worker/                     scheduler process
│   │   ├── routes/                     FastAPI routers
│   │   └── cli.py                      `bk` CLI: migrate, seed, run-source, test-source, digest-preview
│   └── tests/
├── docker-compose.yml                  db (pgvector/pg16), api, worker, web, mailpit (dev only)
├── .env.example                        every variable, no real values
└── Makefile                            make dev / test / visual / migrate / seed
```

## 2. Stack (section 9 confirmed, with these specifics and challenges)

| Area | Choice | Note |
|---|---|---|
| Web | React 19, TypeScript, Vite, `react-router`, `vite-plugin-pwa`, CSS modules on `design/tokens.css` | No UI/icon/CSS library. Icons and kite are hand-written components from `icons.json` / the SVGs. |
| Data fetching | Plain `fetch` + a small hook | Avoids a dependency; revisit if caching gets complex. |
| API | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic | |
| DB | PostgreSQL 16 + pgvector | |
| Scheduler | **Challenge:** a single `worker` process using APScheduler with Postgres advisory locks, no Redis/Celery | One VPS, low volume; fewer moving parts. |
| Auth | Email magic link, server-side session table, HttpOnly cookie | No passwords. OAuth later if wanted. |
| Email | Dev: Mailpit container (nothing leaves the machine). Prod transport: to be chosen (question Q9) | No real email sent without your go-ahead. |
| LLM | Claude API; model names in config. Default: `claude-haiku-5-5` for extraction and scoring, `claude-sonnet-5-5` for digest write-ups | |
| Embeddings | **Gap in spec:** the Claude API has no embedding endpoint. Proposal: local multilingual model (`multilingual-e5-small`, runs on CPU) | Handles English/French/Kinyarwanda text, no extra vendor. Alternative: Voyage AI (Q8). |
| Search collector | Needs a search API (Q7) | |
| Headless | Playwright only for `browser_list` and tests, per spec | Pinned to Playwright 1.63 (preinstalled browser). |
| Python packaging | `uv` | |
| Tests | pytest (+ testcontainers-style real Postgres), Vitest for components, Playwright for e2e/visual | |

## 3. Subagents (`.claude/agents/`)

Each gets a `description`, the narrowest `tools`, and a body with inputs, output format and limits. Every delegation names exact files, the reference page and the viewport.

| Agent | tools | Inputs | Output | Limits / enforcement |
|---|---|---|---|---|
| `ui-builder` | Read, Edit, Write, Glob, Grep, Bash | Component or screen name, reference file + line range, viewport, previous pixel-checker report (verbatim) | Changed files; table of reference values it could **not** reproduce, with reason | Writes only under `web/`. Never touches `design/`, `web/tests/visual/` thresholds or the harness config. A PreToolUse hook rejects Edit/Write outside `web/`. |
| `pixel-checker` | Read, Glob, Grep, Bash | Reference name(s) and viewport | Per page: diff %, pass/fail, list of mismatch regions (bbox, element under it, reference value vs built value), path to diff PNG | No Edit/Write. Bash limited by hook to `npm run visual*`, `git status/diff`, image inspection scripts. `git status` must be clean after its run; orchestrator verifies. |
| `pipeline-builder` | Read, Edit, Write, Glob, Grep, Bash | Spec sections to implement, files to touch, tests to make pass | Changed files, migration list, test results | Writes only under `api/`, `docker-compose.yml`, `.env.example`. Hook enforced. No network beyond package registries. |
| `source-scout` | Read, Write, Bash, WebFetch | The eight seed sources (spec 4.5), where to run from | `docs/m0-access-report.md`: per source, plain fetch / headless / RSS / email alerts / robots.txt / terms, with timestamps and host | Read-only network. ≤1 request per 5 s per host, honest User-Agent, robots.txt checked first, no retries beyond one. Writes only under `docs/`. |
| `reviewer` | Read, Glob, Grep, Bash | Phase number, diff range, spec sections and references in scope | Findings list (correctness, security, a11y, spec drift), each with file:line and severity; sign-off or not | Read-only; Bash for `git diff`, tests and linters only. |

Note: project agent files are picked up when a session starts. If they aren't available as agent types in this session right after I create them, I'll run each delegation with the agent file's body as the brief, so the briefs and limits stay the same.

## 4. Orchestration

- I orchestrate and do no bulk implementation.
- Two git worktrees: `wt-ui` (branch `track/ui`) and `wt-pipeline` (branch `track/pipeline`), both cut from `claude/stoic-johnson-yofc7m`. At each phase end they're merged back into that branch. Only that branch is pushed.
- Per screen: `ui-builder` → `pixel-checker` → (report verbatim) → `ui-builder`, until ≤ 0.5%. If a page stalls after 4 rounds with no movement, I stop and report why rather than loosen anything.
- `reviewer` at every phase end, before I report.
- Small commits, one concern each, tests alongside.

## 5. Visual harness

- Playwright Chromium, `deviceScaleFactor: 1`, `reducedMotion: 'reduce'`, fixed clock `2026-11-24T14:00:00+02:00` (Kigali, Tuesday afternoon). All dates on the boards are consistent with that day (30 Nov = 6 days, 7 Dec = 13, 23 Dec = 29, 31 Dec = 37).
- Reference: opened from `design/reference/*.html` untouched. Built: the matching route with `?fixture=reference`.
- Before screenshotting: `document.fonts.ready`, two animation frames, then a screenshot of the viewport only.
- `pixelmatch` threshold 0.1; pass ≤ 0.5% differing pixels. Report exact % per page in `web/tests/reports/visual-report.md`.
- Layout shift: a `PerformanceObserver('layout-shift')` sum must be 0, and two screenshots 500 ms apart must be identical.
- Fonts: references load Figtree from Google Fonts. I'll vendor the exact woff2 files Google serves (Figtree is OFL) and add a test that their hashes match what Google serves today, so self-hosted and reference fonts are the same bytes. See Q3 for the offline option.

## 6. Phases and exit checks

**Phase 1: foundations**
- UI: scaffold, tokens, fonts, Kite (full/small/orbit/rest), Icon set, Button (primary/secondary/link, hover/focus/disabled), FilterChip (All/stream, selected/unselected), Tag (stream/profile), Field (+error), Switch, FitMeter + FitLine, Flag, DeadlinePill (4 weights + quiet text), TrustNote (3 states), FeedRow (board, desktop list, phone variants), the 4 State cards, both styleguide routes.
- Pipeline: `source-scout` runs M0 (where: Q1). `pipeline-builder`: full schema from section 6 incl. per-user tables, magic-link auth, sessions, roles, invites, server-side role checks, first-admin bootstrap, seed sources as `testing`.
- Exit: `/styleguide/foundations` and `/styleguide/components` ≤ 0.5%; M0 report written; `alembic upgrade head` and `downgrade base` run clean on an empty DB; tests green; reviewer signed off.

**Phase 2: screens on fixtures**
- Feed desktop (list + detail pane), feed phone, opportunity phone, desktop detail pane via `/o/:id`, digest template + preview route; all component-board states wired into the screens.
- Exit: all six references ≤ 0.5%; J/K/S/X work; reflow at 360/768/1024/1440/1920 with no horizontal scroll or overlap; a11y checks (roles, labels, focus ring, 44 px targets, contrast) pass.

**Phase 3: pipeline (M1)**
- Source registry + `source_run` history, `html_list` and `search_query` collectors, two working tender sources (chosen from M0), normalise → dedupe → enrich → extract → validate, scheduler, CLI, URL safety (block private ranges, sandboxed test run).
- Exit: a scheduled run fills the catalogue from real sources; tests for dedupe, date validation (explicit year, plausible window, expiry) and the three trust states.

**Phase 4: personal (M2)**
- Seed profiles from 7.1, hard filters, match (tags + embeddings), score (rules + one LLM call per shortlisted pair), fit word, reasons and flags (incl. the Ironji-specific rules), weekly digest + urgent alert (to Mailpit), UI wired to API, backfill on profile change.
- Exit: your seeded account sees a ranked feed from real data; digest renders from it; visual checks still pass on fixtures.

Stop after Phase 4.

## 7. Spec / design conflicts found (need a ruling)

See the questions list in section 8; this table is the evidence.

| # | Where | What disagrees |
|---|---|---|
| C1 | feed-desktop, feed-phone: event "1 to 2 Dec" | 1 Dec is 7 days from 24 Nov. Spec 12 says ≤ 7 days = solid graphite; the boards show it outlined. |
| C2 | components: Switch | 28 px tall; spec says all tap targets ≥ 44 px. Same for "Open shortlist" / "See all sources" links (~34 px) and "Read the original" (~41 px). |
| C3 | foundations: kite glide 7 s ease-in-out, orbit 14 s, drop 5 s infinite | Brief says three durations and one easing; tokens give 8 s / 6 s orbit. The Found item "drops in once" but the board loops it. |
| C4 | digest-email | Wordmark and headings use `bold` (700) Helvetica; brief says nothing bolder than 600. Card radius 12 px isn't a token. |
| C5 | digest-email | Uses flexbox and inline SVG. Gmail strips SVG; Outlook ignores flex. Pixel-matching the board in Chromium and rendering well in real inboxes pull in different directions. |
| C6 | feed-phone | Shows 5 rows (no develoPPP) while the greeting says "Six things". Also no Events chip in the markup. |
| C7 | feed-phone vs feed-desktop | Row subtitles differ: "Kigali Convention Centre" vs "Startups and investors · Kigali Convention Centre"; "NCST" vs full name; BNR without "· trading on the RSE". No stated rule. |
| C8 | feed-desktop rows | Subtitle pattern varies: "Strong fit · Org", "Topic · Venue" (events), "Good fit · needs matching funds" (flag replaces org), "Org · note" (investments, unscored). |
| C9 | trust note copy | Desktop pane and phone page word the same "not yet confirmed" note differently. |
| C10 | feed-desktop at narrow widths | Its own flex-wrap stacks the full sidebar nav above the feed below ~792 px. The phone board uses a top header + bottom tab bar instead. The switch point between them isn't designed. |

Token mismatches (reference wins; logged, no ruling needed): many board values are off the space scale (9, 18, 22, 36, 40, 44, 56 px), line-heights 1.45/1.5 aren't tokens, trust panel is `#F6F5F2` on desktop and `#EFEDE9` on phone, phone deadline pill is 12 px with 3/4 px padding. All go in `docs/token-mismatches.md`.

## 8. Questions

See the chat message for the list with defaults; answers will be recorded in `docs/decisions.md`.
