#!/usr/bin/env bash
# Local end-to-end smoke test of the whole stack, through the proxy.
#   deploy/smoke/run.sh            build, start, check (stack left running)
#   deploy/smoke/run.sh --down     the same, then remove containers, volumes, networks
# Run from the repository root with a local .env (docs/deploy.md, "Local stack").
# Uses docker-compose.local.yml (BK_ENV=dev, Mailpit) and deploy/smoke/compose.smoke.yml
# (a local page for the renderer). Fictional demo data only; no real email, no
# real sites, no model or search API calls. Needs node with Playwright on the host.
set -uo pipefail
cd "$(dirname "$0")/../.."
export COMPOSE="docker compose -f docker-compose.yml -f docker-compose.local.yml -f deploy/smoke/compose.smoke.yml --profile dev"
C=$COMPOSE
OUT=$(mktemp -d)
BASE=http://localhost:8080
EMAIL=owner@example.com
pass=0
fail=0
result() { # result PASS|FAIL name evidence
  if [ "$1" = PASS ]; then pass=$((pass + 1)); else fail=$((fail + 1)); fi
  echo "$1 $2: $3"
}
expect() { # expect name evidence command...  (PASS when the command succeeds)
  local name=$1 evidence=$2
  shift 2
  if "$@" >>"$OUT/cmd.log" 2>&1; then result PASS "$name" "$evidence"; else result FAIL "$name" "$evidence (see $OUT/cmd.log)"; fi
}

echo "== build and start"
$C build >"$OUT/build.log" 2>&1 || { echo "FAIL build (see $OUT/build.log)"; exit 1; }
$C up -d --wait >"$OUT/up.log" 2>&1 || { echo "FAIL up (see $OUT/up.log)"; $C ps; exit 1; }
for s in db api worker renderer proxy mailpit testpage; do
  h=$(docker inspect -f '{{.State.Health.Status}}' "$($C ps -q "$s")" 2>/dev/null)
  [ "$h" = healthy ] && result PASS "healthcheck $s" "$h" || result FAIL "healthcheck $s" "${h:-no container}"
done

echo "== database and seed"
expect "bk migrate (api container)" "alembic upgrade head" $C exec -T api bk migrate
out=$($C exec -T -e BK_FIRST_ADMIN_EMAIL=$EMAIL api bk bootstrap 2>&1)
grep -q '^admin: ' <<<"$out" && result PASS "bk bootstrap $EMAIL" "$(tr '\n' ';' <<<"$out")" || result FAIL "bk bootstrap" "$out"
out=$($C exec -T -e BK_FIRST_ADMIN_EMAIL=$EMAIL api bk demo-seed 2>&1)
grep -q 'demo catalogue' <<<"$out" && result PASS "bk demo-seed (local override, BK_ENV=dev)" "$(head -1 <<<"$out")" || result FAIL "bk demo-seed" "$out"
out=$($C exec -T -e BK_ENV=prod api bk demo-seed 2>&1); rc=$?
[ $rc -ne 0 ] && grep -q refused <<<"$out" && result PASS "bk demo-seed refused with BK_ENV=prod" "exit $rc: $(head -1 <<<"$out")" || result FAIL "demo-seed under prod" "exit $rc: $out"
prod_env=$(docker compose -f docker-compose.yml config --format json 2>/dev/null | python3 -c 'import json,sys; c=json.load(sys.stdin)["services"]; print(c["api"]["environment"]["BK_ENV"], c["worker"]["environment"]["BK_ENV"], c["api"]["environment"]["BK_COOKIE_SECURE"])')
[ "$prod_env" = "prod prod true" ] && result PASS "base compose file is prod (BK_ENV, secure cookies)" "$prod_env" || result FAIL "base compose prod defaults" "$prod_env"

