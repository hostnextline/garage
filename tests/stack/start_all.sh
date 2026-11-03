#!/bin/bash
# starts the whole local Supabase copy: Postgres, Auth, PostgREST, functions, fakes, static site
S=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
D=${PGDATA_DIR:-$(cat "$S/.pgdata" 2>/dev/null || true)}; D=${D:-$S/pg}   # (written by installer.sh)
PGBIN=${PGBIN:-$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)}
as_pg(){ if [ "$(id -u)" = 0 ]; then su postgres -c "$*"; else bash -c "$*"; fi; }
# everything is down when this runs: old pid numbers may now belong to other programs
rm -f $S/*.pid $S/*.pid2
# a gateway or fake left from an earlier run would keep its port with old routes
for n in gateway.js mocks.js; do for pid in $(pgrep -f "node $n"); do kill $pid 2>/dev/null; done; done; sleep 0.5
as_pg "$PGBIN/pg_ctl -D $D/data -l $D/pg.log -o '-p 54322 -k /tmp -c listen_addresses=127.0.0.1' start" >/dev/null 2>&1
for i in $(seq 1 30); do pg_isready -h 127.0.0.1 -p 54322 -q && break; sleep 0.3; done
cd $S/gotrue && (set -a; . $S/gotrue.env; set +a; nohup ./auth > $S/gotrue.log 2>&1 & echo $! > $S/gotrue.pid2)
cd $S && (nohup ./postgrest postgrest.conf > postgrest.log 2>&1 & echo $! > $S/postgrest.pid2)
bash $S/up.sh
