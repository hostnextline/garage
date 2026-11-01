"""Scanning a receipt: the photo is read on the device and the expense fills in (date, shop, total, TPS, TVQ, payment,
category); each filled box is marked, everything stays editable; the photo is kept as the receipt; then « Enregistrer »
saves what the person checked. The reading engine is served from the test machine (on the phone it comes from the internet once)."""
import time, json
from team_seed import *
from playwright.sync_api import sync_playwright
OCR = "window.__ocrBase = '%socrtest/npm/'; window.__ocrLang = '%socrtest/lang';" % (BASE, BASE)

def form(p):
    return p.evaluate("""(() => { const v = id => (document.getElementById(id) || {}).value; const a = id => { const e = document.getElementById(id); return !!e && e.classList.contains('auto'); };
      return {date: v('x-date'), vendor: v('x-vendor'), total: v('x-total'), tps: v('x-tps'), tvq: v('x-tvq'), cat: v('x-cat'), pay: (document.querySelector('[data-act="x-pay"].on') || {}).textContent || '',
              auto: ['x-date', 'x-vendor', 'x-total', 'x-tps', 'x-tvq'].filter(a), msg: (document.getElementById('x-scanmsg') || {}).innerText || '', photo: !!document.querySelector('#x-prev img')}; })()""")
def open_form(p):
    p.evaluate("location.hash = 'tresor'"); p.wait_for_timeout(700)
    p.click('[data-act="exp-new"]'); p.wait_for_selector('#x-scanf', state='attached', timeout=8000); p.wait_for_timeout(300)
def scan(p, f, ms=90000):
    t0 = time.time(); p.set_input_files('#x-scanf', f)
    ok = wait_for(p, "/Rempli|pas pu lire|besoin d'Internet/.test((document.getElementById('x-scanmsg') || {}).innerText || '')", ms)
    return ok, round(time.time() - t0, 1)