echo "== browser flow through the proxy"
unsub=$($C exec -T api python -c "
from blackkite.config import get_settings
from blackkite.db.session import get_sessionmaker
from blackkite.db.models import User
from blackkite.delivery.unsubscribe import make_token
s = get_settings()
with get_sessionmaker()() as db:
    u = db.query(User).filter(User.email == '$EMAIL').one()
    print(make_token(s, u, 'digest'))
" 2>/dev/null | tail -1)
SMOKE_OUT=$OUT SMOKE_UNSUB_TOKEN=$unsub BASE=$BASE node deploy/smoke/browser.cjs >"$OUT/browser.log" 2>&1
cat "$OUT/browser.log"
pass=$((pass + $(grep -c '^PASS' "$OUT/browser.log")))
fail=$((fail + $(grep -c '^FAIL' "$OUT/browser.log")))

echo "== logs"
cal=$(cat "$OUT/calendar-token" 2>/dev/null)
proxylog=$($C logs --no-log-prefix proxy 2>&1)
apilog=$($C logs --no-log-prefix api 2>&1)
line=$(grep -o '"uri":"/api/calendar.ics?token=[^"]*"' <<<"$proxylog" | head -1)
[ -n "$cal" ] && [ -n "$line" ] && ! grep -qF "$cal" <<<"$proxylog" && grep -q 'token=\[redacted\]' <<<"$line" \
  && result PASS "proxy access log redacts the calendar token" "$line" || result FAIL "proxy log redaction" "${line:-no calendar line}"
! grep -qF "$cal" <<<"$apilog" && [ -n "$cal" ] && result PASS "api log never shows the calendar token" "$(grep -o '"GET /api/calendar.ics?token=[^ ]*' <<<"$apilog" | head -1)" || result FAIL "api log redaction" "token found"
[ -n "$unsub" ] && ! grep -qF "$unsub" <<<"$proxylog$apilog" && result PASS "unsubscribe token in no log" "token sent only in a JSON body" || result FAIL "unsubscribe token in logs" "found or missing"
! grep -Eq '"(GET|POST) /(auth/confirm|unsubscribe)[ ?#]' <<<"$apilog" && result PASS "/auth/confirm and /unsubscribe never reach the api" "no such request in the api access log" || result FAIL "SPA-only paths reached the api" "$(grep -E '/(auth/confirm|unsubscribe)' <<<"$apilog" | head -2)"
# Caddy's error log carries the request too: make the upstream fail and look.
$C stop api >>"$OUT/cmd.log" 2>&1
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/calendar.ics?token=errorlogsecret123")
$C start api >>"$OUT/cmd.log" 2>&1
errline=$($C logs --no-log-prefix proxy 2>&1 | grep -F 'calendar.ics' | grep -v '"status":200' | tail -1)
! $C logs proxy 2>&1 | grep -q errorlogsecret123 && [ "$code" = 502 ] && result PASS "proxy error log redacts tokens (upstream down)" "502; $(grep -o '"uri":"[^"]*"' <<<"$errline" | tail -1)" || result FAIL "proxy error log redaction" "status $code"
timeout 120 sh -c "until [ \"\$(docker inspect -f '{{.State.Health.Status}}' \$($C ps -q api))\" = healthy ]; do sleep 2; done"

echo "== X-Forwarded-For"
curl -s -o /dev/null -H 'X-Forwarded-For: 203.0.113.9' "$BASE/me?xff-check-1"
xline=$($C logs --no-log-prefix api 2>&1 | grep 'xff-check-1' | tail -1)
proxy_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$($C ps -q proxy)")
gateway=$(docker network inspect -f '{{(index .IPAM.Config 0).Gateway}}' blackkite_edge)
grep -q '203.0.113.9' <<<"$xline" && result FAIL "forged X-Forwarded-For through the proxy" "$xline" \
  || { grep -q "^INFO: *$gateway:" <<<"$xline" && result PASS "proxy overwrites X-Forwarded-For; api sees the real client" "proxy $proxy_ip, client $gateway: $xline" || result FAIL "X-Forwarded-For" "$xline"; }
$C exec -T worker python -c "import urllib.request as u; r=u.Request('http://api:8000/me?xff-check-2', headers={'X-Forwarded-For': '198.51.100.7'});
try: u.urlopen(r)
except Exception: pass" >>"$OUT/cmd.log" 2>&1
xline=$($C logs --no-log-prefix api 2>&1 | grep 'xff-check-2' | tail -1)
! grep -q '198.51.100.7' <<<"$xline" && [ -n "$xline" ] && result PASS "api ignores X-Forwarded-For from anything but the proxy" "$xline" || result FAIL "XFF from non-proxy trusted" "$xline"

echo "== renderer isolation"
rid=$($C ps -q renderer)
names=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$rid" | cut -d= -f1 | sort | tr '\n' ' ')
bad=$(tr ' ' '\n' <<<"$names" | grep -Ex 'BK_DATABASE_URL|ANTHROPIC_API_KEY|VOYAGE_API_KEY|BRAVE_API_KEY|RESEND_API_KEY|BK_UNSUBSCRIBE_SECRET|BK_CALENDAR_SECRET|BK_INGEST_IMAP_PASSWORD|BK_SMTP_PASSWORD|POSTGRES_PASSWORD|POSTGRES_USER|.*SECRET.*|.*PASSWORD.*|.*API_KEY.*')
[ -z "$bad" ] && result PASS "renderer env holds no secrets (docker inspect)" "names: $names" || result FAIL "renderer env" "$bad"
mounts=$(docker inspect -f '{{len .Mounts}} mounts, user {{.Config.User}}, caps dropped {{.HostConfig.CapDrop}}, nets {{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$rid")
result PASS "renderer container shape" "$mounts"
dbip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$($C ps -q db)")
out=$($C exec -T renderer python -c "
import socket
for target in ('db', '$dbip'):
    try:
        socket.create_connection((target, 5432), timeout=3).close(); print('CONNECTED', target)
    except Exception as e:
        print('refused', target, type(e).__name__, e)
" 2>&1)
! grep -q CONNECTED <<<"$out" && result PASS "renderer cannot reach db:5432" "$(tr '\n' ';' <<<"$out")" || result FAIL "renderer reached the db" "$out"
out=$($C run --rm --no-deps -T -e ANTHROPIC_API_KEY= renderer 2>&1); rc=$?
[ $rc -eq 2 ] && grep -q 'holds no secrets' <<<"$out" && result PASS "renderer refuses to start with a secret injected" "exit $rc: $(grep -o 'error:.*' <<<"$out")" || result FAIL "renderer started with a secret" "exit $rc: $out"
out=$($C exec -T api python - <<'PY' 2>&1
import json, os, urllib.error, urllib.request
def render(url, token):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request("http://renderer:8100/render", data=json.dumps({"url": url}).encode(), headers=h)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)
tok = os.environ["BK_RENDERER_TOKEN"]
s1, _ = render("http://testpage/", None)
s2, _ = render("http://testpage/", "0123456789abcdef" * 4)
s3, b = render("http://testpage/", tok)
s4, c = render("http://10.0.0.1/", tok)
ok = s1 == 401 and s2 == 401 and s3 == 200 and b.get("ok") and "rendered-by-chromium-7f3a" in b["html"] and c.get("kind") == "unsafe_url"
print("OK" if ok else "BAD", f"no token {s1}; wrong token {s2}; right token {s3} ok={b.get('ok')} script ran={'rendered-by-chromium-7f3a' in (b.get('html') or '')} requests={[(r['url'], r['outcome']) for r in b.get('request_log', [])]}; private address: {c.get('kind')} {c.get('error')}")
PY
)
grep -q '^OK' <<<"$out" && result PASS "api -> renderer renders a local page only with the token" "${out#OK }" || result FAIL "api -> renderer" "$out"

echo "== worker"
out=$($C exec -T worker bk worker --once 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q 'one tick done' <<<"$out" && result PASS "bk worker --once in the worker container" "exit 0: $(grep -o 'worker: one tick done' <<<"$out")" || result FAIL "bk worker --once" "exit $rc: $(tail -3 <<<"$out")"

echo "== backup and restore"
counts() { # counts SERVICE-EXEC-PREFIX...  -> "users opportunities profiles sources"
  "$@" psql -U blackkite -d blackkite -tAc "select (select count(*) from \"user\")||' '||(select count(*) from opportunity)||' '||(select count(*) from profile)||' '||(select count(*) from source)"
}
before=$(counts $C exec -T db)
dump=$(deploy/backup.sh "$OUT/backups" 2>>"$OUT/cmd.log" | awk '{print $1}')
[ -s "$dump" ] && result PASS "deploy/backup.sh" "$(basename "$dump"), $(du -h "$dump" | cut -f1), counts users/opps/profiles/sources: $before" || result FAIL "backup" "no dump"
# Restore into a fresh database server (new container, new volume).
docker run -d --name bk-smoke-restore -e POSTGRES_USER=blackkite -e POSTGRES_PASSWORD=restoretest -e POSTGRES_DB=blackkite pgvector/pgvector:pg16 >>"$OUT/cmd.log" 2>&1
timeout 60 sh -c 'until docker exec bk-smoke-restore pg_isready -U blackkite -d blackkite -h 127.0.0.1 >/dev/null 2>&1; do sleep 1; done'
docker exec -i bk-smoke-restore pg_restore -U blackkite -d blackkite --no-owner --exit-on-error <"$dump" >>"$OUT/cmd.log" 2>&1; rc=$?
fresh=$(counts docker exec bk-smoke-restore)
docker rm -f -v bk-smoke-restore >>"$OUT/cmd.log" 2>&1
[ $rc -eq 0 ] && [ "$fresh" = "$before" ] && result PASS "restore into a fresh database" "pg_restore exit 0; counts $fresh" || result FAIL "fresh restore" "exit $rc; $fresh vs $before"
# Restore over the stack's own database with deploy/restore.sh, after a change.
$C exec -T db psql -U blackkite -d blackkite -c "update \"user\" set name = 'changed after the dump'" >>"$OUT/cmd.log" 2>&1
deploy/restore.sh "$dump" --yes >>"$OUT/cmd.log" 2>&1; rc=$?
after=$(counts $C exec -T db)
changed=$($C exec -T db psql -U blackkite -d blackkite -tAc "select count(*) from \"user\" where name = 'changed after the dump'")
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/me")
[ $rc -eq 0 ] && [ "$after" = "$before" ] && [ "$changed" = 0 ] && [ "$code" = 401 ] && result PASS "deploy/restore.sh over the live stack" "exit 0; counts $after; post-dump change gone; stack back up (GET /me -> $code)" || result FAIL "restore.sh" "exit $rc; $after vs $before; changed=$changed; /me $code"

echo
echo "== $pass passed, $fail failed (logs in $OUT)"
if [ "${1:-}" = "--down" ]; then
  $C down -v --remove-orphans >>"$OUT/cmd.log" 2>&1 && echo "stack removed (containers, volumes, networks)"
fi
[ "$fail" -eq 0 ]
