#!/usr/bin/env bash
# Smoke test for the shared-proxy layout (deploy/compose.shared-proxy.yml).
# Creates throwaway Docker networks and containers, starts the blackkite proxy
# with an echo upstream that reflects the X-Forwarded-For and X-Forwarded-Proto
# it receives, and checks:
#   (a) trusted-peer XFF passthrough (upstream sees the forwarded client IP)
#   (b) untrusted-peer forged XFF stripped (upstream does NOT see the forged IP)
#   (c) HSTS only for forwarded HTTPS from a trusted peer, not from untrusted
#   (d) token= values are redacted in proxy logs
#
# Run from the repo root:  deploy/smoke-shared-proxy.sh
# Requires: docker with compose plugin, curl.
set -uo pipefail
cd "$(dirname "$0")/.."

NET=bk-smoke-shared-$$
PROJECT=bk-smoke-shared-$$
EDGE_NET="${PROJECT}-edge"
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
  docker network rm "$NET" "$EDGE_NET" 2>/dev/null
  rm -rf "$OUT"
  echo "cleaned up containers, networks and temp files"
}
trap cleanup EXIT

result() {
  if [ "$1" = PASS ]; then pass=$((pass + 1)); else fail=$((fail + 1)); fi
  echo "$1 $2: $3"
}

echo "== setup: network $NET ($SUBNET)"
docker network create --subnet="$SUBNET" "$NET" >"$OUT/net.log" 2>&1 \
  || { echo "FAIL: could not create network $NET (see $OUT/net.log)"; exit 1; }

# --- echo upstream: returns the X-Forwarded-For and X-Forwarded-Proto it receives ---
echo "== start echo upstream"
cat > "$OUT/echo-caddyfile" <<'EOF'
{
	admin off
}
:8000 {
	header X-Echo-Xff "{header.X-Forwarded-For}"
	header X-Echo-Xfp "{header.X-Forwarded-Proto}"
	respond "ok" 200
}
EOF

docker run -d --name "$ECHO_NAME" --network "$NET" \
  -v "$OUT/echo-caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy:2.11.6-alpine >"$OUT/echo.log" 2>&1

# --- build and start the blackkite proxy with the shared override ---
echo "== build proxy image"
docker compose -f docker-compose.yml build proxy >"$OUT/build.log" 2>&1 \
  || { echo "FAIL: proxy build failed (see $OUT/build.log)"; exit 1; }

# The proxy needs two networks: the edge network (reaching the echo "api") and
# the shared network (where the trusted peer lives). The untrusted peer uses
# only the edge network, which is outside BK_TRUSTED_PROXIES.
EDGE_SUBNET="172.30.251.0/24"
PROXY_IP="172.30.251.10"
docker network create --subnet="$EDGE_SUBNET" "$EDGE_NET" >"$OUT/edge.log" 2>&1

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
for _ in $(seq 1 30); do
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

# (a) Trusted XFF is honoured: the shared Caddy sends X-Forwarded-For and
#     X-Forwarded-Proto.  The echo upstream reflects what it received as
#     X-Echo-Xff and X-Echo-Xfp response headers.
echo "-- (a) trusted XFF honoured"
trusted_resp=$(docker exec "$TRUSTED_NAME" curl -sI \
  -H "X-Forwarded-For: 203.0.113.7" \
  -H "X-Forwarded-Proto: https" \
  "http://blackkite-proxy:80/api/healthz" 2>&1)
trusted_xff=$(echo "$trusted_resp" | grep -i 'x-echo-xff' | tr -d '\r')
if echo "$trusted_xff" | grep -q '203.0.113.7'; then
  result PASS "(a) trusted XFF: upstream sees 203.0.113.7" "$trusted_xff"
else
  result FAIL "(a) trusted XFF: upstream does not see 203.0.113.7" "got: $trusted_xff"
fi

# (b) Untrusted XFF is replaced: a container NOT on the trusted subnet sends a
#     forged header.  The echo upstream must NOT see the forged address.
echo "-- (b) untrusted XFF replaced"
untrusted_resp=$(docker run --rm --network "$EDGE_NET" curlimages/curl:8.11.1 \
  curl -sI -H "X-Forwarded-For: 198.51.100.9" \
  "http://${PROXY_IP}:80/api/healthz" 2>&1)
untrusted_xff=$(echo "$untrusted_resp" | grep -i 'x-echo-xff' | tr -d '\r')
if echo "$untrusted_xff" | grep -q '198.51.100.9'; then
  result FAIL "(b) untrusted XFF: forged 198.51.100.9 passed through" "$untrusted_xff"
else
  result PASS "(b) untrusted XFF: forged header replaced" "$untrusted_xff"
fi

# (c) HSTS from trusted X-Forwarded-Proto: https (reuse the trusted response).
echo "-- (c) HSTS from trusted forwarded HTTPS"
hsts_trusted=$(echo "$trusted_resp" | grep -i 'strict-transport-security' | tr -d '\r')
if [ -n "$hsts_trusted" ]; then
  result PASS "(c) HSTS sent for trusted X-Forwarded-Proto: https" "$hsts_trusted"
else
  result FAIL "(c) HSTS missing for trusted forwarded HTTPS" "no Strict-Transport-Security header"
fi

# HSTS must NOT appear for the same header from an untrusted peer.
echo "-- (c) no HSTS from untrusted forwarded HTTPS"
untrusted_hsts_resp=$(docker run --rm --network "$EDGE_NET" curlimages/curl:8.11.1 \
  curl -sI -H "X-Forwarded-Proto: https" \
  "http://${PROXY_IP}:80/api/healthz" 2>&1)
hsts_untrusted=$(echo "$untrusted_hsts_resp" | grep -i 'strict-transport-security' | tr -d '\r')
if [ -z "$hsts_untrusted" ]; then
  result PASS "(c) HSTS NOT sent for untrusted X-Forwarded-Proto: https" "correct"
else
  result FAIL "(c) HSTS sent for untrusted peer" "$hsts_untrusted"
fi

# (d) Token redaction in proxy logs.
echo "-- (d) token redaction"
docker exec "$TRUSTED_NAME" curl -s \
  "http://blackkite-proxy:80/api/calendar.ics?token=secret123smoke" >/dev/null 2>&1
sleep 1
proxylog=$(docker logs "$PROXY_NAME" 2>&1)
if echo "$proxylog" | grep -q 'secret123smoke'; then
  result FAIL "(d) token value 'secret123smoke' found in proxy logs" "not redacted"
else
  if echo "$proxylog" | grep -q 'token=\[redacted\]'; then
    result PASS "(d) token= redacted in proxy logs" "token=[redacted] present"
  else
    result PASS "(d) token value absent from proxy logs" "no token value leaked"
  fi
fi

echo
echo "== $pass passed, $fail failed"
[ "$fail" -eq 0 ]
