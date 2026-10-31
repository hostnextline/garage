"""Images pour Hassan : la fiche « Mettre l'app sur ton téléphone » (iPhone), l'avertissement dans Facebook / courriel, le bandeau « Nouvelle version »."""
from team_seed import *
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont
IOS = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1'
FB = IOS.replace('Version/18.5 Mobile/15E148 Safari/604.1', 'Mobile/15E148 [FBAN/FBIOS;FBAV/480.0.0.38.108]')
otok, pw = seed()
def mkc(b, ua):
    c = ctx(b, phone=True); c.close()
    c = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, timezone_id='America/Toronto', locale='fr-CA', has_touch=True, is_mobile=True, user_agent=ua)
    c.route('https://tile.openstreetmap.org/**', lambda r: r.fulfill(status=200, content_type='image/png', body=b''))
    c.route('https://fonts.**', lambda r: r.abort())
    return c
shots = []
with sync_playwright() as pl:
    b = pl.chromium.launch()
    c = mkc(b, IOS); p = page(c, 'ios'); login(p, 'saleh@garage.test', pw['saleh']); p.wait_for_timeout(800)
    p.click('#inst-card [data-act="app-install"]'); p.wait_for_timeout(700)
    p.screenshot(path='sh_ios.png'); shots.append(('sh_ios.png', '1. iPhone : les étapes, avec les vrais boutons'))
    c.close()
    c = mkc(b, FB); p = page(c, 'fb'); login(p, 'ali@garage.test', pw['ali']); p.wait_for_timeout(800)
    p.click('#inst-card [data-act="app-install"]'); p.wait_for_timeout(700)
    p.screenshot(path='sh_fb.png'); shots.append(('sh_fb.png', '2. Ouvert depuis Facebook ou le courriel'))
    c.close()
    c = mkc(b, IOS); p = page(c, 'upd'); login(p, 'saleh@garage.test', pw['saleh'])
    wait_for(p, 'navigator.serviceWorker.controller !== null', 20000); p.reload(); p.wait_for_timeout(2500)
    p.evaluate("navigator.serviceWorker.dispatchEvent(new Event('controllerchange'))"); p.wait_for_timeout(600)
    p.screenshot(path='sh_upd.png'); shots.append(('sh_upd.png', '3. Nouvelle version : un seul bouton'))
    c.close(); b.close()
ims = [Image.open(f).convert('RGB') for f, _ in shots]
W = sum(i.width for i in ims) + 40 * (len(ims) + 1); H = max(i.height for i in ims) + 150
out = Image.new('RGB', (W, H), (233, 222, 210)); d = ImageDraw.Draw(out)
try: font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 40)
except Exception: font = ImageFont.load_default()
x = 40
for im, (_, label) in zip(ims, shots):
    d.text((x, 45), label, fill=(30, 25, 21), font=font); out.paste(im, (x, 120)); x += im.width + 40
out.save('install_revue.png'); print(out.size)
