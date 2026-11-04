"""Team version on the local Supabase copy: photos before/after, client signature, extra work approved by the client,
invoice texted to the client, paid by card through a fake Stripe (same API, signed notices)."""
import json, os, re, sys, time, hmac, hashlib
from playwright.sync_api import sync_playwright
from team_seed import *

def stripe_log(): return json.loads(urllib.request.urlopen('http://127.0.0.1:9202/__log').read())
def ghl_log(): return json.loads(urllib.request.urlopen('http://127.0.0.1:9200/__log').read())
urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:9202/__reset', data=b'{}', method='POST'))
otok, PW = seed()
PHOTO1, PHOTO2 = os.path.join(SC, 'recu_test.jpg'), os.path.join(SC, 'vin/vin_civic.png')
def go_job(p, jid): p.evaluate("id => { const S = window.__garageApi.S; S.tab = 'agenda'; S.screen = 'job'; S.jobId = id; window.__garageApi.render(); window.scrollTo(0, 0); }", jid); p.wait_for_timeout(500)
def resync(p): p.evaluate('window.__supa.resync(true)'); p.wait_for_timeout(900)
def secret(name): return psql("select value from public.app_secrets where name='%s'" % name)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    # ---------- 1. owner plugs Stripe (key stays on the server) ----------
    oc = ctx(br); op = page(oc, 'owner'); login(op, 'hassan@garage.test', PW['hassan'])
    op.goto(BASE + '#equipe'); op.wait_for_selector('#st-key', timeout=15000)
    check('Équipe et accès: Stripe « Pas branché » at first', 'Pas branché' in txt(op, 'section:has(#st-key)'))
    op.fill('#st-key', 'pk_live_abc123456789'); op.click('[data-act="st-save"]')
    check('public key (pk_) refused with a clear message', toast_has(op, 'sk_live_'), txt(op, '#toast'))
    op.fill('#st-key', 'sk_test_mauvaise1234567'); op.click('[data-act="st-save"]')
    check('wrong key refused by Stripe', toast_has(op, 'Stripe refuse cette clé'), txt(op, '#toast'))
    op.fill('#st-key', 'sk_test_good1234567890'); op.click('[data-act="st-save"]')
    check('good test key: « branché en mode test »', toast_has(op, 'mode test'), txt(op, '#toast'))
    op.wait_for_timeout(500)
    sl = stripe_log()
    hooks = list(sl['hooks'].values())
    check('the « paid » notice (webhook) is created at Stripe, pointed at the garage server', len(hooks) == 1 and hooks[0]['url'].endswith('/functions/v1/client') and 'checkout.session.completed' in hooks[0]['events'], hooks)
    check('key + notice secret kept only on the server (app_secrets)', secret('STRIPE_KEY') == 'sk_test_good1234567890' and secret('STRIPE_WEBHOOK_SECRET') == hooks[0]['secret'] and secret('STRIPE_WEBHOOK_ID') == hooks[0]['id'])
    check('the page shows only the last 4 characters', 'sk_test_good1234567890' not in op.content() and '…7890' in txt(op, 'section:has(#st-key)') and 'mode test' in txt(op, 'section:has(#st-key)') and 'confirmation automatique' in txt(op, 'section:has(#st-key)'))
    op.fill('#st-key', 'sk_test_good1234567890'); op.click('[data-act="st-save"]'); toast_has(op, 'mode test'); op.wait_for_timeout(400)
    check('saving again replaces the notice (old one deleted at Stripe, still 1)', len(stripe_log()['hooks']) == 1 and list(stripe_log()['hooks'].values())[0]['id'] != hooks[0]['id'])
    check('everyone\'s phone knows « Payer » is on (config/keys.payOnline)', (doc('config/keys') or {}).get('payOnline') is True)
    r = http('POST', API + '/rest/v1/rpc/doc_set', {'p_path': 'config/x', 'p_data': {}}, otok)
    rd = http('GET', API + '/rest/v1/app_secrets?select=name', token=otok)
    check('nobody can read the keys through the API, not even the owner', (isinstance(rd, list) and len(rd) == 0) or (isinstance(rd, dict) and rd.get('_status') in (401, 403)), rd)

    # ---------- 2. Saleh (phone): no more photos, the client signs the waiver before the work ----------
    sc = ctx(br, phone=True); sp = page(sc, 'saleh'); login(sp, 'saleh@garage.test', PW['saleh'])
    go_job(sp, 'j1')
    check('phone job page: « Décharge du client » fold, no photo buttons', sp.locator('#wv-fold').count() == 1 and sp.locator('#pin-av, #pin-ap').count() == 0)
    if sp.locator('#wv-fold[open]').count() == 0: sp.click('#wv-fold summary'); sp.wait_for_timeout(200)
    sp.click('#wv-fold [data-act="wv-open"]'); sp.wait_for_selector('#sigpad')
    check('waiver sheet: the text the client signs (with the garage\'s name) + pad + name', 'J\'autorise Garage NextLine' in txt(sp, '#sheet') and sp.input_value('#sig-name') == 'Marie Tremblay' and sp.locator('#sig-save[disabled]').count() == 1)
    bb = sp.locator('#sigpad').bounding_box()
    sp.mouse.move(bb['x'] + 30, bb['y'] + 120); sp.mouse.down()
    for i in range(1, 30): sp.mouse.move(bb['x'] + 30 + i * 9, bb['y'] + 120 - 50 * abs(((i % 10) - 5) / 5))
    sp.mouse.up(); sp.wait_for_timeout(200)
    check('after drawing, « Enregistrer » is enabled', sp.locator('#sig-save[disabled]').count() == 0)
    sp.click('#sig-save'); sp.wait_for_timeout(1800)
    j1 = doc('jobs/j1') or {}; wv = j1.get('waiver') or {}
    sdoc = doc('photos/' + wv.get('id', 'x')) or {}
    check('waiver saved: name, time, the text signed; the signature kept apart (small picture)', wv.get('name') == 'Marie Tremblay' and wv.get('at') and 'Garage NextLine' in wv.get('text', '') and sdoc.get('kind') == 'waiver' and sdoc.get('img', '').startswith('data:image/') and len(sdoc.get('img', '')) < 130000, [wv, sdoc.get('kind')])
    check('waiver shown on the job', 'Signée par Marie Tremblay' in (sp.text_content('#wv-fold') or '') and sp.locator('#wv-fold .sigbox img').count() == 1)
    check('phone: no sideways scroll', no_hscroll(sp))
    # access rules (the signatures are kept like the photos were)
    atok, ttok, stok = token('ali@garage.test', PW['ali']), token('nadia@garage.test', PW['nadia']), token('saleh@garage.test', PW['saleh'])
    r = http('GET', API + '/rest/v1/docs?select=path&col=eq.photos', token=atok)
    check('Ali (another mechanic) sees the signature on Saleh\'s job too (every route, to help)', isinstance(r, list) and len(r) == 1, r)
    r = doc_set(atok, 'photos/j1__help', {'jobId': 'j1', 'kind': 'avant', 'img': 'x'})
    check('…and may add a photo to Saleh\'s job (helping)', not (isinstance(r, dict) and r.get('_status', 200) >= 400), r)
    psql("delete from public.docs where path = 'photos/j1__help'")
    r = http('POST', API + '/rest/v1/rpc/doc_set', {'p_path': 'photos/j1__x', 'p_data': {'jobId': 'j1', 'img': 'x'}})
    check('without signing in: no photo', isinstance(r, dict) and r.get('_status', 200) >= 400, r)
    r = http('GET', API + '/rest/v1/docs?select=path&col=eq.photos', token=ttok)
    check('treasurer sees it (1)…', isinstance(r, list) and len(r) == 1, r)
    r = doc_set(ttok, 'photos/j1__t', {'jobId': 'j1', 'kind': 'waiver', 'img': 'x'})
    check('… but cannot add one', isinstance(r, dict) and r.get('_status') in (400, 401, 403), r)

    # ---------- 3. the photos of the old way stay visible ----------
    doc_set(otok, 'photos/j1__old1', {'jobId': 'j1', 'kind': 'avant', 'img': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=', 'at': 1})
    psql("update public.docs set data = data || '{\"photos\": [{\"id\": \"j1__old1\", \"kind\": \"avant\", \"at\": 1}]}' where path = 'jobs/j1'")
    sp.reload(); sp.wait_for_timeout(1500); go_job(sp, 'j1')
    if sp.locator('#wv-fold[open]').count() == 0: sp.click('#wv-fold summary'); sp.wait_for_timeout(200)
    check('a job with photos from before: they are still there, under « ancienne façon »', sp.locator('#wv-fold details', has_text='ancienne façon').count() == 1 and sp.locator('#wv-fold .pthumb').count() == 1)

    # ---------- 4. extra work: proposed, texted, accepted by the client ----------
    sp.click('#xp-fold summary') if sp.locator('#xp-fold[open]').count() == 0 else None; sp.wait_for_timeout(200)
    sp.click('#xp-fold [data-act="xp-new"]'); sp.wait_for_selector('#xp-desc')
    sp.click('[data-act="xp-svc"] >> text=Freins avant'); sp.fill('#xp-desc', 'Disques avant'); sp.fill('#xp-price', '180'); sp.click('[data-act="xp-add"]')
    sp.fill('#xp-note', 'Plaquettes à 2 mm, disques rainurés.')
    check('proposal sheet: 2 items, total 429,00 $ before taxes', 'Freins avant (plaquettes)' in txt(sp, '#xp-list') and 'Disques avant' in txt(sp, '#xp-list') and '429,00 $' in txt(sp, '#xp-list'), txt(sp, '#xp-list'))
    sp.click('[data-act="xp-save"]'); sp.wait_for_timeout(1200)
    xs = (doc('jobs/j1') or {}).get('extras') or []
    check('proposal saved « en attente »', len(xs) == 1 and xs[0]['status'] == 'attente' and xs[0]['total'] == 429 and xs[0]['note'].startswith('Plaquettes'), xs)
    sp.wait_for_timeout(300)
    check('phone: fold opened « 1 en attente du client »', '1 en attente du client' in txt(sp, '#xp-fold summary'))
    sp.click('#xp-fold [data-act="xp-send"]')
    check('« Envoyer au client par texto » → texto envoyé', toast_has(sp, 'Texto envoyé au client', 15000), txt(sp, '#toast'))
    sms = [x for x in ghl_log() if x['path'] == '/conversations/messages']
    link = re.search(r'(http://127\.0\.0\.1:8088/client\.html#t=[A-Za-z0-9_-]{20,})', sms[-1]['body']['message']).group(1) if sms else ''
    check('the text: Saleh proposes work on the Honda Civic (429,00 $), with the secret link', link and 'Saleh de Garage NextLine propose des travaux' in sms[-1]['body']['message'] and '2018 Honda Civic' in sms[-1]['body']['message'] and '429,00 $' in sms[-1]['body']['message'], sms[-1:] if sms else None)
    check('job records it was sent by text', ((doc('jobs/j1') or {}).get('extras') or [{}])[0].get('smsStatus') == 'sent')
    cc = ctx(br, phone=True, scheme='dark'); cp = page(cc, 'client')
    cp.goto(link); cp.wait_for_selector('[data-ans="1"]', timeout=15000)
    check('client page: « Bonjour Marie · 2018 Honda Civic », proposal with the 2 items and the note', 'Bonjour Marie · 2018 Honda Civic' in txt(cp, 'h1') and 'Freins avant (plaquettes)' in txt(cp, 'main') and 'Disques avant' in txt(cp, 'main') and 'Plaquettes à 2 mm' in txt(cp, 'main'), txt(cp, 'main')[:300])
    check('client page shows nothing internal (no mechanic notes, no other jobs, no keys)', 'Paul' not in cp.content() and 'pit-' not in cp.content() and 'sk_test' not in cp.content())
    check('client page: no sideways scroll (phone, dark)', no_hscroll(cp))
    cp.screenshot(path=os.path.join(SC, 'c_travaux_dark.png'))
    cp.click('[data-ans="1"]'); cp.wait_for_timeout(1200)
    check('client accepts: « Merci ! Le mécano est avisé »', 'Le mécano est avisé' in txt(cp, 'main') and 'Acceptés' in txt(cp, 'main'))
    x0 = ((doc('jobs/j1') or {}).get('extras') or [{}])[0]
    check('server: proposal accepted, by the client\'s link', x0.get('status') == 'accepte' and x0.get('answeredBy') == 'lien' and x0.get('answeredAt'), x0)
    r = http('POST', API + '/functions/v1/client', {'action': 'answer', 'token': link.split('t=')[1], 'extraId': x0['id'], 'accept': False})
    check('answering twice does not change the answer', ((doc('jobs/j1') or {}).get('extras') or [{}])[0].get('status') == 'accepte' and r.get('already'), r)
    resync(sp); go_job(sp, 'j1')
    check('mechanic\'s phone shows « Accepté … par le client (lien) »', 'Accepté' in txt(sp, '#xp-fold') and 'par le client (lien)' in txt(sp, '#xp-fold'), txt(sp, '#xp-fold')[:200])
    # a second proposal refused out loud, a third signed on the phone
    for label, act in (('Pneus', 'xp-no'), ('Essuie-glaces', 'xp-sign')):
        if sp.locator('#xp-fold[open]').count() == 0: sp.click('#xp-fold summary'); sp.wait_for_timeout(200)
        sp.click('#xp-fold [data-act="xp-new"]'); sp.wait_for_selector('#xp-desc'); sp.fill('#xp-desc', label); sp.fill('#xp-price', '40'); sp.click('[data-act="xp-save"]'); sp.wait_for_timeout(1200)
        go_job(sp, 'j1')
        if sp.locator('#xp-fold[open]').count() == 0: sp.click('#xp-fold summary'); sp.wait_for_timeout(200)
        sp.click('#xp-fold [data-act="%s"] >> nth=-1' % act); sp.wait_for_timeout(600)
        if act == 'xp-sign':
            check('« Le client signe ici » shows the work and price to accept', 'J\'accepte les travaux supplémentaires proposés : Essuie-glaces (40,00 $ avant taxes)' in txt(sp, '#sheet'), txt(sp, '#sheet')[:200])
            bb = sp.locator('#sigpad').bounding_box(); sp.mouse.move(bb['x'] + 40, bb['y'] + 100); sp.mouse.down(); sp.mouse.move(bb['x'] + 200, bb['y'] + 60); sp.mouse.move(bb['x'] + 260, bb['y'] + 130); sp.mouse.up()
            sp.click('#sig-save'); sp.wait_for_timeout(1800)
    xs = (doc('jobs/j1') or {}).get('extras') or []
    check('« Il a dit non » → refused; signed → accepted with the signature', [x['status'] for x in xs] == ['accepte', 'refuse', 'accepte'] and xs[1]['answeredBy'] == 'manuel' and xs[2]['answeredBy'] == 'signature' and xs[2].get('sigId'), [(x['status'], x.get('answeredBy')) for x in xs])

    # ---------- 5. invoice: accepted work at its price, texted to the client ----------
    go_job(sp, 'j1')
    sp.evaluate("() => { const S = window.__garageApi.S; }")
    sp.click('#ph-fold ~ details >> text=Facture') if False else None
    sp.evaluate("() => window.__garageApi.S && document.querySelector('[data-act=\"invoice\"]') && document.querySelector('[data-act=\"invoice\"]').click()"); sp.wait_for_selector('#lines', timeout=10000); sp.wait_for_timeout(400)
    descs = sp.evaluate("[...document.querySelectorAll('#lines input')].filter(i => i.id && i.id.indexOf('desc') >= 0 || (i.getAttribute('data-f') === 'desc')).map(i => i.value)")
    lines = sp.evaluate("window.__garageApi.S.inv.lines.map(l => l.desc + '=' + l.price)")
    check('invoice prefilled: oil change + the 2 accepted extras at their approved price (not the refused one)', any(l.startswith("Changement d'huile") for l in lines) and 'Freins avant (plaquettes)=249' in lines and 'Disques avant=180' in lines and 'Essuie-glaces=40' in lines and not any(l.startswith('Pneus') for l in lines), lines)
    sp.click('#i-final'); sp.wait_for_timeout(2000)
    inv = (doc('jobs/j1') or {}).get('invoice') or {}
    check('invoice F-0001 finalized', inv.get('number') == 'F-0001' and inv.get('total') == round(558.95 + round(558.95 * 0.05 + 1e-9, 2) + round(558.95 * 0.09975 + 1e-9, 2), 2), inv.get('total'))
    go_job(sp, 'j1'); sp.click('details:has-text("Facture") summary') if sp.locator('details:has([data-act="inv-send"])[open]').count() == 0 else None; sp.wait_for_timeout(300)
    check('« Envoyer la facture au client (avec « Payer ») »', 'Envoyer la facture au client (avec « Payer »)' in txt(sp, '[data-act="inv-send"]'), txt(sp, '[data-act="inv-send"]'))
    sp.click('[data-act="inv-send"]'); toast_has(sp, 'Texto envoyé', 15000); sp.wait_for_timeout(500)
    sms = [x for x in ghl_log() if x['path'] == '/conversations/messages']
    check('text: « votre facture F-0001 … Vous pouvez la payer en ligne par carte. », same link as before', 'votre facture F-0001 de Garage NextLine' in sms[-1]['body']['message'] and 'payer en ligne par carte' in sms[-1]['body']['message'] and link in sms[-1]['body']['message'], sms[-1]['body']['message'])
    check('invoice records it was sent', (doc('jobs/j1') or {}).get('invoice', {}).get('smsStatus') == 'sent')

    # ---------- 6. the client pays by card (fake Stripe) ----------
    cp.goto(link); cp.reload(); cp.wait_for_selector('#pay', timeout=15000)
    total = inv['total']
    check('client page: Facture F-0001 « À payer », lines, taxes, total, « Payer … par carte »', 'Facture F-0001' in txt(cp, 'main') and 'À payer' in txt(cp, 'main') and 'TVQ (9,975 %)' in txt(cp, 'main') and 'Payer' in txt(cp, '#pay'), txt(cp, 'main')[-300:])
    cp.screenshot(path=os.path.join(SC, 'c_facture_dark.png'))
    cp.click('#pay'); cp.wait_for_url(re.compile(r'127\.0\.0\.1:9202/pay/'), timeout=15000)
    sess = list(stripe_log()['sessions'].values())[-1]
    check('Stripe Checkout opened: CAD, exact total in cents, French, invoice + job in the metadata', sess['currency'] == 'cad' and sess['amount_total'] == round(total * 100) and sess['locale'] == 'fr-CA' and sess['metadata'] == {'job_id': 'j1', 'invoice': 'F-0001', 'kind': 'invoice'} and '#t=' in sess['success_url'], sess)
    cp.click('#pay'); cp.wait_for_url(re.compile(r'client\.html'), timeout=15000); cp.wait_for_timeout(2000)
    dl = stripe_log()['delivered']
    check('Stripe\'s signed notice reached the garage server (200)', dl and dl[-1]['status'] == 200 and '"full":true' in dl[-1]['body'].replace(' ', ''), dl[-1:])
    inv = (doc('jobs/j1') or {}).get('invoice') or {}
    check('invoice marked paid: « Carte (en ligne) », today, amount kept', inv.get('paid') is True and inv.get('method') == 'Carte (en ligne)' and inv.get('paidAt') == TODAY and inv.get('stripe', {}).get('amount') == total and not inv['stripe'].get('short'), inv)
    check('back on the client page: « Paiement reçu. Merci ! » + « Payée »', 'Paiement reçu' in txt(cp, 'main') and 'Payée' in txt(cp, 'main') and cp.locator('#pay').count() == 0, txt(cp, 'main')[:200])
    resync(op); go_job(op, 'j1')
    check('owner sees « Payée en ligne par carte » on the job', 'Payée en ligne par carte' in txt(op, 'main') and 'Payée' in txt(op, 'main'), txt(op, 'main')[-400:])
    # the same notice again, a forged notice
    ev = {'id': 'evt_replay', 'type': 'checkout.session.completed', 'data': {'object': dict(sess, payment_status='paid')}}
    payload = json.dumps(ev); t = str(int(time.time()))
    sig = hmac.new(secret('STRIPE_WEBHOOK_SECRET').encode(), (t + '.' + payload).encode(), hashlib.sha256).hexdigest()
    def hook(payload, header):
        req = urllib.request.Request(API + '/functions/v1/client', data=payload.encode(), method='POST', headers={'Content-Type': 'application/json', 'apikey': K['anon'], 'stripe-signature': header})
        try:
            with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read().decode() or '{}')
    st1, b1 = hook(payload, 't=%s,v1=%s' % (t, sig)); st2, b2 = hook(payload, 't=%s,v1=%s' % (t, sig))
    check('the same notice twice: handled once', st1 == 200 and st2 == 200 and b2.get('duplicate') is True, (b1, b2))
    forged = json.dumps({'id': 'evt_forged', 'type': 'checkout.session.completed', 'data': {'object': {'id': 'cs_x', 'payment_status': 'paid', 'amount_total': 1, 'metadata': {'job_id': 'j2'}}}})
    st3, b3 = hook(forged, 't=%s,v1=%s' % (t, 'a' * 64))
    st4, b4 = hook(forged, 't=%s,v1=%s' % (str(int(time.time()) - 900), hmac.new(secret('STRIPE_WEBHOOK_SECRET').encode(), (str(int(time.time()) - 900) + '.' + forged).encode(), hashlib.sha256).hexdigest()))
    check('a forged notice (bad signature, or replayed 15 min later) is refused', st3 == 400 and st4 == 400 and not (doc('jobs/j2') or {}).get('invoice'), (st3, st4))

    # ---------- 7. notice lost: the client coming back confirms it; amount changed after → flagged, not paid ----------
    doc_set(otok, 'jobs/j2', dict(doc('jobs/j2'), invoice={'number': 'F-0002', 'issuedAt': TODAY, 'lines': [{'type': 'mo', 'desc': 'Inspection multipoints', 'qty': 1, 'price': 59}], 'taxesOn': True, 'sub': 59, 'tps': 2.95, 'tvq': 5.89, 'total': 67.84, 'paid': False}))
    r = fn(otok, 'client', {'action': 'link', 'jobId': 'j2', 'base': BASE})
    link2 = r.get('link', '')
    check('owner makes a link without texting (Ali\'s job)', link2.startswith(BASE + 'client.html#t='), r)
    cp.goto(link2); cp.reload(); cp.wait_for_selector('#pay', timeout=15000); cp.click('#pay'); cp.wait_for_url(re.compile(r'127\.0\.0\.1:9202/pay/'), timeout=15000)
    cp.click('#pay-nohook'); cp.wait_for_url(re.compile(r'client\.html'), timeout=15000); cp.wait_for_timeout(2500)
    check('no notice from Stripe: coming back to the page checks with Stripe and marks it paid', (doc('jobs/j2') or {}).get('invoice', {}).get('paid') is True and 'Paiement reçu' in txt(cp, 'main'), (doc('jobs/j2') or {}).get('invoice'))
    jx = dict(doc('jobs/j2')); jx.pop('invoice'); jx['invoice'] = {'number': 'F-0003', 'issuedAt': TODAY, 'lines': [{'type': 'mo', 'desc': 'Diagnostic', 'qty': 1, 'price': 100}], 'taxesOn': True, 'sub': 100, 'tps': 5, 'tvq': 9.98, 'total': 114.98, 'paid': False}
    doc_set(otok, 'jobs/j3', dict(jx, status='termine')); r = fn(otok, 'client', {'action': 'link', 'jobId': 'j3', 'base': BASE}); link3 = r.get('link', '')
    cp.goto(link3); cp.reload(); cp.wait_for_selector('#pay', timeout=15000); cp.click('#pay'); cp.wait_for_url(re.compile(r'127\.0\.0\.1:9202/pay/'), timeout=15000)
    j3 = doc('jobs/j3'); j3['invoice'] = dict(j3['invoice'], total=150.0); doc_set(otok, 'jobs/j3', j3)   # the invoice changed while the client was paying
    cp.click('#pay'); cp.wait_for_url(re.compile(r'client\.html'), timeout=15000); cp.wait_for_timeout(2000)
    i3 = (doc('jobs/j3') or {}).get('invoice') or {}
    check('amount different from the invoice: kept but NOT marked paid, flagged', i3.get('paid') is False and i3.get('stripe', {}).get('amount') == 114.98 and i3['stripe'].get('short') is True, i3)
    resync(op); go_job(op, 'j3')
    check('owner sees the warning « ne correspond pas au total »', 'ne correspond pas au total' in txt(op, 'main'))

    # ---------- 8. who may make links; broken links ----------
    r = fn(stok, 'client', {'action': 'link', 'jobId': 'j2', 'send': 'facture'})
    check('Saleh may text Ali\'s client (every mechanic does every job)', r.get('ok') and r.get('token'), r)
    r = fn(ttok, 'client', {'action': 'link', 'jobId': 'j1'})
    check('the treasurer cannot send links', r.get('_status') == 403, r)
    r = fn(None, 'client', {'action': 'link', 'jobId': 'j1'})
    check('nobody signed in → refused', r.get('_status') == 401, r)
    cp.goto(BASE + 'client.html#t=' + 'x' * 24); cp.reload(); cp.wait_for_timeout(1500)
    check('a wrong link: « Ce lien n\'est plus valide »', 'plus valide' in txt(cp, 'main'), txt(cp, 'main'))
    psql("update public.client_links set expires_at = now() - interval '1 day' where job_id='j2'")
    cp.goto(link2); cp.reload(); cp.wait_for_timeout(1500)
    check('an expired link (120 days) no longer opens', 'plus valide' in txt(cp, 'main'), txt(cp, 'main'))
    # ---------- 9. truck stock with the real access rules ----------
    r = doc_set(ttok, 'stock/c1__huile-0w-20', {'truck': 'c1', 'name': 'Huile 0W-20', 'ref': '', 'unit': 'L', 'qty': 20, 'min': 10})
    r2_ = doc_set(ttok, 'stock/c1__filtre-ph7317', {'truck': 'c1', 'name': 'Filtre', 'ref': 'PH7317', 'unit': 'unité', 'qty': 3, 'min': 2})
    check('treasurer stocks Camion 1 (oil 20 L, 3 filters)', r is None and r2_ is None and psql("select count(*) from public.docs where col='stock'") == '2', (r, r2_))
    doc_set(otok, 'specs/2018-honda-civic-2-4', {'key': '2018-honda-civic-2-4', 'year': '2018', 'make': 'Honda', 'model': 'Civic', 'displL': 2, 'cyl': 4, 'oilL': 4.4, 'oilVisc': '0W-20', 'oilFilter': 'PH7317', 'parts': []})
    j4 = dict(doc('jobs/j1')); [j4.pop(k, None) for k in ('invoice', 'extras', 'photos', 'signature', 'done', 'used')]
    doc_set(otok, 'jobs/j4', dict(j4, status='place', time='16:00', services=["Changement d'huile et filtre"]))
    r = http('GET', API + '/rest/v1/docs?select=path&col=eq.stock', token=atok)
    check('every mechanic sees the trucks\' stock', isinstance(r, list) and len(r) == 2, r)
    resync(sp); go_job(sp, 'j4')
    sp.evaluate("() => document.querySelector('[data-act=\"done-edit\"]').click()"); sp.wait_for_selector('#use-box .userow', timeout=10000)
    check('team · Saleh: « Pièces utilisées » ready (oil 4,4 L + filter, from the inventory)', sp.locator('#use-box .userow').count() == 2 and 'enlevées de l\'inventaire' in txt(sp, '#use-box') and 'en stock' in txt(sp, '#use-box'), txt(sp, '#use-box'))
    sp.click('[data-act="done-save"]'); sp.wait_for_timeout(2000)
    check('team · stock lowered in the real base (15,6 L, 2 filters)', (doc('stock/c1__huile-0w-20') or {}).get('qty') == 15.6 and (doc('stock/c1__filtre-ph7317') or {}).get('qty') == 2, (doc('stock/c1__huile-0w-20'), doc('stock/c1__filtre-ph7317')))
    r = http('POST', API + '/rest/v1/rpc/doc_merge', {'p_path': 'config/main', 'p_patch': {'rate': 1}}, stok)
    check('a refused update now says « not_granted » (not « not_found »)', isinstance(r, dict) and r.get('_status') in (401, 403) and 'not_granted' in r.get('_body', ''), r)
    check('no script errors', not ERRS, ERRS[:5])
    br.close()

psql("truncate public.members, public.docs, public.docs_deleted, public.mech_live, public.mech_positions, public.tracks, public.setup_codes, public.app_secrets, public.client_links, public.stripe_events cascade; delete from auth.users;")
sys.exit(0 if summary() else 1)
