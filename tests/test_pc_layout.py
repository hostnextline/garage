# L'ordinateur a sa propre interface : menu à gauche, page large. Le téléphone garde la sienne.
from playwright.sync_api import sync_playwright
PAGE = open('/home/claude/garage/web/index.html', encoding='utf8').read()
IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
ok = 0; bad = []
def chk(c, m):
    global ok
    if c: ok += 1
    else: bad.append(m)
def open_page(b, w, h, ua=None, scheme='light', touch=False):
    kw = dict(viewport={'width': w, 'height': h}, locale='fr-CA', timezone_id='America/Toronto', color_scheme=scheme)
    if ua: kw.update(user_agent=ua, is_mobile=True, has_touch=True)
    ctx = b.new_context(**kw); pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=PAGE) if r.request.url == 'https://local.test/' else r.abort())
    pg.goto('https://local.test/'); pg.wait_for_timeout(400)
    return ctx, pg, errs
def box(pg, sel): return pg.eval_on_selector(sel, 'e => { const r = e.getBoundingClientRect(); return {x:r.x, y:r.y, w:r.width, h:r.height}; }')
with sync_playwright() as p:
    b = p.chromium.launch()
    # 1. grand écran d'ordinateur
    ctx, pg, errs = open_page(b, 1440, 900)
    chk(pg.evaluate("document.body.classList.contains('ui-pc') && !document.body.classList.contains('ui-phone')"), 'ordi : classe ui-pc')
    tb = box(pg, '#tabbar'); chk(tb['x'] < 20 and tb['w'] < 260 and tb['h'] > 700, f'ordi : menu à gauche {tb}')
    labels = pg.eval_on_selector_all('#tabbar .tab:not([hidden])', 'els => els.map(e => e.textContent.trim())')
    chk(labels == ['Accueil', 'Agenda', 'Clients', 'Factures', 'Trésorerie', 'Réglages'], f'ordi : sections {labels}')
    chk(pg.eval_on_selector('#tabbar', "e => getComputedStyle(e, '::before').content").strip('"') == 'Garage mobile', 'ordi : nom du garage en haut du menu')
    m = box(pg, '#main'); chk(m['x'] >= 248 and m['w'] > 1100, f'ordi : page large à droite du menu {m}')
    chk(pg.evaluate('document.documentElement.scrollWidth') <= 1440, 'ordi : pas de défilement de côté')
    ys = pg.eval_on_selector_all('#tabbar .tab:not([hidden])', 'els => els.map(e => e.getBoundingClientRect().y)')
    chk(all(ys[i] < ys[i + 1] for i in range(len(ys) - 1)), 'ordi : sections une sous l\'autre')
    pg.click('#tabbar .tab[data-t="agenda"]'); pg.wait_for_timeout(200)
    chk(pg.get_attribute('#tabbar .tab[data-t="agenda"]', 'aria-current') == 'page', 'ordi : clic sur Agenda')
    chk(pg.query_selector('#cal') is not None, 'ordi : l\'agenda s\'affiche')
    cw = pg.eval_on_selector('#cal', 'e => e.getBoundingClientRect().width'); chk(cw > 1000, f'ordi : agenda large {cw}')
    pg.click('#tabbar .tab[data-t="reglages"]'); pg.wait_for_timeout(200)
    chk(pg.get_attribute('body', 'data-w') == 'narrow', 'ordi : réglages en colonne plus étroite')
    mw = box(pg, '#main')['w']; chk(860 <= mw <= 900, f'ordi : largeur des réglages {mw}')
    chk(pg.locator('#ph-setlist .ph-row').count() == 9 and not pg.is_visible('#s-name'), 'ordi : réglages = une liste de parties')
    pg.click('#ph-setlist .ph-row:has-text("Le garage")'); pg.wait_for_timeout(150)
    chk(pg.is_visible('#s-name') and not pg.is_visible('#s-tps'), 'ordi : une partie à la fois')
    pg.fill('#s-name', 'Garage Hassan'); pg.wait_for_timeout(100)
    pg.click('#tabbar .tab[data-t="accueil"]'); pg.wait_for_timeout(300)
    pg.screenshot(path='pcl_1440.png')
    # nouvelle réservation : le menu se cache, la page reprend toute la largeur
    btn = True
    if btn:
        pg.click('text=+ Nouveau client'); pg.wait_for_timeout(300)
        chk(pg.evaluate("document.body.classList.contains('nav-off') && document.getElementById('tabbar').hidden"), 'ordi : formulaire = menu caché')
        chk(pg.evaluate("parseFloat(getComputedStyle(document.body).paddingLeft)") == 0, 'ordi : formulaire sans marge de menu')
        pg.click('#top [data-act="cform-back"]'); pg.wait_for_timeout(300)
        chk(pg.evaluate("!document.body.classList.contains('nav-off') && !document.getElementById('tabbar').hidden && parseFloat(getComputedStyle(document.body).paddingLeft) == 248"), 'ordi : retour = menu revenu')
    else: bad.append('bouton + Facture sur place introuvable')
    chk(not errs, f'ordi : erreurs {errs}')
    ctx.close()
    # 2. sombre
    ctx, pg, errs = open_page(b, 1280, 800, scheme='dark'); pg.screenshot(path='pcl_dark.png')
    chk(pg.evaluate("document.body.classList.contains('ui-pc')"), 'sombre : ui-pc'); chk(not errs, f'sombre : erreurs {errs}'); ctx.close()
    # 3. petite fenêtre d'ordinateur : la barre du bas reste (pas de menu qui mange la place)
    ctx, pg, errs = open_page(b, 820, 900)
    tb = box(pg, '#tabbar'); chk(tb['y'] > 780 and tb['w'] > 600, f'petite fenêtre : barre en bas {tb}')
    chk(pg.evaluate('document.documentElement.scrollWidth') <= 820, 'petite fenêtre : pas de défilement de côté')
    ctx.close()
    # 4. 1024 (portable avec agrandissement)
    ctx, pg, errs = open_page(b, 1024, 700)
    tb = box(pg, '#tabbar'); chk(tb['x'] < 20 and tb['h'] > 600, f'1024 : menu à gauche {tb}')
    chk(pg.evaluate('document.documentElement.scrollWidth') <= 1024, '1024 : pas de défilement de côté')
    pg.screenshot(path='pcl_1024.png'); ctx.close()
    # 5. vrai téléphone : rien ne change
    ctx, pg, errs = open_page(b, 390, 844, ua=IPHONE)
    chk(pg.evaluate("document.body.classList.contains('ui-phone') && !document.body.classList.contains('ui-pc')"), 'téléphone : interface téléphone')
    labels = pg.eval_on_selector_all('#tabbar .tab:not([hidden])', 'els => els.map(e => e.textContent.trim())')
    tb = box(pg, '#tabbar'); chk(tb['y'] > 740, f'téléphone : barre en bas {tb}')
    chk('Plus' in labels and 'Réglages' not in labels, f'téléphone : sections {labels}')
    chk(not errs, f'téléphone : erreurs {errs}'); ctx.close()
    # 6. tablette (iPad) = version complète, pas le menu téléphone
    ctx, pg, errs = open_page(b, 1180, 820, ua='Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1')
    chk(pg.evaluate("document.body.classList.contains('ui-pc')"), 'tablette : version complète avec menu'); ctx.close()
    b.close()
print(f'{ok}/{ok + len(bad)} passed')
for x in bad: print(' FAIL', x)
