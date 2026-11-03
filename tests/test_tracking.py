"""Le suivi du mécano (copie locale de Supabase, vraies écritures) :
1. la page de suivi du client : la carte se charge (OpenStreetMap reçoit le nom du site, seulement le nom du site) ;
2. une job sans mécano (camion sans mécano) : celui qui appuie « En route » sur son téléphone est suivi —
   sa journée commence, sa position part, le client voit le camion avancer ; à l'arrivée, sa position s'arrête ;
3. sur l'ordi, pour une job sans mécano : on lui dit d'appuyer « En route » sur le téléphone de celui qui part."""
import time, re, os, json, urllib.request
from team_seed import *
from playwright.sync_api import sync_playwright

otok, pw = seed()
c2 = doc('clients/c2')
snap2 = {'id': 'c2', 'firstName': c2['firstName'], 'lastName': c2['lastName'], 'name': c2['firstName'] + ' ' + c2['lastName'], 'phone': c2['phone'], 'address': c2['address'], 'postal': c2['postal'], 'geo': c2['geo']}
doc_set(otok, 'jobs/j3', {'date': TODAY, 'time': '16:00', 'durationMin': 60, 'mechanic': '', 'truck': 'c3', 'clientId': 'c2', 'client': snap2,
                          'vehicle': {'make': 'Toyota', 'model': 'Corolla', 'year': '2016'}, 'services': ['Inspection multipoints'], 'service': 'Inspection multipoints', 'status': 'planifie', 'createdAt': 1})
HID = psql("select user_id from public.members where name = 'Hassan Banho'")
psql("update public.members set mechanic = null where user_id = '%s'" % HID)   # (the owner without a mechanic's name: no work-day card of his own)