otok, pw = seed()
n_exp0 = psql("select count(*) from public.docs where path like 'expenses/%' or path like 'receipts/%'")
with sync_playwright() as pl:
    b = pl.chromium.launch()
    for phone in (False, True):
        tag = 'téléphone' if phone else 'ordi'
        c = ctx(b, phone=phone); c.add_init_script(OCR); p = page(c, 'nadia' + tag)
        login(p, 'nadia@garage.test', pw['nadia']); open_form(p)
        if not phone:
            check('« + Dépense »: « 📷 Scanner le reçu » at the top, with what it does', p.locator('label[for="x-scanf"]', has_text='Scanner le reçu').count() == 1 and 'se remplissent' in txt(p, '#x-scanmsg'))
        ok, sec = scan(p, 'rc_napa.jpg'); f = form(p)
        p.screenshot(path='receipt_%s.png' % ('ph' if phone else 'pc'))
        check('%s · a NAPA receipt (read in %s s, the 1st time with the engine loading): date, shop, total, TPS, TVQ, Visa, « Pièces »' % (tag, sec),
              ok and f['date'] == '2026-10-28' and f['vendor'] == 'NAPA' and f['total'] == '57,49' and f['tps'] == '2,50' and f['tvq'] == '4,99' and f['pay'] == 'Crédit' and f['cat'] == 'pieces', f)
        check('%s · …the filled boxes are marked to check, the message says what was filled, the photo is kept as the receipt' % tag,
              set(f['auto']) >= {'x-date', 'x-vendor', 'x-total', 'x-tps', 'x-tvq'} and 'Rempli à partir du reçu' in f['msg'] and 'le total' in f['msg'] and f['photo'], f)
        if not phone:
            p.fill('#x-total', '57,50'); p.wait_for_timeout(100)
            check('…a box he corrects is no longer marked (it is his now)', 'x-total' not in form(p)['auto'] and form(p)['total'] == '57,50')
            p.click('#x-save'); p.wait_for_timeout(1500)
            ex = psql("select data::text from public.docs where path like 'expenses/%' order by updated_at desc limit 1")
            d = json.loads(ex) if ex else {}
            check('…« Enregistrer la dépense »: saved as he checked it (57,50 $, NAPA, 28 oct., Pièces, Crédit, TPS 2,50, TVQ 4,99) with the receipt photo',
                  abs(d.get('total', 0) - 57.5) < 0.001 and d.get('vendor') == 'NAPA' and d.get('date') == '2026-10-28' and d.get('cat') == 'pieces' and d.get('method') == 'Crédit' and abs(d.get('tps', 0) - 2.5) < .001 and abs(d.get('tvq', 0) - 4.99) < .001 and bool(d.get('receipt')), d)
            open_form(p)
            ok, sec2 = scan(p, 'rc_esso.jpg'); f = form(p)
            check('a gas receipt photographed crooked, with grain (read in %s s, the engine already there): Esso, 28/10, 70,35 $, TPS, TVQ, Interac, « Essence »' % sec2,
                  ok and f['vendor'] == 'Esso' and f['date'] == '2026-10-28' and f['total'] == '70,35' and f['tps'] == '3,06' and f['tvq'] == '6,10' and f['pay'] == 'Débit' and f['cat'] == 'essence', f)
            p.click('#sheet .sheet-head [data-act="sheet-close"]'); p.wait_for_timeout(300); open_form(p)
            ok, _ = scan(p, 'rc_blank.jpg'); f = form(p)
            check('a photo with nothing to read: it says so, the photo is kept, he writes the amount himself (nothing invented)', ok and 'pas pu lire' in f['msg'] and f['photo'] and f['total'] == '' and not f['auto'], f)
            # a registration receipt (no TPS / TVQ on it): the taxes box is unticked, nothing invented
            p.click('#sheet .sheet-head [data-act="sheet-close"]'); p.wait_for_timeout(300); open_form(p)
            ok, _ = scan(p, 'rc_saaq.jpg'); f = form(p); tx = p.evaluate("({on: document.getElementById('x-taxin').checked, hid: document.getElementById('x-taxes').hidden})")
            check('a SAAQ receipt (registration, no taxes on it): SAAQ, « Immatriculation », 312,45 $, Interac, and « TPS et TVQ incluses » unticked (no tax invented)',
                  ok and f['vendor'] == 'SAAQ' and f['cat'] == 'immat' and f['total'] == '312,45' and f['pay'] == 'Débit' and not tx['on'] and tx['hid'], [f, tx])
            # taxes not printed, a kind of expense with taxes: calculated from the total, marked to check
            p.click('#sheet .sheet-head [data-act="sheet-close"]'); p.wait_for_timeout(300); open_form(p)
            ok, _ = scan(p, 'rc_notax.jpg'); f = form(p)
            check('a receipt without the taxes written (Pièces): the TPS and TVQ are calculated from 114,98 $ (5,00 / 9,98) and marked « to check », the message says so',
                  ok and f['total'] == '114,98' and f['tps'] == '5,00' and f['tvq'] == '9,98' and {'x-tps', 'x-tvq'} <= set(f['auto']) and 'calculées' in f['msg'], f)
            p.fill('#x-total', '120,00'); p.wait_for_timeout(100); f = form(p)
            check('…he changes the total: the taxes follow his total and are his (no longer marked)', f['tps'] == '5,22' and f['tvq'] == '10,41' and not ({'x-tps', 'x-tvq'} & set(f['auto'])), f)
            # what he wrote before the scan stays his
            p.click('#sheet .sheet-head [data-act="sheet-close"]'); p.wait_for_timeout(300); open_form(p)
            p.fill('#x-vendor', 'Mon fournisseur'); p.click('[data-act="x-pay"][data-v="Comptant"]'); p.wait_for_timeout(100)
            ok, _ = scan(p, 'rc_napa.jpg'); f = form(p)
            check('he wrote the supplier and chose « Comptant » before scanning: both stay his, the rest fills in', ok and f['vendor'] == 'Mon fournisseur' and f['pay'] == 'Comptant' and f['total'] == '57,49' and 'x-vendor' not in f['auto'], f)
            # two photos one after the other: the last one counts
            p.click('#sheet .sheet-head [data-act="sheet-close"]'); p.wait_for_timeout(300); open_form(p)
            p.set_input_files('#x-scanf', 'rc_napa.jpg'); p.wait_for_timeout(60)
            ok, _ = scan(p, 'rc_esso.jpg'); p.wait_for_timeout(1500); f = form(p)
            check('a second photo chosen while the first is read: the second one fills the form (the first is ignored)', ok and f['vendor'] == 'Esso' and f['total'] == '70,35', f)
            # the form closed while reading: the next expense is not filled by it
            p.click('#sheet .sheet-head [data-act="sheet-close"]'); p.wait_for_timeout(300); open_form(p)
            p.set_input_files('#x-scanf', 'rc_napa.jpg'); p.wait_for_timeout(80)
            p.click('#sheet .sheet-head [data-act="sheet-close"]'); p.wait_for_timeout(200); open_form(p); p.wait_for_timeout(3500); f = form(p)
            check('closed while reading, then a new expense: the new one stays empty (nothing from the closed one)', f['total'] == '' and f['vendor'] == '' and not f['auto'] and not f['photo'] and 'se remplissent' in f['msg'], f)
        c.close()
    # the engine can't be downloaded (no internet the first time)
    c = ctx(b); c.add_init_script("window.__ocrBase = 'http://127.0.0.1:9/nowhere/';"); p = page(c, 'offline')
    login(p, 'nadia@garage.test', pw['nadia']); open_form(p)
    ok, _ = scan(p, 'rc_napa.jpg', 30000); f = form(p)
    check('no internet for the first scan: « Le lecteur de reçus a besoin d\'Internet la première fois », the photo is kept, the form still works', ok and "besoin d'Internet" in f['msg'] and f['photo'], f)
    c.close()
    b.close()
# back to the start
psql("delete from public.docs where path like 'expenses/%' or path like 'receipts/%'")
check('back to the start (the test expense and its receipt removed)', psql("select count(*) from public.docs where path like 'expenses/%' or path like 'receipts/%'") == n_exp0 == '0', n_exp0)
check('no page errors', not [e for e in ERRS if 'nowhere' not in e and '127.0.0.1:9' not in e], ERRS[:5])
summary()
