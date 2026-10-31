import json, base64, io, os, sys, datetime
from playwright.sync_api import sync_playwright
from pypdf import PdfReader

SC = os.path.dirname(os.path.abspath(__file__))
PAGE = open('/home/claude/garage/carnet.html', encoding='utf8').read()
MOCK = open(os.path.join(SC, 'mock.js'), encoding='utf8').read()
JSPDF = os.path.join(SC, 'deps/node_modules/jspdf/dist/jspdf.umd.min.js')
if not os.path.exists(JSPDF):
    JSPDF = os.path.join(SC, 'deps/node_modules/jspdf/dist/jspdf.umd.js')
RESET = 'html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}'

def harness(mode):
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<style>{RESET}</style><script>try{{localStorage.setItem("gm.ui","full")}}catch(e){{}}window.__MOCK={json.dumps(mode)};</script><script>{MOCK}</script></head><body>{PAGE}</body></html>')

results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)) if detail and not cond else ''))

def new_page(browser, mode, scheme='light', width=390, secure=True):
    ctx = browser.new_context(viewport={'width': width, 'height': 844}, color_scheme=scheme, timezone_id='America/Toronto', locale='fr-CA')
    base = 'https://local.test/' if secure else 'http://local.test/'
    ctx.grant_permissions(['clipboard-read', 'clipboard-write'], origin=base.rstrip('/'))
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' and 'fonts.g' not in m.text and 'ERR_FAILED' not in m.text else None)
    def route(r):
        u = r.request.url
        if u == base:
            r.fulfill(status=200, content_type='text/html; charset=utf-8', body=harness(mode))
        elif 'cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js' in u:
            r.fulfill(status=200, content_type='application/javascript', body=open(JSPDF, encoding='utf8').read())
        else:
            r.abort()
    page.route('**/*', route)
    page.goto(base + '#agenda')
    page.wait_for_timeout(250)
    return ctx, page, errors

def store(page):
    return page.evaluate('JSON.parse(JSON.stringify(window.__store))')

def jobs(page):
    return {k: v for k, v in store(page).items() if k.startswith('jobs/')}

def no_hscroll(page):
    return page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')

def sheet_new_client(pg, first, last, phone, addr, email=''):
    pg.click('[data-act="cs-new"]'); pg.wait_for_timeout(200)
    pg.fill('#c-first', first); pg.fill('#c-last', last); pg.fill('#c-phone', phone); pg.fill('#c-addr', addr)
    if email: pg.fill('#c-email', email)
    pg.click('#c-save'); pg.wait_for_timeout(350)

def sheet_pick_client(pg, q):
    pg.fill('#cs-q', q); pg.wait_for_timeout(120)
    pg.locator('#cs-results .crow').first.click(); pg.wait_for_timeout(350)

