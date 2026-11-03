#!/bin/bash
# Construit la copie locale de Supabase qui sert aux tests. Une seule fois ; la relancer ne casse rien.
#   - Postgres (celui de la machine, version 16), Auth (GoTrue v2.180.0), PostgREST v12.2.3, les fonctions du garage (Deno),
#   - de faux GoHighLevel, Stripe, TomTom, OSRM, Photon, vPIC et GitHub : aucun vrai service n'est appelé,
#   - la base : les rôles de Supabase, puis chaque changement de supabase/migrations, dans l'ordre,
#   - des clés inventées ici, qui ne servent qu'à cette copie (jamais les vraies clés du garage),
#   - la version équipe de l'app, construite pour cette copie (servie sur http://127.0.0.1:8088/).
# Ensuite : bash tests/stack/start_all.sh (démarrer), bash tests/tout_tester.sh (tout tester), bash tests/stack/arreter.sh.
set -e
S=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); T=$(cd "$S/.." && pwd)
if [ -n "$GARAGE_DIR" ]; then G=$GARAGE_DIR; elif [ -f "$T/../carnet.html" ]; then G=$(cd "$T/.." && pwd); else G=/home/claude/garage; fi
# where the database lives (Postgres runs as « postgres » when we are root: its folder must be one it can reach)
D=${PGDATA_DIR:-$(cat "$S/.pgdata" 2>/dev/null || true)}
if [ -z "$D" ]; then if [ "$(id -u)" = 0 ]; then D=/var/lib/postgresql/garage-$(echo -n "$S" | md5sum | cut -c1-8); else D=$S/pg; fi; fi
echo "$D" > "$S/.pgdata"
PGBIN=${PGBIN:-$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)}
as_pg(){ if [ "$(id -u)" = 0 ]; then su postgres -c "$*"; else bash -c "$*"; fi; }
say(){ echo "== $*"; }
[ -x "$PGBIN/initdb" ] || { echo "Postgres 16 manque (sudo apt-get install postgresql-16)"; exit 1; }
cd $S

say "programmes (versions fixes, vérifiées)"
if [ ! -x gotrue/auth ]; then
  curl -sSfL -o auth.tgz https://github.com/supabase/auth/releases/download/v2.180.0/auth-v2.180.0-x86.tar.gz
  echo "3fe064281f5cf7bda94251a3bd9e87a690d081381d9ea93b1491163735209e2e  auth.tgz" | sha256sum -c -
  mkdir -p gotrue && tar -xzf auth.tgz -C gotrue && rm -f auth.tgz
fi
if [ ! -x postgrest ]; then
  curl -sSfL -o postgrest.tar.xz https://github.com/PostgREST/postgrest/releases/download/v12.2.3/postgrest-v12.2.3-linux-static-x64.tar.xz
  echo "9f71269e61ac3a940281e93ff415760f5957e430e475ba4c3889f3ede7d5527c  postgrest.tar.xz" | sha256sum -c -
  tar -xJf postgrest.tar.xz && rm -f postgrest.tar.xz
