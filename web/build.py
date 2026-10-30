"""Builds web/index.html (the hosted "version rapide") from carnet.html + shim.js."""
import os, re, json, shutil
D = os.path.dirname(os.path.abspath(__file__))

def pwa(out_dir, name, short, ident):
    """Home-screen icon: manifest + icons next to index.html (the page links them)."""
    m = json.load(open(os.path.join(D, 'pwa.json'), encoding='utf8'))  # template
    m.update(name=name, short_name=short, id=ident)
    json.dump(m, open(os.path.join(out_dir, 'manifest.webmanifest'), 'w', encoding='utf8'), ensure_ascii=False, indent=2)
    if os.path.abspath(out_dir) != D:
        shutil.copytree(os.path.join(D, 'icons'), os.path.join(out_dir, 'icons'), dirs_exist_ok=True)
PWA_TAGS = ('<link rel="manifest" href="manifest.webmanifest"><link rel="icon" type="image/png" href="icons/icon-192.png">'
            '<link rel="apple-touch-icon" href="icons/icon-180.png"><meta name="mobile-web-app-capable" content="yes">'
            '<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="default">'
            '<meta name="theme-color" media="(prefers-color-scheme: light)" content="#E9DED2"><meta name="theme-color" media="(prefers-color-scheme: dark)" content="#1E1915">')
app = open(os.path.join(D, '..', 'carnet.html'), encoding='utf8').read()
shim = open(os.path.join(D, 'shim.js'), encoding='utf8').read()
cut = app.index('</style>') + len('</style>')
head, body = app[:cut], app[cut:]
head = head.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', '')
reset = 'html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}'
out = ('<!doctype html><html lang="fr-CA"><head><meta charset="utf-8">'
       '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
       '<meta name="robots" content="noindex,nofollow">' + PWA_TAGS + '<meta name="apple-mobile-web-app-title" content="Garage essai">'
              '<link rel="preconnect" href="https://photon.komoot.io" crossorigin><link rel="preconnect" href="https://api.tomtom.com" crossorigin><link rel="preconnect" href="https://maps.googleapis.com">'
       '<style>' + reset + '</style>\n' + head + '\n<script>\n' + shim + '\n</script>\n</head><body>\n' + body + '\n</body></html>\n')
assert out.count('<script>') >= 2
pwa(D, 'Carnet du garage (essai)', 'Garage essai', 'garage-essai')
open(os.path.join(D, 'index.html'), 'w', encoding='utf8').write(out)
print('index.html', len(out), 'bytes')
