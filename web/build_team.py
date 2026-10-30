"""Builds the team version (logins, roles, map, « en route ») into web/team/:
   index.html  the notebook + supa.js + equipe.js (+ shim.js for the address search)
   suivi.html  the public page the client opens from the text message
   config.js   where the garage's Supabase is (written only if missing; the public key is meant to be public)
   vendor/     supabase-js and Leaflet, served from the same place (no outside CDN)
Usage: python3 build_team.py [--url URL --key KEY] [--out DIR] [--vendor NODE_MODULES]"""
import os, sys, shutil, argparse
D = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('--out', default=os.path.join(D, 'team'))
ap.add_argument('--url'); ap.add_argument('--key')
ap.add_argument('--vendor', default=os.environ.get('GARAGE_NODE_MODULES', ''))
a = ap.parse_args()
os.makedirs(os.path.join(a.out, 'vendor'), exist_ok=True)

app = open(os.path.join(D, '..', 'carnet.html'), encoding='utf8').read()
read = lambda n: open(os.path.join(D, n), encoding='utf8').read()
cut = app.index('</style>') + len('</style>')
head, body = app[:cut], app[cut:]
head = head.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', '')
head = head.replace('<title>Carnet du garage mobile</title>', '<title>Carnet du garage · équipe</title>')
reset = 'html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}body.locked{overflow:hidden}'
icon = "data:image/svg+xml," + "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%231D4B77'/%3E%3Cpath d='M18 44l8-8m10-10l10-10M26 36a8 8 0 1 0 10-10' stroke='%23F2B200' stroke-width='6' fill='none' stroke-linecap='round'/%3E%3C/svg%3E"
out = ('<!doctype html><html lang="fr-CA"><head><meta charset="utf-8">'
       '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
       '<meta name="robots" content="noindex,nofollow"><meta name="theme-color" content="#1D4B77">'
       '<link rel="icon" href="' + icon + '"><link rel="stylesheet" href="vendor/leaflet.css">'
       '<link rel="preconnect" href="https://photon.komoot.io" crossorigin><link rel="preconnect" href="https://api.tomtom.com" crossorigin>'
       '<style>' + reset + '</style>\n' + head + '\n'
       '<script>window.__GARAGE_TEAM = true;</script>\n'
       '<script src="config.js"></script>\n<script src="vendor/supabase.js"></script>\n<script src="vendor/leaflet.js"></script>\n'
       '<script>\n' + read('shim.js') + '\n</script>\n<script>\n' + read('supa.js') + '\n</script>\n<script>\n' + read('equipe.js') + '\n</script>\n'
       '</head><body>\n' + body + '\n</body></html>\n')
open(os.path.join(a.out, 'index.html'), 'w', encoding='utf8').write(out)
shutil.copyfile(os.path.join(D, 'suivi.html'), os.path.join(a.out, 'suivi.html'))
cfg = os.path.join(a.out, 'config.js')
if a.url and a.key:
    open(cfg, 'w', encoding='utf8').write("/* Où est la base du garage. La clé publique (anon / publishable) est faite pour être publique : les règles d'accès protègent les données. */\nwindow.GARAGE_CFG = {url:%r, key:%r};\n" % (a.url.rstrip('/'), a.key))
elif not os.path.exists(cfg):
    open(cfg, 'w', encoding='utf8').write("window.GARAGE_CFG = {url:'', key:''};\n")
if a.vendor:
    shutil.copyfile(os.path.join(a.vendor, '@supabase/supabase-js/dist/umd/supabase.js'), os.path.join(a.out, 'vendor/supabase.js'))
    for n in ('leaflet.js', 'leaflet.css'):
        shutil.copyfile(os.path.join(a.vendor, 'leaflet/dist', n), os.path.join(a.out, 'vendor', n))
    shutil.copytree(os.path.join(a.vendor, 'leaflet/dist/images'), os.path.join(a.out, 'vendor/images'), dirs_exist_ok=True)
print('team/index.html', len(out), 'bytes ->', a.out)
