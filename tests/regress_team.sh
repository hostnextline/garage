#!/bin/bash
# the team version on the local Supabase copy (one at a time: they share the same database)
cd "$(dirname "${BASH_SOURCE[0]}")"
for t in test_team test_offline test_client test_backup test_invite test_roles test_rights test_tour test_tour_fit test_tour_guards test_receipt test_google_login test_map test_sched test_i18n test_leave test_crew test_blocks test_tour_blocks test_quickfix test_tracking test_truckbtn test_specref test_payrdv test_dnd test_comptes test_dnd_top test_estimate_svc test_truckname; do
  echo "== $t"; timeout 1200 python3 $t.py 2>&1 | grep -E "FAIL|passed|Error|Traceback" | tail -8
done
echo TEAMDONE
