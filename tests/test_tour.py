"""Visite guidée de la première visite (mécano, trésorier, bureau) + « Sa première visite » dans « Voir comme… »."""
from team_seed import *
from playwright.sync_api import sync_playwright
def rpc(tok, name, body): return http('POST', API + '/rest/v1/rpc/' + name, body, tok)
def steps_txt(p):
    out = []
    for _ in range(10):
        out.append(txt(p, '#tour'))
        if p.locator('#tour [data-act="tour-go"].primary').count(): p.click('#tour [data-act="tour-go"].primary'); p.wait_for_timeout(250)
        else: break
    return out
otok, pw = seed()
uid = {k: psql("select id from auth.users where email='%s@garage.test'" % k) for k in ('hassan', 'saleh', 'nadia', 'lina')}
psql("delete from public.docs where path like 'data/users/%/tour' and path not like '%" + uid['hassan'] + "%'")
with sync_playwright() as pl:
    b = pl.chromium.launch()
    # ---------- mechanic, first time, on his phone ----------
    sc = ctx(b, phone=True); sp = page(sc, 'saleh'); login(sp, 'saleh@garage.test', pw['saleh'], tour=True)
    ok = wait_for(sp, "document.getElementById('tour') !== null", 8000)
    check('first time: the guided tour opens by itself, « Bienvenue, Saleh », step 1', ok and 'Bienvenue, Saleh' in txt(sp, '#sheet-title') and 'étape 1 sur 5' in txt(sp, '#sheet-sub'), [txt(sp, '#sheet-title'), txt(sp, '#sheet-sub')])
    sp.screenshot(path='tour_1.png')
    sp.click('#tour [data-act="tour-go"].primary'); sp.wait_for_timeout(300)
    check('step 2: « Commencer ma journée », position only during the day', 'Commencer ma journée' in txt(sp, '#tour') and 'seulement pendant ta journée' in txt(sp, '#tour'))
    sp.screenshot(path='tour_2.png')
    sp.click('#tour [data-act="tour-go"]:not(.primary)'); sp.wait_for_timeout(300)
    check('« Retour » goes back to step 1', 'étape 1 sur 5' in txt(sp, '#sheet-sub'))
    st = steps_txt(sp)
    check('5 steps: the app, the morning button, the big button of a job, the « + », then the home screen', len(st) == 5 and 'Je pars' in st[2] and 'facture sur place' in st[3] and 'nouvelle réservation' not in st[3] and 'écran d\'accueil' in st[4], [s[:40] for s in st])
    sp.screenshot(path='tour_5.png')
    sp.click('#tour [data-act="tour-end"]'); sp.wait_for_timeout(1000)
    check('« C\'est parti »: then how to put the app on the phone', sp.locator('#sheet:not([hidden]) .inst').count() == 1)
    check('the tour is remembered (once per person)', bool((doc('data/users/%s/tour' % uid['saleh']) or {}).get('seenAt')))
    seen = doc('data/users/%s/tour' % uid['saleh'])['seenAt']
    sp.keyboard.press('Escape'); sp.reload(); sp.wait_for_timeout(2500)
    check('next time: no tour', sp.locator('#tour').count() == 0)
    sp.click('.tab[data-t="plus"]'); sp.wait_for_timeout(400)
    check('Plus: « Revoir la visite guidée »', sp.locator('.ph-row[data-act="tour-replay"]').count() == 1)
    sp.click('.ph-row[data-act="tour-replay"]'); sp.wait_for_timeout(500)
    check('…opens it again from step 1', sp.locator('#tour').count() == 1 and 'étape 1 sur' in txt(sp, '#sheet-sub'))
    sp.click('#tour [data-act="tour-end"]'); sp.wait_for_timeout(600)
    check('« Passer » closes it (no install sheet when replaying)', sp.locator('#tour').count() == 0 and sp.locator('#sheet:not([hidden]) .inst').count() == 0)
    sc.close()
    # with the box « Prendre des rendez-vous », the tour says so
    doc_set(otok, 'config/roles', {'mecano': {'book': True}})
    psql("delete from public.docs where path='data/users/%s/tour'" % uid['saleh'])
    sc = ctx(b, phone=True); sp = page(sc, 'saleh2'); login(sp, 'saleh@garage.test', pw['saleh'], tour=True); wait_for(sp, "document.getElementById('tour') !== null", 8000)
    st = steps_txt(sp)
    check('tour follows the boxes: « nouvelle réservation » in the « + » step when he may book', len(st) == 5 and 'nouvelle réservation' in st[3], st[3:4])
    sp.click('#tour [data-act="tour-end"]'); sp.wait_for_timeout(600); sc.close()
    # ---------- treasurer and office, on a computer ----------
    nc = ctx(b); np_ = page(nc, 'nadia'); login(np_, 'nadia@garage.test', pw['nadia'], tour=True)
    ok = wait_for(np_, "document.getElementById('tour') !== null", 8000); st = steps_txt(np_) if ok else []
    check('treasurer: her own tour (Trésorerie, receipt photo, report and taxes, what else she sees) — no phone step on a computer', len(st) == 4 and 'Trésorerie' in st[0] and 'reçu' in st[1] and 'taxes' in st[2] and 'les factures' in st[3] and 'les clients' in st[3], [s[:50] for s in st])
    np_.screenshot(path='tour_nadia.png')
    np_.click('#tour [data-act="tour-end"]'); np_.wait_for_timeout(600)
    check('…remembered for her, no install sheet on a computer', bool(doc('data/users/%s/tour' % uid['nadia'])) and np_.locator('#sheet:not([hidden]) .inst').count() == 0)
    nc.close()
    lc = ctx(b); lp = page(lc, 'lina'); login(lp, 'lina@garage.test', pw['lina'], tour=True)
    ok = wait_for(lp, "document.getElementById('tour') !== null", 8000); st = steps_txt(lp) if ok else []
    check('office: her tour (agenda, « + Réservation », the map, invoices)', len(st) == 4 and 'Réservation' in st[1] and 'carte' in st[2].lower(), [s[:40] for s in st])
    lp.click('#tour [data-act="tour-end"]'); lp.wait_for_timeout(500); lc.close()
    # ---------- owner: no tour for him; « Sa première visite » in the preview ----------
    oc = ctx(b); op = page(oc, 'owner'); op.set_viewport_size({'width': 1280, 'height': 900}); login(op, 'hassan@garage.test', pw['hassan']); op.wait_for_timeout(2500)
    check('owner: no tour (he has his « Par où commencer » guide)', op.locator('#tour').count() == 0)
    op.evaluate("location.hash = 'equipe'"); op.wait_for_selector('#eq-viewas', timeout=10000); op.wait_for_timeout(800)
    psql("delete from public.docs where path='data/users/%s/tour'" % uid['saleh'])
    op.click('#eq-viewas [data-act="pv-start"][data-mech="Saleh"]'); op.wait_for_timeout(2500)
    check('the preview does not open the tour by itself', op.locator('#tour').count() == 0)
    op.click('#pv-bar [data-act="tour-replay"]'); op.wait_for_timeout(600)
    check('bar « 👋 Sa première visite »: exactly Saleh\'s tour (« Bienvenue, Saleh », 5 steps)', 'Bienvenue, Saleh' in txt(op, '#sheet-title') and 'étape 1 sur 5' in txt(op, '#sheet-sub'), [txt(op, '#sheet-title'), txt(op, '#sheet-sub')])
    st = steps_txt(op)
    op.screenshot(path='tour_preview.png')
    op.click('#tour [data-act="tour-end"]'); op.wait_for_timeout(800)
    check('…nothing recorded (not for Saleh, not for you), no install sheet', doc('data/users/%s/tour' % uid['saleh']) is None and op.locator('#sheet:not([hidden]) .inst').count() == 0)
    op.click('#eq-viewas, #pv-bar [data-act="pv-exit"]') if op.locator('#pv-bar').count() else None; op.wait_for_timeout(800)
    oc.close()
    b.close()
# back to the start
rpc(otok, 'doc_delete', {'p_path': 'config/roles'})
psql("insert into public.docs (path, data) select 'data/users/' || user_id || '/tour', '{\"seenAt\": 1}' from public.members on conflict (path) do nothing")
check('back to the start (boxes as before)', doc('config/roles') is None)
check('no page errors', not ERRS, ERRS[:5])
summary()
