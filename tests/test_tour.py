"""The guided tours, rebuilt: the person does it. Every change of screen is HIS touch (the menu, « Plus », a tab, a button):
the tour lights where, waits (no « Passer »), and a touch elsewhere does nothing. On each screen he tries things; nothing
tried is saved and his view comes back as it was. Each role, on the phone and on the computer, walked like a person."""
import json, time
from team_seed import *
from tour_walk import *
from playwright.sync_api import sync_playwright

def dbsig():   # everything in the base except the « visit seen » notes
    return psql("select md5(coalesce(string_agg(path || data::text, ',' order by path), '')) from public.docs where path not like 'data/users/%/tour'") + '|' + \
           psql("select md5(coalesce(string_agg(user_id::text || role || coalesce(array_to_string(roles, ','), '') || coalesce(perms::text, ''), ',' order by user_id), '')) from public.members") + '|' + \
           psql("select count(*) from public.invites")
def start(p, who, phone):
    if who == 'hassan':
        p.wait_for_timeout(1200)
        if phone: p.click('.tab[data-t="plus"]'); p.wait_for_timeout(400); p.click('.ph-row[data-act="tour-replay"]')
        else: p.click('#navfoot [data-act="tour-replay"]')
    p.wait_for_function("!!document.querySelector('#tour-ov .tt-tip')", timeout=9000); ready(p)

