"""Visite guidée de toute l'app (calme : pas de points, pas de trophée) : le mécano (téléphone), le trésorier et le bureau (ordinateur),
le propriétaire (depuis le menu), une personne à deux rôles, et « Sa première visite » dans « Voir comme… ».
Copie locale de Supabase ; tout est remis comme au départ."""
from team_seed import *
from playwright.sync_api import sync_playwright
def rpc(tok, name, body): return http('POST', API + '/rest/v1/rpc/' + name, body, tok)
def tip(p): return txt(p, '#tour-ov .tt-tip')
def info(p):
    return p.evaluate("""(() => { const t = document.querySelector('#tour-ov .tt-tip'); if (!t) return null;
      return {ch: t.querySelector('.tt-ch').textContent.split(' · ')[0], t: t.querySelector('h3').textContent.replace(/\\u00a0/g, ' '), n: t.querySelector('.tt-n').textContent,
              hash: location.hash, sched: !!document.querySelector('#sched'), screen: window.__garageApi ? window.__garageApi.S.screen : null, hole: !!document.querySelector('#tour-ov .tt-hole')}; })()""")
def lit(p, sel):
    """is the lit hole around this element (or around its top part, for a tall one)?"""
    return p.evaluate("""(sel) => { const h = document.querySelector('#tour-ov .tt-hole'); const e = [...document.querySelectorAll(sel)].find(x => x.getBoundingClientRect().width > 0); if (!h || !e) return false;
      const a = h.getBoundingClientRect(), b = e.getBoundingClientRect(); return a.left <= b.left + 1 && a.right >= b.right - 1 && a.top <= Math.max(b.top, 70) + 1 && (a.bottom >= b.bottom - 1 || a.height >= innerHeight * .45); }""", sel)
def settle(p): p.wait_for_function("!!document.querySelector('#tour-ov[data-ready=\"1\"]')", timeout=9000); p.wait_for_timeout(60)
def nxt(p): p.click('#tour-ov [data-act="tt-next"]'); p.wait_for_timeout(60); settle(p)
def walk(p):
    """« Suivant » to the last step; returns what each step showed"""
    seen = [info(p)]
    for k in range(40):
        if p.locator('#tour-ov [data-act="tt-end"]').count(): break
        nxt(p); seen.append(info(p))
    return seen
REC = """(() => { window.__tt = []; window.__ttOn = true; (function f(){ const o = document.querySelector('#tour-ov'); if (o){ const h = o.querySelector('.tt-hole'), t = o.querySelector('.tt-tip'), i = t && t.querySelector('.tt-in'), r = h.getBoundingClientRect();
  window.__tt.push({hash: location.hash, screen: window.__garageApi ? window.__garageApi.S.screen : null, shut: h.classList.contains('shut'), top: Math.round(r.top), h: Math.round(r.height), to: +getComputedStyle(t).opacity, io: i ? +getComputedStyle(i).opacity : 1, title: ((t.querySelector('h3') || {}).textContent || '').replace(/\u00a0/g, ' ')}); }
  if (window.__ttOn) requestAnimationFrame(f); })(); })()"""
def rec_next(p):
    """« Suivant », filmed: what the light and the bubble do on each frame until the step is ready"""
    p.evaluate("window.__keep = [document.querySelector('#tour-ov .tt-hole'), document.querySelector('#tour-ov .tt-tip')]")
    p.evaluate(REC); p.click('#tour-ov [data-act="tt-next"]'); p.wait_for_timeout(60); settle(p)
    fr = p.evaluate("window.__ttOn = false, window.__tt")
    same = p.evaluate("window.__keep[0] === document.querySelector('#tour-ov .tt-hole') && window.__keep[1] === document.querySelector('#tour-ov .tt-tip')")
    return fr, same
