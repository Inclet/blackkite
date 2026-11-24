# Blackkite: kickoff prompt for Claude Code

How to use this:

1. Create an empty repository and copy this whole folder into its root (`CLAUDE.md`, `design/`, this file).
2. Start Claude Code in that folder, in plan mode.
3. Paste everything below the line as your first message.

---

You are the lead engineer for Blackkite, a multi-user platform that finds, ranks and tracks opportunities in Rwanda (tenders, investments, funding, events). You will plan the work, split it across subagents, and hold the result to the approved design.

## Read these first, in full

1. `CLAUDE.md`: the product spec. Sections 5 to 11 define the pipeline, data model, scoring, delivery, stack, guardrails and milestones. Section 12 summarises the design.
2. `design/tokens.css`: the design tokens.
3. `design/assets/icons.json`, `design/assets/kite-full.svg`, `design/assets/kite-small.svg`: exact icon and logo data.
4. `design/reference/*.html`: the six approved boards. Open each one and read its markup. Every size, colour, spacing and radius is written inline, so these files are the source of truth.

## How I want you to work

- Start in plan mode. Do not write code until I approve the plan.
- Your plan must include: repository layout, the stack with any change you propose to section 9 of the spec, the subagent definitions, the phases with their exit checks, and every question you need answered.
- Stop at the end of each phase and report: what was built, the pixel-diff table, what is unverified, and open questions. Wait for my go-ahead before the next phase.
- If something is ambiguous, ask. Do not guess at product behaviour and do not invent design.

## Stack defaults (confirm or challenge in your plan)

- Web app: React, TypeScript, Vite, installable as a PWA. Plain CSS (CSS modules) driven by `design/tokens.css`. No UI component library, no icon library, no CSS framework that restyles defaults.
- API and pipeline: Python, FastAPI, PostgreSQL with pgvector, a scheduler for collectors.
- Docker Compose for local and single-VPS use.
- Playwright for end-to-end and visual tests.

## The design contract: pixel-level match

The six reference pages are approved. The built screens must match them.

**Method**

1. Build a visual test harness with Playwright. For each reference page, screenshot the reference file and the matching built route at the same viewport, in Chromium, device scale factor 1, and compare with `pixelmatch`.
2. Before any screenshot: wait for `document.fonts.ready`, emulate `prefers-reduced-motion: reduce` so animations are still, and load the fixture data that reproduces the reference content word for word.
3. Pass mark: no more than 0.5% of pixels differ at a `pixelmatch` threshold of 0.1, and no visible layout shift. Report the exact percentage for every page.

| Reference | Viewport | Built route |
|---|---|---|
| `foundations.html` | 1440 x 1000 | `/styleguide/foundations` |
| `components.html` | 1440 x 1000 | `/styleguide/components` |
| `feed-desktop.html` | 1440 x 900 | `/` |
| `feed-phone.html` | 390 x 844 | `/` |
| `opportunity-phone.html` | 390 x 844 | `/o/:id` |
| `digest-email.html` | 640 x 1000 | digest template preview |

**Rules**

- Copy exact values from the reference markup. Do not round to a spacing scale, substitute a similar colour, or swap an icon. Tokens give names to values; they do not override the reference.
- Use Figtree at weights 400, 500 and 600, self-hosted, and confirm it renders identically to the reference. Nothing bolder than 600.
- Never make a visual test pass by raising the threshold, masking a region, editing a reference file, or changing a viewport. If a page cannot reach the pass mark, stop and tell me why.
- If a token and a reference disagree, follow the reference and list the mismatch in your report.
- The two styleguide routes exist so components are checked in isolation. Build screens only from those components.
- Between the reference viewports, layouts must reflow cleanly from 360 to 1920 pixels wide. The desktop reference is fluid; the phone references are fixed frames.
- Accessibility is part of the design: real `button`, `a`, `input` and `label` elements, the double focus ring on every control, tap targets at least 44 pixels high, visible text at 4.5:1 contrast or better.
- Motion: three durations and one easing from the tokens. The circling kite replaces every spinner. A new item drops in once. With reduced motion, nothing moves.