with sync_playwright() as pl:
    b = pl.chromium.launch()
    # ---------- 2. Hassan (owner, not a mechanic) goes himself, phone in hand ----------
    hc = ctx(b, phone=True, geo={'latitude': 45.5010, 'longitude': -73.6000}); hp = page(hc, 'hassan-phone'); login(hp, 'hassan@garage.test', pw['hassan'])
    check('before: Hassan has no work day running', psql("select coalesce(bool_or(on_shift), false) from public.mech_live where user_id = '%s'" % HID) == 'f')
    hp.wait_for_selector('.ph-job[data-id="j3"]', timeout=15000); hp.click('.ph-job[data-id="j3"]'); hp.wait_for_selector('.nextbtn', timeout=8000)
    nb = txt(hp, '.nextbtn')
    check('job without a mechanic: big button « aviser Paul »', 'aviser Paul' in nb, nb)
    hp.click('.nextbtn')
    check('text sent to Paul', toast_has(hp, 'Texto envoyé à Paul', 15000))
    tr = None
    for _ in range(30):
        tr = psql("select user_id || '|' || status from public.tracks where job_id = 'j3' order by created_at desc limit 1")
        live = psql("select on_shift || '|' || coalesce(job_id, '') || '|' || (lat is not null) from public.mech_live where user_id = '%s'" % HID)
        if live == 'true|j3|true': break
        time.sleep(0.5)
    check('the client follows the one who pressed (Hassan)', tr == HID + '|active', tr)
    check('his work day started by itself and his position reached the server (for this job)', live == 'true|j3|true', live)
    check('the day path has his point', int(psql("select count(*) from public.mech_positions where user_id = '%s'" % HID) or 0) >= 1)
    hp.wait_for_selector('.er-eta', timeout=10000)
    check('arrival time shown on his phone (his position is known)', re.search(r'\d{1,2} h \d{2}', txt(hp, '.er-eta')) is not None, txt(hp, '.er-eta'))
    link = 'http://127.0.0.1:8088/suivi.html#t=' + psql("select token from public.tracks where job_id = 'j3' and status = 'active'")

    # ---------- 1. the client's page: the map loads, the truck shows ----------
    cc = ctx(b, phone=True); refs = []
    cc.on('request', lambda r: refs.append(r.all_headers().get('referer')) if 'tile.openstreetmap.org' in r.url else None)
    cp = page(cc, 'client'); cp.goto(link)
    ok = wait_for(cp, "() => [...document.querySelectorAll('.pin')].some(e => e.textContent.includes('🚐'))", 15000)
    check('client page: the truck (Hassan) is on the map', ok, txt(cp, '#note'))
    check('client page: no « position will show » note any more', cp.locator('#note').is_hidden(), txt(cp, '#note'))
    cp.wait_for_timeout(800)
    check('client page: map tiles asked for', len(refs) > 0, len(refs))
    check('map tiles carry only the site name (OpenStreetMap refuses tiles without it; never the tracking link)', refs and all(r == 'http://127.0.0.1:8088/' for r in refs), refs[:3])
    check('client page: the page itself still shares nothing (no-referrer kept)', cp.evaluate("document.querySelector('meta[name=referrer]').content") == 'no-referrer')
    cp.screenshot(path=os.path.join(SC, 'tracking_client.png'))

    # ---------- 2b. he arrives: the client no longer sees him, his position stops ----------
    hp.goto(BASE + '#clients'); hp.wait_for_timeout(400); hp.goto(BASE + '#agenda'); hp.wait_for_selector('.ph-job[data-id="j3"]', timeout=15000); hp.click('.ph-job[data-id="j3"]'); hp.wait_for_selector('.nextbtn[data-v="place"]', timeout=8000)
    hp.click('.nextbtn[data-v="place"]')
    ok = False
    for _ in range(30):
        st = psql("select status from public.tracks where job_id = 'j3' order by created_at desc limit 1"); sh = psql("select on_shift from public.mech_live where user_id = '%s'" % HID)
        if st == 'arrived' and sh == 'f': ok = True; break
        time.sleep(0.4)
    check('arrived: tracking closed and his position sharing stopped (he is not a mechanic)', ok, (st, sh))
    check('…told plainly', toast_has(hp, 'ne voit plus ta position', 6000))
    check('phone: no errors', not ERRS, ERRS[:3])

    http('POST', API + '/rest/v1/rpc/doc_merge', {'p_path': 'jobs/j3', 'p_patch': {'payWaived': {'by': 'test'}}}, otok)   # (paid: he may leave for the next client)
    # ---------- 2c. someone with a work-day card (a mechanic's name) keeps his day running after arriving ----------
    psql("update public.members set mechanic = 'Hassan' where user_id = '%s'" % HID)
    doc_set(otok, 'jobs/j4', {'date': TODAY, 'time': '17:00', 'durationMin': 60, 'mechanic': '', 'truck': 'c3', 'clientId': 'c2', 'client': snap2, 'services': ['Inspection multipoints'], 'status': 'planifie', 'createdAt': 1})
    hc2 = ctx(b, phone=True, geo={'latitude': 45.52, 'longitude': -73.59}); h2 = page(hc2, 'hassan-phone-2'); login(h2, 'hassan@garage.test', pw['hassan'])
    h2.wait_for_selector('.ph-job[data-id="j4"]', timeout=15000); h2.click('.ph-job[data-id="j4"]'); h2.wait_for_selector('.nextbtn', timeout=8000); h2.click('.nextbtn')
    ok = False
    for _ in range(30):
        if psql("select on_shift || '|' || coalesce(job_id, '') from public.mech_live where user_id = '%s'" % HID) == 'true|j4': ok = True; break
        time.sleep(0.5)
    check('with a mechanic\'s name: followed too', ok)
    h2.goto(BASE + '#clients'); h2.wait_for_timeout(400); h2.goto(BASE + '#agenda'); h2.wait_for_selector('.ph-job[data-id="j4"]', timeout=15000); h2.click('.ph-job[data-id="j4"]'); h2.wait_for_selector('.nextbtn[data-v="place"]', timeout=8000); h2.click('.nextbtn[data-v="place"]')
    for _ in range(20):
        if psql("select status from public.tracks where job_id = 'j4' order by created_at desc limit 1") == 'arrived': break
        time.sleep(0.4)
    h2.wait_for_timeout(1000)
    check('…and his work day keeps going after he arrives (he closes it himself, as before)', psql("select on_shift from public.mech_live where user_id = '%s'" % HID) == 't')
    h2.goto(BASE + '#clients'); h2.wait_for_timeout(400); h2.goto(BASE + '#agenda'); h2.wait_for_timeout(800)
    check('…his work-day card is there to close it', h2.locator('[data-act="sh-end"]').count() >= 1)

    # ---------- 2e. leaving without texting the client (to test, as often as you want) ----------
    def gsms(): return [x for x in json.loads(urllib.request.urlopen('http://127.0.0.1:9200/__log').read()) if x['path'] == '/conversations/messages']
    doc_set(otok, 'jobs/j7', {'date': TODAY, 'time': '18:00', 'durationMin': 60, 'mechanic': '', 'truck': 'c2', 'clientId': 'c2', 'client': snap2, 'services': ['Inspection multipoints'], 'status': 'planifie', 'createdAt': 1})
    doc_set(otok, 'jobs/j8', {'date': TODAY, 'time': '18:30', 'durationMin': 60, 'mechanic': '', 'truck': 'c2', 'clientId': 'c2', 'client': snap2, 'services': ['Inspection multipoints'], 'status': 'planifie', 'createdAt': 1})
    h2.evaluate('window.__supa.resync(true)'); h2.wait_for_timeout(1200)
    h2.goto(BASE + '#clients'); h2.wait_for_timeout(400); h2.goto(BASE + '#agenda'); h2.wait_for_selector('.ph-job[data-id="j7"]', timeout=15000); h2.click('.ph-job[data-id="j7"]'); h2.wait_for_selector('.nextbtn', timeout=8000)
    check('« Aviser Paul par texto » under the button, ticked', h2.is_checked('.er [data-act="er-notify"]') and 'Aviser Paul par texto' in txt(h2, '.er'))
    h2.click('.er [data-act="er-notify"]'); h2.wait_for_timeout(400)
    check('unticked: the button says « Je pars (sans texto) »', txt(h2, '.nextbtn') == 'Je pars (sans texto)', txt(h2, '.nextbtn'))
    n0 = len(gsms()); h2.click('.nextbtn')
    check('« Parti sans texto : Paul n\'est pas avisé »', toast_has(h2, 'Parti sans texto', 15000))
    h2.wait_for_timeout(800)
    check('…no text to the client, the tracking still made (marked « quiet »)', len(gsms()) == n0 and psql("select sms_status from public.tracks where job_id = 'j7' order by created_at desc limit 1") == 'quiet', (len(gsms()) - n0, psql("select sms_status from public.tracks where job_id = 'j7'")))
    h2.goto(BASE + '#clients'); h2.wait_for_timeout(400); h2.goto(BASE + '#agenda'); h2.wait_for_selector('.ph-job[data-id="j8"]', timeout=15000); h2.click('.ph-job[data-id="j8"]'); h2.wait_for_selector('.nextbtn', timeout=8000)
    check('the next job: ticked again (a real client is never forgotten)', h2.is_checked('.er [data-act="er-notify"]') and txt(h2, '.nextbtn').startswith('Je pars : aviser'), txt(h2, '.nextbtn'))

    # ---------- 2d. the office on a phone: not followed (the office does not drive) ----------
    doc_set(otok, 'jobs/j6', {'date': TODAY, 'time': '19:00', 'durationMin': 60, 'mechanic': '', 'truck': 'c3', 'clientId': 'c2', 'client': snap2, 'services': ['Inspection multipoints'], 'status': 'planifie', 'createdAt': 1})
    LID = psql("select user_id from public.members where name = 'Lina Bureau'")
    lc2 = ctx(b, phone=True, geo={'latitude': 45.50, 'longitude': -73.57}); l2 = page(lc2, 'lina-phone'); login(l2, 'lina@garage.test', pw['lina'])
    l2.wait_for_selector('.ph-job[data-id="j6"]', timeout=15000); l2.click('.ph-job[data-id="j6"]'); l2.wait_for_selector('.er', timeout=8000)
    check('office phone, job without a mechanic: told to press « En route » on the phone of the one who goes', 'téléphone de celui qui part' in txt(l2, '.er'), txt(l2, '.er'))
    l2.wait_for_timeout(1500)
    check('…and her position is never sent', psql("select count(*) from public.mech_live where user_id = '%s' and on_shift" % LID) == '0')

    # ---------- 3. on the computer ----------
    lc = ctx(b); lp = page(lc, 'lina-pc'); login(lp, 'lina@garage.test', pw['lina'])
    doc_set(otok, 'jobs/j5', {'date': TODAY, 'time': '18:00', 'durationMin': 60, 'mechanic': '', 'truck': 'c3', 'clientId': 'c2', 'client': snap2, 'services': ['Inspection multipoints'], 'status': 'planifie', 'createdAt': 1})
    lp.evaluate('window.__supa.resync(true)'); lp.wait_for_timeout(1200)
    lp.goto(BASE + '#agenda'); lp.wait_for_timeout(800)
    if lp.locator('[data-act="open"][data-id="j5"]').count() == 0:
        lp.click('[data-act="view"][data-v="list"]') if lp.locator('[data-act="view"][data-v="list"]').count() else None; lp.wait_for_timeout(600)
    lp.locator('[data-act="open"][data-id="j5"]').first.click(); lp.wait_for_selector('.er', timeout=8000)
    check('computer, job without a mechanic: « press En route on the phone of the one who goes »', 'téléphone de celui qui part' in txt(lp, '.er'), txt(lp, '.er'))
    check('computer: no errors', not ERRS, ERRS[:3])
    b.close()
summary()
