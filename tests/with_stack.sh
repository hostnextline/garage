#!/bin/bash
# runs the given commands with the local Supabase copy up (started here if it is down, so it lives as long as the tests)
cd "$(dirname "${BASH_SOURCE[0]}")"
up(){ [ "$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$1/)" != "000" ]; }
if ! up 9102 || ! up 3000; then bash stack/start_all.sh > stack_start.log 2>&1; fi
ready=no
for i in $(seq 1 60); do if up 9200 && up 9102 && up 8088 && up 9105 && up 3000 && up 9999; then ready=yes; break; fi; sleep 2; done
[ $ready = yes ] || echo "ATTENTION : la copie locale n'a pas démarré au complet (voir stack/*.log)"
eval "$@"
