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
| Sources, Calendar, admin screens, evening mode | Not built (Sources UI is M3) | Calendar and Sources render in the app frame as "Not designed yet."; evening mode not shipped. Profiles and Shortlist are built (Phase 4, below) |
| Layout between 792 and 1024 px | Phase 2, FeedDesktop | Follows the board's own flex/grid; the detail pane stacks under the list below about 1200 px |
| Sign-in confirm page `/auth/confirm` | Phase 2, AuthConfirm | Wordmark, heading, body, one primary "Continue to sign in" button; plain error message (decision 17) |
| State cards inside the feed | Phase 2, feed | Checking, source down and first visit sit above the list; nothing new replaces list and pane; phone card margin 0 12px, padding 22px 24px; first visit shows the list unranked |
| Nothing-new card reused when everything is dismissed or filtered away | Phase 2, feed | Same card and copy |
| Save action | Phase 2, updated Phase 4 | One label, "Save to shortlist"; aria-pressed carries the state. Saved: secondary style with the ui "check" icon (16px, stroke 1.6, 8px gap) before the label; unsaved: primary, no icon. S or a second press unsaves |
| Dismiss action | Phase 2, updated Phase 4 | Row leaves the list, selection moves to next (or previous); phone returns to the feed; no undo. Optional reason: see "Dismiss reason card" |
| Live region announcements | Phase 2, feed | Visually hidden, for save and dismiss |
| Selected-row hover | Phase 2, FeedRow | Text turns slate (board's a:hover); no hover fill |
| New-row drop | Phase 2, FeedRow | 8 px over --bk-settle with --bk-ease, once |
| Closed rows in list and phone layouts | Phase 2, FeedRow | Stone tile, slate icon and title (from the board's closed row) |
| Past and running events | Phase 2, DeadlinePill | "Ended 20 Nov" plain text; started-not-ended stays alert red |
| Summary-line wording | Phase 2, lib/feed.ts | "Five things worth a look.", "Two close within a week.", "Nothing to look at right now." |
| Unscored subtitle | Phase 2, lib/subtitle.ts | "Not scored · develoPPP" pattern |
| Trust panel, confirmed and conflict | Phase 2, TrustPanel | Conflict title in alert-text; confirmed with graphite icon |
| Unknown item | Phase 2, feed | "We could not find that item" in the pane (desktop) or as a page with a back link (phone) |
| Account button | Phase 2, updated Phase 4 | Phone header button opens /account |
| Placeholder screens | Phase 2, updated Phase 4 | /calendar and /sources are still placeholders; the rest are built (below) |
| Invented fixture details | Phase 2, fixtures | Reasons, trust copy, profile tags, URLs for the five non-WFP items; edge-case items |
| Digest, investment items | Phase 2, digest template | Lagoon text/swatch from tokens; the board has no investment item |
| Digest count wording | Phase 2, digest template | "1 more is waiting there."; line omitted at 0; "The 1 source was checked this week." |
| Sendable digest layout | Phase 2, digest template | Natural height, mist surround, 560 px card (the board is a fixed 1000 px frame) |
| Sign-in screen `/sign-in` (and on any 401) | Phase 4 | Wordmark, "Sign in to Blackkite", "We email you a link to sign in. There is no password.", email Field, primary "Email me a sign-in link", then "Check your email for a link."; field error, too-many and unreachable messages |
| Loading and reloading | Phase 4 | Checking card "Loading" / "This usually takes a moment."; with data kept on screen: "Checking for changes" / "The list below stays on screen meanwhile." |
| Unreachable and undone changes | Phase 4 | Source-down card "We could not reach Blackkite just now" + "Try again"; "…so that change was undone. Try again." |
| Live state-card copy | Phase 4 | "Checking N sources"; nothing-new with live counts |
| Progress and note in the detail pane | Phase 4 | "Your progress" FilterChips "Acting on it" / "Done"; "Your note" Field, secondary "Save note", "Note saved." and its error |
| App shell on undesigned screens | Phase 4 | Same sidebar as the feed board; Digest settings and Account reached from Profiles and from phone More |
| Shortlist | Phase 4 | FeedRow list (desktop list / phone layout), summary line, empty card "Nothing on your shortlist yet" + "Open the feed" |
| Profiles list | Phase 4 | Cards: name, kind · streams, Provisional/Paused tags, Edit; "Add a business profile" / "Add a personal profile" |
| Profile editor | Phase 4 | Cards About, What you offer, Registrations, Capacity (five number fields incl. smallest/largest load in tonnes), Interests, Leave out; comma-separated list Fields; FilterChips for streams, instruments, topics; Switch rows Active and Provisional; field errors in the board's style ("Choose at least one stream.", "Use a whole number, such as 100.", "Use whole tonnes for a range, such as 20.", "Make this at least the smallest load."); delete with a confirm step; "Saved. Open items are being ranked against it again." |
| SwitchRow | Phase 4 | The Components board's Urgent alerts row as a component |
| Digest settings | Phase 4 | Weekly digest switch ("Every Monday, by email to {address}."), stream chips incl. "My profiles' streams", the board's Urgent alerts switch, "Alert me about": "Strong fits only" / "Strong and good fits" |
| Account | Phase 4 | Signed in as, Sign out, "Export my data", "Delete my account" with typed-email confirm ("Delete my account for good" / "Keep my account"), "Your account is deleted." |
| More (phone) | Phase 4 | Card of NavItems: Profiles, Digest, Sources, Account |
| Urgent alert email | Phase 4 | Heading "Closing within 5 days"; subject "Closes {date}: {title}" / "{N} items close within 5 days"; intro "Found today and at your alert level, so it should not wait for Monday's digest."; footer names the chosen fit word ("…is a strong fit for one of your profiles…") and links to alert settings |
| Digest additions | Phase 4 | "Closing in 7 days" block (15px bold heading); value line "Value: FRW 12,000,000 ({note})"; full dates with times; subject and intro wording for counts; greeting by time of day |
| Trust copy not on the boards | Phase 4 | Confirmed: "Matched to the notice on {publisher}'s own site." / "Listed on {publisher}'s own site."; conflict without an original; private item "You added this item yourself, so nobody else has checked it." |
| Rules-only scoring | Phase 4 | Fit word at most "Possible" without the model |
| Demo data | Phase 4 | `bk demo-seed` items titled "[Demo] …", organisations "(fictional)"; dev only |
| Provisional tag | Phase 4 | Neutral profile-style Tag "Provisional" after the profile Tag in the desktop detail pane and the phone opportunity page; the tag row may wrap on a narrow phone (the boards never wrap) |
| Provisional in emails | Phase 4 | Digest and alert labels read "TENDER · FOR AI LAB (PROVISIONAL)" |
| Greeting without a name | Phase 4 | App: "Good afternoon" (morning/evening alike) with no name; digest: "Good morning" |
| Account button fallback | Phase 4 | First letter of the name, else of the email, else empty |
| Profiles "Settings" card | Phase 4 | Card with two side NavItems, "Digest settings" and "Account", on desktop and phone; desktop Digest settings and Account highlight Profiles in the sidebar |
| Dismiss reason card | Phase 4 | After a dismiss: card "Why not? (optional)" (accessible name "Why not? (optional): {title}", label 13px/500, padding 16px, gap 10px) with five one-shot action chips (FilterChip look, no pressed state): "Not my sector", "Too small", "Can't meet the requirements", "Already knew about it", "Other". Desktop: above the list; the pane's "Not for me" moves focus to the first chip, X keeps focus on the list. Phone: on the feed. Announced "Marked not for me: {title}. You can say why (optional)."; after a choice "Thanks, noted." or "We could not reach Blackkite just now, so the reason was not saved."; closes after a choice or on navigation (J/K) |
| FilterChip action variant | Phase 4 | Unselected chip look as a one-shot button (no aria-pressed); not shown on the styleguide (would change the components board) |
| Unscored tenders and funding | Phase 4 | No profile or Provisional tag in the detail pane or phone page when the item has no fit word |
