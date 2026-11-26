# M5 report: second user, benchmarks, procurement plans

Date: 2026-11-26. Branch `claude/stoic-johnson-yofc7m`. Reviewer: **signed off** (code and the second-user test on demo data) on the second pass; a cleanup round followed. Real-data items stay open.

## Exit check (spec 1 success test for a second user; spec 11, M5)

| Check | Result |
|---|---|
| A second user with a different profile, without code changes | **Pass on demo data**: an invited member built an NGO business profile and a personal-investing profile in the app. NGO-only grant shown to the NGO and filtered for Ironji/AI lab with the quoted rule; their chosen investment kinds rank first (treasury 69 vs corporate bond 43) and unchosen kinds leave their digest (decision 54); each user's feed, calendar, Coming up, mutes, private items and digests stay their own |
| Benchmarks | **Pass on demo data**: price ranges per category and currency (≥ 3 awards), matching an independent recomputation exactly; "similar awarded contracts" on tenders |
| Procurement plans | **Pass on demo data**: planned tenders matched to profiles, dropped once advertised |
| Same test with real data, weekly digest success test (spec 1) | **Not done**: needs real sources and the model |
| Tests | **Pass**: api 1278; web 633 unit, 350 e2e; visual six at 0.00% |

## Fixed because of the second-user run

Investment choices had no effect; demo data couldn't run an NGO test; reasons overstated matches; planned tenders matched on one shared word or one sector word; blank space in list rows; planned dates and benchmark wording; first-visit wording; free-text NGO types; a profile-editor race that could wipe typed edits; awards from different buyers with the same generic title could merge.

## Unverified

Real Umucyo award and plan pages (markup, rendering, pagination, formats, whether award refs match tender refs, fiscal vs calendar quarters); categories are keyword rules to tune on real titles; Strong/Good split and urgent alerts need the model.

## Waiting for the owner

The same five items as before: M0 from the owner's computer, API keys, bot contact URL, VPS details, shared inbox for email alerts.
