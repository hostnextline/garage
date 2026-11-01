#!/bin/bash
# the team version on the local Supabase copy (one at a time: they share the same database)
cd /tmp/claude-0/-home-claude/a3bd0a01-f5c0-5b1c-a92a-e2ade1101bff/scratchpad
for t in test_team test_offline test_client test_backup test_invite test_roles test_rights test_tour test_tour_fit test_tour_guards test_receipt test_google_login test_map test_sched; do
  echo "== $t"; timeout 1200 python3 $t.py 2>&1 | grep -E "FAIL|passed|Error|Traceback" | tail -8
done
echo TEAMDONE