otok, pw = seed()
uid = {k: psql("select id from auth.users where email='%s@garage.test'" % k) for k in ('hassan', 'saleh', 'ali', 'lina', 'nadia')}
psql("delete from public.docs where path like 'data/users/%/tour'")
sig0 = dbsig()
WALKS = {}
with sync_playwright() as pl:
    b = pl.chromium.launch()
    # ---------- 1. the first time: the visit starts by itself (not for the owner) ----------
    c = ctx(b, phone=True); p = page(c, 'saleh'); login(p, 'saleh@garage.test', pw['saleh'], tour=True)
    ok = wait_for(p, "!!document.querySelector('#tour-ov .tt-tip')", 9000); ready(p); s = p.evaluate(STEP)
    check('first time: the visit starts by itself (« Bienvenue, Saleh ! »), it says the person does it and nothing is saved', ok and s['t'] == 'Bienvenue, Saleh !' and 'toi qui touches' in s['words'] and 'enregistré' in s['words'], s)
    check('…« Plus tard » and « Commencer la visite »', p.locator('#tour-ov [data-act="tt-skip"]', has_text='Plus tard').count() == 1 and p.locator('#tour-ov [data-act="tt-next"]', has_text='Commencer la visite').count() == 1)
    st = walk(p, shots='tour_meca'); WALKS['mécano · téléphone'] = st
    p.click('#tour-ov [data-act="tt-end"]'); p.wait_for_timeout(900)
    ti = [s['t'] for s in st]
    check('the visit starts with putting the app on the home screen: right after « Bienvenue », he touches « Plus », then « Mettre l\'app sur l\'écran d\'accueil », the steps for his phone open and he can do it right away',
          ti[1:2] == ["D'abord : l'app sur ton écran d'accueil"] and "Mettre l'app sur l'écran d'accueil" in ti[:5] and 'Fais-le maintenant' in ti[:6] and [s for s in st if s['t'] == 'Fais-le maintenant'][0].get('did') == 'install', ti[:7])
    check('« Terminer »: the visit closes, back on his day, a short message (the install help does not open again: it was the first part)', p.locator('#tour-ov').count() == 0 and p.locator('#sched').count() == 0 and p.evaluate('location.hash') == '#jour' and p.locator('#sheet:not([hidden]) .inst').count() == 0)
    t0 = doc('data/users/%s/tour' % uid['saleh'])
    check('…remembered once per person', bool(t0) and t0.get('seenAt'))
    c.close()
    c = ctx(b, phone=True); p = page(c, 'saleh2'); login(p, 'saleh@garage.test', pw['saleh'], tour=True); p.wait_for_timeout(2500)
    check('next time: no visit by itself; « Revoir la visite guidée » in Plus starts it again', p.locator('#tour-ov').count() == 0 and (p.click('.tab[data-t="plus"]') or True) and (p.wait_for_timeout(400) or True) and p.locator('.ph-row[data-act="tour-replay"]', has_text='Revoir la visite guidée').count() == 1)
    p.click('.ph-row[data-act="tour-replay"]'); p.wait_for_function("!!document.querySelector('#tour-ov .tt-tip')", timeout=9000); ready(p)
    p.keyboard.press('Escape'); p.wait_for_timeout(600)
    check('Escape (or ✕) stops it at any step', p.locator('#tour-ov').count() == 0)
    c.close()
    # ---------- 2. every role, phone and computer, walked like a person ----------
    for who, phone, tag in (('nadia', True, 'trésorier · téléphone'), ('nadia', False, 'trésorier · ordi'), ('lina', False, 'bureau · ordi'), ('lina', True, 'bureau · téléphone'),
                            ('hassan', False, 'propriétaire · ordi'), ('hassan', True, 'propriétaire · téléphone'), ('saleh', False, 'mécano · ordi')):
        psql("delete from public.docs where path like 'data/users/%/tour'")
        c = ctx(b, phone=phone); p = page(c, who)
        if not phone: p.set_viewport_size({'width': 1366, 'height': 860})
        login(p, who + '@garage.test', pw[who], tour=True); start(p, who, phone)
        cfg0 = psql("select data::text from public.docs where path='config/main'")
        before = p.evaluate(STATE)
        WALKS[tag] = walk(p, shots='tour_' + who + ('_ph' if phone else '_pc'))
        p.click('#tour-ov [data-act="tt-end"]'); p.wait_for_timeout(900)
        after = p.evaluate(STATE)
        WALKS[tag + ' (après)'] = {'before': before, 'after': after, 'ov': p.locator('#tour-ov').count(), 'sched': p.locator('#sched').count(), 'sheet': p.evaluate("!!window.__garageApi.S.sheet && !document.querySelector('#sheet .inst')")}
        if who == 'hassan':   # the color he picked during the visit stays: on screen, saved for the garage, still there when the app is opened again
            saved = (doc('config/main') or {}).get('lux') or ''
            p.reload(); p.wait_for_selector('#tabbar, .acct, .ph-top', timeout=15000); p.wait_for_timeout(1800)
            WALKS[tag + ' (couleur)'] = {'before': before['lux'], 'after': after['lux'], 'saved': saved, 'reopened': p.evaluate("document.documentElement.getAttribute('data-lux') || ''")}
            psql("update public.docs set data = '%s'::jsonb where path = 'config/main'" % cfg0.replace("'", "''"))   # (the test puts the garage's color back)
        c.close()
    # ---------- 3. one person, two roles (mechanic + treasurer) ----------
    fn(otok, 'members', {'action': 'update', 'user_id': uid['ali'], 'roles': ['mecano', 'tresorier'], 'mechanic': 'Ali'})
    psql("delete from public.docs where path like 'data/users/%/tour'")
    c = ctx(b, phone=True); p = page(c, 'ali'); login(p, 'ali@garage.test', pw['ali'], tour=True); start(p, 'ali', True)
    st = walk(p); WALKS['mécano + trésorier · téléphone'] = st
    chs = []
    for x in st:
        if x['ch'] not in chs: chs.append(x['ch'])
    check('two roles: his mechanic visit first, then the treasury; each part once', 'Ta journée' in chs and 'La trésorerie' in chs and chs.index('Ta journée') < chs.index('La trésorerie') and len(chs) == len(set(chs)), chs)
    c.close()
    # ---------- 4. the owner's « Voir comme… »: Saleh's visit, nothing recorded ----------
    psql("delete from public.docs where path like 'data/users/%/tour'")
    c = ctx(b); p = page(c, 'owner'); p.set_viewport_size({'width': 1440, 'height': 900}); login(p, 'hassan@garage.test', pw['hassan'])
    p.evaluate("location.hash = 'equipe'"); p.wait_for_selector('#eq-viewas', timeout=10000); p.wait_for_timeout(800)
    hdoc = doc('data/users/%s/tour' % uid['hassan'])
    p.click('#eq-viewas [data-act="pv-start"][data-mech="Saleh"]'); p.wait_for_timeout(2500)
    check('« Voir comme… »: the preview does not start the visit by itself', p.locator('#tour-ov').count() == 0)
    p.click('#pv-bar [data-act="tour-replay"]'); p.wait_for_function("!!document.querySelector('#tour-ov .tt-tip')", timeout=9000); ready(p)
    st = walk(p); WALKS['aperçu de Saleh'] = st
    p.click('#tour-ov [data-act="tt-end"]'); p.wait_for_timeout(900)
    check('…his visit, by touches, to the end; nothing recorded for him or for you', st and st[-1]['t'] == "C'est tout !" and not autonav(st) and doc('data/users/%s/tour' % uid['saleh']) is None and doc('data/users/%s/tour' % uid['hassan']) == hdoc and p.locator('#pv-bar').count() == 1, len(st))
    p.click('#pv-bar [data-act="pv-exit"]'); p.wait_for_timeout(600)
    c.close()
    b.close()

