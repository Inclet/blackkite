# Phase 4 contracts

Fixed before Phase 4 work starts so three tracks can build in parallel. Change only through the orchestrator.

## 1. Scoring output (scoring track writes, member API reads)

One `user_opportunity_score` row per (user, opportunity, profile). Columns: `score` (0–100, internal, never shown), `score_reason` (one sentence), `score_breakdown` (jsonb):

```json
{
  "version": 1,
  "components": {"fit": 0-40, "eligibility": 0-20, "value": 0-15, "time": 0-15, "source": 0-10},
  "fit_confidence": 0.0-1.0,
  "eligibility_confidence": 0.0-1.0,
  "fit_word": "strong" | "good" | "possible" | null,
  "reasons": ["It asks for transport, warehousing and logistics support, which you offer."],
  "flags": [{"code": "owned_fleet", "label": "May require owned fleet", "quote": "copies of vehicle logbooks", "to_check": "WFP's transport call asks for vehicle logbooks, so this one may require an owned fleet."}],
  "provisional": false,
  "hard_filtered": null | "outside_rwanda" | "deadline_passed" | "stream_not_selected" | "muted_source_only" | "ineligible" | "below_min_value",
  "model": "claude-haiku-5-5", "prompt_version": "score-v1", "scored_at": "ISO-8601"
}
```

- `fit_word` rule (revised 2026-11-25 to match the boards; owner to confirm): **strong** when fit_confidence ≥ 0.7 and eligibility_confidence ≥ 0.7 (flags allowed: the WFP item is Strong with a "To check" note); **good** when fit_confidence ≥ 0.6 and eligibility_confidence ≥ 0.5 ("matches, with something to check"); **possible** when fit_confidence ≥ 0.4 (eligibility unclear); otherwise null (not shown). Thresholds in config. Investments and events: fit_word null (decision 24 / boards), ranked on time, verification and source kind (spec 7.1).
- Hard-filtered pairs are stored with `hard_filtered` set and never shown or sent.
- A user's best profile for an item = highest score among non-filtered rows; that profile's name is the item's `profile`.

## 2. Member API (member-API track builds, web track consumes)

All JSON in camelCase (request bodies also accept snake_case keys; `GET /me` alone keeps its Phase 1 snake_case keys; a source's `config` object keeps its collector's own keys). **Every member route below lives under `/api`** (e.g. `GET /api/feed`), so no API path collides with a web page (`/shortlist`, `/profiles` are also screens). `/auth/*` and `GET /me` keep their paths. **M3: every admin route moves under `/api/admin`** (`/api/admin/sources*`, `/api/admin/source-suggestions*`, `/api/admin/users*`, `/api/admin/invites*`, `/api/admin/catalogue*`) because `/admin/...` becomes the admin screens; and the Phase 3 member source routes move too: `/api/sources`, `/api/sources/{id}/mute`, `/api/source-suggestions` (`/sources` is also a screen). Every route requires a session; every query filters by the caller (spec 6) and by `pipeline/visibility.py`.

