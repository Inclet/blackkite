# M4 report: calendar, private items, full opportunity page, feed filters

Date: 2026-11-26. Branch `claude/stoic-johnson-yofc7m`, head 8862db0. Reviewer: **signed off** on the third pass (after two fix rounds). Also includes owner decisions 46, 48, 49 (separate renderer container, robots on redirects, skipped-email warnings).

## Exit check (spec 11, M4: feed, opportunity page, actions, calendar, private manual items)

| Check | Result |
|---|---|
| Calendar of deadlines and events | **Pass** (live): month grid and list, filters, today, keyboard; personal `.ics` link with rotation |
| Private manual items | **Pass** (live): add, edit, delete; invisible to every other user and to admins; share consent; admin publish only with consent; owner keeps access, note and private history after publishing |
| Opportunity page | **Pass** (live): fields with their quotes, sources, documents (names), history |
| Feed filters (spec 8) | **Pass**: stream, profile, status, deadline window, fit word, source, verification |
| Visual boards | **Pass**: all six at 0.00% |
| Tests | **Pass**: api 1097; web 587 unit, 305 e2e, typecheck, build |

## Fixed during review

- A published item's private edit history was shown to everyone; now owner-only.
- "You added it yourself" was shown to non-owners; wording is now per viewer.
- An edit, delete or consent withdrawal racing a publish could change a public item; now refused (409) with nothing written.
- Calendar and unsubscribe tokens were in access logs; now redacted (the VPS reverse proxy must do the same).
- The item form dropped a same-day event's end time on save; the editor now sends only changed fields.
- A published own item could vanish from its owner's feed; it stays theirs.

## Unverified

- Real calendar apps subscribing to the `.ics` link (parsed with an independent library only).
- The Docker stack, including the renderer container's network isolation (written and structure-tested, not built).

## Owner decisions recorded

46–53 in docs/decisions.md. Undesigned screens and wording: docs/design-review.md.
