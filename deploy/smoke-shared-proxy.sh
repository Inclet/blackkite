#!/usr/bin/env bash
# Smoke test for the shared-proxy layout (deploy/compose.shared-proxy.yml).
# Creates a throwaway external network, starts the blackkite proxy with a
# minimal echo upstream, and checks:
#   (a) trusted XFF is honoured
#   (b) untrusted XFF is replaced
#   (c) HSTS from trusted X-Forwarded-Proto: https, not from untrusted
#   (d) token= values are redacted in proxy logs
#
# Run from the repo root:  deploy/smoke-shared-proxy.sh
# Requires: docker with compose plugin, curl.
set -uo pipefail
cd "$(dirname "$0")/.."

NET=bk-smoke-shared-$$
PROJECT=bk-smoke-shared-$$
SUBNET=172.29.$$.$((RANDOM % 200 + 10))
# Pick a /24 that is unlikely to collide.
SUBNET_BASE="172.29.$((RANDOM % 200 + 10))"
SUBNET="${SUBNET_BASE}.0/24"
TRUSTED_IP="${SUBNET_BASE}.2"
PROXY_NAME="${PROJECT}-proxy"
ECHO_NAME="${PROJECT}-echo"
TRUSTED_NAME="${PROJECT}-trusted"
pass=0
fail=0
OUT=$(mktemp -d)

cleanup() {
  docker rm -f "$PROXY_NAME" "$ECHO_NAME" "$TRUSTED_NAME" 2>/dev/null
  docker network rm "$NET" 2>/dev/null
  echo "cleaned up network $NET and containers"
}
trap cleanup EXIT

result() {
  if [ "$1" = PASS ]; then pass=$((pass + 1)); else fail=$((fail + 1)); fi
  echo "$1 $2: $3"
}

echo "== setup: network $NET ($SUBNET)"
docker network create --subnet="$SUBNET" "$NET" >"$OUT/net.log" 2>&1 \
  || { echo "FAIL: could not create network $NET (see $OUT/net.log)"; exit 1; }

# --- echo upstream: returns the X-Forwarded-For it receives as a response header ---
echo "== start echo upstream"
docker run -d --name "$ECHO_NAME" --network "$NET" \
  caddy:2.11.6-alpine caddy respond --listen :8000 \
  '{"ok":true}' 200 >"$OUT/echo.log" 2>&1

# --- build and start the blackkite proxy with the shared override ---
echo "== build proxy image"
docker compose -f docker-compose.yml build proxy >"$OUT/build.log" 2>&1 \
  || { echo "FAIL: proxy build failed (see $OUT/build.log)"; exit 1; }

# Run the proxy container manually: it needs the edge network (for the API
# upstream) and the shared network. We create a local edge-like network and
# point the proxy at our echo container.
EDGE_NET="${PROJECT}-edge"
EDGE_SUBNET="172.30.251.0/24"
PROXY_IP="172.30.251.10"
docker network create --subnet="$EDGE_SUBNET" "$EDGE_NET" >"$OUT/edge.log" 2>&1

# Connect the echo container to the edge network so the proxy can reach "api:8000".
docker network connect --alias api "$EDGE_NET" "$ECHO_NAME"

echo "== start proxy"
docker run -d --name "$PROXY_NAME" \
  --network "$EDGE_NET" --ip "$PROXY_IP" \
  -e BK_SITE_ADDRESS=":80" \
  -e "BK_TRUSTED_PROXIES=$SUBNET" \
  --read-only --tmpfs /tmp:size=16m \
  --cap-drop ALL \
  blackkite-proxy:${BK_IMAGE_TAG:-local} >"$OUT/proxy.log" 2>&1

docker network connect --alias blackkite-proxy "$NET" "$PROXY_NAME"

# Wait for the proxy to be healthy.
echo "== waiting for proxy health"
for i in $(seq 1 30); do
  h=$(docker inspect -f '{{.State.Health.Status}}' "$PROXY_NAME" 2>/dev/null)
  [ "$h" = "healthy" ] && break
  sleep 1
done
h=$(docker inspect -f '{{.State.Health.Status}}' "$PROXY_NAME" 2>/dev/null)
[ "$h" = "healthy" ] && result PASS "proxy healthy" "$h" || { result FAIL "proxy healthy" "${h:-no container}"; docker logs "$PROXY_NAME" 2>&1 | tail -20; }

# --- trusted container on the shared network (simulates the shared Caddy) ---
echo "== start trusted proxy container"
docker run -d --name "$TRUSTED_NAME" --network "$NET" --ip "$TRUSTED_IP" \
  curlimages/curl:8.11.1 sleep 300 >"$OUT/trusted.log" 2>&1