json.dump(WALKS, open('tour_walks.json', 'w'), ensure_ascii=False, indent=1, default=str)
walks = {k: v for k, v in WALKS.items() if isinstance(v, list)}
allst = [s for v in walks.values() for s in v]
taps = [s for s in allst if s['kind'] == 'tap']; tries = [s for s in allst if s['kind'] == 'try']
check('%d visits walked to « C\'est tout ! » (each role, phone and computer)' % len(walks), all(v and v[-1]['t'] == "C'est tout !" for v in walks.values()), {k: (len(v), v[-1]['t'] if v else None) for k, v in walks.items()})
bad = {k: autonav(v) for k, v in walks.items() if autonav(v)}
check('EVERY change of screen is the person\'s own touch: the tour never moves by itself (%d steps)' % len(allst), not bad, bad)
check('every « touch it » step: the button is lit and pulses, the bubble says what to touch, and there is NO « Passer » (%d)' % len(taps), all(s['pulse'] and 'Touche' in s['words'] and not s['next'] for s in taps), [(s['t'], s['pulse'], s['next']) for s in taps if not (s['pulse'] and 'Touche' in s['words'] and not s['next'])][:5])
check('…a touch elsewhere does nothing (the visit waits for the lit button)', all(s.get('blocked') for s in taps), [s['t'] for s in taps if not s.get('blocked')][:5])
check('…touching the lit button does what it always does, and the visit goes on right away (slowest %.2f s)' % max(s.get('went') or 9 for s in taps), all(s.get('went') is not None and s['went'] < 2.0 for s in taps), [(s['t'], s.get('went')) for s in taps if not (s.get('went') is not None and s['went'] < 2.0)][:5])
check('every « try it » step registers what the person did (%d tries: grid, colors, search, filters, « ? », period, map, roles, amount, days, views)' % len(tries), all(s.get('tried_after') for s in tries), [(s['t'], s.get('did')) for s in tries if not s.get('tried_after')][:6])
kinds = set(s.get('did') for s in tries)
check('…all the kinds of tries happen somewhere', {'drag grid', 'color', 'search', 'filter', '?', 'quarter', 'amount', 'role', 'week', 'next day', 'other day'} <= kinds and ({'marker', 'drag map'} & kinds), sorted(k for k in kinds if k))
am = [s for s in tries if s.get('did') == 'amount']
check('expense amount tried, then « Entrée » pressed (which saves an expense normally): nothing is sent, the window stays open as it was (%d)' % len(am), am and all(s.get('enter') is True for s in am), [s.get('enter') for s in am])
check('the « ? » opens its explanation, lit with it', all(s.get('helptip', 0) >= 1 for s in tries if s.get('did') == '?'))
ph = [s['t'] for s in walks['mécano · téléphone']]
check('mechanic: his day (› then « Aujourd\'hui »), he opens Marie\'s job himself, opens the sections, the « + », clients, invoices, the map, the stock (no « his hours »: his truck\'s schedule decides)',
      all(t in ph for t in ('Changer de jour', 'Revenir à aujourd\'hui', 'Ouvre un rendez-vous', 'Les sections', 'Le bouton « + »', 'Chercher', 'Les filtres', 'L\'inventaire')) and 'Tes disponibilités' not in ph, ph)
ow = [s['t'] for s in walks['propriétaire · ordi']]
check('owner: agenda (days, views, schedule grid), clients, invoices, treasury (expense, report, period), stock, map, availability, colors, team (roles)',
      all(t in ow for t in ('Changer de jour', 'Jour, semaine ou liste', 'La grille', 'Le montant', 'La période', 'L\'inventaire', 'La carte de l\'équipe', 'Les couleurs', 'Les rôles')), ow)
tr = [s['t'] for s in walks['trésorier · téléphone']]
check('treasurer: her treasury first (expense amount, report, period), the stock through « Plus », invoices and clients', tr.index('Le montant') < tr.index('Le rapport') < tr.index('La période') and 'L\'inventaire' in tr and 'Les filtres' in tr, tr)
after = {k: v for k, v in WALKS.items() if k.endswith('(après)')}
nolux = lambda d: {k: v for k, v in d.items() if k != 'lux'}
check('after each visit: his view is back as it was (agenda view, invoice filter, search, report view, day)', all(nolux(v['before']) == nolux(v['after']) for v in after.values()), {k: (v['before'], v['after']) for k, v in after.items() if nolux(v['before']) != nolux(v['after'])})
check('…the people who have no color step keep the app\'s color as it was', all(v['before']['lux'] == v['after']['lux'] for k, v in after.items() if 'propriétaire' not in k), {k: (v['before']['lux'], v['after']['lux']) for k, v in after.items() if 'propriétaire' not in k})
lux = {k: v for k, v in WALKS.items() if k.endswith('(couleur)')}
check('the owner picks a color during the visit: IT STAYS after « Terminer », it is saved for the garage, and it is still there when the app is opened again (%s)' % ', '.join('%s → %s' % (v['before'] or 'sable', v['after']) for v in lux.values()),
      len(lux) == 2 and all(v['after'] and v['after'] != v['before'] and v['saved'] == v['after'] and v['reopened'] == v['after'] for v in lux.values()), lux)
check('…the visit is closed, no schedule window, no form left open', all(v['ov'] == 0 and v['sched'] == 0 and not v['sheet'] for v in after.values()), after)
fn(otok, 'members', {'action': 'update', 'user_id': uid['ali'], 'roles': ['mecano'], 'mechanic': 'Ali'})   # (the test itself gave Ali a 2nd role)
check('NOTHING else tried during the visits was saved: the base is exactly as before (jobs, clients, settings, hours, people, rights, invitations; the color chosen was put back by the test)', dbsig() == sig0, [sig0, dbsig()])
psql("insert into public.docs (path, data) select 'data/users/' || user_id || '/tour', '{\"seenAt\": 1}' from public.members on conflict (path) do nothing")
check('back to the start (Ali a mechanic only)', psql("select array_to_string(roles, ',') from public.members where user_id='%s'" % uid['ali']) == 'mecano')
check('no page errors', not ERRS, ERRS[:5])
summary()
