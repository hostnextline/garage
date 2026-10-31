"""Offline mode of the team version (local Supabase copy): the phone opens without network, keeps changes, sends them when the signal comes back."""
import json, sys, time
from playwright.sync_api import sync_playwright
from team_seed import *

otok, PW = seed()
with sync_playwright() as pw:
    br = pw.chromium.launch()
    # ---------- 1. Saleh signs in once with network ----------
    sc = ctx(br, phone=True); sp = page(sc, 'saleh')
    login(sp, 'saleh@garage.test', PW['saleh'])
    sp.evaluate("() => { const S = window.__garageApi.S; S.tab = 'jour'; S.day = '%s'; window.__garageApi.render(); }" % TODAY); sp.wait_for_timeout(500)
    check('online: Saleh sees his job (Marie)', 'Marie' in txt(sp, 'main'), txt(sp, 'main')[:200])
    ok = wait_for(sp, "navigator.serviceWorker && navigator.serviceWorker.controller !== null || (navigator.serviceWorker && navigator.serviceWorker.getRegistration().then(r => !!(r && r.active)))", 15000)
    sp.wait_for_timeout(1500)
    reg = sp.evaluate("navigator.serviceWorker.getRegistration().then(r => r ? {scope: r.scope, active: !!r.active} : null)")
    check('the page installs itself on the phone (service worker active)', reg and reg['active'] and reg['scope'] == BASE, reg)
    cached = sp.evaluate("caches.keys().then(ks => Promise.all(ks.map(k => caches.open(k).then(c => c.keys().then(rs => rs.map(r => r.url)))))).then(a => a.flat())")
    check('page, settings, libraries kept (app, config, supabase, barcode reader, Excel)', BASE in cached and BASE + 'config.js' in cached and BASE + 'vendor/supabase.js' in cached and any('zxing' in u for u in cached) and any('xlsx' in u for u in cached), cached)
    sp.wait_for_timeout(1500)
    keys = sp.evaluate("""new Promise(res => { const r = indexedDB.open('gm-team'); r.onsuccess = () => { const t = r.result.transaction('kv').objectStore('kv').getAllKeys(); t.onsuccess = () => res(t.result); }; r.onerror = () => res([]); })""")
    check('copy of the notebook kept on the phone (jobs, clients, config)', any(k.endswith('|jobs') for k in keys) and any(k.endswith('|clients') for k in keys) and any(k.endswith('|config') for k in keys), keys)
    check('no banner while online', sp.locator('.banner.net').count() == 0)

    # ---------- 2. no network: the app still opens ----------
    sc.set_offline(True)
    sp.reload(); sp.wait_for_timeout(2500)
    check('offline reload: no login screen', sp.locator('#gate').count() == 0, txt(sp, '#gate'))
    sp.evaluate("() => { const S = window.__garageApi.S; S.tab = 'jour'; S.day = '%s'; window.__garageApi.render(); }" % TODAY); sp.wait_for_timeout(500)
    check('offline: Marie\'s job still there (copy of the phone)', 'Marie' in txt(sp, 'main'))
    check('offline banner: « Hors ligne »', 'Hors ligne' in txt(sp, '.banner.net'), txt(sp, '.banner.net'))
    sp.click('.ph-job[data-id="j1"]'); sp.wait_for_timeout(500)
    sp.select_option('#ph-st', 'place'); sp.wait_for_timeout(800)
    check('offline: the job shows « Sur place » right away', 'Sur place' in txt(sp, 'main'))
    check('banner: 1 change kept on the phone', '1 changement gardé sur le téléphone' in txt(sp, '.banner.net'), txt(sp, '.banner.net'))
    check('server not touched yet (still planifié)', (doc('jobs/j1') or {}).get('status') == 'planifie')
    sp.evaluate("window.__supa.db.doc('jobs/j1').update({notes: 'Bruit au freinage, vu sur place'})"); sp.wait_for_timeout(300)
    sp.evaluate("window.__supa.db.doc('config/main').update({rate: 1})"); sp.wait_for_timeout(300)   # a mechanic may not change the settings: the server will refuse it
    check('3 changes waiting', '3 changements' in txt(sp, '.banner.net'), txt(sp, '.banner.net'))
    sp.reload(); sp.wait_for_timeout(2500)
    sp.evaluate("() => { const S = window.__garageApi.S; S.screen = 'job'; S.jobId = 'j1'; window.__garageApi.render(); }"); sp.wait_for_timeout(500)
    check('after closing and reopening without network: changes still there', 'Sur place' in txt(sp, 'main') and '3 changements' in txt(sp, '.banner.net'), (txt(sp, '.banner.net'), txt(sp, 'main')[:150]))

    # ---------- 3. signal back: everything is sent, in order ----------
    sc.set_offline(False)
    sp.evaluate("window.dispatchEvent(new Event('online'))")
    ok = wait_for(sp, "window.__supa.pending() === 0", 40000)
    j1 = doc('jobs/j1') or {}
    check('signal back: changes sent to the server (status + note)', ok and j1.get('status') == 'place' and j1.get('notes') == 'Bruit au freinage, vu sur place', j1)
    check('refused change put aside (settings untouched on the server)', (doc('config/main') or {}).get('rate') == 120)
    sp.wait_for_timeout(1500)
    check('banner: « 1 changement refusé par le serveur » (réglages, pas permis)', '1 changement refusé' in txt(sp, 'main') and 'réglages' in txt(sp, 'main'), txt(sp, '.banner.net'))
    check('the phone goes back to the server\'s settings (rate 120)', wait_for(sp, "window.__garageApi.cfg().rate === 120", 10000), sp.evaluate("window.__garageApi.cfg().rate"))
    sp.click('[data-act="net-ok"]'); sp.wait_for_timeout(300)
    check('« OK » clears the refused message', sp.locator('.banner.net').count() == 0)
    oc = ctx(br); op = page(oc, 'owner'); login(op, 'hassan@garage.test', PW['hassan'])
    op.evaluate("() => { const S = window.__garageApi.S; S.screen = 'job'; S.jobId = 'j1'; window.__garageApi.render(); }"); op.wait_for_timeout(600)
    check('owner sees the change made offline', 'Sur place' in txt(op, 'main'))

    # ---------- 4. long offline: session expired on the phone ----------
    sc.set_offline(True)
    sp.evaluate("""() => { const k = 'gm.team.auth'; const o = JSON.parse(localStorage.getItem(k)); o.expires_at = Math.floor(Date.now() / 1000) - 3600; localStorage.setItem(k, JSON.stringify(o)); }""")
    sp.reload(); sp.wait_for_timeout(3000)
    check('expired session + no network: still opens with the phone copy', sp.locator('#gate').count() == 0 and 'Hors ligne' in txt(sp, '.banner.net'), (txt(sp, '#gate'), txt(sp, '.banner.net')))
    sp.evaluate("() => { const S = window.__garageApi.S; S.screen = 'job'; S.jobId = 'j1'; window.__garageApi.render(); }"); sp.wait_for_timeout(400)
    sp.select_option('#ph-st', 'termine'); sp.wait_for_timeout(800)
    check('offline change while the session is expired', '1 changement' in txt(sp, '.banner.net'))
    sc.set_offline(False); sp.evaluate("window.dispatchEvent(new Event('online'))")
    ok = wait_for(sp, "window.__supa.pending() === 0 && !window.__supa.net.offlineMode", 45000)
    check('signal back: the session renews itself and the change goes out', ok and (doc('jobs/j1') or {}).get('status') == 'termine', (sp.evaluate("JSON.stringify(window.__supa.net)"), (doc('jobs/j1') or {}).get('status')))
    check('no login was asked', sp.locator('#gate').count() == 0)

    # ---------- 5. other phone changed the same job meanwhile: both changes kept ----------
    sc.set_offline(True)
    sp.evaluate("window.__supa.db.doc('jobs/j1').update({km: '142 000'})"); sp.wait_for_timeout(300)
    doc_set(otok, 'jobs/j1', dict(doc('jobs/j1'), time='15:30'))
    sc.set_offline(False); sp.evaluate("window.dispatchEvent(new Event('online'))")
    wait_for(sp, "window.__supa.pending() === 0", 40000); sp.wait_for_timeout(1500)
    j1 = doc('jobs/j1') or {}
    check('the office changed the time, the mechanic (offline) added the km: both kept', j1.get('time') == '15:30' and j1.get('km') == '142 000', j1)
    sp.evaluate("window.__supa.resync(true)"); sp.wait_for_timeout(1500)
    check('the phone shows both', sp.evaluate("(() => { const j = window.__garageApi.findJob('j1'); return j && j.time === '15:30' && j.km === '142 000'; })()"))

    # ---------- 6. signing out with changes not sent yet ----------
    sc.set_offline(True)
    sp.evaluate("window.__supa.db.doc('jobs/j1').update({notes: 'pas envoyé'})"); sp.wait_for_timeout(300)
    sp.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'plus'; window.__garageApi.render(); }"); sp.wait_for_timeout(400)
    sp.click('[data-act="acct-out"]'); sp.wait_for_timeout(500)
    check('sign out with 1 change waiting: warned first, still signed in', 'pas encore envoyé' in txt(sp, '#toast') and sp.locator('#gate').count() == 0, txt(sp, '#toast'))
    sc.set_offline(False); sp.evaluate("window.dispatchEvent(new Event('online'))"); wait_for(sp, "window.__supa.pending() === 0", 40000)
    sp.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'plus'; window.__garageApi.render(); }"); sp.wait_for_timeout(400)
    sp.click('[data-act="acct-out"]'); sp.wait_for_selector('#gate #g-email', timeout=15000)
    dbs = sp.evaluate("indexedDB.databases ? indexedDB.databases().then(d => d.map(x => x.name)) : []")
    check('nothing waiting → signs out, and the phone\'s copy is erased', 'gm-team' not in dbs and sp.evaluate("localStorage.getItem('gm.team.member')") is None, dbs)
    check('change sent before signing out', (doc('jobs/j1') or {}).get('notes') == 'pas envoyé')

    # ---------- 7. never signed in on this phone + no network ----------
    nc = ctx(br, phone=True); npg = page(nc, 'new')
    npg.goto(BASE); npg.wait_for_selector('#gate #g-email', timeout=15000); npg.wait_for_timeout(1500)
    nc.set_offline(True); npg.reload(); npg.wait_for_timeout(2500)
    check('a phone that never signed in: page opens offline, asks to sign in (no data)', npg.locator('#gate').count() == 1 and npg.evaluate("window.__garageApi.S.jobs.length") == 0, txt(npg, '#gate')[:100])
    npg.fill('#g-email', 'ali@garage.test'); npg.fill('#g-pw', PW['ali']); npg.click('#g-go'); npg.wait_for_timeout(1500)
    check('… and says there is no connection', 'Pas de connexion' in txt(npg, '#g-msg'), txt(npg, '#g-msg'))
    check('no script errors', not ERRS, ERRS[:5])
    br.close()

# back to the start state for the other tests
psql("truncate public.members, public.docs, public.docs_deleted, public.mech_live, public.mech_positions, public.tracks, public.setup_codes, public.app_secrets cascade; delete from auth.users;")
sys.exit(0 if summary() else 1)
