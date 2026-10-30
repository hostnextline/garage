#!/bin/bash
cd "$(dirname "$0")"
for t in test_carnet test_postal test_units test_clients test_tomtom test_link test_smart test_instant test_pclist test_svc test_est test_promo test_web test_google test_web_pc test_dash test_phone; do
  echo "== $t"; timeout 900 python3 $t.py 2>&1 | grep -E "FAIL|passed|Error|Traceback" | tail -8
done
echo "== test_api"; (cd stack && timeout 300 node test_api.js 2>&1 | grep -E "FAIL|passed|ok [0-9]+/" | tail -5)
echo DONE
