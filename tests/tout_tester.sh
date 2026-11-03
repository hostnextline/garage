#!/bin/bash
# Tout tester, de A à Z, sur la copie locale de Supabase (jamais sur la vraie base) : la version d'essai, la version équipe,
# le serveur, l'anglais, la mise en page en français et en anglais. Chaque suite écrit « n/m passed » ; à la fin, un
# résumé. Code de sortie 1 s'il y a un seul échec. (Une première fois : bash stack/installer.sh)
cd "$(dirname "${BASH_SOURCE[0]}")"
mkdir -p i18n scan
bash rebuild.sh || exit 1
bash with_stack.sh 'bash regress.sh > trial_reg.log 2>&1; bash full_run.sh'
echo; echo "===== Résumé ====="
cat trial_reg.log team_reg.log | grep -E "^== |passed|ok [0-9]+/|still in French|errors|FAIL|Traceback|Error" | grep -v "^PASS"
bad=$(cat trial_reg.log team_reg.log | grep -c -E "^FAIL|Traceback|Error:|passed, [1-9][0-9]* failed")
fails=$(cat trial_reg.log team_reg.log | grep -E "^([0-9]+)/([0-9]+) passed" | awk -F'[/ ]' '$1 != $2' | wc -l)
if [ "$bad" != "0" ] || [ "$fails" != "0" ]; then echo "ÉCHECS : $bad ligne(s) en échec, $fails suite(s) incomplète(s)"; exit 1; fi
echo "TOUT EST VERT"
