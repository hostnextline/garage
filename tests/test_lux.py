"""Mode vitrine plus transparent + couleurs de luxe (Réglages → Couleurs de l'app), version essai (sans serveur).
Le choix est gardé pour tout le garage (config), l'appareil s'en souvient pour ouvrir dans les bonnes couleurs."""
import json, os, re
from chemins import GARAGE, SAUVEGARDES   # (où est l'app : ici ou dans le dépôt)
from playwright.sync_api import sync_playwright
SC = os.path.dirname(os.path.abspath(__file__))
PAGE = open(GARAGE + '/carnet.html', encoding='utf8').read()
MOCK = open(os.path.join(SC, 'mock.js'), encoding='utf8').read()
RESET = 'html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}'
METAS = '<meta name="theme-color" media="(prefers-color-scheme: light)" content="#E9DED2"><meta name="theme-color" media="(prefers-color-scheme: dark)" content="#1E1915">'
base = {'biz': {'name': 'Garage NextLine', 'phone': '514 555-0000'}, 'mechanics': ['Saleh'], 'rate': 120, 'taxesOn': True, 'prefix': 'F-', 'startNo': 1}
def harness(mode, ui):
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">' + METAS +
            f'<style>{RESET}</style><script>try{{localStorage.setItem("gm.ui",{json.dumps(ui)})}}catch(e){{}}window.__MOCK={json.dumps(mode)};</script><script>{MOCK}</script></head><body>{PAGE}</body></html>')
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)[:300]) if detail and not cond else ''), flush=True)
ERRS = []
def open_page(br, seed, width=1280, ui='full', scheme='light', hash='reglages', ctx=None):
    ctx = ctx or br.new_context(viewport={'width': width, 'height': 860}, color_scheme=scheme, timezone_id='America/Toronto', locale='fr-CA', has_touch=width < 700)
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: ERRS.append(str(e)))
    pg.on('console', lambda m: ERRS.append(m.text) if m.type == 'error' and 'fonts.g' not in m.text and 'ERR_FAILED' not in m.text else None)
    body = harness({'seed': seed}, ui)
    pg.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=body) if r.request.url.startswith('https://local.test/') else r.abort())
    pg.goto('https://local.test/#' + hash); pg.wait_for_timeout(700)
    return ctx, pg
def attrs(pg): return pg.evaluate("[document.documentElement.getAttribute('data-lux'), document.documentElement.getAttribute('data-theme')]")
def var(pg, name): return pg.evaluate("n => getComputedStyle(document.documentElement).getPropertyValue(n).trim()", name)
def store(pg, path): return pg.evaluate('p => window.__store[p] || null', path)
def ls(pg): return pg.evaluate("localStorage.getItem('gm.lux')")
def metas(pg): return pg.evaluate("[...document.querySelectorAll('meta[name=\"theme-color\"]')].map(m => m.content)")
def pressed(pg): return pg.evaluate("[...document.querySelectorAll('.lux-sw[aria-pressed=\"true\"]')].map(b => b.dataset.v)")
def toast(pg): return (pg.locator('#toast').text_content() or '')
def alpha(c):
    m = re.match(r'rgba\(([^)]*)\)', c.replace(' ', '')); return float(m.group(1).split(',')[3]) if m else 1.0
def open_colors(pg):
    if pg.locator('.lux-sw[data-v="noir"]').is_visible(): return   # (the part is still open)
    pg.locator('.ph-row[data-act="ph-sec"]', has_text='Couleurs').first.click(); pg.wait_for_timeout(300)
