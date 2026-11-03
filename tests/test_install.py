"""Version d'essai : « Mettre l'app sur ton téléphone » envoie vers la vraie app du garage (equipe/), code QR lisible, lien dans la barre d'essai."""
import os, re, numpy as np, cv2
from chemins import GARAGE, SAUVEGARDES   # (où est l'app : ici ou dans le dépôt)
from playwright.sync_api import sync_playwright
SC = os.path.dirname(os.path.abspath(__file__))
PAGE = open(GARAGE + '/web/index.html', encoding='utf8').read()
IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1'
SAMSUNG = 'Mozilla/5.0 (Linux; Android 14; SM-S921W) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/26.0 Chrome/122.0 Mobile Safari/537.36'
GSA = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Mobile Safari/537.36 GSA/15.30'
REAL = 'https://local.test/garage/equipe/'
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)) if detail and not cond else ''))
def open_page(br, ua=None, width=1280):
    kw = dict(viewport={'width': width, 'height': 900}, timezone_id='America/Toronto', locale='fr-CA')
    if ua: kw.update(user_agent=ua, has_touch=True, is_mobile=True, viewport={'width': 390, 'height': 844})
    ctx = br.new_context(**kw); pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=PAGE) if r.request.url.split('#')[0] == 'https://local.test/garage/' else r.abort())
    pg.goto('https://local.test/garage/#agenda'); pg.wait_for_timeout(700)
    return ctx, pg, errs
def txt(pg, sel):
    l = pg.locator(sel); return re.sub(r'\s+', ' ', l.first.inner_text()) if l.count() else ''
def open_sheet(pg):
    if pg.locator('[data-act="app-install"]:visible').count() == 0:
        pg.click('.tab[data-t="plus"]'); pg.wait_for_timeout(300)
    pg.locator('[data-act="app-install"]:visible').first.click(); pg.wait_for_timeout(500)
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx, pg, errs = open_page(br)
    a = pg.locator('#demo-bar a.db-real')
    check('computer sidebar: « Mettre l\'app sur ton téléphone » always there', pg.locator('#navfoot [data-act="app-install"]').count() == 1 and pg.is_visible('#navfoot [data-act="app-install"]'))
    check('essai strip: a link « L\'app du garage (avec ton compte) » to the real app', a.count() == 1 and pg.evaluate("document.querySelector('#demo-bar a.db-real').href") == REAL and pg.is_visible('#demo-bar a.db-real'), a.count())
    open_sheet(pg)
    check('computer: sheet says this is the trial version and the code points to the real app', 'version d\'essai' in txt(pg, '.inst') and REAL.replace('https://', '') in txt(pg, '#inst-url'), txt(pg, '.inst')[:200])
    shot = pg.locator('#inst-qr').screenshot()
    val = cv2.QRCodeDetector().detectAndDecode(cv2.imdecode(np.frombuffer(shot, np.uint8), cv2.IMREAD_COLOR))[0]
    check('the code read by a camera gives the real app address (not the trial)', val == REAL, val)
    check('computer: first « Sur cet ordinateur : une icône sur le bureau » (Chrome / Edge, Safari), then iPhone + Android steps, Samsung / Chrome iPhone folded',
          pg.locator('.inst > .inst-b').count() == 3 and pg.locator('.inst > .inst-b').first.get_attribute('data-p') == 'pc' and 'icône sur le bureau' in txt(pg, '.inst > .inst-b[data-p="pc"]') and pg.locator('.inst details .inst-b').count() == 2)
    pg.screenshot(path=os.path.join(SC, 'inst_essai_pc.png'))
    ctx.close()
    ctx, pg, errs2 = open_page(br, IPHONE); errs += errs2
    open_sheet(pg)
    btn = pg.locator('.inst .banner a.btn')
    check('iPhone on the trial: big button « Ouvrir l\'app du garage » to the real app', btn.count() == 1 and 'Ouvrir l\'app du garage' in btn.inner_text() and pg.evaluate("document.querySelector('.inst .banner a.btn').href") == REAL)
    check('iPhone Safari steps first, with « Ouvrir en tant qu\'app web »', pg.locator('.inst .inst-b').first.get_attribute('data-p') == 'ios-safari' and 'Ouvrir en tant qu\'app web' in txt(pg, '.inst-b[data-p="ios-safari"]'))
    check('icon preview + « connecte-toi la première fois »', pg.locator('.inst-icon img').count() == 1 and 'première fois' in txt(pg, '.inst-icon'))
    pg.screenshot(path=os.path.join(SC, 'inst_essai_iphone.png'), full_page=False)
    ctx.close()
    ctx, pg, errs2 = open_page(br, SAMSUNG); errs += errs2
    open_sheet(pg)
    check('Samsung Internet: Samsung steps first', pg.locator('.inst .inst-b').first.get_attribute('data-p') == 'samsung', pg.locator('.inst .inst-b').first.get_attribute('data-p'))
    ctx.close()
    ctx, pg, errs2 = open_page(br, GSA); errs += errs2
    open_sheet(pg)
    check('opened inside the Google app: warning « Ouvrir dans Chrome » + Android steps', 'à l\'intérieur d\'une autre app' in txt(pg, '.inst .banner.warn') and 'Ouvrir dans Chrome' in txt(pg, '.inst .banner.warn') and pg.locator('.inst .inst-b').first.get_attribute('data-p') == 'android-chrome')
    ctx.close()
    br.close()
check('no page errors', not errs, errs[:5])
print('\n%d/%d passed' % (sum(1 for _, ok in results if ok), len(results)))
