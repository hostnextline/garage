#!/bin/bash
# starts the whole local Supabase copy: Postgres, Auth, PostgREST, functions, fakes, static site
S=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
D=${PGDATA_DIR:-$(cat "$S/.pgdata" 2>/dev/null || true)}; D=${D:-$S/pg}   # (written by installer.sh)
PGBIN=${PGBIN:-$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)}
as_pg(){ if [ "$(id -u)" = 0 ]; then su postgres -c "$*"; else bash -c "$*"; fi; }
# everything is down when this runs: old pid numbers may now belong to other programs
rm -f $S/*.pid $S/*.pid2
# whatever still holds our ports (an earlier run, another copy of the bench) is stopped first: otherwise the tests
# would talk to it (old routes, other keys, another database)
for n in "node gateway.js" "node mocks.js" "node_modules/deno/deno run" "http.server 8088"; do pkill -f "$n" 2>/dev/null; done
pkill -x postgrest 2>/dev/null; pkill -x auth 2>/dev/null
other=$(psql -h 127.0.0.1 -p 54322 -U postgres -Atc "show data_directory" 2>/dev/null)
[ -n "$other" ] && [ "$other" != "$D/data" ] && as_pg "$PGBIN/pg_ctl -D $other stop -m fast" >/dev/null 2>&1
sleep 0.5
as_pg "$PGBIN/pg_ctl -D $D/data -l $D/pg.log -o '-p 54322 -k /tmp -c listen_addresses=127.0.0.1' start" >/dev/null 2>&1
for i in $(seq 1 30); do pg_isready -h 127.0.0.1 -p 54322 -q && break; sleep 0.3; done
cd $S/gotrue && (set -a; . $S/gotrue.env; set +a; nohup ./auth > $S/gotrue.log 2>&1 & echo $! > $S/gotrue.pid2)
cd $S && (nohup ./postgrest postgrest.conf > postgrest.log 2>&1 & echo $! > $S/postgrest.pid2)
bash $S/up.sh
