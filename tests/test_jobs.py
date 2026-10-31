"""Cancel (amount lost, in negative), no-show (trace in the client file, card on file next time), work done (fills the invoice)."""
import json, os, datetime, re, sys
from playwright.sync_api import sync_playwright
SC = os.path.dirname(os.path.abspath(__file__))
PAGE = open('/home/claude/garage/carnet.html', encoding='utf8').read()
MOCK = open(os.path.join(SC, 'mock.js'), encoding='utf8').read()
RESET = 'html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}'
T = datetime.date.today(); iso = lambda d: d.isoformat()
seed = {'config/main': {'biz': {'name': 'Garage NextLine'}, 'mechanics': ['Saleh', 'Ali'], 'trucks': [], 'rate': 120, 'taxesOn': True, 'prefix': 'F-', 'startNo': 1,
                        'services': [{'name': "Changement d'huile et filtre", 'price': 89.95}]}}
def cdoc(f, l, p): return {'firstName': f, 'lastName': l, 'phone': p, 'address': '4520 rue Saint-Denis, Montréal', 'postal': 'H2J 2L3'}
for cid, f, l, p in (('c2', 'Paul', 'Roy', '4385550202'), ('c3', 'Zoé', 'Gagnon', '5145550303'), ('c4', 'Luc', 'Bélanger', '4505550404')):
    seed['clients/' + cid] = cdoc(f, l, p)
def snap(cid):
    c = seed['clients/' + cid]; return dict(c, id=cid, name=c['firstName'] + ' ' + c['lastName'])
jobs = [('a2', '10:30', 'Saleh', 'route', 'c2', ['Changement de pneus saisonnier']),
        ('a3', '13:00', 'Ali', 'planifie', 'c3', ['Freins avant (plaquettes)']),
        ('a4', '15:30', 'Ali', 'planifie', 'c4', ["Changement d'huile et filtre", 'Inspection multipoints'])]
for (i, t, m, st, cid, sv) in jobs:
    seed['jobs/' + i] = {'date': iso(T), 'time': t, 'durationMin': 60, 'mechanic': m, 'status': st, 'clientId': cid, 'client': snap(cid), 'services': sv, 'service': ', '.join(sv), 'vehicle': {'year': '2018', 'make': 'Honda', 'model': 'Civic'}}
def harness(mode, ui='full'):
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<style>{RESET}</style><script>try{{localStorage.setItem("gm.ui",{json.dumps(ui)})}}catch(e){{}}window.__MOCK={json.dumps(mode)};</script><script>{MOCK}</script></head><body>{PAGE}</body></html>')
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)[:300]) if detail and not cond else ''), flush=True)
def open_page(br, mode, width=1100, ui='full'):
    ctx = br.new_context(viewport={'width': width, 'height': 900}, timezone_id='America/Toronto', locale='fr-CA', has_touch=width < 700, **({'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'} if width < 700 else {}))
    pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'fonts.g' not in m.text and 'ERR_FAILED' not in m.text else None)
    pg.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=harness(mode, ui)) if r.request.url == 'https://local.test/' else r.abort())
    pg.goto('https://local.test/'); pg.wait_for_timeout(700)
    return ctx, pg, errs