with sync_playwright() as p:
    br = p.chromium.launch()

    # ---------- main flow ----------
    ctx, pg, errs = new_page(br, {'seed': {'config/main': {'trucks': []}}})
    check('1. Empty agenda shows the day grid with a "touch a free case" hint', pg.locator('text=Touche une case libre').count() == 1 and pg.locator('.cal').count() == 1)
    check('1b. No horizontal scroll at 390px (agenda)', no_hscroll(pg))
    pg.screenshot(path=os.path.join(SC, 'shot_empty.png'), full_page=True)

    # settings
    pg.click('.tab[data-t="reglages"]'); pg.wait_for_timeout(100)
    pg.fill('#s-name', 'Garage Mobile Test'); pg.fill('#s-phone', '5145550000'); pg.fill('#s-addr', '123 rue Test, Montréal')
    pg.fill('#s-tps', '123456789 RT0001'); pg.fill('#s-tvq', '1234567890 TQ0001')
    pg.fill('#s-rate', '95'); pg.fill('#s-travel', '40')
    pg.fill('#sv-name-0', "Changement d'huile"); pg.fill('#sv-price-0', '89,99')
    pg.click('[data-act="addsvcrow"]'); pg.fill('#sv-name-1', 'Batterie (pose)'); pg.fill('#sv-price-1', '45')
    pg.fill('#s-mechs', 'Ali\nMarc'); pg.fill('#s-footer', 'Garantie 12 mois sur les pièces. Merci !')
    pg.click('#s-save'); pg.wait_for_timeout(150)
    c = store(pg).get('config/main', {})
    check('2. Settings saved (name, taxes nos, rate, 2 services, 2 mechanics)',
          c.get('biz', {}).get('name') == 'Garage Mobile Test' and c.get('rate') == 95 and c.get('travelFee') == 40
          and len(c.get('services', [])) == 2 and c['services'][0]['price'] == 89.99 and c.get('mechanics') == ['Ali', 'Marc']
          and c.get('biz', {}).get('phone') == '(514) 555-0000', c)
    check('2b. Settings form still shows saved values after re-render', pg.input_value('#s-name') == 'Garage Mobile Test')

    # booking validation
    pg.click('.tab[data-t="agenda"]'); pg.wait_for_timeout(100)
    check('3. Header shows garage name from settings', pg.locator('#top h1').inner_text() == 'Garage Mobile Test')
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250)
    check('C1. Booking starts by choosing or creating the client', pg.is_visible('#sheet') and pg.locator('#cs-q').count() == 1 and pg.locator('[data-act="cs-new"]').count() == 1 and pg.locator('#jobform').count() == 0)
    pg.click('[data-act="cs-new"]'); pg.wait_for_timeout(200)
    pg.click('#c-save'); pg.wait_for_timeout(60)
    ce = pg.inner_text('#c-err')
    check('C2. Empty client file refused: first name, last name, phone and address are required', 'le prénom' in ce and 'le nom' in ce and 'le téléphone' in ce and "l'adresse" in ce and 'courriel' not in ce, ce)
    pg.fill('#c-first', 'Jean'); pg.fill('#c-last', 'Tremblay'); pg.fill('#c-phone', '514 555 123'); pg.fill('#c-addr', '4500 boul. Décarie, Montréal')
    pg.click('#c-save'); pg.wait_for_timeout(60)
    check('C3. A 9-digit phone is refused', '10 chiffres' in pg.inner_text('#c-err'))
    pg.fill('#c-phone', '514 555 1234'); pg.press('#c-phone', 'Tab')
    check('6. Phone auto-formatted on blur', pg.input_value('#c-phone') == '(514) 555-1234')
    check('C4a. Address without postal code: hint asks for it', 'Ajoute le code postal' in pg.inner_text('#c-addrmsg'))
    pg.click('#c-save'); pg.wait_for_timeout(60)
    check('C4. Address without postal code is refused', 'code postal' in pg.inner_text('#c-err'))
    pg.fill('#c-addr', '4500 boul. Décarie, Montréal h4p2b5'); pg.press('#c-addr', 'Tab'); pg.wait_for_timeout(60)
    check('C5. One address line; the postal code inside is found and tidied', pg.input_value('#c-addr') == '4500 boul. Décarie, Montréal H4P 2B5' and 'Code postal H4P 2B5 · zone H4P' in pg.inner_text('#c-addrmsg'), (pg.input_value('#c-addr'), pg.inner_text('#c-addrmsg')))
    pg.fill('#c-email', 'jean@'); pg.click('#c-save'); pg.wait_for_timeout(60)
    check('C6. Invalid email refused (email itself is optional)', 'courriel' in pg.inner_text('#c-err').lower())
    pg.fill('#c-email', 'jean@exemple.ca'); pg.wait_for_timeout(1000)
    cd = store(pg).get('data/users/u_test/draft-client') or {}
    check('C7. The client form is auto-saved too', cd.get('firstName') == 'Jean' and cd.get('phone') == '(514) 555-1234', cd)
    pg.click('#c-save'); pg.wait_for_timeout(350)
    cls = {k: v for k, v in store(pg).items() if k.startswith('clients/')}
    cid = list(cls.keys())[0].split('/')[1] if cls else None
    cdoc = cls.get('clients/' + str(cid), {})
    check('C8. Client file saved (first, last, phone, single-line address, postal, email)', len(cls) == 1 and cdoc.get('firstName') == 'Jean' and cdoc.get('lastName') == 'Tremblay' and cdoc.get('phone') == '(514) 555-1234'
          and cdoc.get('address') == '4500 boul. Décarie, Montréal H4P 2B5' and cdoc.get('postal') == 'H4P 2B5' and cdoc.get('email') == 'jean@exemple.ca' and 'data/users/u_test/draft-client' not in store(pg), cdoc)
    check('C9. Then straight to the booking form, with the client card', pg.locator('#sheet #jobform').count() == 1 and 'Jean Tremblay' in pg.inner_text('.ccard') and '(514) 555-1234' in pg.inner_text('.ccard'))
    pg.click('#f-save'); pg.wait_for_timeout(50)
    err_txt = pg.inner_text('#formerr')
    check('4. Booking without a time is refused with a clear message', pg.is_visible('#formerr') and "l'heure" in err_txt, err_txt)
    check('4b. Form opens in the popup over the agenda', pg.is_visible('#sheet') and pg.locator('#sheet #jobform').count() == 1)

    # VIN check
    pg.fill('#f-vin', '1m8gdm9axkp042788'); pg.wait_for_timeout(50)
    check('5. VIN auto-uppercased', pg.input_value('#f-vin') == '1M8GDM9AXKP042788')
    check('5b. Valid VIN recognized (check digit) + year 1989', 'VIN valide' in pg.inner_text('#vinmsg') and '1989' in pg.inner_text('#vinmsg'), pg.inner_text('#vinmsg'))
    pg.click('[data-act="vinyear"]')
    check('5c. Year button fills the year', pg.input_value('#f-year') == '1989')
    pg.fill('#f-vin', '1M8GDM9AXKP042789'); pg.wait_for_timeout(30)
    check('5d. Wrong check digit is flagged', 'ne balance pas' in pg.inner_text('#vinmsg'), pg.inner_text('#vinmsg'))
    pg.fill('#f-vin', '1M8GDM9AOKP04278'); pg.wait_for_timeout(30)
    check('5e. Letter O flagged', 'I, O ou Q' in pg.inner_text('#vinmsg'))
    pg.fill('#f-vin', '2HGFC2F59JH542376')  # 2018 Honda Civic-shaped VIN


    # --- multi-choice services ---
    pg.click('#f-svc-in'); pg.wait_for_timeout(50)
    check('S1. Focusing "Services" opens the choices (promos first, then the price list)', pg.is_visible('#svc-opts') and pg.locator('#svc-opts .opt').count() >= 5
          and 'PROMO' in pg.locator('#svc-opts .opt').first.inner_text().upper() and "Changement d'huile" in pg.locator('#svc-opts .opt:not(.promo)').first.inner_text() and '89,99' in pg.locator('#svc-opts .opt:not(.promo)').first.inner_text())
    pg.type('#f-svc-in', 'altern'); pg.wait_for_timeout(50)
    first = pg.locator('#svc-opts .opt').first.inner_text()
    check('S2. Typing "altern" filters to the alternator', "alternateur" in first.lower() and pg.locator('#svc-opts .opt.active').count() == 1, first)
    pg.press('#f-svc-in', 'Enter'); pg.wait_for_timeout(50)
    check('S3. Enter picks it as a chip and clears the box', pg.locator('.pchip').count() == 1 and pg.input_value('#f-svc-in') == '' and "alternateur" in pg.inner_text('.pchip').lower())
    pg.type('#f-svc-in', 'huile'); pg.wait_for_timeout(50)
    pg.locator('#svc-opts .opt', has_text="Changement d'huile").first.click(); pg.wait_for_timeout(50)
    check('S4. Tapping a choice adds a 2nd chip with its price', pg.locator('.pchip').count() == 2 and '89,99' in pg.locator('.pchip').nth(1).inner_text())
    pg.type('#f-svc-in', 'Bruit roue avant gauche'); pg.wait_for_timeout(50)
    check('S5. Unknown text offers "+ Ajouter"', pg.locator('#svc-opts .opt.new').count() == 1 and 'Bruit roue avant gauche' in pg.inner_text('#svc-opts .opt.new'))
    pg.locator('#svc-opts .opt.new').click(); pg.wait_for_timeout(50)
    check('S6. Free text added as a 3rd chip', pg.locator('.pchip').count() == 3)
    pg.type('#f-svc-in', 'huile'); pg.wait_for_timeout(50)
    check('S7. Already-chosen service is not offered again', not any(t.strip().startswith("Changement d'huile\n") or t.strip() == "Changement d'huile" for t in pg.locator('#svc-opts .opt').all_inner_texts()) and pg.locator('#svc-opts .opt:not(.promo)', has_text="Changement d'huile et filtre").count() == 1, pg.locator('#svc-opts .opt').all_inner_texts())
    pg.fill('#f-svc-in', ''); pg.press('#f-svc-in', 'Backspace'); pg.wait_for_timeout(50)
    check('S8. Backspace on empty box removes the last chip', pg.locator('.pchip').count() == 2)
    pg.locator('.pchip button').nth(1).click(); pg.wait_for_timeout(50)
    check('S9. ✕ removes a chip', pg.locator('.pchip').count() == 1)
    pg.type('#f-svc-in', 'huile'); pg.locator('#svc-opts .opt', has_text="Changement d'huile").first.click()
    pg.type('#f-svc-in', 'Bruit roue avant gauche'); pg.press('#f-svc-in', 'Enter'); pg.wait_for_timeout(50)
    check('S10. Enter on new text adds it (3 chips again)', pg.locator('.pchip').count() == 3)

    # --- autosave ---
    pg.wait_for_timeout(1200)
    dr = store(pg).get('data/users/u_test/draft-booking')
    check('A1. Form auto-saved to the database while typing', dr is not None and dr['client']['name'] == 'Jean Tremblay' and dr.get('clientId') == cid and len(dr['services']) == 3 and dr['vehicle']['vin'] == '2HGFC2F59JH542376', dr)
    check('A2. "Brouillon sauvegardé à …" shown', 'Brouillon sauvegardé' in pg.inner_text('#draftmsg'), pg.inner_text('#draftmsg'))
    pg.fill('#f-notes', 'Stationné en arrière')
    pg.click('[data-act="back-edit"]'); pg.wait_for_timeout(250)
    dr = store(pg).get('data/users/u_test/draft-booking') or {}
    check('A3. Closing right after typing still saves the last change', dr.get('notes') == 'Stationné en arrière', dr.get('notes'))
    check('A4. Nothing put in the shared carnet yet', len(jobs(pg)) == 0)
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250)
    check('A5. Reopening the form restores the draft (client + notes + chips + banner)', 'Jean Tremblay' in pg.inner_text('.ccard') and pg.input_value('#f-notes') == 'Stationné en arrière'
          and pg.locator('.pchip').count() == 3 and pg.is_visible('#draftbanner'))
    pg.fill('#f-year', '2018'); pg.fill('#f-make', 'Honda'); pg.fill('#f-model', 'Civic'); pg.fill('#f-plate', 'abc123'); pg.fill('#f-km', '142000')
    pg.fill('#f-prob', 'Témoin de batterie allumé')
    pg.fill('#f-time', '09:30'); pg.select_option('#f-mech', 'Ali')
    pg.click('#f-save'); pg.wait_for_timeout(200)
    J = jobs(pg); jid = list(J.keys())[0] if J else None; j = J.get(jid, {})
    check('7. Booking saved with status Planifié', len(J) == 1 and j.get('status') == 'planifie' and j['client']['phone'] == '(514) 555-1234'
          and j['vehicle']['plate'] == 'ABC123' and j['mechanic'] == 'Ali' and j['time'] == '09:30', j)
    check('7f. Booking linked to the client file', j.get('clientId') == cid and j['client'].get('postal') == 'H4P 2B5')
    check('7a. 3 services saved as a list', j.get('services') == ["Remplacement de l'alternateur", "Changement d'huile", 'Bruit roue avant gauche'] and j.get('service', '').count(',') == 2, j.get('services'))
    check('A6. Draft deleted once the booking is saved', 'data/users/u_test/draft-booking' not in store(pg))
    check('G0. Popup closes after saving; appointment block shows in Ali\'s column', not pg.is_visible('#sheet') and pg.locator('.col[data-col="Ali"] .appt', has_text='Jean Tremblay').count() == 1)
    pg.locator('.appt', has_text='Jean Tremblay').click(); pg.wait_for_timeout(80)
    check('7e. Detail shows the 3 services as tags', pg.locator('section:has(h3:text("Travail demandé")) .tags .tag').count() == 3)
    check('7b. Job detail screen opened', pg.locator('#top h1').inner_text() == 'Jean Tremblay')
    check('7c. Detail shows VIN check result', pg.locator('text=Chiffre de contrôle correct').count() + pg.locator('text=À vérifier').count() >= 1)
    check('7d. No horizontal scroll (job detail)', no_hscroll(pg))

    # status flow
    pg.click('.seg button[data-v="route"]'); pg.wait_for_timeout(100)
    check('8. Status → En route written', jobs(pg)[jid]['status'] == 'route')
    pg.click('.seg button[data-v="place"]'); pg.wait_for_timeout(100)
    check('8b. Status → Sur place written', jobs(pg)[jid]['status'] == 'place')

    # agenda + mechanic filter
    pg.click('[data-act="back"]'); pg.wait_for_timeout(100)
    check('9. Appointment appears in the day grid', pg.locator('.appt').count() == 1 and 'Jean Tremblay' in pg.inner_text('.appt'))
    pg.click('.chip[data-v="Marc"]'); pg.wait_for_timeout(50)
    check('9b. Filter Marc shows only Marc\'s column', pg.locator('.appt').count() == 0 and pg.locator('.colh').count() == 1)
    pg.click('.chip[data-act="mech"][data-v=""]'); pg.wait_for_timeout(50)
    check('9c. Filter Tous shows it again', pg.locator('.appt').count() == 1 and pg.locator('.colh').count() == 2)

    # invoice
    pg.click('.appt'); pg.wait_for_timeout(80)
    pg.click('[data-act="invoice"]'); pg.wait_for_timeout(80)
    check('10. Invoice prefilled: one line per service (catalogue price or hourly rate)', pg.locator('.line').count() == 3 and pg.input_value('#l0-desc') == "Remplacement de l'alternateur" and pg.input_value('#l0-price') == '95'
          and pg.input_value('#l1-price') == '89,99' and pg.input_value('#l2-price') == '95')
    pg.click('[data-act="delline"][data-v="2"]'); pg.click('[data-act="delline"][data-v="1"]'); pg.wait_for_timeout(30)
    pg.fill('#l0-qty', '1,5')
    pg.click('[data-act="addline"][data-v="piece"]'); pg.fill('#l1-desc', 'Alternateur reconditionné'); pg.fill('#l1-price', '289,99')
    pg.click('[data-act="addline"][data-v="frais"]')
    check('10b. Travel fee prefilled from settings', pg.input_value('#l2-price') == '40' and pg.input_value('#l2-desc') == 'Frais de déplacement')
    pg.click('[data-act="addsvc"][data-v="1"]')
    pg.click('[data-act="addline"][data-v="rabais"]'); pg.fill('#l4-desc', 'Rabais nouveau client'); pg.fill('#l4-price', '10')
    # expected: 1.5*95=142.50 + 289.99 + 40 + 45 - 10 = 507.49 ; tps 25.37 ; tvq 50.62 ; total 583.48
    tot = pg.inner_text('#totdl')
    check('10c. Live totals correct (507,49 / 25,37 / 50,62 / 583,48)', all(x in tot for x in ['507,49', '25,37', '50,62', '583,48']), tot)
    pg.check('#i-paid-1'); pg.click('[data-act="finalize"]'); pg.wait_for_timeout(60)
    check('10e. Paid without payment method is refused', pg.is_visible('#inverr') and 'mode de paiement' in pg.inner_text('#inverr'))
    pg.select_option('#i-method', 'Débit')
    pg.click('[data-act="finalize"]'); pg.wait_for_timeout(300)
    inv = jobs(pg)[jid].get('invoice', {})
    check('11. Invoice F-0001 saved: paid by Débit, totals stored, job Terminé',
          inv.get('number') == 'F-0001' and inv.get('paid') is True and inv.get('method') == 'Débit' and inv.get('sub') == 507.49
          and inv.get('tps') == 25.37 and inv.get('tvq') == 50.62 and inv.get('total') == 583.48 and len(inv.get('lines', [])) == 5
          and jobs(pg)[jid]['status'] == 'termine', inv)
    check('11b. Counter advanced to 2', store(pg).get('meta/invoices', {}).get('next') == 2, store(pg).get('meta/invoices'))
    check('11c. Preview shows number, total and Payée stamp', pg.locator('.inv-no b').inner_text() == 'F-0001' and '583,48' in pg.inner_text('.paper') and 'Payée' in pg.inner_text('.stamp'))
    check('11d. Preview shows TPS/TVQ numbers', '123456789 RT0001' in pg.inner_text('.paper'))
    check('11e. No horizontal scroll (invoice preview)', no_hscroll(pg))
    pg.screenshot(path=os.path.join(SC, 'shot_preview.png'), full_page=True)

    # PDF
    pg.click('[data-act="pdf"]'); pg.wait_for_timeout(1500)
    saved = pg.evaluate('window.__saved')
    ok_pdf = False; txt = ''
    if saved:
        data = base64.b64decode(saved[0]['b64'])
        ok_pdf = data[:4] == b'%PDF'
        txt = '\n'.join(pg_.extract_text() for pg_ in PdfReader(io.BytesIO(data)).pages)
        open(os.path.join(SC, 'facture_test.pdf'), 'wb').write(data)
    check('12. PDF generated and handed to download', ok_pdf and saved[0]['filename'].startswith('Facture F-0001'), saved[0]['filename'] if saved else 'none')
    check('12b. PDF text has accents, totals, taxes, VIN', all(x in txt for x in ['FACTURE', 'F-0001', 'Garage Mobile Test', 'Alternateur reconditionné', 'Main-d\'œuvre', '583,48', 'TVQ (9,975 %)', '2HGFC2F59JH542376', 'PAYÉE', 'Débit', 'Facturé à'.upper()]), txt[:600])

    # copy text
    pg.click('[data-act="copytext"]'); pg.wait_for_timeout(150)
    clip = pg.evaluate('navigator.clipboard ? navigator.clipboard.readText().catch(function(){return ""}) : ""')
    fb = pg.locator('#copyta').count()
    check('13. "Copier la facture" puts the invoice text on the clipboard (or shows the fallback box)',
          ('Total : 583,48' in clip and 'F-0001' in clip), clip[:200])

    # invoices tab
    pg.click('[data-act="back-prev"]'); pg.wait_for_timeout(60)
    check('14. Finalized job: delete button hidden (kept for bookkeeping)', pg.locator('[data-act="del"]').count() == 0)
    pg.click('[data-act="back"]'); pg.click('.tab[data-t="factures"]'); pg.wait_for_timeout(80)
    pg.click('.chip[data-v="paid"]'); pg.wait_for_timeout(40)
    check('15. Invoices tab lists F-0001 under Payées', pg.locator('.row').count() == 1 and 'F-0001' in pg.inner_text('.row'))

    # quick invoice (walk-in), unpaid then mark paid
    pg.click('[data-act="quick"]'); pg.wait_for_timeout(250)
    sheet_new_client(pg, 'Marie', 'Côté', '4385559876', '88 rue Saint-Denis, Montréal H2X 3K8')
    check('16. Quick invoice form pre-fills today and current time', pg.input_value('#f-date') != '' and pg.input_value('#f-time') != '')
    pg.type('#f-svc-in', 'huile'); pg.locator('#svc-opts .opt', has_text="Changement d'huile").first.click()
    pg.click('#f-save'); pg.wait_for_timeout(300)
    check('16b. Goes straight to the invoice with the catalogue price (89,99)', pg.locator('#l0-price').count() == 1 and pg.input_value('#l0-price') == '89,99')
    pg.click('[data-act="finalize"]'); pg.wait_for_timeout(300)
    J = jobs(pg); qid = [k for k, v in J.items() if v['client']['name'] == 'Marie Côté'][0]
    qinv = J[qid]['invoice']
    check('16c. Second invoice numbered F-0002, unpaid, total 103,47', qinv['number'] == 'F-0002' and qinv['paid'] is False and qinv['total'] == 103.47, qinv)
    pg.select_option('#p-method', 'Comptant'); pg.click('[data-act="markpaid"]'); pg.wait_for_timeout(150)
    qinv = jobs(pg)[qid]['invoice']
    check('16d. "Marquer payée" records Comptant + date, keeps lines', qinv['paid'] is True and qinv['method'] == 'Comptant' and qinv['paidAt'] and len(qinv['lines']) == 1, qinv)

    # draft + delete flow
    pg.click('[data-act="back-prev"]'); pg.click('[data-act="back"]'); pg.click('.tab[data-t="agenda"]'); pg.wait_for_timeout(60)
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250)
    sheet_new_client(pg, 'Test', 'Supprimer', '5140000000', '1 rue Test, Montréal H3B 1A1')
    pg.fill('#f-time', '14:00')
    pg.click('#f-save'); pg.wait_for_timeout(200)
    did = [k for k, v in jobs(pg).items() if v['client']['name'] == 'Test Supprimer'][0]
    pg.locator('.appt', has_text='Test Supprimer').click(); pg.wait_for_timeout(60)
    pg.click('[data-act="invoice"]'); pg.fill('#l0-desc', 'Diagnostic'); pg.click('[data-act="savedraft"]'); pg.wait_for_timeout(150)
    d = jobs(pg)[did]['invoice']
    check('17. Draft invoice saved without a number', d.get('number') is None and d['lines'][0]['desc'] == 'Diagnostic', d)
    pg.click('[data-act="del"]'); pg.wait_for_timeout(40)
    check('17b. Delete asks for confirmation inside the page', pg.locator('[data-act="del-yes"]').count() == 1)
    pg.click('[data-act="del-no"]'); pg.wait_for_timeout(40)
    check('17c. "Garder" cancels', did in jobs(pg))
    pg.click('[data-act="del"]'); pg.click('[data-act="del-yes"]'); pg.wait_for_timeout(150)
    check('17d. Confirmed delete removes the job', did not in jobs(pg))

    # edit booking
    pg.locator('.appt', has_text='Jean Tremblay').click(); pg.click('[data-act="edit"]'); pg.wait_for_timeout(60)
    pg.fill('#f-km', '142500'); pg.click('#f-save'); pg.wait_for_timeout(150)
    check('18. Editing a booking keeps its invoice, services, and updates the field', jobs(pg)[jid]['vehicle']['km'] == '142500' and jobs(pg)[jid]['invoice']['number'] == 'F-0001' and len(jobs(pg)[jid]['services']) == 3)

    # ---------- weekly hours in settings ----------
    pg.click('[data-act="back"]'); pg.click('.tab[data-t="reglages"]'); pg.wait_for_timeout(80)
    for d in range(7):
        pg.check(f'#h-{d}-open')
    pg.select_option('#h-6-start', '09:00'); pg.select_option('#h-6-end', '15:00')
    pg.click('#s-save'); pg.wait_for_timeout(150)
    hrs = store(pg)['config/main'].get('hours', {})
    check('H0. Weekly hours saved (7 days open, Saturday 9 h–15 h, 1 unité = 10 min by default)', all(hrs[str(d)]['open'] for d in range(7)) and hrs['6']['start'] == '09:00' and hrs['6']['end'] == '15:00' and store(pg)['config/main'].get('slotMin') == 10, hrs)
    pg.select_option('#h-1-start', '18:00'); pg.select_option('#h-1-end', '08:00'); pg.click('#s-save'); pg.wait_for_timeout(100)
    check('H0b. Closing before opening is refused', 'fermeture doit être après' in pg.inner_text('#toast') and store(pg)['config/main']['hours']['1']['start'] == '08:00')
    pg.click('[data-act="setreset"]'); pg.wait_for_timeout(50)

    # ---------- day grid ----------
    pg.click('.tab[data-t="agenda"]'); pg.wait_for_timeout(80)
    pg.screenshot(path=os.path.join(SC, 'shot_grid.png'), full_page=True)
    check('G1. Grid has one column per mechanic', pg.locator('.colh').all_inner_texts()[0].startswith('Ali') and pg.locator('.colh').nth(1).inner_text().startswith('Marc'))
    def slot(col, t): return pg.locator(f'.col[data-col="{col}"] .slot[data-t="{t}"]')
    check('G2. 7 h is closed (hatched), 8 h and 10 h are open', 'closed' in slot('Ali', '07:00').get_attribute('class') and 'open' in slot('Ali', '08:00').get_attribute('class') and 'open' in slot('Marc', '10:00').get_attribute('class'))
    slot('Ali', '07:00').click(); pg.wait_for_timeout(60)
    check('G3. Tapping a closed case does not open the form and explains why', not pg.is_visible('#sheet') and 'Case fermée' in pg.inner_text('#toast'))
    slot('Marc', '10:00').click(); pg.wait_for_timeout(250)
    check('G4a. Tapping a free case opens the popup on the client search, with 10 h · Marc in the title', pg.is_visible('#sheet') and pg.locator('#cs-q').count() == 1 and '10 h' in pg.inner_text('#sheet-sub').lower() and 'marc' in pg.inner_text('#sheet-sub').lower())
    check('G4b. Client search ready to type', pg.evaluate('document.activeElement && document.activeElement.id') == 'cs-q')
    sheet_pick_client(pg, 'jean')
    check('G4. Picking the client opens the form with date, 10 h and Marc filled', pg.is_visible('#sheet') and pg.input_value('#f-time') == '10:00' and pg.input_value('#f-mech') == 'Marc' and '10 h' in pg.inner_text('#sheet-sub').lower() and 'marc' in pg.inner_text('#sheet-sub').lower(), (pg.is_visible('#sheet'), pg.input_value('#f-time') if pg.locator('#f-time').count() else None, pg.input_value('#f-mech') if pg.locator('#f-mech').count() else None, pg.inner_text('#sheet-sub')))
    pg.screenshot(path=os.path.join(SC, 'shot_sheet.png'), full_page=False)
    n_before = len(jobs(pg))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(100)
    check('G5. Escape closes the popup without saving anything', not pg.is_visible('#sheet') and len(jobs(pg)) == n_before)
    slot('Marc', '10:00').click(); pg.wait_for_timeout(300)
    check('G5b. Reopening goes straight back to the form for the same client (draft)', 'Jean Tremblay' in pg.inner_text('.ccard') and pg.input_value('#f-time') == '10:00')
    pg.click('[data-act="cs-change"]'); pg.wait_for_timeout(200)
    sheet_new_client(pg, 'Luc', 'Grille', '5145557777', '2 rue Test, Montréal H4N 1B2')
    check('G5c. "Changer" lets you switch client; the case time stays', 'Luc Grille' in pg.inner_text('.ccard') and pg.input_value('#f-time') == '10:00' and pg.input_value('#f-mech') == 'Marc')
    pg.fill('#f-notes', 'Porte de côté')
    pg.click('.sheet-back', position={'x': 10, 'y': 10}); pg.wait_for_timeout(200)
    dr = store(pg).get('data/users/u_test/draft-booking') or {}
    check('G6. Tapping outside closes it and keeps the draft', not pg.is_visible('#sheet') and dr.get('client', {}).get('name') == 'Luc Grille', dr.get('client'))
    slot('Ali', '12:00').click(); pg.wait_for_timeout(250)  # 11 h is now covered by the 9 h 30 job (2 h estimated: alternator + oil change)
    check('G7. Another case reopens the draft but with the new time and mechanic', 'Luc Grille' in pg.inner_text('.ccard') and pg.input_value('#f-notes') == 'Porte de côté' and pg.input_value('#f-time') == '12:00' and pg.input_value('#f-mech') == 'Ali')
    pg.click('#f-save'); pg.wait_for_timeout(200)
    lj = [v for v in jobs(pg).values() if v['client']['name'] == 'Luc Grille']
    check('G8. Saved at 12 h with Ali, popup closed, draft gone', len(lj) == 1 and lj[0]['time'] == '12:00' and lj[0]['mechanic'] == 'Ali' and not pg.is_visible('#sheet') and 'data/users/u_test/draft-booking' not in store(pg))
    box = pg.locator('.appt', has_text='Luc Grille').bounding_box()
    check('G9. A 1-hour booking covers six 10-min units', box and 135 <= box['height'] <= 147, box)
    check('G10. No horizontal page scroll with the grid', no_hscroll(pg))

    # ---------- open / close the schedule ----------
    pg.click('[data-act="hours-edit"]'); pg.wait_for_timeout(80)
    check('H1. "Ouvrir / fermer l\'horaire" shows the hours panel', pg.is_visible('#hours-panel') and pg.locator('.cal.editing').count() == 1)
    slot('Ali', '07:00').click(); pg.wait_for_timeout(120)
    dd = store(pg).get('days/' + datetime.date.today().isoformat(), {})
    check('H2. Tapping a closed case opens it (saved for this day only)', 'Ali@07:00' in dd.get('opened', []) and 'open' in slot('Ali', '07:00').get_attribute('class'), dd)
    slot('Ali', '12:00').click(); pg.wait_for_timeout(120)
    dd = store(pg).get('days/' + datetime.date.today().isoformat(), {})
    check('H3. Tapping an open case closes it (lunch break)', 'Ali@12:00' in dd.get('blocked', []) and 'closed' in slot('Ali', '12:00').get_attribute('class') and 'open' in slot('Marc', '12:00').get_attribute('class'), dd)
    pg.screenshot(path=os.path.join(SC, 'shot_hours_edit.png'), full_page=True)
    slot('Ali', '12:00').click(); pg.wait_for_timeout(120)
    dd = store(pg).get('days/' + datetime.date.today().isoformat(), {})
    check('H3b. Tapping again reopens it', 'Ali@12:00' not in dd.get('blocked', []))
    pg.select_option('#d-start', '09:00'); pg.wait_for_timeout(120)
    dd = store(pg).get('days/' + datetime.date.today().isoformat(), {})
    check('H4. Changing today\'s opening to 9 h closes 8 h for everyone (but keeps Ali\'s 7 h)', dd.get('start') == '09:00' and 'closed' in slot('Marc', '08:00').get_attribute('class') and 'open' in slot('Ali', '07:00').get_attribute('class'))
    pg.click('[data-act="day-close"]'); pg.wait_for_timeout(120)
    dd = store(pg).get('days/' + datetime.date.today().isoformat(), {})
    check('H5. "Fermer toute la journée" closes the day', dd.get('closed') is True and 'closed' in slot('Marc', '10:00').get_attribute('class') and 'Fermé' in pg.inner_text('.hoursline'))
    pg.click('[data-act="day-open"]'); pg.wait_for_timeout(120)
    dd = store(pg).get('days/' + datetime.date.today().isoformat(), {})
    check('H6. "Ouvrir cette journée" reopens it', dd.get('closed') is None and 'open' in slot('Marc', '10:00').get_attribute('class'))
    pg.click('[data-act="day-reset"]'); pg.wait_for_timeout(120)
    check('H7. "Revenir à l\'horaire normal" removes today\'s changes', ('days/' + datetime.date.today().isoformat()) not in store(pg) and 'closed' in slot('Ali', '07:00').get_attribute('class'))
    pg.click('#hours-panel [data-act="hours-edit"]'); pg.wait_for_timeout(60)
    check('H8. "Terminé" leaves the hours mode', pg.locator('#hours-panel').count() == 0 and pg.locator('.cal.editing').count() == 0)
    sat = (datetime.date.today() + datetime.timedelta(days=(5 - datetime.date.today().weekday()) % 7)).isoformat()
    pg.click(f'.day[data-v="{sat}"]'); pg.wait_for_timeout(60)
    check('H9. Saturday follows the weekly hours (8 h closed, 9 h open)', 'closed' in slot('Marc', '08:00').get_attribute('class') and 'open' in slot('Marc', '09:00').get_attribute('class') and '9 h' in pg.inner_text('.hoursline'))
    pg.click('[data-act="today"]'); pg.wait_for_timeout(60)
    pg.click('.chip[data-act="view"][data-v="list"]'); pg.wait_for_timeout(60)
    check('L1. "Liste" shows the same day as cards', pg.locator('.ticket').count() == pg.evaluate("Object.values(window.__store).filter(function(j){return j.date==='" + datetime.date.today().isoformat() + "' && j.client}).length") and pg.locator('.cal').count() == 0)
    pg.click('.chip[data-act="view"][data-v="grid"]'); pg.wait_for_timeout(60)

    # ---------- week view ----------
    tdy = datetime.date.today(); mon = tdy - datetime.timedelta(days=tdy.weekday())
    thu = (mon + datetime.timedelta(days=3)).isoformat(); satw = (mon + datetime.timedelta(days=5)).isoformat(); tdi = tdy.isoformat(); thu_name = 'jeudi'
    if thu == tdi: thu = (mon + datetime.timedelta(days=2)).isoformat(); thu_name = 'mercredi'  # today's column already has appointments at 10 h
    pg.click('.chip[data-act="view"][data-v="week"]'); pg.wait_for_timeout(80)
    check('W1. "Semaine" shows 7 day columns and the week title', pg.locator('.cal.week').count() == 1 and pg.locator('.cal.week .dayh').count() == 7 and 'Semaine du' in pg.inner_text('.daytitle'))
    n_today = len([v for v in jobs(pg).values() if v.get('date') == tdi and v.get('time') and v.get('status') != 'annule'])
    check('W2. Today\'s appointments are in today\'s column, with the mechanic name', pg.locator(f'.col[data-date="{tdi}"] .appt').count() == n_today and 'Ali' in pg.locator(f'.col[data-date="{tdi}"] .appt', has_text='Luc Grille').inner_text(), (n_today, pg.locator(f'.col[data-date="{tdi}"] .appt').count()))
    check('W3. Saturday column follows its hours (8 h closed, 9 h open)', 'closed' in pg.locator(f'.col[data-date="{satw}"] .slot[data-t="08:00"]').get_attribute('class') and 'open' in pg.locator(f'.col[data-date="{satw}"] .slot[data-t="09:00"]').get_attribute('class'))
    check('W3b. Week summary counts the whole week', pg.locator('.sum .stat b').first.inner_text() == str(len([v for v in jobs(pg).values() if mon.isoformat() <= v.get('date', '') <= (mon + datetime.timedelta(days=6)).isoformat() and v.get('status') != 'annule'])))
    pg.screenshot(path=os.path.join(SC, 'shot_week.png'), full_page=False)
    pg.locator(f'.col[data-date="{thu}"] .slot[data-t="10:00"]').click(); pg.wait_for_timeout(250)
    sheet_new_client(pg, 'Paul', 'Semaine', '5145553333', '3 rue Test, Montréal H2J 2L3')
    check('W4. Tapping Thursday 10 h opens the form for that day and time', pg.is_visible('#sheet') and pg.input_value('#f-date') == thu and pg.input_value('#f-time') == '10:00' and pg.input_value('#f-mech') == '')
    pg.select_option('#f-mech', 'Marc')
    pg.click('#f-save'); pg.wait_for_timeout(250)
    pj = [v for v in jobs(pg).values() if v['client']['name'] == 'Paul Semaine']
    check('W5. Saved on Thursday 10 h with Marc, shown in the Thursday column, still in week view', len(pj) == 1 and pj[0]['date'] == thu and pj[0]['time'] == '10:00' and pj[0]['mechanic'] == 'Marc'
          and pg.locator(f'.col[data-date="{thu}"] .appt', has_text='Paul Semaine').count() == 1 and pg.locator('.cal.week').count() == 1)
    pg.click('.chip[data-v="Marc"]'); pg.wait_for_timeout(60)
    marc_week = len([v for v in jobs(pg).values() if v.get('mechanic') == 'Marc' and mon.isoformat() <= v.get('date', '') <= (mon + datetime.timedelta(days=6)).isoformat() and v.get('time') and v.get('status') != 'annule'])
    check('W6. Filter Marc in week view shows only Marc\'s appointments', pg.locator('.cal.week .appt').count() == marc_week, (marc_week, pg.locator('.cal.week .appt').count()))
    pg.click('.chip[data-act="mech"][data-v=""]'); pg.wait_for_timeout(60)
    check('W7. Week view has its own "Ouvrir / fermer l\'horaire de la semaine" button', pg.locator('[data-act="hours-edit"]').count() == 1 and 'de la semaine' in pg.inner_text('[data-act="hours-edit"]'))
    check('W8. No horizontal page scroll (the week scrolls inside its box)', no_hscroll(pg))
    pg.locator(f'.col[data-date="{satw}"] .slot[data-t="08:00"]').click(); pg.wait_for_timeout(60)
    check('W9. Closed case in week view does not open the form', not pg.is_visible('#sheet') and 'Case fermée' in pg.inner_text('#toast'))
    pg.click(f'.dayh[data-v="{thu}"]'); pg.wait_for_timeout(80)
    check('W10. Tapping a day header opens that day in "Jour" view', pg.locator('.cal.week').count() == 0 and pg.locator('.cal').count() == 1 and thu_name in pg.inner_text('.daytitle').lower()
          and pg.locator('.col[data-col="Marc"] .appt', has_text='Paul Semaine').count() == 1 and 'on' in pg.locator('.chip[data-act="view"][data-v="grid"]').get_attribute('class'))
    pg.click('.chip[data-act="view"][data-v="week"]'); pg.click(f'.day[data-v="{satw}"]'); pg.wait_for_timeout(60)
    check('W11. Tapping a day in the strip from week view also opens that day', pg.locator('.cal.week').count() == 0 and 'samedi' in pg.inner_text('.daytitle').lower())
    pg.click('[data-act="today"]'); pg.wait_for_timeout(60)
    ctx2 = br.new_context(viewport={'width': 1280, 'height': 900}, timezone_id='America/Toronto', locale='fr-CA')
    ctx2.close()

    # draft reset
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250)
    pg.click('.sheet-head [data-act="sheet-close"]'); pg.wait_for_timeout(80)
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250)
    sheet_pick_client(pg, 'jean')
    pg.fill('#f-notes', 'Brouillon à jeter'); pg.wait_for_timeout(1100)
    pg.click('[data-act="back-edit"]'); pg.wait_for_timeout(150); pg.click('#top [data-act="new"]'); pg.wait_for_timeout(300)
    ok_restore = pg.input_value('#f-notes') == 'Brouillon à jeter'
    pg.click('[data-act="draft-reset"]'); pg.wait_for_timeout(250)
    check('A7. "Recommencer à zéro" deletes the draft and starts again from the client search', ok_restore and pg.is_visible('#sheet') and pg.locator('#cs-q').count() == 1 and pg.locator('#jobform').count() == 0 and 'data/users/u_test/draft-booking' not in store(pg))
    pg.click('.sheet-head [data-act="sheet-close"]'); pg.wait_for_timeout(100)

    check('19. No script errors in the whole flow', not errs, errs[:5])
    ctx.close()

    # ---------- dark mode look (seeded) ----------
    import datetime
    td = datetime.date.today().isoformat()
    seed = {'config/main': {'biz': {'name': 'Garage Mobile Test', 'phone': '(514) 555-0000'}, 'taxesOn': True, 'tpsNo': '123456789 RT0001', 'tvqNo': '1234567890 TQ0001', 'rate': 95, 'trucks': [], 'mechanics': ['Ali', 'Marc'], 'services': [{'name': "Changement d'huile", 'price': 89.99}]},
            'jobs/a1': {'client': {'name': 'Jean Tremblay', 'phone': '(514) 555-1234', 'address': '4500 boul. Décarie, Montréal'}, 'vehicle': {'year': '2018', 'make': 'Honda', 'model': 'Civic', 'vin': '2HGFC2F59JH542376', 'km': '142000'},
                        'service': "Changer l'alternateur", 'date': td, 'time': '09:30', 'durationMin': 90, 'mechanic': 'Ali', 'status': 'place',
                        'invoice': {'lines': [{'type': 'piece', 'desc': 'Batterie', 'qty': 1, 'price': 180}], 'taxesOn': True, 'sub': 180, 'tps': 9, 'tvq': 17.96, 'total': 206.96, 'paid': False, 'method': '', 'paidAt': None, 'note': '', 'number': 'F-0009', 'issuedAt': td}},
            'jobs/a2': {'client': {'name': 'Marie Côté', 'address': '88 rue Saint-Denis'}, 'vehicle': {'year': '2015', 'make': 'Toyota', 'model': 'RAV4'}, 'service': "Changement d'huile", 'date': td, 'time': '13:00', 'durationMin': 45, 'mechanic': 'Marc', 'status': 'planifie'}}
    ctx, pg, errs = new_page(br, {'seed': seed}, scheme='dark', secure=False)
    bg = pg.evaluate('getComputedStyle(document.documentElement).backgroundColor')
    scene = pg.evaluate("getComputedStyle(document.body, '::after').backgroundImage")
    check('20. Dark theme applies to page background (dark base + night scene)', bg == 'rgb(20, 15, 12)' and 'rgb(23, 18, 15)' in scene, (bg, scene[:120]))
    check('20a. Seeded day shows 2 appointments and the day summary', pg.locator('.appt').count() == 2 and '206,96' in pg.inner_text('.sum'), pg.inner_text('main')[:300])
    pg.screenshot(path=os.path.join(SC, 'shot_dark.png'), full_page=True)
    pg.locator('.appt', has_text='Jean Tremblay').click(); pg.click('[data-act="preview"]'); pg.wait_for_timeout(80)
    pg.click('[data-act="copytext"]'); pg.wait_for_timeout(120)
    check('20b. Where the clipboard is blocked, a select-and-copy box appears with the invoice', pg.locator('#copyta').count() == 1 and '206,96' in pg.input_value('#copyta'))
    pg.screenshot(path=os.path.join(SC, 'shot_dark_preview.png'), full_page=True)
    check('20c. No script errors (dark run)', not errs, errs[:3])
    ctx.close()
    ctx, pg, errs = new_page(br, {'seed': seed}, scheme='light')
    pg.screenshot(path=os.path.join(SC, 'shot_light.png'), full_page=False)
    pg.locator('.appt', has_text='Jean Tremblay').click(); pg.wait_for_timeout(60)
    pg.screenshot(path=os.path.join(SC, 'shot_job.png'), full_page=True)
    pg.click('[data-act="invoice"]'); pg.wait_for_timeout(60)
    pg.screenshot(path=os.path.join(SC, 'shot_invoice_editor.png'), full_page=True)
    pg.click('[data-act="back-inv"]'); pg.click('[data-act="back"]'); pg.wait_for_timeout(60)
    pg.locator('.appt', has_text='Marie').click(); pg.click('[data-act="invoice"]'); pg.wait_for_timeout(60)
    check('25. Older booking (single service text) still prefills the invoice at the price-list price', pg.input_value('#l0-desc') == "Changement d'huile" and pg.input_value('#l0-price') == '89,99')
    pg.click('[data-act="back-inv"]'); pg.click('[data-act="back"]'); pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250)
    sheet_new_client(pg, 'Essai', 'Picker', '5145550101', '5 rue Test, Montréal H4P 2B5')
    pg.click('#f-svc-in'); pg.type('#f-svc-in', 'frein'); pg.wait_for_timeout(60)
    pg.screenshot(path=os.path.join(SC, 'shot_picker.png'), full_page=False)
    pg.press('#f-svc-in', 'Enter'); pg.type('#f-svc-in', 'batt'); pg.press('#f-svc-in', 'Enter'); pg.click('#f-prob'); pg.wait_for_timeout(200)
    pg.locator('#svc-picker').scroll_into_view_if_needed()
    pg.screenshot(path=os.path.join(SC, 'shot_picker_chips.png'), full_page=False)
    check('26. No horizontal scroll with chips (phone)', no_hscroll(pg))
    check('27. No script errors (seeded light run)', not errs, errs[:3])
    ctx.close()

    # ---------- read-only viewer ----------
    ctx, pg, errs = new_page(br, {'readOnly': True})
    check('21. Read-only viewer: banner shown, no "+ Réservation"', pg.locator('text=lecture seule').count() >= 1 and pg.locator('[data-act="new"]').count() == 0)
    ctx.close()

    # ---------- contributor (not admin) can't change settings ----------
    ctx, pg, errs = new_page(br, {'notAdmin': True})
    pg.click('.tab[data-t="reglages"]'); pg.wait_for_timeout(80)
    check('22. Contributor sees settings disabled', pg.is_disabled('#s-name') and pg.locator('#s-save').count() == 0)
    pg.click('.tab[data-t="agenda"]'); pg.wait_for_timeout(80)
    check('22b. Contributor has no "Ouvrir / fermer l\'horaire" button', pg.locator('[data-act="hours-edit"]').count() == 0)
    pg.locator('.slot.closed').first.click(); pg.wait_for_timeout(60)
    check('22c. Contributor tapping a closed case gets a plain message', 'on ne peut pas réserver' in pg.inner_text('#toast'))
    ctx.close()

    # ---------- page opened outside Claude ----------
    ctx, pg, errs = new_page(br, {'noClaude': True})
    check('23. Outside Claude: clear banner, no crash', pg.locator('text=Ouvre cette page dans Claude').count() >= 1 and not errs, errs)
    ctx.close()

    # ---------- desktop width ----------
    ctx, pg, errs = new_page(br, {}, width=1280)
    check('24. Desktop width: no horizontal scroll', no_hscroll(pg))
    ctx.close()
    br.close()

res = [r for r in results if r is not None]
print('\n%d/%d passed' % (sum(1 for r in res if r[1]), len(res)))