**Not designed yet**

Sources, Profiles, Shortlist, Calendar, the admin screens and full evening mode have no reference. Build them from existing components and tokens only, add no new colours or patterns, and list each one in your report as "needs design review". Do not ship evening mode.

## Agents

Create these project subagents in `.claude/agents/` as part of the approved plan. Give each a short `description`, the narrowest `tools` list that works, and a body that states its inputs, its output format and its limits. Each subagent starts with a fresh context, so every delegation must name the exact files, reference page and viewport it concerns.

| Subagent | Job | Limits |
|---|---|---|
| `ui-builder` | Builds components and screens from the tokens and reference pages | Touches only the web app. Reports which reference values it could not reproduce |
| `pixel-checker` | Runs the visual harness, reads the diff images, and reports each mismatch with its location and the reference value | Never edits application source, tests, thresholds or references |
| `pipeline-builder` | Builds schema, collectors and the shared pipeline per spec sections 4 to 6 | Touches only the API and pipeline |
| `source-scout` | Runs the milestone M0 access test on the eight seed sources and writes the results | Read-only network checks, low request rate, honours robots.txt and site terms |
| `reviewer` | Reviews each phase for correctness, security, accessibility and spec drift | Read-only |

Orchestration:

- You stay the orchestrator. Do not do bulk implementation in the main session.
- Run the UI track and the pipeline track in parallel, each in its own git worktree, and merge at phase ends.
- For every screen, loop `ui-builder` then `pixel-checker` until the pass mark is met. Send `pixel-checker`'s report back to `ui-builder` verbatim.
- Run `reviewer` at the end of every phase, before you report to me.
- Subagents may spawn helpers for wide searches. They may not change scope.

## Phases

**Phase 0: plan.** Read everything, then present the plan described above. No code.

**Phase 1: foundations.**
- UI track: scaffold the app, load tokens and fonts, build the kite, icons and every component on the Components board, plus both styleguide routes.
- Pipeline track: `source-scout` runs M0 and records an access note for each seed source. `pipeline-builder` creates the full multi-user schema, authentication, roles and invites from spec sections 3 and 6.
- Exit: both styleguide routes pass the visual check. M0 report written. Schema migrations run clean.

**Phase 2: screens on fixtures.**
- Build the feed (desktop and phone), the opportunity page (phone, and the desktop detail pane), and the digest email template, all on fixture data that matches the references.
- Build every state on the Components board: checking, nothing new, first visit, source down, long title, missing deadline, closed item.
- Exit: all six references pass. Keyboard navigation works (J, K, S, X). Reflow checked at 360, 768, 1024, 1440 and 1920.

**Phase 3: pipeline.**
- Source registry with run history, two collector types (`html_list`, `search_query`), two working tender sources, and the shared pipeline through validation (spec milestone M1).
- Exit: a scheduled run fills the catalogue from real sources, with tests for dedupe, date validation and the three trust states.

**Phase 4: make it personal.**
- Profiles from spec section 7.1, matching and scoring, the fit word with its reasons and flags, the weekly digest and urgent alert, and the UI wired to the API (spec milestone M2).
- Exit: my seeded account sees a ranked feed from real data, and the digest renders correctly from it. Visual checks still pass on fixtures.

Stop after Phase 4. Sources UI, admin screens and the remaining streams come after I review.

## Guardrails

- Follow spec section 10 in full: robots and terms, honest client identity, rate limits, summaries with links rather than republished notices, investment items as facts only, private user data, sandboxed source config.
- Secrets live in environment variables. Commit an `.env.example`, never a real key.
- Do not send real email, deploy anywhere, or contact any site beyond the M0 checks and approved collectors without asking me first.
- Write tests alongside the code. A phase is not done while tests fail.
- Small commits with clear messages, one concern each.
- If you find the spec and the design disagree, stop and ask which wins.

## Definition of done for this engagement

All six reference pages pass the visual check with the percentages reported, every state on the Components board exists, the feed runs on real data for my account, the digest renders from that data, the reviewer has signed off each phase, and everything not yet designed is listed for design review.
