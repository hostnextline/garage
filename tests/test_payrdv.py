"""Texto de rendez-vous + paiement avant le départ du mécano (copie locale de Supabase, vrais textos GHL et Stripe simulés) :
1. réservation → texto automatique : la date, le bloc (entre 8 h et 12 h), le lien pour voir et payer d'avance ;
   changé de bloc → un 2e texto (« a changé ») ; modifié sans changer de bloc → rien ;
2. la page du client : son rendez-vous, le prix prévu, « Payer d'avance » par carte → payé d'avance ;
3. sur place : la facture enlève ce qui est payé d'avance (rien à payer : la job se termine) ;
4. pas payé : « Terminer » est bloqué, « Encaisser » ; « En route » vers le client suivant bloqué ;
   le lien de paiement par texto → le client paie → la job se débloque toute seule ;
5. « Payé sur place » (Débit) ; 6. le propriétaire : « Laisser partir sans paiement » (pas le mécano)."""
import json, os, re, time, datetime
from team_seed import *
from playwright.sync_api import sync_playwright

def stripe_log(): return json.loads(urllib.request.urlopen('http://127.0.0.1:9202/__log').read())
def ghl_log(): return json.loads(urllib.request.urlopen('http://127.0.0.1:9200/__log').read())
def sms(): return [x['body']['message'] for x in ghl_log() if x['path'] == '/conversations/messages']
urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:9202/__reset', data=b'{}', method='POST'))
T0 = datetime.date.today()
D = T0 + datetime.timedelta(days=2)
while D.weekday() >= 5: D += datetime.timedelta(days=1)
DS = D.isoformat()
JOURS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']
DAYTXT = '%s %d %s' % (JOURS[D.weekday()], D.day, MOIS[D.month - 1])
def job(i): return doc('jobs/' + i) or {}
def go_job(p, jid): p.evaluate("id => { const A = window.__garageApi, S = A.S; S.tab = 'agenda'; S.screen = 'job'; S.jobId = id; A.render(); window.scrollTo(0, 0); }", jid); p.wait_for_timeout(500)
def resync(p): p.evaluate('window.__supa.resync(true)'); p.wait_for_timeout(900)
def merge(path, patch): return http('POST', API + '/rest/v1/rpc/doc_merge', {'p_path': path, 'p_patch': patch}, otok)

otok, pw = seed()
c = doc('config/main'); c.pop('bookMode', None); c['homePostal'] = 'H4P 2B5'
c['hours'] = {str(x): {'open': True, 'start': '08:00', 'end': '20:00'} for x in range(7)}
doc_set(otok, 'config/main', c)
QUOTE = round(89.95 + round(89.95 * 0.05, 2) + round(89.95 * 0.09975, 2), 2)

