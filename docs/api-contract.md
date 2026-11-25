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

All JSON in camelCase. **Every member route below lives under `/api`** (e.g. `GET /api/feed`), so no API path collides with a web page (`/shortlist`, `/profiles` are also screens). `/auth/*`, `GET /me` and the Phase 3 admin routes (`/admin/sources*`, `/admin/source-suggestions*`) keep their paths; `/admin/catalogue` moves to `/api/admin/catalogue`, and the Phase 3 member source routes move too: `/api/sources`, `/api/sources/{id}/mute`, `/api/source-suggestions` (`/sources` is also a screen). Every route requires a session; every query filters by the caller (spec 6) and by `pipeline/visibility.py`.

| Route | Returns |
|---|---|
| `GET /feed?stream=&profile=&window=&verification=&source=&state=` | `FeedContent` exactly as `web/src/fixtures/types.ts` (user, sources, digest, items: `FeedItem[]`). Default order: closing soonest first (feed boards). Excludes dismissed, hard-filtered and not-visible items, and (decision 41) tenders and funding whose best active-profile row has no fit word (`fit` null or `"not-scored"`) unless the caller's state for the item is saved, acting or done, or it is the caller's own private item. Events and investments are unaffected; with `profile=`, that profile's row decides. Summary counts the web derives from `items` follow. |
| `GET /opportunities/{id}` | `FeedItem` plus `detail.fields` (extracted fields with their snippets), `detail.sources` (visible sources: name, url, isOriginal, firstSeen, lastSeen), `detail.documents` (names only, never content), `detail.changes`, `detail.note`. 404 for items the caller can't see, including other users' private items. |
| `PUT /opportunities/{id}/state` | body `{state: "saved"\|"dismissed"\|"acting"\|"done"\|"unseen", dismissReason?}`; per (user, opportunity) (decision 19). |
| `PUT /opportunities/{id}/note` | body `{note}` |
| `GET/POST/PATCH/DELETE /profiles` | the caller's profiles; scoring-relevant edits queue a backfill that the worker runs (spec 5, decision 36). |
| `GET/PUT /digest-settings` | channel email, frequency weekly\|off, day mon, `alertMinFit`: "strong"\|"good"\|null (null = alerts off; compared against the best active profile's fit word, never the numeric score), streams (decision 18). |
| `GET /shortlist` | saved/acting items, `FeedItem[]`, soonest first. Unchanged by decision 41: saved and acting items show with or without a fit word. |
| `POST /unsubscribe` | **No session** (decision 43). Body `{token}` as JSON (from the web page `/unsubscribe`, which reads `#token=` from its URL), or the RFC 8058 one-click form POST `List-Unsubscribe=One-Click` (urlencoded or multipart) with `?token=` in the query. A digest token sets the email digest's frequency to "off" (creating the setting row if absent); an alert token sets `alertMinFit` to null. Idempotent. 200 `{kind: "digest"\|"alert", detail: "You won't get these emails any more."}`; 400 for a bad, revoked or unknown-user token; 415 other content types; 429 rate-limited per client address (like `/auth/request-link`). `GET /unsubscribe` changes nothing and answers 405 "Use POST". Tokens: HMAC-SHA256 (key `BK_UNSUBSCRIBE_SECRET`) over user id, kind and the user's `unsubscribe_nonce`; rotating the nonce revokes old links. Every digest and alert carries the page link `{web}/unsubscribe#token=…` and the headers `List-Unsubscribe: <{api}/api/unsubscribe?token=…>` (plus `<mailto:…>` when `BK_UNSUBSCRIBE_MAILTO` is set) and `List-Unsubscribe-Post: List-Unsubscribe=One-Click`. |
| `PATCH /me`, `GET /me/export`, `DELETE /me` | name for the greeting; data export; account deletion (spec 10). |

Field mapping for `FeedItem`: `provisional` = true when the matched profile is provisional (spec 7.1: AI lab), shown as a label next to the profile; `state` = the caller's state for the item ("unseen"|"saved"|"dismissed"|"acting"|"done"), always sent on feed, shortlist and detail items; `fit` = fit_word, or `"not-scored"` when no score row exists for a scorable stream, or null for events/investments/closed; `topFlag` = first flag label, sent only when `fit` is "good" (feed boards: develoPPP "Good fit · needs matching funds"; WFP is Strong with a flag and shows the organisation); `detail.reasons` = reasons; `detail.toCheck` = first flag's `to_check`; `detail.trust.state` = `evidence._trust` (confirmed/unconfirmed/conflict); `detail.trust.desktop` / `.phone` = the two copy templates the web fixtures already use, filled from the source names and dates; `deadline` = Kigali date of deadline_at.

## 3. Digest (member-API track)

`DigestView` from `api/blackkite/delivery/digest.py` is built from scores: top items across the user's profiles, capped at 12, each stream capped (investments and events at 3 each, spec 7.1), plus a "closing in 7 days" block for saved items and the value line (spec 8). Weekly on Monday; urgent alert for items above the user's threshold closing within 5 days, the day they are found. Delivery is Mailpit/console only; nothing real is sent without the owner's go-ahead.
