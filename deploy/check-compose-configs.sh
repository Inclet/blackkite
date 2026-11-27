#!/usr/bin/env bash
# Validate compose configurations for both standalone and shared-proxy layouts.
# Run from the repo root:  deploy/check-compose-configs.sh
# Requires: docker compose (v2.24+), python3.
set -uo pipefail
cd "$(dirname "$0")/.."

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

pass=0
fail=0
result() {
  if [ "$1" = PASS ]; then pass=$((pass + 1)); else fail=$((fail + 1)); fi
  echo "$1 $2: $3"
}

echo "== standalone layout (docker-compose.yml)"

# Standalone config succeeds.
standalone=$(BK_DOMAIN=test.example.com \
  POSTGRES_PASSWORD=aaaaaaaaaaaabbbbbbbbbbbb \
  BK_RENDERER_TOKEN=aaaaaaaaaaaabbbbbbbbbbbbcccccccccccc \
  docker compose -f docker-compose.yml config --format json 2>"$tmpdir/standalone-err" || true)
if [ -n "$standalone" ]; then
  result PASS "standalone config parses" "ok"
else
  result FAIL "standalone config parses" "$(cat "$tmpdir/standalone-err")"
fi

# Standalone publishes 80, 443, 443/udp.
ports=$(echo "$standalone" | python3 -c "
import json, sys
c = json.load(sys.stdin)
proxy = c['services']['proxy']
published = sorted(f\"{p['published']}:{p['target']}/{p.get('protocol','tcp')}\" for p in proxy.get('ports', []))
print(' '.join(published))
" 2>/dev/null)
expected="443:443/tcp 443:443/udp 80:80/tcp"
[ "$ports" = "$expected" ] \
  && result PASS "standalone proxy publishes 80, 443, 443/udp" "$ports" \
  || result FAIL "standalone proxy ports" "got '$ports', expected '$expected'"

echo "== shared-proxy layout (docker-compose.yml + deploy/compose.shared-proxy.yml)"

# Shared config succeeds with required variables.
shared=$(BK_DOMAIN=test.example.com \
  POSTGRES_PASSWORD=aaaaaaaaaaaabbbbbbbbbbbb \
  BK_RENDERER_TOKEN=aaaaaaaaaaaabbbbbbbbbbbbcccccccccccc \
  BK_CADDY_NETWORK=octant-caddy \
  BK_TRUSTED_PROXIES=172.18.0.0/16 \
  docker compose -f docker-compose.yml -f deploy/compose.shared-proxy.yml config --format json 2>"$tmpdir/shared-err" || true)
if [ -n "$shared" ]; then
  result PASS "shared config parses with BK_CADDY_NETWORK + BK_TRUSTED_PROXIES" "ok"
else
  result FAIL "shared config parses" "$(cat "$tmpdir/shared-err")"
fi

# Proxy has no ports in shared config.
shared_ports=$(echo "$shared" | python3 -c "
import json, sys
c = json.load(sys.stdin)
proxy = c['services']['proxy']
print(len(proxy.get('ports', [])))
" 2>/dev/null)
[ "$shared_ports" = "0" ] \
  && result PASS "shared proxy has no published ports" "ports: []" \
  || result FAIL "shared proxy still has ports" "$shared_ports port(s)"

# BK_SITE_ADDRESS is :80 in shared config.
site_addr=$(echo "$shared" | python3 -c "
import json, sys
c = json.load(sys.stdin)
print(c['services']['proxy']['environment'].get('BK_SITE_ADDRESS', ''))
" 2>/dev/null)
[ "$site_addr" = ":80" ] \
  && result PASS "shared BK_SITE_ADDRESS is :80" "$site_addr" \
  || result FAIL "shared BK_SITE_ADDRESS" "'$site_addr'"

# Only the proxy is on the shared network.
shared_net_services=$(echo "$shared" | python3 -c "
import json, sys
c = json.load(sys.stdin)
net_name = 'octant-caddy'
on_it = []
for svc, cfg in c['services'].items():
    for n in cfg.get('networks', {}):
        nobj = c.get('networks', {}).get(n, {})
        if nobj.get('name') == net_name or n == 'shared_edge':
            on_it.append(svc)
print(' '.join(sorted(set(on_it))))
" 2>/dev/null)
[ "$shared_net_services" = "proxy" ] \
  && result PASS "only proxy is on the shared network" "$shared_net_services" \
  || result FAIL "services on shared network" "'$shared_net_services'"

echo "== missing variables"

# Shared config fails without BK_CADDY_NETWORK.
err_no_net=$(BK_DOMAIN=test.example.com \
  POSTGRES_PASSWORD=aaaaaaaaaaaabbbbbbbbbbbb \
  BK_RENDERER_TOKEN=aaaaaaaaaaaabbbbbbbbbbbbcccccccccccc \
  BK_TRUSTED_PROXIES=172.18.0.0/16 \
  docker compose -f docker-compose.yml -f deploy/compose.shared-proxy.yml config 2>&1 >/dev/null; echo "exit:$?")
echo "$err_no_net" | grep -q 'BK_CADDY_NETWORK' && echo "$err_no_net" | grep -q 'exit:1' \
  && result PASS "shared config fails without BK_CADDY_NETWORK" "names the variable" \
  || result FAIL "shared config without BK_CADDY_NETWORK" "$err_no_net"

# Shared config fails without BK_TRUSTED_PROXIES.
err_no_tp=$(BK_DOMAIN=test.example.com \
  POSTGRES_PASSWORD=aaaaaaaaaaaabbbbbbbbbbbb \
  BK_RENDERER_TOKEN=aaaaaaaaaaaabbbbbbbbbbbbcccccccccccc \
  BK_CADDY_NETWORK=octant-caddy \
  docker compose -f docker-compose.yml -f deploy/compose.shared-proxy.yml config 2>&1 >/dev/null; echo "exit:$?")
echo "$err_no_tp" | grep -q 'BK_TRUSTED_PROXIES' && echo "$err_no_tp" | grep -q 'exit:1' \
  && result PASS "shared config fails without BK_TRUSTED_PROXIES" "names the variable" \
  || result FAIL "shared config without BK_TRUSTED_PROXIES" "$err_no_tp"

echo
echo "== $pass passed, $fail failed"
[ "$fail" -eq 0 ]