| Route | Returns |
|---|---|
| `GET /feed?stream=&profile=&window=&verification=&source=&state=` | `FeedContent` exactly as `web/src/fixtures/types.ts` (user, sources, digest, items: `FeedItem[]`). Default order: closing soonest first (feed boards). Excludes dismissed, hard-filtered and not-visible items, and (decision 41) tenders and funding whose best active-profile row has no fit word (`fit` null or `"not-scored"`) unless the caller's state for the item is saved, acting or done, or it is the caller's own private item. Events and investments are unaffected; with `profile=`, that profile's row decides. Summary counts the web derives from `items` follow. |
| `GET /opportunities/{id}` | `FeedItem` plus `detail.fields` (extracted fields with their snippets), `detail.sources` (visible sources: name, url, isOriginal, firstSeen, lastSeen), `detail.documents` (names only, never content), `detail.changes`, `detail.note`. 404 for items the caller can't see, including other users' private items. |
| `PUT /opportunities/{id}/state` | body `{state: "saved"\|"dismissed"\|"acting"\|"done"\|"unseen", dismissReason?}`; per (user, opportunity) (decision 19). |
| `PUT /opportunities/{id}/note` | body `{note}` |
| `GET/POST/PATCH/DELETE /profiles` | the caller's profiles; scoring-relevant edits queue a backfill that the worker runs (spec 5, decision 36). |
| `GET/PUT /digest-settings` | channel email, frequency weekly\|off, day mon, `alertMinFit`: "strong"\|"good"\|null (null = alerts off; compared against the best active profile's fit word, never the numeric score), streams (decision 18). |
| `GET /shortlist` | saved/acting items, `FeedItem[]`, soonest first. Unchanged by decision 41: saved and acting items show with or without a fit word. |
| `POST /unsubscribe` | **No session** (decision 43). Body `{token}` as JSON (from the web page `/unsubscribe`, which reads `#token=` from its URL), or the RFC 8058 one-click form POST `List-Unsubscribe=One-Click` (urlencoded or multipart) with `?token=` in the query. A digest token sets the email digest's frequency to "off" (creating the setting row if absent); an alert token sets `alertMinFit` to null. Idempotent. 200 `{kind: "digest"\|"alert", detail: "You won't get these emails any more."}`; 400 for a bad, revoked or unknown-user token; 415 other content types; 429 when rate-limited: per token (hash; `BK_UNSUBSCRIBE_RATE_PER_TOKEN_PER_HOUR`, default 10) so provider one-click POSTs from shared addresses pass, plus a per-address flood ceiling (`BK_UNSUBSCRIBE_RATE_PER_IP_PER_HOUR`, default 300). `GET /unsubscribe` changes nothing and answers 405 "Use POST". Tokens: HMAC-SHA256 (key `BK_UNSUBSCRIBE_SECRET`) over user id, kind and the user's `unsubscribe_nonce`; rotating the nonce revokes old links. Every digest and alert carries the page link `{web}/unsubscribe#token=…` and the headers `List-Unsubscribe: <{api}/api/unsubscribe?token=…>` (plus `<mailto:…>` when `BK_UNSUBSCRIBE_MAILTO` is set) and `List-Unsubscribe-Post: List-Unsubscribe=One-Click`. |
| `PATCH /me`, `GET /me/export`, `DELETE /me` | name for the greeting; data export; account deletion (spec 10). |

Field mapping for `FeedItem`: `provisional` = true when the matched profile is provisional (spec 7.1: AI lab), shown as a label next to the profile; `state` = the caller's state for the item ("unseen"|"saved"|"dismissed"|"acting"|"done"), always sent on feed, shortlist and detail items; `fit` = fit_word, or `"not-scored"` when no score row exists for a scorable stream, or null for events/investments/closed; `topFlag` = first flag label, sent only when `fit` is "good" (feed boards: develoPPP "Good fit · needs matching funds"; WFP is Strong with a flag and shows the organisation); `detail.reasons` = reasons; `detail.toCheck` = first flag's `to_check`; `detail.trust.state` = `evidence._trust` (confirmed/unconfirmed/conflict); `detail.trust.desktop` / `.phone` = the two copy templates the web fixtures already use, filled from the source names and dates; `deadline` = Kigali date of deadline_at.

## 3. Digest (member-API track)

`DigestView` from `api/blackkite/delivery/digest.py` is built from scores: top items across the user's profiles, capped at 12, each stream capped (investments and events at 3 each, spec 7.1), plus a "closing in 7 days" block for saved items and the value line (spec 8). Weekly on Monday; urgent alert for items above the user's threshold closing within 5 days, the day they are found. Delivery is Mailpit/console only; nothing real is sent without the owner's go-ahead.

## 4. M3: sources and admin screens (added 2026-11-25)

Web screens (undesigned; existing components only; design review): `/sources` (members: active sources with publisher, kind, streams, last successful run, items in 30 days, health, mute; suggest-a-source form), `/admin/sources` (all sources by status), `/admin/sources/new` and `/admin/sources/{id}` (record and config editor per collector type, test-run preview that writes nothing, status changes with the promotion gate, run history and error log), `/admin/suggestions`, `/admin/review` (catalogue items with needs_review reasons; "Mark reviewed"), `/admin/users` (users, invite, deactivate). Admin links appear only for admins; the server enforces roles regardless.

Collector types completed in M3 (spec 4.2): `rss`, `browser_list` (Playwright, same URL guard, robots, rate limit and size caps as `html_list`), `json_api`, `email_ingest` (a shared inbox over IMAP; sender address/pattern per source), `custom` (a named class from an allowlist in code; config never names arbitrary import paths). Each returns `RawItem` and raises `CollectorError` on failure.

### 4.1 Routes (built 2026-11-25)

Every route below needs a session; `/api/admin/*` also needs `role = admin` (401 signed out, 403 for members, checked on the server). No API route is served under `/admin/*` any more.

| Route | Body / query | Returns |
|---|---|---|
| `GET /api/sources` | | active sources: `id, name, homeUrl, publisher, kind, streams, lastSuccessAt, items30d, health` (ok\|degraded\|failing\|unknown), `muted` (the caller's own mute) |
| `POST`/`DELETE /api/sources/{id}/mute` | | 204 |
| `POST /api/source-suggestions` | `{url, note?}` | 201, the created suggestion `{id, url, note, status, createdAt, reviewedAt, sourceId}`; 429 `{detail: "You can suggest up to 10 sources a day. Please try again tomorrow."}` past `BK_SUGGESTIONS_PER_USER_PER_DAY` (default 10) in any 24 hours |
| `GET /api/source-suggestions` | | the caller's suggestions, newest first |
| `GET /api/admin/sources` | `?status=` | `SourceOut[]`: the full record (`config`, `accessNote`, `schedule`, `effectiveSchedule`, `rateLimit`, `status`, `addedBy`, `configChangedAt`, ...) plus `health, lastSuccessAt, lastRunAt, items30d, promotionRuns` |
| `POST /api/admin/sources` | `SourceIn` (`name, homeUrl, publisher?, streams, kind, collectorType, config, schedule?, rateLimit?, accessNote?, suggestionId?`) | 201 `SourceDetailOut`; always created as `testing` |
| `GET /api/admin/sources/{id}` | | `SourceDetailOut` = `SourceOut` + `promotionGate {goodRuns, needed: 2, since, met}` (runs that succeeded and found items since `since` = the last config change) + `statusHistory [{at, oldStatus, newStatus, changedBy, reason}]`, newest first (`oldStatus` null = created; `reason` "created" or "config changed"). History starts with migration 0012; older sources have none. |
| `PATCH /api/admin/sources/{id}` | any `SourceIn` field except `suggestionId` | `SourceDetailOut`; a config or collector-type change on an active source sends it back to testing (decision 27) |
| `POST /api/admin/sources/{id}/status` | `{status}` | `SourceDetailOut`; 409 with the reason when the graph or the promotion gate refuses |
| `GET /api/admin/sources/{id}/runs` | `?status=running\|succeeded\|failed&limit=1..200 (50)&offset=` | `{total, items: [{id, startedAt, finishedAt, status, itemsFound, itemsNew, itemsFailed, error}]}`, newest first; the error log is `status=failed` |
| `POST /api/admin/sources/test-run` | `{collectorType, config, homeUrl?, streams?, rateLimit?}` | `PreviewOut {ok, error, items, totalParsed, requestsMade, elapsedSeconds}`; writes nothing. 429 `{detail: "Another test run is in progress; try again in a minute."}` when `BK_TEST_RUNS_MAX_CONCURRENT` (default 2) test runs of any type, browser_list included, are already running |
| `POST /api/admin/sources/{id}/test-run` | | the same, with the saved config |
| `GET /api/admin/collector-types` | | one entry per collector type, in spec order: `{type, implemented, schemaSource, fields}`; `schemaSource` is always `"model"` (every type has a config model; `"declared"` is no longer sent). Each field `{name, kind, required, help, default, options, min, max, fields}`. `name` is the key in `config`. `kind`: string, url, integer, number, boolean, choice (`options`), string_list, selector (a CSS string or `{css, attr}`), object (nested `fields`), object_list (nested `fields`), map (string to string), json. Mapped in `sources/collector_types.py` from `registry.config_forms()` (`collectors/forms.py`); help text is each model field's `description`. Shapes without a widget are `json` with the shapes in `help`: json_api `pagination` (a choice of page-number or next-link variants) and custom `options` (the fields of each allowlisted collector). |
| `GET /api/admin/source-suggestions` | `?status=suggested (default)\|accepted\|rejected` | suggestions with `userId, reviewedBy` |
| `POST /api/admin/source-suggestions/{id}/accept`, `/reject` | | the suggestion; then `POST /api/admin/sources` with `suggestionId` links the two |
| `GET /api/admin/catalogue` | `?needsReview=true&stream=&limit=&offset=` | `{total, items}`; the review queue is `needsReview=true` (items carry `reviewReasons`) |
| `POST /api/admin/catalogue/{id}/review` | | the item, `needsReview` cleared ("Mark reviewed") |
| `GET /api/admin/users` | | `[{id, email, name, role, status, createdAt, lastSignInAt}]`, oldest first (`lastSignInAt` null = never signed in) |
| `PATCH /api/admin/users/{id}` | `{role: "member"\|"admin"}` | the user. 400 on your own account; 409 if it would leave no active admin. Not in spec 3 (invite and deactivate only): needed so the first admin can add a second; **for the owner to confirm**. |
| `POST /api/admin/users/{id}/deactivate` | | the user; 400 on yourself, 409 for the last active admin (decision 20) |
| `GET /api/admin/invites` | `?status=pending\|expired\|accepted` | `[{id, email, invitedBy, createdAt, expiresAt, acceptedAt, status}]`, newest first |
| `POST /api/admin/invites` | `{email}` | 201 the invite (mail goes to the dev transport); 409 for an existing account |
| `DELETE /api/admin/invites/{id}` | | 204; 409 once accepted |

Collector config forms: every type has its own config model (`browser_list` is the `html_list` fields plus `wait_for`). The "declared" fallback for types without one is gone.
