#!/bin/bash
# stops the local test copy (everything started by start_all.sh)
S=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
D=${PGDATA_DIR:-$(cat "$S/.pgdata" 2>/dev/null || true)}; D=${D:-$S/pg}   # (written by installer.sh)
PGBIN=${PGBIN:-$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)}
as_pg(){ if [ "$(id -u)" = 0 ]; then su postgres -c "$*"; else bash -c "$*"; fi; }
cd $S; pkill -f "node_modules/deno/deno run" 2>/dev/null
for f in *.pid *.pid2; do [ -f "$f" ] && kill $(cat "$f") 2>/dev/null; rm -f "$f"; done
for n in gateway.js mocks.js; do for pid in $(pgrep -f "node $n"); do kill $pid 2>/dev/null; done; done
as_pg "$PGBIN/pg_ctl -D $D/data stop -m fast" >/dev/null 2>&1; true