def no_game(p): t = tip(p); return '⭐' not in t and 'point' not in t.lower() and 'À toi' not in t and p.locator('#tour-ov .tt-pts, #tour-ov .tt-win, #tour-ov .tt-conf, .tt-pop').count() == 0
otok, pw = seed()
uid = {k: psql("select id from auth.users where email='%s@garage.test'" % k) for k in ('hassan', 'saleh', 'ali', 'nadia', 'lina')}
psql("delete from public.docs where path like 'data/users/%/tour'")
with sync_playwright() as pl:
    b = pl.chromium.launch()
    # ---------- 1. the mechanic, first time, on his phone ----------
    sc = ctx(b, phone=True); sp = page(sc, 'saleh'); login(sp, 'saleh@garage.test', pw['saleh'], tour=True)
    ok = wait_for(sp, "!!document.querySelector('#tour-ov .tt-tip')", 9000); settle(sp)
    i = info(sp)
    check('first time: the visit starts by itself, inside the app (« Bienvenue, Saleh ! », step 1 of N)', ok and i['t'] == 'Bienvenue, Saleh !' and i['ch'] == 'Bienvenue' and i['n'].startswith('1 sur '), i)
    check('two clear buttons: « Plus tard » and « Commencer la visite »', sp.locator('#tour-ov [data-act="tt-skip"]', has_text='Plus tard').count() == 1 and sp.locator('#tour-ov [data-act="tt-next"]', has_text='Commencer la visite').count() == 1)
    check('no game: no points, no « À toi ! », no trophy', no_game(sp), tip(sp)[:120])
    sp.screenshot(path='tour_1.png')
    nxt(sp); i = info(sp)
    check('« Ta journée »: the date at the top is lit, explained beside it', i['ch'] == 'Ta journée' and lit(sp, '.dayhead') and 'hier ou demain' in tip(sp), i)
    nxt(sp)
    check('…then the REAL « Début de journée » card (« Commencer ma journée », shared only during his day)', lit(sp, '.shift') and 'Commencer ma journée' in tip(sp) and 'Fin de journée' in tip(sp))
    sp.screenshot(path='tour_2.png')
    c = sp.evaluate("(() => { const r = document.querySelector('.tab[data-t=\"factures\"]').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()")
    sp.mouse.click(c[0], c[1]); sp.wait_for_timeout(500)
    check('the rest of the screen waits during the visit (touching « Factures » does nothing)', sp.evaluate('location.hash') != '#factures' and sp.locator('#tour-ov').count() == 1)
    nxt(sp)
    check('…his appointments of the day (Marie), with what each label means', lit(sp, '.ph-list') and 'Planifié' in tip(sp) and 'Terminé' in tip(sp))
    old = info(sp)['t']; fr, same = rec_next(sp); i = info(sp)
    changed = [f for f in fr if f['screen'] == 'job']
    check('smooth: on a change of screen, the light closes first (the whole screen dims evenly) and the new screen comes in the dark', bool(changed) and changed[0]['shut'], [(f['screen'], f['shut']) for f in fr[:12]])
    check('…the words of the last step never show over the new screen (the bubble leaves, then comes back with the new words)', all(f['to'] * f['io'] < 0.06 for f in changed if f['title'] == old), [(round(f['to'], 2), round(f['io'], 2), f['title'][:12]) for f in changed[:8]])
    check('…one light and one bubble for the whole visit (they move, nothing is rebuilt)', same)
    check('« Une job, du début à la fin »: the visit opens his job by itself (call, text, GPS)', i['ch'] == 'Une job, du début à la fin' and i['screen'] == 'job' and lit(sp, '.pjob') and 'itinéraire' in tip(sp), i)
    fr, same = rec_next(sp)
    tops = [f['top'] for f in fr if not f['shut']]
    mid = [t for t in tops if min(tops[0], tops[-1]) + 2 < t < max(tops[0], tops[-1]) - 2] if tops else []
    check('smooth: on the same screen, the light glides from one part to the next (in-between positions, no jump)', len(set(mid)) >= 3 and same, [tops[:3], len(set(mid)), tops[-1:]])
    nw = [f for f in fr if f['title'] == 'Le gros bouton']
    check('…the new words come in hidden, then fade in (never half-shown over the old ones)', bool(nw) and nw[0]['io'] < 0.06 and nw[-1]['io'] > 0.94, [round(f['io'], 2) for f in nw[:6]])
    check('…the big button explained (« Je pars » texts the client, then « Je suis arrivé »…)', lit(sp, '.nextbtn') and 'Je pars' in tip(sp) and 'Je suis arrivé' in tip(sp))
    sp.screenshot(path='tour_4.png')
    sp.click('#tour-ov [data-act="tt-prev"]'); sp.wait_for_timeout(60); settle(sp)
    check('« ‹ Retour » goes back one step', info(sp)['t'] == 'La fiche de la job')
    sp.keyboard.press('ArrowRight'); sp.wait_for_timeout(60); settle(sp)
    check('the → key goes forward too', info(sp)['t'] == 'Le gros bouton')
    n0 = info(sp)['n']; sp.click('#tour-ov [data-act="tt-next"]'); sp.mouse.click(*sp.evaluate("(() => { const r = document.querySelector('#tour-ov .tt-tip').getBoundingClientRect(); return [r.right - 60, r.bottom - 30]; })()")); sp.wait_for_timeout(60); settle(sp)
    check('a quick double tap on « Suivant » moves one step only', int(info(sp)['n'].split()[0]) == int(n0.split()[0]) + 1, [n0, info(sp)['n']])
    sp.click('#tour-ov [data-act="tt-prev"]'); sp.wait_for_timeout(60); settle(sp)
    sp.set_viewport_size({'width': 390, 'height': 700}); sp.wait_for_timeout(400)
    tb = sp.evaluate("(() => { const t = document.querySelector('#tour-ov .tt-tip').getBoundingClientRect(); return [t.top, t.bottom]; })()")
    check('the phone bar shows / hides (smaller screen): the bubble moves to stay inside, nothing is rebuilt', tb[1] <= 700 and tb[0] >= 0 and info(sp)['t'] == 'Le gros bouton', tb)
    sp.set_viewport_size({'width': 390, 'height': 844}); sp.wait_for_timeout(400)
    rest = walk(sp)
    chs = []
    for x in rest:
        if x['ch'] not in chs: chs.append(x['ch'])
    check('then, in order: the VIN, photos and signature, extra work, the invoice; clients and invoices; the map; his hours; the truck; the end', chs == ['Une job, du début à la fin', 'Clients et factures', 'La carte de l\'équipe', 'Ton horaire', 'Le camion', 'Pour finir'], chs)
    ts = [x['t'] for x in rest]
    check('…every part of the job screen is explained', all(t in ts for t in ('Le VIN et la fiche du moteur', 'Photos et signature', 'Travaux supplémentaires', 'La facture sur place')), ts)
    hs = set(x['hash'] for x in rest)
    check('…each screen opens by itself (his clients, his invoices, the map, his availability, the stock)', {'#clients', '#factures', '#carte', '#dispos', '#stock'} <= hs, sorted(hs))
    check('…the glass schedule window opens to show how to drag on the boxes', any(x['sched'] and x['t'] == 'La grille' for x in rest) and any(x['sched'] and 'combien de temps' in x['t'] for x in rest))
    check('…the « + » button: « Facture sur place » and « Nouveau client » (no booking: box not ticked)', any(x['t'] == 'Le bouton « + »' for x in rest) and 'Nouvelle réservation' not in ' '.join(t for t in ts))
    i = info(sp)
    check('last step « C\'est tout ! »: where to see it again, a « Terminer » button, no game', i['t'] == "C'est tout !" and 'Revoir la visite guidée' in tip(sp) and sp.locator('#tour-ov [data-act="tt-end"]', has_text='Terminer').count() == 1 and no_game(sp), i)
    sp.screenshot(path='tour_end.png')
    sp.click('#tour-ov [data-act="tt-end"]'); sp.wait_for_timeout(1300)
    check('« Terminer »: the visit closes (schedule window too), back on his day, a short message', sp.locator('#tour-ov').count() == 0 and sp.locator('#sched').count() == 0 and sp.evaluate('location.hash') == '#jour' and toast_has(sp, 'Visite terminée'), sp.evaluate('location.hash'))
    check('…then how to put the app on his phone opens by itself', sp.locator('#sheet:not([hidden]) .inst').count() == 1)
    t0 = (doc('data/users/%s/tour' % uid['saleh']) or {}).get('seenAt')
    check('the visit is remembered (once per person)', bool(t0))
    sp.keyboard.press('Escape'); sp.reload(); sp.wait_for_timeout(2800)
    check('next time: no visit', sp.locator('#tour-ov').count() == 0)
    sp.click('.tab[data-t="plus"]'); sp.wait_for_timeout(400)
    check('Plus: « Revoir la visite guidée »', sp.locator('.ph-row[data-act="tour-replay"]', has_text='Revoir la visite guidée').count() == 1)
    sp.click('.ph-row[data-act="tour-replay"]'); sp.wait_for_timeout(100); settle(sp)
    check('…it starts again', sp.locator('#tour-ov .tt-tip').count() == 1 and info(sp)['t'] == 'Bienvenue, Saleh !')
    nxt(sp); nxt(sp)
    sp.click('#tour-ov .tt-x[data-act="tt-skip"]'); sp.wait_for_timeout(800)
    check('« ✕ » stops it at any step (no install sheet on a replay, nothing recorded again)', sp.locator('#tour-ov').count() == 0 and sp.locator('#sheet:not([hidden]) .inst').count() == 0 and (doc('data/users/%s/tour' % uid['saleh']) or {}).get('seenAt') == t0)
    sp.click('.tab[data-t="plus"]'); sp.wait_for_timeout(300); sp.click('.ph-row[data-act="tour-replay"]'); sp.wait_for_timeout(100); settle(sp)
    sp.keyboard.press('Escape'); sp.wait_for_timeout(500)
    check('Escape closes it too', sp.locator('#tour-ov').count() == 0)
    sc.close()
    # with the box « Prendre des rendez-vous »
    doc_set(otok, 'config/roles', {'mecano': {'book': True}}); psql("delete from public.docs where path='data/users/%s/tour'" % uid['saleh'])
    sc = ctx(b, phone=True); sp = page(sc, 'saleh2'); login(sp, 'saleh@garage.test', pw['saleh'], tour=True); wait_for(sp, "!!document.querySelector('#tour-ov .tt-tip')", 9000); settle(sp)
    for k in range(25):
        if info(sp)['t'] == 'Le bouton « + »': break
        nxt(sp)
    check('…« + »: « Facture sur place », « Nouveau client » and « Nouvelle réservation » (box ticked)', info(sp)['t'] == 'Le bouton « + »' and 'Nouvelle réservation' in tip(sp) and lit(sp, '.tab-new'), tip(sp)[:160])
    sp.keyboard.press('Escape'); sc.close()
    # ---------- 2. the treasurer, on a computer ----------
    nc = ctx(b); np_ = page(nc, 'nadia'); np_.set_viewport_size({'width': 1280, 'height': 900}); login(np_, 'nadia@garage.test', pw['nadia'], tour=True)
    wait_for(np_, "!!document.querySelector('#tour-ov .tt-tip')", 9000); settle(np_)
    check('treasurer: « Bienvenue, Nadia ! »', info(np_)['t'] == 'Bienvenue, Nadia !')
    nxt(np_); i = info(np_)
    check('…her treasury first (« La trésorerie »: in, out, what is left; the period at the top)', i['ch'] == 'La trésorerie' and i['hash'] == '#tresor' and 'dépenses' in tip(np_), i)
    nxt(np_)
    check('…« + Dépense » lit: photo of the receipt, the category, taxes counted', lit(np_, '#top [data-act="exp-new"], [data-act="exp-new"]') and 'reçu' in tip(np_) and 'TVQ' in tip(np_))
    np_.screenshot(path='tour_nadia.png')
    nxt(np_); nxt(np_)
    check('…the report opens by itself (revenue, expenses, profit, taxes to send)', np_.evaluate("window.__garageApi.S.trView") == 'rap' and 'taxes à remettre' in tip(np_))
    nxt(np_)
    check('…the Excel file for the accountant, lit', lit(np_, '[data-act="tr-xlsx"]'))
    st = walk(np_); chs = []
    for x in st:
        if x['ch'] not in chs: chs.append(x['ch'])
    check('…then invoices and clients (her boxes), the map, the stock, the end', chs[:3] == ['La trésorerie', 'Clients et factures', 'La carte de l\'équipe'] and chs[-1] == 'Pour finir' and {'#factures', '#clients', '#carte'} <= set(x['hash'] for x in st), chs)
    np_.click('#tour-ov [data-act="tt-end"]'); np_.wait_for_timeout(900)
    check('…remembered; back on her Trésorerie; no install sheet on a computer', bool(doc('data/users/%s/tour' % uid['nadia'])) and np_.evaluate('location.hash') == '#tresor' and np_.locator('#sheet:not([hidden]) .inst').count() == 0)
    check('computer menu: « 👋 Revoir la visite guidée » at the bottom', np_.locator('#navfoot [data-act="tour-replay"]', has_text='Revoir la visite guidée').count() == 1)
    nc.close()
    # ---------- 3. the office, on a computer ----------
    lc = ctx(b); lp = page(lc, 'lina'); lp.set_viewport_size({'width': 1280, 'height': 900}); login(lp, 'lina@garage.test', pw['lina'], tour=True)
    wait_for(lp, "!!document.querySelector('#tour-ov .tt-tip')", 9000); settle(lp)
    st = walk(lp); chs = []
    for x in st:
        if x['ch'] not in chs: chs.append(x['ch'])
    check('office: dashboard, agenda, clients and invoices, the map, the team (availability, stock), the end', chs == ['Bienvenue', 'Le tableau de bord', 'L\'agenda', 'Clients et factures', 'La carte de l\'équipe', 'L\'équipe', 'Pour finir'], chs)
    check('…« + Réservation » and « Modifier l\'horaire » explained, the garage schedule window shown', any(x['t'] == '« + Réservation »' for x in st) and any(x['t'] == 'Modifier l\'horaire' for x in st) and any(x['sched'] and x['t'] == 'La grille de l\'horaire' for x in st))
    lp.click('#tour-ov [data-act="tt-end"]'); lp.wait_for_timeout(700)
    check('…ends cleanly (window closed, back on her home screen)', lp.locator('#sched').count() == 0 and lp.locator('#tour-ov').count() == 0 and lp.evaluate('location.hash') == '#accueil')
    lc.close()
    # ---------- 4. one person, two roles (mechanic + treasurer) ----------
    fn(otok, 'members', {'action': 'update', 'user_id': uid['ali'], 'roles': ['mecano', 'tresorier'], 'mechanic': 'Ali'})
    psql("delete from public.docs where path='data/users/%s/tour'" % uid['ali'])
    ac = ctx(b, phone=True); ap = page(ac, 'ali'); login(ap, 'ali@garage.test', pw['ali'], tour=True); wait_for(ap, "!!document.querySelector('#tour-ov .tt-tip')", 9000); settle(ap)
    st = walk(ap); chs = []
    for x in st:
        if x['ch'] not in chs: chs.append(x['ch'])
    check('two roles: his mechanic visit first, then the treasury — each part once', chs.index('Ta journée') < chs.index('La trésorerie') and len([x for x in st if x['t'] == 'Bienvenue, Ali !']) == 1 and len([x for x in st if x['t'] in ('Tes clients', 'Les clients')]) == 1, chs)
    ap.keyboard.press('Escape'); ac.close()
    fn(otok, 'members', {'action': 'update', 'user_id': uid['ali'], 'roles': ['mecano'], 'mechanic': 'Ali'})
    # ---------- 5. the owner: nothing by itself; the full visit from the menu ----------
    oc = ctx(b); op = page(oc, 'owner'); op.set_viewport_size({'width': 1280, 'height': 900}); login(op, 'hassan@garage.test', pw['hassan'], tour=True); op.wait_for_timeout(2800)
    check('owner: no visit by itself (he has his « Par où commencer » guide)', op.locator('#tour-ov').count() == 0)
    check('…« 👋 Visite guidée de l\'app » at the bottom of his menu', op.locator('#navfoot [data-act="tour-replay"]', has_text='Visite guidée de l\'app').count() == 1)
    op.click('#navfoot [data-act="tour-replay"]'); op.wait_for_timeout(100); settle(op)
    st = walk(op); chs = []
    for x in st:
        if x['ch'] not in chs: chs.append(x['ch'])
    check('…the complete visit: dashboard, agenda, clients, invoices, treasury, map, team, access, settings', all(c in chs for c in ('Le tableau de bord', 'L\'agenda', 'Clients et factures', 'La trésorerie', 'La carte de l\'équipe', 'L\'équipe', 'L\'équipe et les accès', 'Les réglages')), chs)
    check('…« Inviter une personne » (roles and rights) and the colors of the app explained', any(x['t'] == 'Inviter une personne' and x['hash'] == '#equipe' for x in st) and any(x['t'] == 'Les couleurs de l\'app' and x['hash'] == '#reglages' for x in st))
    op.click('#tour-ov [data-act="tt-end"]'); op.wait_for_timeout(800)
    check('…nothing recorded for him', doc('data/users/%s/tour' % uid['hassan']) is None and op.locator('#tour-ov').count() == 0)
    # ---------- 6. « Sa première visite » in « Voir comme… » ----------
    op.evaluate("location.hash = 'equipe'"); op.wait_for_selector('#eq-viewas', timeout=10000); op.wait_for_timeout(800)
    psql("delete from public.docs where path='data/users/%s/tour'" % uid['saleh'])
    op.click('#eq-viewas [data-act="pv-start"][data-mech="Saleh"]'); op.wait_for_timeout(2500)
    check('the preview does not start the visit by itself', op.locator('#tour-ov').count() == 0)
    op.click('#pv-bar [data-act="tour-replay"]'); op.wait_for_timeout(100); settle(op)
    check('bar « 👋 Sa première visite »: Saleh\'s visit, on his phone screen', op.locator('#tour-ov .tt-tip').count() == 1 and info(op)['t'] == 'Bienvenue, Saleh !' and op.evaluate("document.body.classList.contains('ui-phone')"))
    st = walk(op)
    check('…all the way to « C\'est tout ! »', info(op)['t'] == "C'est tout !" and len(st) >= 15, len(st))
    op.screenshot(path='tour_preview_end.png')
    op.click('#tour-ov [data-act="tt-end"]'); op.wait_for_timeout(900)
    check('…nothing recorded (not for Saleh, not for you), no install sheet, still in the preview', doc('data/users/%s/tour' % uid['saleh']) is None and doc('data/users/%s/tour' % uid['hassan']) is None and op.locator('#sheet:not([hidden]) .inst').count() == 0 and op.locator('#pv-bar').count() == 1)
    op.click('#pv-bar [data-act="pv-exit"]'); op.wait_for_timeout(800)
    oc.close()
    b.close()
# back to the start
rpc(otok, 'doc_delete', {'p_path': 'config/roles'})
psql("insert into public.docs (path, data) select 'data/users/' || user_id || '/tour', '{\"seenAt\": 1}' from public.members on conflict (path) do nothing")
check('back to the start (boxes as before, Ali a mechanic only)', doc('config/roles') is None and psql("select array_to_string(roles, ',') from public.members where user_id='%s'" % uid['ali']) == 'mecano')
check('no page errors', not ERRS, ERRS[:5])
summary()
