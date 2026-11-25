# API contract

`api-schemas.json` is the member API's JSON Schema for the responses the web app
reads (feed, opportunity, profiles and their per-type data, digest settings,
`/me`) and the bodies it sends (`ProfileIn`, `DigestSettingsIn`, `StateIn`), dumped from the
API's own Pydantic models. `omitIfNone` lists, per model, the keys the API leaves
out when empty instead of sending `null`.

Two unit tests (part of `npm test`) check against it, with the small checker in
`schemaCheck.ts` (no dependency, nothing imported from `api/`):

- `stub.contract.test.ts`: the e2e stub (`tests/e2e/stubApi.ts`) answers in the
  real shapes.
- `src/api/requestContract.test.ts`: what the profile editor and digest form send
  is what the API accepts.

The stub test also pins the shapes the screens depend on: `DigestSettingsIn` has
`alertMinFit` and no `alertThreshold`, `FeedItem` (and `OpportunityOut`) require
`provisional`, and `StateIn` exists with the dismiss reason codes in
`src/api/types.ts` (`DISMISS_REASONS`).

## Regenerate

After any change to the API's member models, from `web/`:

    npm run contract:schemas

which runs `cd ../api && uv run python ../web/tests/contract/dump_schemas.py`.
Commit the new `api-schemas.json`, then run `npm test`; a failure names the path
and the mismatch.
