#!/bin/bash
# Les tests essentiels (environ 10 minutes) : le serveur seul, puis les parties de l'app qui comptent le plus
# (réservation par bloc, factures, hors ligne, page du client, droits, réglages). Ceux que GitHub lance à chaque envoi.
# Chaque suite garde son détail dans logs/<suite>.log ; en cas d'échec, les lignes utiles sont recopiées ici.
cd "$(dirname "${BASH_SOURCE[0]}")"
mkdir -p logs; export L=$(pwd)/logs
bash rebuild.sh || exit 1
bash with_stack.sh '
  run(){ local n=$1; shift; echo "== $n"; timeout 1200 "$@" > $L/$n.log 2>&1; grep -E "^FAIL|passed|Error|Traceback|^DIAG" $L/$n.log | tail -8
         if grep -q -E "^FAIL|Traceback|passed, [1-9][0-9]* failed" $L/$n.log; then echo "--- détails ($n)"; grep -E "^FAIL|^DIAG|File \".*(test_|team_seed|tour_walk)|Error|Call log|waiting for|  - " $L/$n.log | tail -25; fi; }
  (cd stack && run test_api node test_api.js)
  for t in test_quickfix test_tracking test_truckbtn test_specref test_payrdv test_dnd test_comptes test_dnd_top test_estimate_svc test_pick test_team test_blocks test_offline test_client test_crew test_leave test_quickfix_trial; do run $t python3 $t.py; done
  run test_carnet python3 run_on_day.py $(python3 -c "import datetime as d; t=d.date.today(); print(t + d.timedelta(days=(2 - t.weekday()) % 7))") test_carnet.py
' > essentiels.log 2>&1
cat essentiels.log
bad=$(grep -c -E "^FAIL|Traceback|Error:" essentiels.log)
fails=$(grep -E "^([0-9]+)/([0-9]+) passed" essentiels.log | awk -F'[/ ]' '$1 != $2' | wc -l)
api=$(grep -c -E "passed, [1-9][0-9]* failed" essentiels.log)
if [ "$bad" != "0" ] || [ "$fails" != "0" ] || [ "$api" != "0" ]; then echo "ÉCHECS"; exit 1; fi
echo "TOUT EST VERT (tests essentiels)"