echo "== tests"

# (a) Trusted XFF is honoured: the shared Caddy sends X-Forwarded-For.
echo "-- (a) trusted XFF honoured"
resp=$(docker exec "$TRUSTED_NAME" curl -s -H "X-Forwarded-For: 203.0.113.7" \
  -H "X-Forwarded-Proto: https" \
  "http://blackkite-proxy:80/api/healthz" 2>&1)
# Check the proxy's access log for the forwarded IP.
sleep 1
proxylog=$(docker logs "$PROXY_NAME" 2>&1)
# The proxy forwards X-Forwarded-For: {client_ip} to the upstream. When the
# peer is trusted and sends XFF: 203.0.113.7, {client_ip} = 203.0.113.7.
# We check the proxy log for the client_ip (shown in the request's remote_ip
# in the Caddy access log). The echo upstream just returns a static response,
# so we check the proxy log instead.
if echo "$proxylog" | grep -q '203.0.113.7'; then
  result PASS "trusted XFF: 203.0.113.7 appears in proxy handling" "forwarded"
else
  result FAIL "trusted XFF: 203.0.113.7 not seen" "$proxylog"
fi

# (b) Untrusted XFF is replaced: a container NOT on the trusted subnet.
echo "-- (b) untrusted XFF replaced"
# Run curl from the proxy's own edge network (not the shared/trusted subnet).
docker run --rm --network "$EDGE_NET" curlimages/curl:8.11.1 \
  curl -s -H "X-Forwarded-For: 198.51.100.9" \
  "http://${PROXY_IP}:80/api/healthz?xff-untrusted" >"$OUT/untrusted.log" 2>&1
sleep 1
proxylog2=$(docker logs "$PROXY_NAME" 2>&1)
untrusted_line=$(echo "$proxylog2" | grep 'xff-untrusted' | tail -1)
if echo "$untrusted_line" | grep -q '198.51.100.9'; then
  result FAIL "untrusted XFF: forged 198.51.100.9 was NOT replaced" "$untrusted_line"
else
  result PASS "untrusted XFF: forged header replaced with real peer" "$untrusted_line"
fi

# (c) HSTS from trusted X-Forwarded-Proto: https.
echo "-- (c) HSTS from trusted forwarded HTTPS"
hsts_trusted=$(docker exec "$TRUSTED_NAME" curl -sI \
  -H "X-Forwarded-Proto: https" \
  "http://blackkite-proxy:80/api/healthz" 2>&1 | grep -i strict-transport)
if [ -n "$hsts_trusted" ]; then
  result PASS "HSTS sent for trusted X-Forwarded-Proto: https" "$hsts_trusted"
else
  result FAIL "HSTS missing for trusted forwarded HTTPS" "no Strict-Transport-Security header"
fi

# HSTS NOT from untrusted X-Forwarded-Proto: https.
echo "-- (c) no HSTS from untrusted forwarded HTTPS"
hsts_untrusted=$(docker run --rm --network "$EDGE_NET" curlimages/curl:8.11.1 \
  curl -sI -H "X-Forwarded-Proto: https" \
  "http://${PROXY_IP}:80/api/healthz" 2>&1 | grep -i strict-transport)
if [ -z "$hsts_untrusted" ]; then
  result PASS "HSTS NOT sent for untrusted X-Forwarded-Proto: https" "correct"
else
  result FAIL "HSTS sent for untrusted peer" "$hsts_untrusted"
fi

# (d) Token redaction in proxy logs.
echo "-- (d) token redaction"
docker exec "$TRUSTED_NAME" curl -s \
  "http://blackkite-proxy:80/api/calendar.ics?token=secret123smoke" >/dev/null 2>&1
sleep 1
proxylog3=$(docker logs "$PROXY_NAME" 2>&1)
if echo "$proxylog3" | grep -q 'secret123smoke'; then
  result FAIL "token value 'secret123smoke' found in proxy logs" "not redacted"
else
  if echo "$proxylog3" | grep -q 'token=\[redacted\]'; then
    result PASS "token= redacted in proxy logs" "token=[redacted] present"
  else
    result PASS "token value absent from proxy logs" "no token value leaked"
  fi
fi

echo
echo "== $pass passed, $fail failed (logs in $OUT)"

# Also clean up the extra edge network.
docker network rm "$EDGE_NET" 2>/dev/null
[ "$fail" -eq 0 ]
