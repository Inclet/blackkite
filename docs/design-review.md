# Needs design review

Anything built without a reference board. Built from existing components and tokens only.

| Item | Built in | What was decided without a board |
|---|---|---|
| Secondary button hover | Phase 1, Button | Fill stone-100 |
| Unselected chip hover | Phase 1, FilterChip | Fill stone-100 |
| Selected investment / funding / event chips | Phase 1, FilterChip | Tint fill, tint border, text colour, following the selected tender chip |
| Unselected "All" chip | Phase 1, FilterChip | White, 1px stone-200 border, padding 0 15px |
| Switch off state | Phase 1, Switch | Stone-300 track, thumb left |
| "Closes today" pill | Phase 1, DeadlinePill | Same as "Closes tomorrow" (alert red) |
| Sources, Profiles, Shortlist, Calendar, admin, evening mode | Not built | Per brief |
| Layout between 792 and 1024 px | Phase 2, FeedDesktop | Follows the board's own flex/grid; the detail pane stacks under the list below about 1200 px |
| Sign-in confirm page `/auth/confirm` | Phase 2, AuthConfirm | Wordmark, heading, body, one primary "Continue to sign in" button; plain error message (decision 17) |
| State cards inside the feed | Phase 2, feed | Checking, source down and first visit sit above the list; nothing new replaces list and pane; phone card margin 0 12px, padding 22px 24px; first visit shows the list unranked |
| Nothing-new card reused when everything is dismissed or filtered away | Phase 2, feed | Same card and copy |
| Save action | Phase 2, feed | Button relabels "Saved to shortlist" (aria-pressed); S or a second press unsaves |
| Dismiss action | Phase 2, feed | Row leaves the list, selection moves to next (or previous); phone returns to the feed; no undo, no reason yet |
| Live region announcements | Phase 2, feed | Visually hidden, for save and dismiss |
| Selected-row hover | Phase 2, FeedRow | Text turns slate (board's a:hover); no hover fill |
| New-row drop | Phase 2, FeedRow | 8 px over --bk-settle with --bk-ease, once |
| Closed rows in list and phone layouts | Phase 2, FeedRow | Stone tile, slate icon and title (from the board's closed row) |
| Past and running events | Phase 2, DeadlinePill | "Ended 20 Nov" plain text; started-not-ended stays alert red |
| Summary-line wording | Phase 2, lib/feed.ts | "Five things worth a look.", "Two close within a week.", "Nothing to look at right now." |
| Unscored subtitle | Phase 2, lib/subtitle.ts | "Not scored · develoPPP" pattern |
| Trust panel, confirmed and conflict | Phase 2, TrustPanel | Conflict title in alert-text; confirmed with graphite icon |
| Unknown item | Phase 2, feed | "We could not find that item" in the pane (desktop) or as a page with a back link (phone) |
| Account button | Phase 2 | Does nothing yet; no menu designed |
| Placeholder screens | Phase 2 | /shortlist, /calendar, /sources, /profiles, /more |
| Invented fixture details | Phase 2, fixtures | Reasons, trust copy, profile tags, URLs for the five non-WFP items; edge-case items |
| Digest, investment items | Phase 2, digest template | Lagoon text/swatch from tokens; the board has no investment item |
| Digest count wording | Phase 2, digest template | "1 more is waiting there."; line omitted at 0; "The 1 source was checked this week." |
| Sendable digest layout | Phase 2, digest template | Natural height, mist surround, 560 px card (the board is a fixed 1000 px frame) |
