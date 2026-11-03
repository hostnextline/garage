cd "$(dirname "${BASH_SOURCE[0]}")"
bash regress_team.sh > team_reg.log 2>&1
echo "== test_api" >> team_reg.log; (cd stack && timeout 300 node test_api.js 2>&1 | grep -E "FAIL|passed|ok [0-9]+/" | tail -8) >> team_reg.log
echo "== i18n_coverage" >> team_reg.log; timeout 2400 python3 i18n_coverage.py > cov.log 2>&1; tail -12 cov.log >> team_reg.log
echo "== i18n_blocks" >> team_reg.log; timeout 600 python3 i18n_blocks.py 2>&1 | tail -8 >> team_reg.log
echo "== scan fr" >> team_reg.log; timeout 1500 python3 scan_layout.py 2>&1 | tail -3 >> team_reg.log
echo "== scan en" >> team_reg.log; I18N_LANG=en timeout 1500 python3 scan_layout.py 2>&1 | tail -3 >> team_reg.log
echo "== trial en" >> team_reg.log; timeout 600 python3 i18n_trial.py 2>&1 | tail -3 >> team_reg.log
echo ALLDONE >> team_reg.log
