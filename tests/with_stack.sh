#!/bin/bash
# runs the given commands with the local Supabase copy up (started here, so it lives as long as the tests)
cd /tmp/claude-0/-home-claude/a3bd0a01-f5c0-5b1c-a92a-e2ade1101bff/scratchpad
ok=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9102/)
if [ "$ok" = "000" ]; then bash stack/start_all.sh > stack_start.log 2>&1; fi
for i in $(seq 1 60); do a=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9200/); b=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9102/); c=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8088/); d=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9105/); [ "$a" != "000" ] && [ "$b" != "000" ] && [ "$c" != "000" ] && [ "$d" != "000" ] && break; sleep 2; done
eval "$@"