fi
[ -x node_modules/.bin/deno ] || npm ci --no-audit --no-fund
# the libraries the tests serve in place of the internet (same versions as the app asks for)
inst(){ local d=$1 first=${2%@*}; shift; [ -d "$T/$d/node_modules/$first" ] || npm install --prefix "$T/$d" --no-audit --no-fund --no-save "$@" >/dev/null; }
inst deps jspdf@2.5.1; inst xlsxlib xlsx@0.18.5; inst zxinglib @zxing/library@0.21.3; inst qrlib qrcode-generator@1.4.4
inst ocrlib tesseract.js@7.0.0 tesseract.js-core@7.0.0 @tesseract.js-data/eng@1.0.0 @tesseract.js-data/fra@1.0.0
# the receipt reader (Tesseract), served by the test copy in place of the internet
O=$T/teamdist/ocrtest; N=$T/ocrlib/node_modules
if [ ! -f "$O/lang/fra.traineddata.gz" ]; then
  mkdir -p $O/npm/tesseract.js@7.0.0/dist $O/npm/tesseract.js-core@7.0.0 $O/lang
  cp $N/tesseract.js/dist/tesseract.min.js $N/tesseract.js/dist/worker.min.js $O/npm/tesseract.js@7.0.0/dist/
  cp $N/tesseract.js-core/*.js $N/tesseract.js-core/*.wasm $O/npm/tesseract.js-core@7.0.0/
  cp $N/@tesseract.js-data/eng/4.0.0_best_int/eng.traineddata.gz $N/@tesseract.js-data/fra/4.0.0_best_int/fra.traineddata.gz $O/lang/
fi
# the fake camera of the VIN test (a barcode on a door sticker, filmed): made from the pictures, too big to keep
[ -f "$T/vin/vin_civic.y4m" ] || { command -v ffmpeg >/dev/null && bash "$T/vin/make_videos.sh"; } || echo "   (ffmpeg manque : le test de la caméra VIN ne pourra pas rouler)"

say "clés de cette copie"
[ -f keys.json ] || node keys.js > keys.json
SECRET=$(node -e "console.log(require('./keys.json').secret)"); ANON=$(node -e "console.log(require('./keys.json').anon)")
cat > gotrue.env <<EOT
GOTRUE_DB_DRIVER=postgres
DATABASE_URL="postgres://supabase_auth_admin:authpw@127.0.0.1:54322/postgres?search_path=auth&sslmode=disable"
GOTRUE_DB_DATABASE_URL="postgres://supabase_auth_admin:authpw@127.0.0.1:54322/postgres?search_path=auth&sslmode=disable"
GOTRUE_DB_NAMESPACE=auth
GOTRUE_DB_MIGRATIONS_PATH=$S/gotrue/migrations
GOTRUE_JWT_SECRET=$SECRET
GOTRUE_JWT_EXP=3600
GOTRUE_JWT_AUD=authenticated
GOTRUE_JWT_DEFAULT_GROUP_NAME=authenticated
GOTRUE_JWT_ADMIN_ROLES=service_role
GOTRUE_SITE_URL=http://127.0.0.1:8088
API_EXTERNAL_URL=http://127.0.0.1:54321/auth/v1
GOTRUE_API_HOST=127.0.0.1
PORT=9999
GOTRUE_DISABLE_SIGNUP=true
GOTRUE_EXTERNAL_EMAIL_ENABLED=true
GOTRUE_MAILER_AUTOCONFIRM=true
GOTRUE_LOG_LEVEL=warn
EOT
cat > postgrest.conf <<EOT
db-uri = "postgres://authenticator:authpw@127.0.0.1:54322/postgres"
db-schemas = "public"
db-anon-role = "anon"
jwt-secret = "$SECRET"
server-host = "127.0.0.1"
server-port = 3000
db-max-rows = 1000
log-level = "warn"
EOT

if [ ! -f "$D/data/PG_VERSION" ]; then
  say "la base (vide), puis les changements du garage"
  mkdir -p "$D"; [ "$(id -u)" = 0 ] && chown -R postgres "$D"
  as_pg "$PGBIN/initdb -D $D/data -U postgres --auth=trust -E UTF8 --locale=C.UTF-8" >/dev/null
  as_pg "$PGBIN/pg_ctl -D $D/data -l $D/pg.log -o '-p 54322 -k /tmp -c listen_addresses=127.0.0.1' start" >/dev/null
  for i in $(seq 1 50); do pg_isready -h 127.0.0.1 -p 54322 -q && break; sleep 0.2; done
  psql -h 127.0.0.1 -p 54322 -U postgres -q -v ON_ERROR_STOP=1 -f base.sql
  # Auth creates its own tables at its first start
  (cd gotrue && set -a && . ../gotrue.env && set +a && ./auth > ../gotrue-first.log 2>&1 &)
  for i in $(seq 1 100); do [ "$(psql -h 127.0.0.1 -p 54322 -U postgres -Atc "select to_regclass('auth.users') is not null and exists (select 1 from pg_proc where proname = 'uid' and pronamespace = 'auth'::regnamespace)")" = "t" ] && break; sleep 0.3; done
  pkill -f "$S/gotrue/auth" 2>/dev/null || pkill -x auth 2>/dev/null || true
  for f in $(ls "$G"/supabase/migrations/*.sql | sort); do psql -h 127.0.0.1 -p 54322 -U postgres -q -v ON_ERROR_STOP=1 -f "$f"; echo "   $(basename "$f")"; done
  as_pg "$PGBIN/pg_ctl -D $D/data stop -m fast" >/dev/null
fi

say "la version équipe pour cette copie (http://127.0.0.1:8088/)"
python3 "$G/web/build_team.py" --out "$T/teamdist" --url http://127.0.0.1:54321 --key "$ANON" --vendor "$S/node_modules" >/dev/null
python3 "$G/web/build.py" >/dev/null
say "prêt"