with sync_playwright() as p:
    br = p.chromium.launch()
    seed = {'config/main': dict(base)}
    ctx, pg = open_page(br, seed)
    check('Réglages: a « Couleurs de l\'app » part (« Sable · mode vitrine »)', pg.locator('.ph-row[data-act="ph-sec"]', has_text='Couleurs de l\'app').count() == 1 and 'Sable · mode vitrine' in pg.locator('.ph-row[data-act="ph-sec"]', has_text='Couleurs').first.text_content())
    open_colors(pg)
    names = pg.evaluate("[...document.querySelectorAll('.lux-sw .lux-n')].map(x => x.textContent)")
    check('9 colors to choose: Sable, HIS clair, HIS sombre, Champagne, Platine, Noir et or, Émeraude, Saphir, Bordeaux', names == ['Sable', 'HIS clair', 'HIS sombre', 'Champagne', 'Platine', 'Noir et or', 'Émeraude', 'Saphir', 'Bordeaux'], names)
    check('each one shows a small preview of its look (background, a glass card, the accent)', pg.locator('.lux-sw .lux-pv i').count() == 9 and pg.evaluate("getComputedStyle(document.querySelector('.lux-sw[data-v=\"noir\"] .lux-pv')).backgroundImage").startswith('radial-gradient'))
    check('Sable is chosen at the start (the look follows the phone: no forced light/dark)', pressed(pg) == ['sable'] and attrs(pg) == [None, None], [pressed(pg), attrs(pg)])
    check('more see-through glass (panels about 40 % white, cards about 56 %)', alpha(var(pg, '--glass')) <= 0.42 and alpha(var(pg, '--card')) <= 0.58, [var(pg, '--glass'), var(pg, '--card')])
    check('page titles in a refined serif (luxury look)', 'Playfair Display' in pg.evaluate("getComputedStyle(document.querySelector('h1')).fontFamily"))
    check('the colors are saved on touch: no « Enregistrer » under this part', not pg.locator('#s-save').is_visible())
    pg.screenshot(path='lux_pick_sable.png')
    pg.click('.lux-sw[data-v="champagne"]'); pg.wait_for_timeout(500)
    check('touch « Champagne »: the app changes right away (light ivory and gold)', attrs(pg) == ['champagne', 'light'] and var(pg, '--signal').upper() == '#B4892F' and pressed(pg) == ['champagne'], [attrs(pg), var(pg, '--signal')])
    check('…saved for the garage (config), with a message', (store(pg, 'config/main') or {}).get('lux') == 'champagne' and 'Champagne' in toast(pg), [store(pg, 'config/main'), toast(pg)])
    check('…the rest of the settings are untouched', (store(pg, 'config/main') or {}).get('biz', {}).get('name') == 'Garage NextLine' and (store(pg, 'config/main') or {}).get('rate') == 120)
    check('…the phone bar takes the same color (theme-color)', metas(pg) == ['#EFE4CC', '#EFE4CC'], metas(pg))
    pg.click('.lux-sw[data-v="noir"]'); pg.wait_for_timeout(500)
    check('« Noir et or »: deep black, gold buttons, always dark', attrs(pg) == ['noir', 'dark'] and var(pg, '--paper').upper() == '#0C0B09' and 'gradient' in pg.evaluate("getComputedStyle(document.querySelector('.btn.primary')).backgroundImage") and pressed(pg) == ['noir'], [attrs(pg), var(pg, '--paper')])
    check('…the device remembers it (opens in these colors next time)', ls(pg) == 'noir')
    pg.screenshot(path='lux_noir_settings.png')
    for k, theme, paper in (('emeraude', 'dark', '#05170F'), ('saphir', 'dark', '#060E26'), ('bordeaux', 'dark', '#190509'), ('platine', 'light', '#F3F5F8')):
        pg.click('.lux-sw[data-v="%s"]' % k); pg.wait_for_timeout(350)
        check('« %s »: its own colors (%s)' % (k, paper), attrs(pg) == [k, theme] and var(pg, '--paper').upper() == paper and (store(pg, 'config/main') or {}).get('lux') == k, [attrs(pg), var(pg, '--paper')])
    # the two H.I.S colors (black, chrome and red, like the logo)
    pg.click('.lux-sw[data-v="his-sombre"]'); pg.wait_for_timeout(500)
    btn = lambda: pg.evaluate("getComputedStyle(document.querySelector('.btn.primary')).backgroundImage")
    check('« HIS sombre »: black background, always dark, saved for the garage, with a message', attrs(pg) == ['his-sombre', 'dark'] and var(pg, '--paper').upper() == '#09090A' and (store(pg, 'config/main') or {}).get('lux') == 'his-sombre' and 'HIS sombre' in toast(pg) and pressed(pg) == ['his-sombre'], [attrs(pg), var(pg, '--paper'), toast(pg)])
    check('…red H.I.S buttons (white text), chrome for what is chosen, red for the signal', 'rgb(225, 34, 43)' in btn() and var(pg, '--btn-ink').upper() == '#FFFFFF' and var(pg, '--sel-bg').upper() == '#E4E8EE' and var(pg, '--signal').upper() == '#FF3B45', [btn(), var(pg, '--sel-bg')])
    check('…the phone bar black, the device remembers it', metas(pg) == ['#09090A', '#09090A'] and ls(pg) == 'his-sombre', [metas(pg), ls(pg)])
    pg.screenshot(path='lux_his_sombre_settings.png')
    pg.click('.lux-sw[data-v="his-clair"]'); pg.wait_for_timeout(500)
    check('« HIS clair »: chrome white, always light, saved for the garage', attrs(pg) == ['his-clair', 'light'] and var(pg, '--paper').upper() == '#F3F4F6' and (store(pg, 'config/main') or {}).get('lux') == 'his-clair' and pressed(pg) == ['his-clair'], [attrs(pg), var(pg, '--paper')])
    check('…black buttons with white text, H.I.S red accent and signal', 'rgb(11, 12, 14)' in btn() and var(pg, '--btn-ink').upper() == '#FFFFFF' and '#E1222B' in var(pg, '--accent').upper() and var(pg, '--signal').upper() == '#D3121D', [btn(), var(pg, '--accent')])
    check('…the phone bar chrome, the device remembers it', metas(pg) == ['#E3E6EA', '#E3E6EA'] and ls(pg) == 'his-clair', [metas(pg), ls(pg)])
    check('…the Réglages line says « HIS clair · mode vitrine »', 'HIS clair · mode vitrine' in pg.locator('#lux-sect').get_attribute('data-sub'), pg.locator('#lux-sect').get_attribute('data-sub'))
    pg.screenshot(path='lux_his_clair_settings.png')
    pg.evaluate("location.hash = 'accueil'"); pg.wait_for_timeout(500)
    pg.screenshot(path='lux_his_clair_accueil.png')
    pg.evaluate("location.hash = 'reglages'"); pg.wait_for_timeout(500); open_colors(pg)
    pg.click('.lux-sw[data-v="his-sombre"]'); pg.wait_for_timeout(400)
    pg.evaluate("location.hash = 'accueil'"); pg.wait_for_timeout(500)
    pg.screenshot(path='lux_his_sombre_accueil.png')
    pg.evaluate("location.hash = 'reglages'"); pg.wait_for_timeout(500); open_colors(pg)
    pg.click('.lux-sw[data-v="noir"]'); pg.wait_for_timeout(400)
    pg.evaluate("location.hash = 'accueil'"); pg.wait_for_timeout(500)
    check('every screen follows (Accueil: gold « + Réservation » on black glass)', 'gradient' in pg.evaluate("getComputedStyle(document.querySelector('#top .btn.primary') || document.querySelector('.btn.primary')).backgroundImage"))
    pg.screenshot(path='lux_noir_accueil.png')
    ctx.close()
    # a light palette stays light on a phone in dark mode; Sable follows the phone
    seed2 = {'config/main': dict(base, lux='champagne')}
    ctx, pg = open_page(br, seed2, width=390, ui='phone', scheme='dark', hash='jour')
    check('phone in dark mode + Champagne chosen: the app stays light (ivory and gold)', attrs(pg) == ['champagne', 'light'] and var(pg, '--paper').upper() == '#F9F4E9', [attrs(pg), var(pg, '--paper')])
    check('no sideways scrolling on the phone', pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'))
    pg.evaluate("location.hash = 'reglages'"); pg.wait_for_timeout(500); open_colors(pg)
    check('phone: the colors in 2 columns, nothing cut', pg.evaluate("getComputedStyle(document.querySelector('.lux-grid')).gridTemplateColumns.split(' ').length") == 2 and pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'))
    pg.screenshot(path='lux_phone_pick.png')
    pg.click('.lux-sw[data-v="sable"]'); pg.wait_for_timeout(500)
    check('back to Sable: follows the phone again (dark at night), the device forgets the forced colors', attrs(pg) == [None, None] and var(pg, '--paper').upper() == '#15110E' and ls(pg) is None and (store(pg, 'config/main') or {}).get('lux') == 'sable', [attrs(pg), var(pg, '--paper'), ls(pg)])
    check('…the phone bar color follows the phone again', metas(pg) == ['#E9DED2', '#1E1915'], metas(pg))
    ctx.close()
    # opening: the colors are there before the first screen (no flash)
    ctx = br.new_context(viewport={'width': 1280, 'height': 860}, color_scheme='light', locale='fr-CA')
    ctx.add_init_script("try{localStorage.setItem('gm.lux','saphir')}catch(e){}")
    seen = []
    pg2 = ctx.new_page(); body = harness({'seed': {'config/main': dict(base, lux='saphir')}}, 'full')
    pg2.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=body) if r.request.url.startswith('https://local.test/') else r.abort())
    pg2.add_init_script("document.addEventListener('DOMContentLoaded', () => { window.__luxAtLoad = document.documentElement.getAttribute('data-lux'); });")
    pg2.goto('https://local.test/'); pg2.wait_for_timeout(600)
    check('opening the app: the garage colors are there from the very first paint (no flash of the default)', pg2.evaluate('window.__luxAtLoad') == 'saphir')
    ctx.close()
    for k, th in (('his-sombre', 'dark'), ('his-clair', 'light')):
        ctx = br.new_context(viewport={'width': 1280, 'height': 860}, color_scheme='light' if th == 'dark' else 'dark', locale='fr-CA')
        ctx.add_init_script("try{localStorage.setItem('gm.lux','%s')}catch(e){}" % k)
        pg3 = ctx.new_page(); body3 = harness({'seed': {'config/main': dict(base, lux=k)}}, 'full')
        def serve(b):
            return lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=b) if r.request.url.startswith('https://local.test/') else r.abort()
        pg3.route('**/*', serve(body3))
        pg3.add_init_script("document.addEventListener('DOMContentLoaded', () => { window.__luxAtLoad = [document.documentElement.getAttribute('data-lux'), document.documentElement.getAttribute('data-theme')]; });")
        pg3.goto('https://local.test/'); pg3.wait_for_timeout(600)
        check('opening with « %s » (phone in the other mode): right from the first paint, %s' % (k, th), pg3.evaluate('window.__luxAtLoad') == [k, th], pg3.evaluate('window.__luxAtLoad'))
        ctx.close()
    br.close()
check('no page errors', not ERRS, ERRS[:5])
print('%d/%d passed' % (sum(1 for _, ok in results if ok), len(results)))
