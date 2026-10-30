#!/bin/bash
# starts the whole local Supabase copy: Postgres, Auth, PostgREST, functions, fakes, static site
S=/tmp/claude-0/-home-claude/a3bd0a01-f5c0-5b1c-a92a-e2ade1101bff/scratchpad/stack
D=/var/lib/postgresql/garage-test
su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D $D/data -l $D/pg.log -o '-p 54322 -k /tmp -c listen_addresses=127.0.0.1' start" >/dev/null 2>&1
for i in $(seq 1 30); do pg_isready -h 127.0.0.1 -p 54322 -q && break; sleep 0.3; done
cd $S/gotrue && (set -a; . $S/gotrue.env; set +a; nohup ./auth > $S/gotrue.log 2>&1 & echo $! > $S/gotrue.pid2)
cd $S && (nohup ./postgrest postgrest.conf > postgrest.log 2>&1 & echo $! > $S/postgrest.pid2)
bash $S/up.sh
