# M3 report: sources and admin

Date: 2026-11-25. Branch `claude/stoic-johnson-yofc7m`. Reviewer: **signed off** (code, tests and a live run of every admin flow). One hardening round followed sign-off. Milestone status: **code complete; the real-source exit is open** (spec 11: "Add investment, funding and event sources through the UI as the test of the design" needs network to those sites and keys).

## Exit check

| Check | Result |
|---|---|
| Sources page, admin add/test/pause flow, suggestions queue | **Pass**, live on demo data: test run of an unreachable site fails cleanly in 0.1 s and saves nothing; private addresses refused; promotion refused with the gate message; invited member suggests → admin accepts → prefilled create; review, role change, deactivation |
| Remaining collector types | **Built and tested offline**: rss, json_api, browser_list, email_ingest, custom (plus html_list, search_query) |
| Add real investment, funding and event sources through the UI | **Not done**: no network to the sites, no keys, M0 not run |
| Tests | **Pass**: api 951; web 476 unit, 243 e2e, typecheck, build; visual six at 0.00% |

## Security review highlights

More than 20 SSRF and code-execution attempts across all seven collector types were refused (IP encodings, hosts-file names, IPv6-mapped addresses, a custom collector named after a system call, eight ways for a browser page to reach the network directly). Hardening after review: email authenticity bound to our own mail server's authserv-id; example and weak secrets refused at startup; suggestion and test-run limits; loopback blocked for Chromium at two layers; plain field-level admin errors.

## Unverified

- Real feeds, real IMAP servers and providers' Authentication-Results formats, real Eventbrite/10times JSON-LD, the Brave and Resend APIs.
- The Docker image (Chromium install, non-root user) is written but not built.

## Waiting for the owner

- Chromium isolation for `browser_list`: (a) separate container without secrets (recommended), (b) Chromium sandbox on the VPS, or (c) accept for now.
- Role change (member ↔ admin) isn't in spec 3; confirm.
- Robots.txt is checked for the pages we request, not for pages a site redirects or navigates to (those still pass the URL guard).
- One-email-per-item mode drops emails with no usable link.
- Health and source-kind wording on the Sources page (design review).