with sync_playwright() as pl:
    b = pl.chromium.launch()
    oc = ctx(b); op = page(oc, 'owner'); op.set_viewport_size({'width': 1300, 'height': 900}); login(op, 'hassan@garage.test', pw['hassan'])
    op.goto(BASE + '#equipe'); op.wait_for_selector('#st-key', timeout=15000)
    op.fill('#st-key', 'sk_test_good1234567890'); op.click('[data-act="st-save"]'); toast_has(op, 'mode test'); op.wait_for_timeout(600)

    # ---------- 1. the booking text ----------
    n0 = len(sms())
    op.goto(BASE + '#agenda'); op.wait_for_timeout(600)
    op.click('#top [data-act="new"]'); op.wait_for_selector('#cs-q', timeout=8000)
    op.fill('#cs-q', 'Marie'); op.wait_for_timeout(400); op.locator('#cs-results .crow').first.click(); op.wait_for_selector('#blkpick .blk', state='attached', timeout=8000)
    op.evaluate("(d) => { const t = document.getElementById('f-date'); t.value = d; t.dispatchEvent(new Event('change', {bubbles:true})); }", DS); op.wait_for_timeout(500)
    op.evaluate("document.querySelector('#blkpick [data-v=\"am\"]').click()"); op.wait_for_timeout(300)
    op.click('#f-svc-in'); op.type('#f-svc-in', 'Changement'); op.wait_for_timeout(200); op.press('#f-svc-in', 'Enter'); op.wait_for_timeout(200)
    op.evaluate("document.getElementById('jobform').requestSubmit()")
    check('booked: « Texto de rendez-vous envoyé à Marie ✓ »', toast_has(op, 'Texto de rendez-vous envoyé à Marie', 15000))
    jid = psql("select id from public.docs where col = 'jobs' and data->>'date' = '%s' and data->'client'->>'firstName' = 'Marie'" % DS)
    m = sms()[n0:]
    check('one text, by itself: « votre rendez-vous avec Garage NextLine est confirmé : %s, entre 8 h et 12 h »' % DAYTXT, len(m) == 1 and ('est confirmé : %s, entre 8 h et 12 h.' % DAYTXT) in m[0], m)
    link = re.search(r'(http\S+client\.html#t=\S+)', m[0] if m else '')
    link = link.group(1) if link else ''
    check('…and the total: « Total prévu : %s $ (taxes incluses). »' % QUOTE, re.search(r'Total prévu : %s\s\$ \(taxes incluses\)\.' % ('%.2f' % QUOTE).replace('.', ','), m[0] if m else '') is not None, m)
    check('…with the link to see it and pay ahead by card', 'payer d\'avance par carte' in (m[0] if m else '') and link.startswith(BASE + 'client.html#t='), m)
    j = job(jid)
    check('the job keeps the price told to the client (Changement d\'huile 89,95 $ + taxes = %s $)' % QUOTE, (j.get('quote') or {}).get('total') == QUOTE and j['quote']['lines'][0]['desc'].startswith('Changement'), j.get('quote'))
    check('the booking made the invoice (a draft) with that total', (j.get('invoice') or {}).get('total') == QUOTE and j['invoice'].get('auto') is True and not j['invoice'].get('number') and j['invoice'].get('paid') is False, j.get('invoice'))
    check('…and that the text went (date + block)', (j.get('rdvSms') or {}).get('status') == 'sent' and j['rdvSms'].get('key') == DS + '|am', j.get('rdvSms'))
    go_job(op, jid)
    check('job page: « Texto de rendez-vous envoyé … ✓ »', 'Texto de rendez-vous envoyé' in txt(op, 'main'), txt(op, 'main')[:300])
    # changed block → a second text; saved without a change → none
    op.click('[data-act="edit"][data-id="%s"]' % jid); op.wait_for_selector('#blkpick .blk', state='attached', timeout=8000); op.wait_for_timeout(400)
    op.evaluate("document.querySelector('#blkpick [data-v=\"pm\"]').click()"); op.wait_for_timeout(300)
    op.evaluate("document.getElementById('jobform').requestSubmit()")
    for _ in range(30):
        if len(sms()) >= n0 + 2: break
        time.sleep(0.5)
    check('moved to the afternoon: a new text (« a changé … entre 12 h et 16 h »)', len(sms()) == n0 + 2 and ('a changé : %s, entre 12 h et 16 h.' % DAYTXT) in sms()[-1], (sms()[-1:], job(jid).get('block'), job(jid).get('time'), job(jid).get('rdvSms'), txt(op, '#toast')))
    op.wait_for_timeout(500); go_job(op, jid)
    op.click('[data-act="edit"][data-id="%s"]' % jid); op.wait_for_selector('#blkpick .blk', state='attached', timeout=8000); op.wait_for_timeout(400)
    op.fill('#f-notes', 'Code de la porte 1234') if op.locator('#f-notes').count() else None
    op.evaluate("document.getElementById('jobform').requestSubmit()"); op.wait_for_timeout(2500)
    check('saved again in the same block: no new text', len(sms()) == n0 + 2, len(sms()) - n0)

    # a booking without the text (a test): the box unticked
    n2 = len(sms())
    op.evaluate("() => { const A = window.__garageApi, S = A.S; S.tab = 'agenda'; S.screen = null; A.render(); }"); op.wait_for_timeout(500)
    op.click('#top [data-act="new"]'); op.wait_for_selector('#cs-q', timeout=8000)
    op.fill('#cs-q', 'Paul'); op.wait_for_timeout(400); op.locator('#cs-results .crow').first.click(); op.wait_for_selector('#blkpick .blk', state='attached', timeout=8000)
    op.evaluate("(d) => { const t = document.getElementById('f-date'); t.value = d; t.dispatchEvent(new Event('change', {bubbles:true})); }", DS); op.wait_for_timeout(500)
    op.evaluate("document.querySelector('#blkpick [data-v=\"eve\"]').click()"); op.wait_for_timeout(300)
    check('booking form: « Texto au client : date, bloc et total », ticked', op.is_checked('#f-rdvsms') and 'date, bloc et total' in txt(op, 'label:has(#f-rdvsms)'))
    op.uncheck('#f-rdvsms'); op.evaluate("document.getElementById('jobform').requestSubmit()"); op.wait_for_timeout(3000)
    pid = psql("select id from public.docs where col = 'jobs' and data->>'date' = '%s' and data->'client'->>'firstName' = 'Paul'" % DS)
    check('box unticked: booked, no text', pid and len(sms()) == n2 and not job(pid).get('rdvSms'), (pid, len(sms()) - n2))
    go_job(op, pid)
    check('…its page offers « Envoyer la confirmation au client » for later', op.locator('[data-act="rdv-send"]').count() == 1)
    op.click('[data-act="rdv-send"]')
    for _ in range(20):
        if len(sms()) > n2: break
        time.sleep(0.5)
    check('…pressed: the text goes (date, block, link)', len(sms()) == n2 + 1 and 'entre 16 h et 20 h' in sms()[-1], sms()[-1:])

    # ---------- 2. the client's page: pay ahead ----------
    cc = ctx(b, phone=True); cp = page(cc, 'client'); cp.goto(link); cp.wait_for_selector('#pay', timeout=15000)
    main = txt(cp, 'main')
    check('client page: « Votre rendez-vous », the day, « entre 12 h et 16 h », the price', 'Votre rendez-vous' in main and DAYTXT in main and 'entre 12 h et 16 h' in main and 'Total prévu' in main and ('%.2f' % QUOTE).replace('.', ',') in main, main[:300])
    check('…« Payer d\'avance … par carte », and paying on site is said possible', 'Payer d\'avance' in txt(cp, '#pay') and 'avant le départ du mécano' in main, txt(cp, '#pay'))
    cp.screenshot(path=os.path.join(SC, 'payrdv_client.png'), full_page=True)
    cp.click('#pay'); cp.wait_for_url(re.compile(r'127\.0\.0\.1:9202/pay/'), timeout=15000)
    sess = list(stripe_log()['sessions'].values())[-1]
    check('Stripe: the quote\'s total, marked « paid ahead » for this job', sess['amount_total'] == round(QUOTE * 100) and sess['metadata'].get('kind') == 'prepay' and sess['metadata'].get('job_id') == jid, (sess['amount_total'], sess['metadata']))
    cp.click('#pay'); cp.wait_for_url(re.compile(r'client\.html'), timeout=15000); cp.wait_for_timeout(2500)
    check('back on his page: « Paiement reçu. Merci ! », « Payé d\'avance », no second « Payer »', 'Paiement reçu' in txt(cp, 'main') and 'Payé d\'avance' in txt(cp, 'main') and cp.locator('#pay').count() == 0, txt(cp, 'main')[:300])
    pre = job(jid).get('prepaid') or {}
    check('the job knows it (real base): paid ahead %s $' % QUOTE, pre.get('amount') == QUOTE and pre.get('method') == 'Carte (en ligne)', pre)

    # ---------- 3. on site: the invoice takes it off ----------
    merge('jobs/' + jid, {'status': 'place', 'mechanic': 'Saleh', 'truck': 'c1', 'date': T0.isoformat(), 'block': 'pm'})
    sc = ctx(b, phone=True); sp = page(sc, 'saleh'); login(sp, 'saleh@garage.test', pw['saleh'])
    resync(sp); go_job(sp, jid); sp.wait_for_selector('.nextbtn', timeout=8000)
    check('on site, no invoice yet: « Travail fini : faire la facture »', txt(sp, '.nextbtn') == 'Travail fini : faire la facture', txt(sp, '.nextbtn'))
    sp.click('.nextbtn'); sp.wait_for_selector('[data-act="done-save"]', timeout=8000); sp.click('[data-act="done-save"]')
    sp.wait_for_selector('#i-final', timeout=8000)
    check('the invoice shows « Payé d\'avance (carte) » and « Reste à payer 0,00 $ »', 'Payé d\'avance (carte)' in txt(sp, '#totdl') and 'Reste à payer' in txt(sp, '#totdl') and '0,00' in txt(sp, '#totdl'), txt(sp, '#totdl'))
    sp.click('#i-final'); sp.wait_for_timeout(2500)
    j = job(jid)
    check('finished: paid (card, ahead), and the job is done', j.get('invoice', {}).get('paid') is True and j['invoice'].get('method') == 'Carte (en ligne)' and j.get('status') == 'termine', (j.get('invoice', {}).get('paid'), j.get('status')))

    # ---------- 4. not paid: no leaving ----------
    TD = T0.isoformat()
    cl2 = doc('clients/c2'); snap2 = {'id': 'c2', 'firstName': 'Paul', 'lastName': 'Roy', 'name': 'Paul Roy', 'phone': cl2['phone'], 'address': cl2['address'], 'postal': cl2['postal'], 'geo': cl2['geo']}
    doc_set(otok, 'jobs/p1', {'date': TD, 'time': '12:00', 'block': 'pm', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c2', 'client': snap2, 'services': ['Inspection multipoints'], 'service': 'Inspection multipoints', 'status': 'place', 'createdAt': 1})
    doc_set(otok, 'jobs/p2', {'date': TD, 'time': '16:00', 'block': 'eve', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c2', 'client': snap2, 'services': ['Inspection multipoints'], 'service': 'Inspection multipoints', 'status': 'planifie', 'createdAt': 1})
    resync(sp); go_job(sp, 'p1'); sp.wait_for_selector('.nextbtn', timeout=8000)
    sp.click('.nextbtn'); sp.wait_for_selector('[data-act="done-save"]', timeout=8000); sp.click('[data-act="done-save"]')
    sp.wait_for_selector('#i-final', timeout=8000); sp.click('#i-final')
    ok = wait_for(sp, "() => /Paiement requis avant de partir/.test((document.getElementById('sheet') || {}).textContent || '')", 10000)
    check('invoice finished, not paid: « Paiement requis avant de partir » opens at once, with what is due', ok and 'À payer' in txt(sp, '#sheet') and '67,84' in txt(sp, '#sheet'), txt(sp, '#sheet')[:200])
    check('…the job is still « on site » (not finished)', job('p1').get('status') == 'place' and job('p1').get('invoice', {}).get('number'))
    check('…the mechanic has no « leave without paying »', sp.locator('#sheet [data-act="pay-waive"]').count() == 0)
    sp.evaluate("document.querySelector('#sheet [data-act=\"sheet-close\"]').click()"); sp.wait_for_timeout(400)
    go_job(sp, 'p1')
    check('job page: the big button says « Encaisser … »', txt(sp, '.nextbtn').startswith('Encaisser'), txt(sp, '.nextbtn'))
    sp.evaluate("() => { const A = window.__garageApi; A.S.jobId = 'p1'; A.changeStatus('termine'); }"); sp.wait_for_timeout(800)
    check('« Terminer » any other way: refused, the payment window instead', job('p1').get('status') == 'place' and 'Paiement requis' in txt(sp, '#sheet'))
    sp.evaluate("document.querySelector('#sheet [data-act=\"sheet-close\"]').click()"); sp.wait_for_timeout(300)
    go_job(sp, 'p2'); sp.wait_for_selector('.nextbtn', timeout=8000); sp.click('.nextbtn'); sp.wait_for_timeout(1000)
    check('« En route » to the next client: blocked (« La job de Paul n\'est pas payée »)', 'n\'est pas payée' in txt(sp, '#sheet') and job('p2').get('status') == 'planifie', (txt(sp, '#sheet')[:160], job('p2').get('status')))
    sp.click('#sheet [data-act="pay-open"]'); sp.wait_for_selector('#sheet [data-act="pay-link"]', timeout=8000)
    n1 = len(sms())
    sp.click('#sheet [data-act="pay-link"]')
    check('« Envoyer le lien de paiement par texto » : sent', toast_has(sp, 'Texto envoyé au client', 12000) and len(sms()) == n1 + 1 and 'voici votre facture' in sms()[-1], sms()[-1:])
    link2 = re.search(r'(http\S+client\.html#t=\S+)', sms()[-1]).group(1)
    cp.goto(link2); cp.reload(); cp.wait_for_selector('#pay', timeout=15000); cp.click('#pay'); cp.wait_for_url(re.compile(r'127\.0\.0\.1:9202/pay/'), timeout=15000)
    cp.click('#pay'); cp.wait_for_url(re.compile(r'client\.html'), timeout=15000); cp.wait_for_timeout(1500)
    ok = toast_has(sp, 'Paiement reçu ✓', 15000) or (resync(sp) or toast_has(sp, 'Paiement reçu ✓', 5000))
    check('the client paid on his phone → on the mechanic\'s phone: « Paiement reçu ✓ », the window goes away', ok and job('p1').get('invoice', {}).get('paid') is True, job('p1').get('invoice', {}).get('paid'))
    go_job(sp, 'p1'); sp.wait_for_selector('.nextbtn', timeout=8000)
    check('…now « Terminer la job »', txt(sp, '.nextbtn') == 'Terminer la job', txt(sp, '.nextbtn'))
    sp.click('.nextbtn'); sp.wait_for_timeout(1500)
    check('…done', job('p1').get('status') == 'termine')

    # ---------- 5. paid on site ----------
    doc_set(otok, 'jobs/p3', {'date': TD, 'time': '13:00', 'block': 'pm', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c2', 'client': snap2, 'services': ['Inspection multipoints'], 'service': 'Inspection multipoints', 'status': 'place', 'createdAt': 1})
    resync(sp); go_job(sp, 'p3'); sp.wait_for_selector('.nextbtn', timeout=8000)
    sp.click('.nextbtn'); sp.wait_for_selector('[data-act="done-save"]', timeout=8000); sp.click('[data-act="done-save"]')
    sp.wait_for_selector('#i-final', timeout=8000); sp.click('#i-final')
    wait_for(sp, "() => !!document.querySelector('#sheet [data-act=\"pay-here\"]')", 10000)
    sp.click('#sheet [data-act="pay-here"][data-v="Débit"]')
    check('« Payé sur place : Débit » : noted', toast_has(sp, 'Paiement noté : Débit'))
    sp.wait_for_timeout(800); i3 = job('p3').get('invoice', {})
    check('…invoice paid by debit (real base)', i3.get('paid') is True and i3.get('method') == 'Débit', i3)
    go_job(sp, 'p3'); sp.wait_for_selector('.nextbtn', timeout=8000); sp.click('.nextbtn'); sp.wait_for_timeout(1200)
    check('…« Terminer la job » : done', job('p3').get('status') == 'termine')
    check('mechanic phone: no errors', not [e for e in ERRS if e.startswith('saleh')], ERRS[:3])

    # ---------- 6. the owner lets one go ----------
    doc_set(otok, 'jobs/p4', {'date': TD, 'time': '14:00', 'block': 'pm', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c2', 'client': snap2, 'services': ['Inspection multipoints'], 'service': 'Inspection multipoints', 'status': 'place', 'createdAt': 1,
                              'invoice': {'lines': [{'type': 'forfait', 'desc': 'Inspection multipoints', 'qty': 1, 'price': 59}], 'taxesOn': True, 'sub': 59, 'tps': 2.95, 'tvq': 5.89, 'total': 67.84, 'paid': False, 'method': '', 'number': 'F-0099', 'issuedAt': TD}})
    resync(op); go_job(op, 'p4'); op.wait_for_selector('.nextbtn', timeout=8000)
    check('owner: the job not paid says « Encaisser 67,84 $ »', txt(op, '.nextbtn') == 'Encaisser 67,84 $', txt(op, '.nextbtn'))
    op.click('.nextbtn'); op.wait_for_selector('#sheet [data-act="pay-waive"]', timeout=8000)
    op.click('#sheet [data-act="pay-waive"]'); op.wait_for_timeout(1200)
    check('owner: « Laisser partir sans paiement » noted on the job (who, when)', (job('p4').get('payWaived') or {}).get('by') and job('p4').get('invoice', {}).get('paid') is False, job('p4').get('payWaived'))
    go_job(op, 'p4'); op.click('.nextbtn'); op.wait_for_timeout(1200)
    check('…then the job can finish (still not paid on the invoice)', job('p4').get('status') == 'termine')
    check('owner computer: no errors', not [e for e in ERRS if e.startswith('owner')], ERRS[:3])
    b.close()
summary()
