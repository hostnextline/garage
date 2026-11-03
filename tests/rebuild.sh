#!/bin/bash
# rebuild the trial page and the team version, then refresh the local copy served on 8088 (its config.js stays)
set -e
T=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [ -n "$GARAGE_DIR" ]; then G=$GARAGE_DIR; elif [ -f "$T/../carnet.html" ]; then G=$(cd "$T/.." && pwd); else G=/home/claude/garage; fi
cd $G/web
python3 build.py >/dev/null
GARAGE_NODE_MODULES=$T/stack/node_modules python3 build_team.py >/dev/null 2>&1 || python3 build_team.py >/dev/null
D=$T/teamdist
for f in index.html client.html suivi.html sw.js manifest.webmanifest; do cp team/$f $D/$f; done
cp -r team/icons $D/ 2>/dev/null || true
echo "built $(stat -c %s $D/index.html) bytes"
