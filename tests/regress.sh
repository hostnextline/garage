#!/bin/bash
cd "$(dirname "${BASH_SOURCE[0]}")"
for t in test_carnet test_postal; do
  echo "== $t (as on a Wednesday: written for weekdays)"; timeout 900 python3 run_on_day.py $(python3 -c "import datetime as d; t=d.date.today(); print(t + d.timedelta(days=(2 - t.weekday()) % 7))") $t.py 2>&1 | grep -E "FAIL|passed|Error|Traceback" | tail -8
done
# the dashboard counts « the last 30 days » and « today »: a Wednesday in the middle of the month
echo "== test_dash (a mid-month Wednesday)"; timeout 900 python3 run_on_day.py $(python3 -c "import datetime as d; t=d.date.today().replace(day=15); print(t + d.timedelta(days=(2 - t.weekday()) % 7))") test_dash.py 2>&1 | grep -E "FAIL|passed|Error|Traceback" | tail -8
for t in test_units test_clients test_tomtom test_link test_smart test_instant test_pclist test_svc test_est test_promo test_web test_google test_web_pc test_phone test_jobs test_trucks test_tresor test_vin test_parts test_simple test_pc_layout test_install test_lux test_quickfix_trial; do
  echo "== $t"; timeout 900 python3 $t.py 2>&1 | grep -E "FAIL|passed|Error|Traceback" | tail -8
done
echo DONE
