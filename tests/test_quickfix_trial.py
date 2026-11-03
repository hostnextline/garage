"""Version d'essai (sans compte, les données dans ce navigateur) : les réglages enregistrent seulement ce qui a changé,
même avec deux onglets ouverts en même temps (ce que l'autre onglet a changé reste)."""
import json, os
from chemins import GARAGE, SAUVEGARDES   # (où est l'app : ici ou dans le dépôt)
from playwright.sync_api import sync_playwright
PAGE = open(GARAGE + '/web/index.html', encoding='utf8').read()
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)[:300]) if detail and not cond else ''), flush=True)

with sync_playwright() as pl:
    b = pl.chromium.launch()
    cx = b.new_context(viewport={'width': 1100, 'height': 900}, timezone_id='America/Toronto', locale='fr-CA')
    cx.add_init_script("try{localStorage.setItem('gm.ui','full')}catch(e){} window.__allSettings = 1;")
    cx.route('https://local.test/', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=PAGE))
    cx.route('https://fonts.googleapis.com/**', lambda r: r.fulfill(status=200, content_type='text/css', body=''))
    cx.route('https://fonts.gstatic.com/**', lambda r: r.abort())
    errs = []
    def tab():
        p = cx.new_page(); p.on('pageerror', lambda e: errs.append(str(e)))
        p.goto('https://local.test/#reglages'); p.wait_for_selector('#s-save', timeout=15000); p.wait_for_timeout(500); return p
    A = tab()
    A.fill('#s-name', 'Garage Essai'); A.click('#s-save'); A.wait_for_timeout(600)          # a first save (the settings exist)
    store = lambda p: p.evaluate("JSON.parse(localStorage.getItem('gm.web.db') || '{}')['config/main'] || {}")
    check('first save: the settings are kept in this browser', store(A).get('biz', {}).get('name') == 'Garage Essai', store(A).get('biz'))
    A.goto('https://local.test/#reglages'); A.wait_for_selector('#s-save'); A.wait_for_timeout(500)
    A.fill('#s-rate', '111'); A.wait_for_timeout(200)                                          # tab A: typing…
    B = tab()
    B.fill('#s-goal', '4321'); B.click('#s-save'); B.wait_for_timeout(600)                     # …tab B saves another field
    B.evaluate("document.querySelector('.lux-sw[data-v=\"emeraude\"]') && document.querySelector('.lux-sw[data-v=\"emeraude\"]').click()"); B.wait_for_timeout(600)
    A.wait_for_timeout(400); A.click('#s-save'); A.wait_for_timeout(700)
    c = store(A)
    check('two tabs: tab A\'s change is saved (rate 111 $)', c.get('rate') == 111, c.get('rate'))
    check('…and tab B\'s changes stay: the goal (a field tab A showed but did not touch) and the colors', c.get('goal') == 4321 and c.get('lux') == 'emeraude', (c.get('goal'), c.get('lux')))
    check('…the name saved first is still there', c.get('biz', {}).get('name') == 'Garage Essai')
    check('no errors', not errs, errs[:3])
    b.close()
n = sum(1 for _, ok in results if ok); print(f'\n{n}/{len(results)} passed')