def txt(pg, sel): return (pg.locator(sel).first.text_content() or '').replace('\xa0', ' ').replace(' ', ' ')
def store(pg, path): return pg.evaluate('p => window.__store[p] || null', path)
def S(pg, k): return pg.evaluate('k => window.__garageApi.S[k]', k)
def wait(pg, ms=300): pg.wait_for_timeout(ms)
def open_job(pg, jid): pg.evaluate("id => { const S = window.__garageApi.S; S.screen = 'job'; S.jobId = id; S.confirmDel = false; window.__garageApi.render(); }", jid); wait(pg)
def home(pg): pg.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'accueil'; window.__garageApi.render(); }"); wait(pg)

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx, pg, errs = open_page(br, {'seed': seed})
    # ---------- cancel ----------
    open_job(pg, 'a4')
    check('job page: « Annuler la job » + « No-show » buttons', pg.locator('.offrow [data-act="cancel"]').count() == 1 and pg.locator('.offrow [data-act="noshow"]').count() == 1)
    check('job page: « Travaux faits » shows the booked work, not yet confirmed', 'Inspection multipoints' in txt(pg, 'section:has(h3:text("Travaux faits"))') and 'Pas encore confirmé' in txt(pg, 'section:has(h3:text("Travaux faits"))'))
    pg.click('[data-act="cancel"]'); wait(pg)
    rows = pg.evaluate("[...document.querySelectorAll('.cx-row')].map(r => [r.querySelector('span').textContent, r.querySelector('b').textContent.replace(/\\s/g,' ')])")
    check('cancel: planned services with their price (price list 89,95 $, inspection 0,5 h × 120 $)', rows == [["Changement d'huile et filtre", '89,95 $'], ['Inspection multipoints', '60,00 $']], rows)
    check('cancel: amount lost = 149,95 (shown in negative)', pg.input_value('#cx-amt') == '149,95' and '−' in txt(pg, '.cx-amt'))
    pg.locator('.cx-svc').nth(1).uncheck(); wait(pg, 100)
    check('cancel: unticking a service lowers the amount', pg.input_value('#cx-amt') == '89,95', pg.input_value('#cx-amt'))
    pg.click('#sheet-body [data-act="sheet-close"]'); wait(pg)
    check('« Garder la job » changes nothing', (store(pg, 'jobs/a4') or {}).get('status') == 'planifie' and not (store(pg, 'jobs/a4') or {}).get('lost'))
    pg.click('[data-act="cancel"]'); wait(pg); pg.locator('.cx-svc').nth(1).uncheck(); wait(pg, 100)
    pg.click('[data-act="cx-why"][data-v="client"]'); pg.fill('#cx-note', 'A trouvé un autre garage'); pg.click('[data-act="cx-yes"]'); wait(pg, 500)
    lo = (store(pg, 'jobs/a4') or {}).get('lost') or {}
    check('cancel saved: status Annulé, -89,95, oil change only, reason, note', (store(pg, 'jobs/a4') or {}).get('status') == 'annule' and lo.get('amount') == -89.95 and lo.get('services') == ["Changement d'huile et filtre"] and lo.get('reason') == 'client' and lo.get('note') == 'A trouvé un autre garage', lo)
    check('job page: banner with the loss, no status buttons, « Remettre »', 'perte de -89,95 $' in txt(pg, '.banner.warn') and 'le client a annulé' in txt(pg, '.banner.warn') and pg.locator('.seg').count() == 0 and pg.locator('[data-act="status"][data-v="planifie"]').count() == 1, txt(pg, '.banner.warn'))
    home(pg)
    check('dashboard: « Annulations : -89,95 $ (1 job) »', 'Annulations : -89,95 $ (1 job)' in txt(pg, '#d-loss'), txt(pg, '#d-loss'))
    check('dashboard: cancelled job not counted today', '2 jobs' in txt(pg, '[aria-labelledby="d-today"] .pill'), txt(pg, '[aria-labelledby="d-today"] .pill'))
    open_job(pg, 'a4'); pg.click('[data-act="status"][data-v="planifie"]'); wait(pg, 400)
    check('« Remettre la job à l\'agenda »: back to Planifié, loss removed', (store(pg, 'jobs/a4') or {}).get('status') == 'planifie' and not (store(pg, 'jobs/a4') or {}).get('lost'))
    home(pg); check('dashboard loss line gone', pg.locator('#d-loss').count() == 0)
    open_job(pg, 'a4'); pg.click('[data-act="cancel"]'); wait(pg)
    pg.fill('#cx-amt', '250'); pg.locator('.cx-svc').nth(0).uncheck(); wait(pg, 100)
    check('cancel: a typed amount is kept when ticking services', pg.input_value('#cx-amt') == '250')
    pg.click('[data-act="cx-yes"]'); wait(pg, 500)
    check('cancel saved with the typed amount (-250)', ((store(pg, 'jobs/a4') or {}).get('lost') or {}).get('amount') == -250)
    pg.click('[data-act="status"][data-v="planifie"]'); wait(pg, 400)
    check('restored again (original state)', (store(pg, 'jobs/a4') or {}).get('status') == 'planifie' and not (store(pg, 'jobs/a4') or {}).get('lost'))
    # ---------- no-show ----------
    open_job(pg, 'a3'); pg.click('[data-act="noshow"]'); wait(pg)
    check('no-show: asks first, says no amount and card next time', 'Aucun montant' in txt(pg, '#sheet-body') and 'carte au dossier' in txt(pg, '#sheet-body'))
    pg.click('[data-act="ns-yes"]'); wait(pg, 500)
    a3 = store(pg, 'jobs/a3') or {}
    check('no-show saved: status, time, no amount', a3.get('status') == 'noshow' and a3.get('noshowAt') and not a3.get('lost'), a3)
    check('job page: No-show banner + pill', 'No-show' in txt(pg, '.banner.warn') and txt(pg, '.pill.noshow') == 'No-show')
    home(pg)
    check('dashboard: « 1 no-show » (no money)', '1 no-show' in txt(pg, '#d-loss') and '$' not in txt(pg, '#d-loss'), txt(pg, '#d-loss'))
    pg.click('.tab[data-t="clients"]'); wait(pg)
    check('client list: Zoé has a « No-show » tag', 'No-show' in txt(pg, '.crow[data-id="c3"]') and 'No-show' not in txt(pg, '.crow[data-id="c2"]'))
    pg.click('.crow[data-id="c3"]'); wait(pg)
    check('client file: « No-show : 1 fois » + take a card on file', 'No-show : 1 fois' in txt(pg, '#ns-banner') and 'carte au dossier' in txt(pg, '#ns-banner'), txt(pg, '#ns-banner'))
    pg.click('[data-act="cl-book"]'); wait(pg, 700)
    check('booking this client: warning + « Carte au dossier prise » box', pg.locator('#ns-box').count() == 1 and pg.locator('#f-card').count() == 1 and not pg.is_checked('#f-card'))
    pg.check('#f-card'); pg.fill('#f-date', iso(T + datetime.timedelta(days=2))); pg.fill('#f-time', '09:00')
    pg.fill('#f-svc-in', 'Freins avant (plaquettes)'); pg.keyboard.press('Enter'); pg.keyboard.press('Escape')
    before = set(pg.evaluate('Object.keys(window.__store)'))
    pg.click('#f-save'); wait(pg, 900)
    nid = [k for k in pg.evaluate('Object.keys(window.__store)') if k.startswith('jobs/') and k not in before]
    check('booking saved with « carte au dossier »', len(nid) == 1 and (store(pg, nid[0]) or {}).get('cardOnFile') is True, nid)
    check('client file remembers the card (date)', (store(pg, 'clients/c3') or {}).get('cardOnFile') == iso(T), store(pg, 'clients/c3'))
    pg.evaluate("() => { const S = window.__garageApi.S; S.screen = 'client'; S.clientId = 'c3'; window.__garageApi.render(); }"); wait(pg)
    check('client banner now says « Carte au dossier depuis le … » (calm)', 'Carte au dossier depuis le' in txt(pg, '#ns-banner') and 'warn' not in (pg.get_attribute('#ns-banner', 'class') or ''))
    # clean-up (mock): remove the booking and the card date
    pg.evaluate("p => { delete window.__store[p]; const c = window.__store['clients/c3']; delete c.cardOnFile; }", nid[0] if nid else '')
    open_job(pg, 'a3'); pg.click('[data-act="status"][data-v="planifie"]'); wait(pg, 400)
    check('no-show undone: Planifié again, no-show time cleared', (store(pg, 'jobs/a3') or {}).get('status') == 'planifie' and not (store(pg, 'jobs/a3') or {}).get('noshowAt'))
    # ---------- work done (full screen) ----------
    open_job(pg, 'a2'); pg.click('[data-act="done-edit"]'); wait(pg)
    check('work done: picker with the booked work', pg.locator('#svc-picked .pchip').count() == 1 and 'pneus' in txt(pg, '#svc-picked'))
    pg.fill('#f-svc-in', 'Alignement'); pg.keyboard.press('Enter'); wait(pg, 100)
    pg.click('#svc-picked [data-act="unpick"][data-v="0"]'); wait(pg, 100); pg.keyboard.press('Escape')
    check('work done: estimated amount shown', 'Montant prévu' in txt(pg, '#done-amt'), txt(pg, '#done-amt'))
    pg.click('[data-act="done-save"]'); wait(pg, 500)
    a2 = store(pg, 'jobs/a2') or {}
    check('work done saved (status unchanged)', a2.get('done') == ['Alignement'] and a2.get('status') == 'route', a2.get('done'))
    check('job page lists the work done, button « Modifier »', 'Alignement' in txt(pg, 'section:has(h3:text("Travaux faits"))') and 'Modifier les travaux faits' in txt(pg, 'section:has(h3:text("Travaux faits"))'))
    pg.click('[data-act="invoice"]'); wait(pg, 500)
    check('invoice starts from the work done', pg.evaluate("window.__garageApi.S.inv.lines.map(l => l.desc)") == ['Alignement'], pg.evaluate("window.__garageApi.S.inv.lines.map(l => l.desc)"))
    pg.evaluate("() => { const st = window.__store['jobs/a2']; delete st.done; delete st.doneAt; const S = window.__garageApi.S; S.screen = null; S.tab = 'agenda'; window.__garageApi.render(); }"); wait(pg)
    check('no page errors', not errs, errs)
    ctx.close()

    # ---------- phone + read-only ----------
    ctx, pg, errs = open_page(br, {'seed': seed}, width=390, ui=None)
    open_job(pg, 'a3')
    check('phone job: Annuler / No-show under the big button', pg.locator('.offrow [data-act="cancel"]').count() == 1 and pg.locator('.offrow [data-act="noshow"]').count() == 1)
    check('phone status menu includes No-show', 'noshow' in pg.evaluate("[...document.querySelectorAll('#ph-st option')].map(o => o.value)"))
    pg.select_option('#ph-st', 'noshow'); wait(pg)
    check('phone: choosing No-show in the menu asks first', pg.locator('[data-act="ns-yes"]').count() == 1 and (store(pg, 'jobs/a3') or {}).get('status') == 'planifie')
    pg.click('#sheet-body [data-act="sheet-close"]'); wait(pg)
    check('phone: closing keeps the old status in the menu', pg.input_value('#ph-st') == 'planifie')
    pg.click('[data-act="back"]'); wait(pg)
    a3_before = [b for b in pg.evaluate("[...document.querySelectorAll('.ph-list > button')].map(b => b.dataset.id || ('gap:' + b.dataset.t))")]
    ctx.close()
    ctx, pg, errs = open_page(br, {'seed': seed, 'readOnly': True})
    open_job(pg, 'a4')
    check('read-only: no cancel / no-show / work-done buttons', pg.locator('.offrow').count() == 0 and pg.locator('[data-act="done-edit"]').count() == 0)
    ctx.close()
    br.close()
ok = sum(1 for _, c in results if c)
print('%d/%d passed' % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
