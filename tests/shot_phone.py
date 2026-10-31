import json, os, sys
exec(open('shot_glass.py').read().split("scheme = sys.argv[1]")[0])
from playwright.sync_api import sync_playwright
seed['clients/c9'] = {'firstName': 'Nadia', 'lastName': 'Haddad', 'phone': '5145550505', 'address': '100 rue Ontario Est, Montréal', 'postal': 'H2X 1H1'}
scheme = sys.argv[1] if len(sys.argv) > 1 else 'light'
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, color_scheme=scheme, timezone_id='America/Toronto', locale='fr-CA', has_touch=True, user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1')
    pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=harness({'seed': seed})) if r.request.url == 'https://local.test/' else r.abort())
    pg.goto('https://local.test/'); pg.wait_for_timeout(900)
    def shot(n, full=False): pg.screenshot(path=os.path.join(SC, 'p_%s_%s.png' % (n, scheme)), full_page=full)
    shot('jour', True)
    pg.click('.ph-job[data-id="a2"]'); pg.wait_for_timeout(300); shot('job_route', True)
    pg.click('[data-act="back"]'); pg.wait_for_timeout(200)
    pg.click('.ph-job[data-id="a4"]'); pg.wait_for_timeout(300); shot('job_plan', True)
    pg.click('[data-act="back"]'); pg.wait_for_timeout(200)
    pg.click('.tab[data-t="plus"]'); pg.wait_for_timeout(300); shot('plus', True)
    pg.click('a[href="#heures"]'); pg.wait_for_timeout(300); shot('heures', True)
    pg.click('.tab[data-t="plus"]'); pg.wait_for_timeout(200); pg.click('a[href="#reglages"]'); pg.wait_for_timeout(300); shot('reglages')
    pg.click('[data-act="ph-sec"][data-v="2"]'); pg.wait_for_timeout(200); shot('reglages_tarifs')
    pg.click('.tab[data-t="jour"]'); pg.wait_for_timeout(200)
    pg.click('.tab-new'); pg.wait_for_timeout(300); shot('plus_menu')
    pg.click('[data-act="ph-go"][data-v="new"]'); pg.wait_for_timeout(500); shot('book_client')
    pg.fill('#cs-q', 'Nadia'); pg.wait_for_timeout(200); pg.locator('#cs-results .crow').first.click(); pg.wait_for_timeout(600); shot('book_1', True)
    pg.click('[data-act="wiz-next"]'); pg.wait_for_timeout(300); shot('book_2', True)
    pg.click('[data-act="wiz-next"]'); pg.wait_for_timeout(300); shot('book_3', True)
    print('errors', errs, 'hscroll', pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'))
    br.close()
