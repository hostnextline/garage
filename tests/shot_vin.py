"""Phone screenshots of the VIN scan + engine sheet for the report (light + dark)."""
import sys, os
sys.argv = ['x']
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_vin.py'), encoding='utf8').read().split('with sync_playwright() as p:')[0])
from PIL import Image
names = []
def shot(pg, n, scheme):
    path = os.path.join(SC, 'v_%s_%s.png' % (n, scheme)); pg.screenshot(path=path); names.append(path)
with sync_playwright() as p:
    for scheme in ('light', 'dark'):
        br = launch(p, 'vin_civic.y4m')
        def mk(hold):
            ctx = br.new_context(viewport={'width': 390, 'height': 844}, timezone_id='America/Toronto', locale='fr-CA', has_touch=True, permissions=['camera'], color_scheme=scheme,
                                 user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1')
            pg = ctx.new_page()
            def route(r):
                u = r.request.url
                if u.startswith('https://local.test/'): return r.fulfill(status=200, content_type='text/html; charset=utf-8', body=harness({'seed': seed}, None))
                if u == ZX_URL: return None if hold else r.fulfill(status=200, content_type='application/javascript', body=ZX)
                m = re.match(r'https://vpic\.nhtsa\.dot\.gov/api/vehicles/DecodeVinValues/([A-Z0-9]+)\?format=json$', u)
                if m: return r.fulfill(status=200, content_type='application/json', body=json.dumps({'Results': [VPIC.get(m.group(1), {})]}))
                return r.abort()
            pg.route('**/*', route); pg.goto('https://local.test/'); pg.wait_for_timeout(800)
            return ctx, pg
        ctx, pg = mk(True)
        go_job(pg, 'j1'); pg.click('#veh-fold summary'); pg.click('#veh-fold [data-act="scan-job"]'); pg.wait_for_timeout(1500)
        pg.evaluate("document.getElementById('scan-msg').textContent = 'Vise le code-barres…'"); shot(pg, 'camera', scheme); ctx.close()
        ctx, pg = mk(False)
        go_job(pg, 'j1'); pg.click('#veh-fold summary'); pg.click('#veh-fold [data-act="scan-job"]'); wait_for(pg, "document.querySelector('#scan-body .vehsum')"); pg.wait_for_timeout(300); shot(pg, 'decode', scheme)
        pg.click('[data-act="scan-use"]'); pg.wait_for_timeout(500)
        pg.click('#veh-fold summary') if not pg.evaluate("document.getElementById('veh-fold').open") else None
        pg.click('#speccard [data-act="spec-edit"]'); pg.wait_for_timeout(300)
        pg.fill('#sp-oilL', '4,4'); pg.click('[data-act="sp-visc"][data-v="0W-20"]'); pg.fill('#sp-oilFilter', 'PH7317'); pg.fill('#sp-drainTorque', '40 N·m'); shot(pg, 'fiche', scheme)
        pg.click('#sp-save'); pg.wait_for_timeout(600)
        pg.wait_for_timeout(3500)
        go_job(pg, 'j2'); pg.evaluate("window.scrollTo(0, 0)"); pg.wait_for_timeout(300); shot(pg, 'job', scheme)
        pg.click('#veh-fold summary'); pg.wait_for_timeout(200); pg.evaluate("document.getElementById('veh-fold').scrollIntoView({block: 'start'}); window.scrollBy(0, -90)"); pg.wait_for_timeout(200); shot(pg, 'jobfiche', scheme)
        ctx.close(); br.close()
for scheme in ('light', 'dark'):
    ims = [Image.open(n).convert('RGB').crop((0, 0, 390, 844)) for n in names if n.endswith('_%s.png' % scheme)]
    bg = (233, 222, 210) if scheme == 'light' else (30, 25, 21)
    out = Image.new('RGB', (24 + len(ims) * 414, 892), bg)
    for i, im in enumerate(ims): out.paste(im, (24 + i * 414, 24))
    out.save(os.path.join(SC, 'apercu_vin_%s.png' % scheme))
print('ok', len(names))
