#!/bin/bash
# (re)starts the local test stack (Postgres must already run on 54322)
S=/tmp/claude-0/-home-claude/a3bd0a01-f5c0-5b1c-a92a-e2ade1101bff/scratchpad/stack
cd $S
pkill -f "node_modules/deno/deno run" 2>/dev/null; for f in *.pid; do [ -f "$f" ] && kill $(cat "$f") 2>/dev/null; rm -f "$f"; done; sleep 0.5
nohup node gateway.js > gateway.log 2>&1 & echo $! > gateway.pid
nohup node mocks.js > mocks.log 2>&1 & echo $! > mocks.pid
SERVICE=$(node -e "console.log(require('./keys.json').service)"); ANON=$(node -e "console.log(require('./keys.json').anon)")
for f in en-route:9101 members:9102 vehicle:9103; do
  name=${f%%:*}; port=${f##*:}
  SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_SERVICE_ROLE_KEY=$SERVICE SUPABASE_ANON_KEY=$ANON GHL_BASE=http://127.0.0.1:9200 OSRM_BASE=http://127.0.0.1:9201 PHOTON_BASE=http://127.0.0.1:9201/photon VPIC_BASE=http://127.0.0.1:9201/vpic TOMTOM_BASE=http://127.0.0.1:9201/tomtom LOCAL_PORT=$port FN_FILE=file:///home/claude/garage/supabase/functions/$name/index.ts DENO_DIR=$S/denocache nohup ./node_modules/.bin/deno run --allow-net --allow-env --allow-read $S/fnwrap.ts > fn-$name.log 2>&1 & echo $! > fn-$name.pid
done
(cd $S/../teamdist && nohup python3 -m http.server 8088 --bind 127.0.0.1 > $S/static.log 2>&1 & echo $! > $S/static.pid)
