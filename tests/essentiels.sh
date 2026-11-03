#!/bin/bash
# Les tests essentiels (environ 20 minutes) : le serveur seul, puis les parties de l'app qui comptent le plus
# (réservation par bloc, factures, hors ligne, page du client, droits, réglages). Ceux que GitHub lance à chaque envoi.
cd "$(dirname "${BASH_SOURCE[0]}")"
bash rebuild.sh || exit 1
bash with_stack.sh '
  echo "== test_api"; (cd stack && timeout 300 node test_api.js 2>&1 | grep -E "FAIL|passed|ok [0-9]+/" | tail -8)
  for t in test_quickfix test_team test_blocks test_offline test_client test_crew test_leave; do echo "== $t"; timeout 1200 python3 $t.py 2>&1 | grep -E "^FAIL|passed|Error|Traceback" | tail -8; done
  for t in test_quickfix_trial; do echo "== $t"; timeout 600 python3 $t.py 2>&1 | grep -E "^FAIL|passed|Error|Traceback" | tail -8; done
  echo "== test_carnet (un mercredi)"; timeout 900 python3 run_on_day.py $(python3 -c "import datetime as d; t=d.date.today(); print(t + d.timedelta(days=(2 - t.weekday()) % 7))") test_carnet.py 2>&1 | grep -E "^FAIL|passed|Error|Traceback" | tail -8
' > essentiels.log 2>&1
cat essentiels.log
bad=$(grep -c -E "^FAIL|Traceback|Error:" essentiels.log)
fails=$(grep -E "^([0-9]+)/([0-9]+) passed" essentiels.log | awk -F'[/ ]' '$1 != $2' | wc -l)
api=$(grep -c -E "passed, [1-9][0-9]* failed" essentiels.log)
if [ "$bad" != "0" ] || [ "$fails" != "0" ] || [ "$api" != "0" ]; then echo "ÉCHECS"; exit 1; fi
echo "TOUT EST VERT (tests essentiels)"
