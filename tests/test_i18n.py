"""French and English, everywhere: each person picks his language (the sign-in screen, « Plus », the computer's side bar),
it follows him on his other devices; numbers, money and dates the English way; every screen of every role in English
(nothing left in French but the person's own words); the guided tour in English; the client's language on his file:
his invoice, his texts (on the way, invoice, extra work), his pages (invoice and payment, tracking) in his language, with
a FR / EN switch for him; an invitation in the language of the person who sends it. French users see no change."""
import json, re, time, urllib.request
from team_seed import *
from tour_walk import walk, autonav
from playwright.sync_api import sync_playwright

def ghl_log(): return json.loads(urllib.request.urlopen('http://127.0.0.1:9200/__log').read())
FRENCH = re.compile(r"(?<![A-Za-zÀ-ÿ])(le|la|les|des|du|une|est|pas|avec|pour|dans|sur|tu|ton|ta|tes|vous|votre|aucune?|jour|semaine|facture|réglages|rendez-vous|enregistrer|annuler|modifier|supprimer|touche|ajouter|ouvrir|fermer)(?![A-Za-zÀ-ÿ])", re.I)
def leftovers(p):
    """texts on the screen still in French (the test garage's own words left aside: names, addresses, notes, services)"""
    return p.evaluate(r"""() => { const out = [], seen = new Set();
      const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = tw.nextNode(); n; n = tw.nextNode()){ const e = n.parentElement; if (!e || e.closest('script,style,textarea,[translate="no"],.notr,#tour-ov .tt-n')) continue;
        const r = e.getBoundingClientRect(); if (!(r.width > 0 && r.height > 0)) continue;
        const t = n.data.replace(/\s+/g, ' ').trim(); if (t.length > 1 && !seen.has(t)){ seen.add(t); out.push(t); } }
      for (const e of document.querySelectorAll('[placeholder],[aria-label],[title]')) for (const a of ['placeholder', 'aria-label', 'title']){ const v = e.getAttribute(a); if (v && !seen.has(v)){ seen.add(v); out.push(v); } }
      return out; }""")
DATA = re.compile(r"Marie|Tremblay|Paul|Roy|Saint-Denis|Ontario|Montréal|Garage NextLine|Honda|Ford|Civic|F-150|Bruit au freinage|Plaquettes|Changement d'huile|Freins avant|Inspection multipoints|Plateau|Mont-Royal|rue |Camion \d|Hassan|Saleh|Ali|Lina|Nadia|Bureau Lina|Trésor|NextLine")
def french(p):
    return [t for t in leftovers(p) if FRENCH.search(t) and not DATA.search(t)]

