"""Builds web/index.html (the hosted "version rapide") from carnet.html + shim.js."""
import os, re
D = os.path.dirname(os.path.abspath(__file__))
app = open(os.path.join(D, '..', 'carnet.html'), encoding='utf8').read()
shim = open(os.path.join(D, 'shim.js'), encoding='utf8').read()
cut = app.index('</style>') + len('</style>')
head, body = app[:cut], app[cut:]
head = head.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', '')
reset = 'html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}'
icon = "data:image/svg+xml," + "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%231D4B77'/%3E%3Cpath d='M18 44l8-8m10-10l10-10M26 36a8 8 0 1 0 10-10' stroke='%23F2B200' stroke-width='6' fill='none' stroke-linecap='round'/%3E%3C/svg%3E"
out = ('<!doctype html><html lang="fr-CA"><head><meta charset="utf-8">'
       '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
       '<meta name="robots" content="noindex,nofollow"><meta name="theme-color" content="#1D4B77">'
       '<link rel="icon" href="' + icon + '">'
       '<link rel="preconnect" href="https://photon.komoot.io" crossorigin><link rel="preconnect" href="https://api.tomtom.com" crossorigin><link rel="preconnect" href="https://maps.googleapis.com">'
       '<style>' + reset + '</style>\n' + head + '\n<script>\n' + shim + '\n</script>\n</head><body>\n' + body + '\n</body></html>\n')
assert out.count('<script>') >= 2
open(os.path.join(D, 'index.html'), 'w', encoding='utf8').write(out)
print('index.html', len(out), 'bytes')