otok, pw = seed()
with sync_playwright() as pl:
    b = pl.chromium.launch()
    # ---------- 1. the sign-in screen: the switch, before signing in ----------
    c = ctx(b); p = page(c, 'gate'); p.goto(BASE + '#agenda'); p.wait_for_selector('#gate #g-email', timeout=15000); p.wait_for_timeout(300)
    check('French by default (a French phone): the sign-in screen in French, with « Français · English » at the bottom', 'Connexion' in txt(p, '#gate') and p.locator('#gate .g-lang [data-v="en"]').count() == 1 and p.evaluate("document.documentElement.lang") == 'fr-CA')
    p.click('#gate .g-lang [data-v="en"]'); p.wait_for_timeout(300)
    g = txt(p, '#gate')
    check('« English »: the sign-in screen is in English at once (« Sign in », the email and password labels)', 'Sign in' in g and 'Email' in g and 'Password' in g and 'Connexion' not in g and p.evaluate("document.documentElement.lang") == 'en-CA', g[:200])
    p.reload(); p.wait_for_selector('#gate #g-email', timeout=15000); p.wait_for_timeout(300)
    check('…remembered on this device (reload: still English)', 'Sign in' in txt(p, '#gate'))
    p.fill('#g-email', 'hassan@garage.test'); p.fill('#g-pw', pw['hassan']); p.click('#g-go'); p.wait_for_selector('#gate', state='detached', timeout=20000); p.wait_for_timeout(1800)
    # ---------- 2. every screen of the owner, computer, in English ----------
    p.set_viewport_size({'width': 1366, 'height': 860})
    bad = {}
    for t in ['accueil', 'agenda', 'clients', 'factures', 'tresor', 'stock', 'carte', 'dispos', 'reglages', 'equipe']:
        p.evaluate("location.hash = '%s'" % t); p.wait_for_timeout(900)
        f = french(p)
        if f: bad[t] = f[:6]
        p.screenshot(path='i18n_en_%s.png' % t)
    check('owner · computer: every screen in English (dashboard, schedule, clients, invoices, finances, stock, map, availability, settings, team)', not bad, bad)
    tabs = p.evaluate("[...document.querySelectorAll('#tabbar .tab:not([hidden]) span')].map(e => e.textContent)")
    check('the menu in English (Dashboard, Schedule, Clients, Invoices, Settings…)', 'Schedule' in tabs and 'Invoices' in tabs and 'Settings' in tabs, tabs)
    p.evaluate("location.hash = 'accueil'"); p.wait_for_timeout(800)
    m = txt(p, '#main')
    check('money the English way ($ in front, a dot for cents) and dates in English', re.search(r'\$\d[\d,]*\.\d\d', m) and not re.search(r'\d,\d\d\s?\$', m) and re.search(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|January|February|March|April|May|June|July|August|September|October|November|December)', txt(p, 'body')), m[:300])
    check('the side bar: « Français · English », English chosen', p.locator('#navfoot .nf-lang [data-v="en"][aria-pressed="true"]').count() == 1)
    # the person's language follows him: saved on his account
    pref = doc('data/users/%s/prefs' % psql("select id from auth.users where email='hassan@garage.test'"))
    check('…saved with his account (so his other devices follow)', not pref or pref.get('lang') in (None, 'en'), pref)
    p.click('#navfoot .nf-lang [data-v="fr"]'); p.wait_for_timeout(600)
    check('« Français »: back to French at once (same screen)', 'Tableau de bord' in txt(p, 'body') or 'Aujourd' in txt(p, 'body'))
    p.click('#navfoot .nf-lang [data-v="en"]'); p.wait_for_timeout(600)
    pref = doc('data/users/%s/prefs' % psql("select id from auth.users where email='hassan@garage.test'"))
    check('…each choice saved with his account (now English)', pref and pref.get('lang') == 'en', pref)
    c.close()
    c = ctx(b, phone=True); p = page(c, 'other device'); login(p, 'hassan@garage.test', pw['hassan']); p.wait_for_timeout(1500)
    check('another device (a French phone, never chosen there): after signing in, the app switches to his language, English', 'More' in txt(p, '#tabbar') and p.evaluate("window.I18N.lang") == 'en', txt(p, '#tabbar'))
    # ---------- 3. the phone: every screen of each role in English ----------
    c.close()
    for who in ('hassan', 'saleh', 'lina', 'nadia'):
        c = ctx(b, phone=True); c.add_init_script("try { localStorage.setItem('gm.lang', 'en'); } catch(e){}"); p = page(c, who + ' en')
        login(p, who + '@garage.test', pw[who]); p.wait_for_timeout(1500)
        bad = {}
        for t in ['jour', 'agenda', 'clients', 'factures', 'plus', 'tresor', 'stock', 'carte', 'dispos', 'reglages', 'accueil', 'equipe']:
            p.evaluate("location.hash = '%s'" % t); p.wait_for_timeout(800)
            if p.evaluate("location.hash") != '#' + t: continue
            f = french(p)
            if f: bad[t] = f[:6]
        p.evaluate("location.hash = 'jour'"); p.wait_for_timeout(600)
        op = p.locator('#main [data-act="open"]')
        if op.count(): op.first.click(); p.wait_for_timeout(1000); f = french(p); bad.update({'job': f[:6]} if f else {}); p.screenshot(path='i18n_en_job_%s.png' % who)
        check('%s · phone: every screen in English (and an open job)' % who, not bad, bad)
        c.close()
    # ---------- 4. the guided tour in English (the owner, phone): every step, nothing left in French ----------
    psql("delete from public.docs where path like 'data/users/%/tour'")
    c = ctx(b, phone=True); c.add_init_script("try { localStorage.setItem('gm.lang', 'en'); } catch(e){}"); p = page(c, 'tour en')
    login(p, 'saleh@garage.test', pw['saleh'], tour=True)
    p.wait_for_function("!!document.querySelector('#tour-ov .tt-tip')", timeout=9000)
    tfr = []
    def rec(pg, s):
        f = [t for t in leftovers(pg) if FRENCH.search(t) and not DATA.search(t) and pg.evaluate("(t) => !!document.querySelector('#tour-ov') && document.querySelector('#tour-ov').innerText.includes(t)", t)]
        if f: tfr.append((s['t'], f[:3]))
    st = walk(p, record=rec)
    words = [s['words'] for s in st]
    tfr += [(s['t'], [w]) for s in st for w in [s['words']] if FRENCH.search(w.replace(s['t'], ''))][:5]
    check('the mechanic\'s guided tour in English, start to end (%d steps): « Welcome, Saleh! », first the app on the home screen, nothing in French' % len(st),
          st and st[0]['t'].startswith('Welcome') and st[-1]['end'] and not tfr and not autonav(st), {'first': [s['t'] for s in st[:4]], 'french': tfr[:6], 'last': st[-1]['t'] if st else '', 'end': st[-1]['end'] if st else '', 'autonav': autonav(st)[:3]})
    p.click('#tour-ov [data-act="tt-end"]'); p.wait_for_timeout(800)
    c.close()
    # ---------- 5. the client's language: on his file; his invoice, his texts, his pages ----------
    c = ctx(b); p = page(c, 'owner fr'); login(p, 'hassan@garage.test', pw['hassan']); p.wait_for_timeout(1200)
    p.click('#navfoot .nf-lang [data-v="fr"]'); p.wait_for_timeout(600)   # (his account was in English: he switches to French, saved with his account)
    p.evaluate("location.hash = 'clients'"); p.wait_for_timeout(700)
    p.locator('#main', has_text='Marie').locator('text=Marie Tremblay').first.click(); p.wait_for_timeout(700)
    p.locator('[data-act="cl-edit"]').first.click(); p.wait_for_timeout(600)
    check('client file: « Langue du client (textos, courriels, facture) » · Français / Anglais (French by default)', p.locator('[data-act="c-lang"][data-v="fr"][aria-pressed="true"]').count() == 1 and 'Langue du client' in txt(p, '#clientform'))
    p.fill('#c-addr', '4520 rue Saint-Denis, Montréal, H2J 2L3'); p.wait_for_timeout(300)   # (the test client's address had no postal code)
    p.click('[data-act="c-lang"][data-v="en"]'); p.click('#c-save'); p.wait_for_timeout(1500)
    check('…« Anglais » saved on Marie\'s file', (doc('clients/c1') or {}).get('lang') == 'en', doc('clients/c1'))
    # an invoice for her: shown in English to the garage (French screen), its copy text in English
    inv = {'number': 'F-0042', 'issuedAt': TODAY, 'lines': [{'desc': "Changement d'huile et filtre", 'qty': 1, 'price': 89.95, 'type': 'svc'}], 'sub': 89.95, 'tps': 4.50, 'tvq': 8.97, 'total': 103.42, 'taxesOn': True, 'paid': False}
    j1 = doc('jobs/j1'); j1['invoice'] = inv; j1['status'] = 'termine'; doc_set(otok, 'jobs/j1', j1); p.reload(); p.wait_for_selector('#tabbar', timeout=15000); p.wait_for_timeout(1800)
    p.evaluate("(() => { const S = window.__garageApi.S; S.jobId = 'j1'; S.screen = 'preview'; window.__garageApi.render(); })()"); p.wait_for_timeout(900)
    pap = txt(p, 'article.paper')
    check('the garage sees Marie\'s invoice in English (her language), the rest of its screen in French', 'Invoice' in pap and 'Subtotal' in pap and 'GST' in pap and '$103.42' in pap and 'Sous-total' not in pap and 'en anglais' in txt(p, '#main') and 'Copier la facture' in txt(p, '#main'), ['en anglais' in txt(p, '#main'), 'Copier la facture' in txt(p, '#main'), txt(p, '#main')[:200], txt(p, '#main')[-400:]])
    p.screenshot(path='i18n_invoice_en_client.png')
    # the link sent to her: her language; her page in English, with a switch
    r = fn(otok, 'client', {'action': 'link', 'jobId': 'j1', 'send': 'facture', 'base': BASE})
    sms = [x for x in ghl_log() if x['path'] == '/conversations/messages'][-1:]
    body = sms[0]['body']['message'] if sms else ''
    check('the text to Marie in English: « Hello Marie, here is your invoice F-0042 from Garage NextLine ($103.42) »', body.startswith('Hello Marie, here is your invoice F-0042 from Garage NextLine ($103.42)') and '&l=en' in body, body)
    link = (r or {}).get('link', '')
    cc = ctx(b, phone=True); cp = page(cc, 'client page'); cp.goto(link); cp.wait_for_selector('#main .card', timeout=15000); cp.wait_for_timeout(500)
    cm = cp.evaluate("document.querySelector('header').innerText + ' ' + document.querySelector('#main').innerText")
    check('her page in English (a French phone): « Hello Marie », « Invoice F-0042 », « Subtotal », « GST (5%) », « $103.42 », « Print or save as PDF »', 'Hello Marie' in cm and 'Invoice F-0042' in cm and 'Subtotal' in cm and 'GST (5%)' in cm and '$103.42' in cm and 'Print or save as PDF' in cm and 'Facture' not in cm and 'Sous-total' not in cm, cm[:400])
    cp.screenshot(path='i18n_client_page_en.png')
    cp.click('[data-lang-set="fr"]'); cp.wait_for_timeout(400)
    check('…she can switch to French on the page (« Bonjour Marie », « Facture F-0042 », « 103,42 $ »)', 'Bonjour Marie' in txt(cp, 'body') and 'Facture F-0042' in txt(cp, 'body') and '103,42' in txt(cp, 'body'))
    cp.reload(); cp.wait_for_selector('#main .card', timeout=15000); cp.wait_for_timeout(400)
    check('…and her choice is remembered (reload: French)', 'Bonjour Marie' in txt(cp, 'body'))
    cc.close()
    # Paul (French): unchanged
    r2 = fn(otok, 'client', {'action': 'link', 'jobId': 'j2', 'base': BASE})
    cc = ctx(b, phone=True); cp = page(cc, 'paul page'); cp.goto(r2.get('link', '')); cp.wait_for_selector('#title', timeout=15000); cp.wait_for_timeout(1200)
    check('Paul (French on his file): his page in French', 'Bonjour Paul' in txt(cp, 'body'), txt(cp, 'body')[:200])
    cc.close()
    # on the way: the text to Marie in English, the tracking page in English
    stok = token('saleh@garage.test', pw['saleh'])
    r3 = fn(stok, 'en-route', {'jobId': 'j1', 'action': 'start', 'base': BASE, 'pos': {'lat': 45.50, 'lon': -73.57, 'acc': 10}})
    sms = [x for x in ghl_log() if x['path'] == '/conversations/messages'][-1:]
    body = sms[0]['body']['message'] if sms else ''
    check('« Je pars » for Marie: the text in English (« Hello Marie, Saleh from Garage NextLine is on the way to you … Follow the trip live »)', body.startswith('Hello Marie, Saleh from Garage NextLine is on the way to you') and 'Follow the trip live' in body and '&l=en' in body, body)
    tl = re.search(r'(http\S+suivi\.html#t=\S+)', body)
    if tl:
        cc = ctx(b, phone=True); cp = page(cc, 'track'); cp.goto(tl.group(1)); cp.wait_for_function("document.querySelector('#title').textContent.length > 5 && !/Chargement|Loading/.test(document.querySelector('#title').textContent)", timeout=15000); cp.wait_for_timeout(600)
        check('…her tracking page in English (« Hello Marie, Saleh is on the way »)', 'is on the way' in txt(cp, '#title') and 'Hello Marie' in txt(cp, '#title'), txt(cp, 'header'))
        cc.close()
    fn(stok, 'en-route', {'jobId': 'j1', 'action': 'end', 'reason': 'arrived'})
    # ---------- 6. an invitation in the language of the person who sends it ----------
    r4 = fn(otok, 'members', {'action': 'invite', 'lang': 'en', 'name': 'Jordan Test', 'email': 'jordan@garage.test', 'roles': ['bureau'], 'base': BASE})
    mail = [x for x in ghl_log() if x['path'] == '/conversations/messages' and x['body'].get('type') == 'Email'][-1:]
    subj = mail[0]['body'].get('subject', '') if mail else ''
    check('an invitation sent from the English app: the email in English (« Your access to the Garage NextLine logbook », « Activate my account »)', subj == 'Your access to the Garage NextLine logbook' and 'Activate my account' in mail[0]['body'].get('html', ''), [subj, (r4 or {}).get('message')])
    il = (r4 or {}).get('link', '')
    cc = ctx(b, phone=True); cp = page(cc, 'invitee'); cp.goto(il); cp.wait_for_selector('#gate', timeout=15000); cp.wait_for_timeout(500)
    check('…his activation page opens in English (a French phone): the link says so', 'Hello Jordan' in txt(cp, '#gate') or 'Activate' in txt(cp, '#gate'), txt(cp, '#gate')[:200])
    cc.close()
    b.close()
check('no page errors', not ERRS, ERRS[:5])
summary()
