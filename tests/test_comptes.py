"""Chaque type de compte, sur l'ordi et le téléphone, devant les changements de novembre :
camions Ouvrir / Fermer et horaire par camion, temps de route estimé, fiche technique remplie toute seule, texto de rendez-vous,
paiement avant de partir, glisser-déposer, suivi (« En route » sur une job sans mécano). Comptes : propriétaire, bureau,
bureau sans « horaire », mécano, trésorier, bureau + mécano. Vraies écritures pour ce qui touche aux droits (horaire d'un camion)."""
import json, os, re, time, datetime
from team_seed import *
from playwright.sync_api import sync_playwright

T0 = datetime.date.today(); TD = T0.isoformat()
DD = T0 + datetime.timedelta(days=2)
while DD.weekday() >= 5: DD += datetime.timedelta(days=1)
D = DD.isoformat()
otok, pw = seed()
for who, email, roles, mech in (('Zoé Bureau', 'zoe@garage.test', ['bureau'], None), ('Karim Double', 'karim@garage.test', ['bureau', 'mecano'], 'Karim')):
    r = fn(otok, 'members', {'action': 'create', 'name': who, 'email': email, 'role': roles[0], 'mechanic': mech, 'password': 'Passe-' + email.split('@')[0] + '-26'})
    assert r and r.get('ok'), r
    pw[email.split('@')[0]] = 'Passe-' + email.split('@')[0] + '-26'
psql("update public.members set perms = '{\"hours_others\": false}'::jsonb where name = 'Zoé Bureau'")
psql("update public.members set roles = '{bureau,mecano}', mechanic = 'Karim' where name = 'Karim Double'")
psql("insert into public.docs (path, data) select 'data/users/' || user_id || '/tour', '{\"seenAt\": 1}' from public.members on conflict (path) do nothing")
c = doc('config/main'); c.pop('bookMode', None); c['homePostal'] = 'H4P 2B5'; c['mechanics'] = ['Hassan', 'Saleh', 'Ali', 'Karim']
c['hours'] = {str(x): {'open': True, 'start': '08:00', 'end': '20:00'} for x in range(7)}
c['trucks'] = [{'id': 'c1', 'name': 'Saleh', 'on': True, 'mech': 'Saleh'}, {'id': 'c2', 'name': 'Ali', 'on': True, 'mech': 'Ali'}, {'id': 'c3', 'name': 'Camion 3', 'on': False, 'mech': ''}]
doc_set(otok, 'config/main', c)
cl1 = doc('clients/c1'); snap = {'id': 'c1', 'firstName': 'Marie', 'lastName': 'Tremblay', 'name': 'Marie Tremblay', 'phone': cl1['phone'], 'address': cl1['address'], 'postal': cl1['postal'], 'geo': cl1['geo']}
base = {'durationMin': 60, 'clientId': 'c1', 'client': snap, 'services': ["Changement d'huile et filtre"], 'createdAt': 1}
doc_set(otok, 'jobs/k1', dict(base, date=D, time='08:00', block='am', mechanic='Saleh', truck='c1', status='planifie', vehicle={'year': '2018', 'make': 'Honda', 'model': 'Civic'}))
doc_set(otok, 'jobs/k4', dict(base, date=D, time='09:00', block='am', mechanic='Ali', truck='c2', status='planifie', vehicle={'year': '2016', 'make': 'Toyota', 'model': 'Corolla'}))
K2 = dict(base, date=TD, time='12:00', block='pm', mechanic='Saleh', truck='c1', status='place', vehicle={'year': '2016', 'make': 'Toyota', 'model': 'Corolla'},
          invoice={'lines': [{'type': 'forfait', 'desc': 'Inspection multipoints', 'qty': 1, 'price': 59}], 'taxesOn': True, 'sub': 59, 'tps': 2.95, 'tvq': 5.89, 'total': 67.84, 'paid': False, 'number': 'F-0098', 'issuedAt': TD})
doc_set(otok, 'jobs/k2', K2)
doc_set(otok, 'jobs/k3', dict(base, date=TD, time='17:00', block='eve', mechanic='', truck='c1', status='planifie'))
# that day, each mechanic picked his truck in his app (nobody assigns them; k3 today stays without a mechanic)
for em, k in (('saleh', 'c1'), ('ali', 'c2')):
    http('POST', API + '/rest/v1/rpc/pick_truck', {'p_date': D, 'p_truck': k}, token(em + '@garage.test', pw[em]))

def show(p, d):
    p.evaluate("(d) => { const A = window.__garageApi, S = A.S; S.tab = 'agenda'; S.screen = null; S.day = d; S.view = 'grid'; S.mech = ''; A.render(); }", d); p.wait_for_timeout(600)
def job_page(p, jid):
    p.evaluate("(id) => { const A = window.__garageApi, S = A.S; S.tab = 'agenda'; S.screen = 'job'; S.jobId = id; A.render(); }", jid); p.wait_for_timeout(500)
    p.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)"); p.wait_for_timeout(150)
def has(p, sel): return p.locator(sel).count() > 0
def close(p): p.evaluate("document.querySelector('#sheet [data-act=\"sheet-close\"]') && document.querySelector('#sheet [data-act=\"sheet-close\"]').click()"); p.wait_for_timeout(300)

# what each account should get        truck btns, open c3, sched tabs, drag, spec chips (k1), rdv btn (k1), Encaisser (k2), waive
EXPECT = {'hassan': dict(trucks=True, open3=True, tabs=True, drag=True, spec=True, rdv=True, pay=True, waive=True),
          'lina':   dict(trucks=True, open3=False, tabs=True, drag=True, spec=True, rdv=True, pay=True, waive=False),
          'zoe':    dict(trucks=False, open3=False, tabs=False, drag=True, spec=True, rdv=True, pay=True, waive=False),
          'saleh':  dict(trucks=False, open3=False, tabs=False, drag=False, spec=True, rdv=True, pay=True, waive=False),
          'nadia':  dict(trucks=False, open3=False, tabs=False, drag=False, spec=False, rdv=False, pay=False, waive=False),
          'karim':  dict(trucks=True, open3=False, tabs=True, drag=True, spec=True, rdv=True, pay=True, waive=False)}
NAMES = {'hassan': 'owner', 'lina': 'office', 'zoe': 'office without « hours »', 'saleh': 'mechanic', 'nadia': 'treasurer', 'karim': 'office + mechanic'}

with sync_playwright() as pl:
    b = pl.chromium.launch()
    for who in ('hassan', 'lina', 'zoe', 'saleh', 'nadia', 'karim'):
        E, nm = EXPECT[who], NAMES[who]
        # ---------- computer ----------
        cx = ctx(b); p = page(cx, who + '-pc'); p.set_viewport_size({'width': 1300, 'height': 900}); login(p, who + '@garage.test', pw[who])
        show(p, D)
        got = dict(trucks=has(p, '.colh [data-act="truck-close"]'), open3=has(p, '.colh[data-truck="c3"] [data-act="truck-open"]'), drag=has(p, '[data-drag]'))
        p.evaluate("document.querySelector('[data-act=\"sched\"][data-v=\"garage\"]') && document.querySelector('[data-act=\"sched\"][data-v=\"garage\"]').click()"); p.wait_for_timeout(500)
        got['tabs'] = has(p, '#sched .sch-tabs')
        p.evaluate("document.querySelector('#sched .sch-foot [data-act=\"sc-close\"]') && document.querySelector('#sched .sch-foot [data-act=\"sc-close\"]').click()"); p.wait_for_timeout(300)
        road = txt(p, '#bbar')
        job_page(p, 'k1')
        got['spec'] = has(p, '#speccard [data-act="spec-eng"]'); got['rdv'] = has(p, '[data-act="rdv-send"]')
        job_page(p, 'k2')
        nb = txt(p, '.nextbtn'); got['pay'] = nb.startswith('Encaisser')
        if got['pay']:
            p.click('.nextbtn'); p.wait_for_timeout(500); got['waive'] = has(p, '#sheet [data-act="pay-waive"]'); here = has(p, '#sheet [data-act="pay-here"]')
            check('%s · computer · « Payé sur place » offered in the payment window' % nm, here)
            if who == 'saleh':   # the mechanic marks his own job paid (real base), then the job is put back for the next accounts
                p.click('#sheet [data-act="pay-here"][data-v="Comptant"]'); p.wait_for_timeout(1500)
                iv = (doc('jobs/k2') or {}).get('invoice') or {}
                check('mechanic · marks his own invoice paid (Comptant): saved by the server', iv.get('paid') is True and iv.get('method') == 'Comptant', iv)
                doc_set(otok, 'jobs/k2', K2)
            else: close(p)
        else: got['waive'] = False
        if who in ('saleh', 'hassan', 'lina'):   # edit an invoice (the mechanic: always, on his jobs)
            job_page(p, 'k2'); p.evaluate("document.querySelector('[data-act=\"invoice\"][data-id=\"k2\"], [data-act=\"preview\"][data-id=\"k2\"]') && document.querySelector('[data-act=\"invoice\"][data-id=\"k2\"], [data-act=\"preview\"][data-id=\"k2\"]').click()"); p.wait_for_timeout(600)
            if has(p, '[data-act="inv-edit"], [data-act="edit-inv"], [data-act="invoice"]') and not has(p, '#i-final'):
                p.evaluate("(document.querySelector('[data-act=\"inv-edit\"]') || document.querySelector('[data-act=\"edit-inv\"]') || document.querySelector('[data-act=\"invoice\"]')).click()"); p.wait_for_timeout(600)
            check('%s · computer · can open the invoice to change it (lines, « Payée »)' % nm, has(p, '#i-final') and has(p, '#i-paid-1'), txt(p, 'main')[:160])
        for k in E:
            check('%s · computer · %s' % (nm, {'trucks': 'truck « Horaire / Fermer » buttons', 'open3': '« Ouvrir » a truck out of service', 'tabs': 'one schedule per truck (tabs)', 'drag': 'drag appointments',
                                              'spec': 'choose the engine (spec sheet)', 'rdv': '« Envoyer la confirmation au client »', 'pay': '« Encaisser » (job on site, not paid)', 'waive': '« Laisser partir sans paiement »'}[k] + (' — yes' if E[k] else ' — no')),
                  got[k] == E[k], got)
        if E['trucks'] or who == 'saleh':
            check('%s · computer · the day bar shows the road time as an estimate' % nm, 'de route (estimé)' in road or not road, road[:160])
        # a real write: the office closes a truck for one day (its schedule document), the owner as before
        if who in ('lina', 'karim'):
            psql("delete from public.docs where col = 'hours'"); p.evaluate('window.__supa.resync(true)'); p.wait_for_timeout(800)
            show(p, D)
            p.click('.colh[data-truck="c2"] [data-act="truck-close"]'); p.wait_for_selector('#sheet [data-act="truck-close-go"]', timeout=8000)
            check('%s · closing a truck: only « that day » (for good: owner only)' % nm, has(p, '#sheet [data-act="truck-close-go"][data-v="day"]') and not has(p, '#sheet [data-act="truck-close-go"][data-v="all"]') and 'seulement le propriétaire' in txt(p, '#sheet'))
            p.click('#sheet [data-act="truck-close-go"][data-v="day"]'); p.wait_for_timeout(1500)
            h = doc('hours/c2') or {}
            check('%s · …saved in Ali\'s schedule (real base, the office\'s rights)' % nm, (h.get('dates') or {}).get(D) == {'on': False}, h)
            psql("delete from public.docs where path = 'hours/c2'")
        if who == 'zoe':
            r = doc_set(token('zoe@garage.test', pw['zoe']), 'hours/c2', {'week': None, 'dates': {D: {'on': False}}})
            check('office without « hours »: the server refuses a truck schedule too', isinstance(r, dict) and r.get('_status') in (400, 401, 403) and doc('hours/c2') is None, r)
        if who == 'saleh':
            r = doc_set(token('saleh@garage.test', pw['saleh']), 'hours/c1', {'week': None, 'dates': {D: {'on': False}}})
            check('mechanic: the server refuses a truck schedule', isinstance(r, dict) and r.get('_status') in (400, 401, 403) and doc('hours/c1') is None, r)
        check('%s · computer: no errors' % nm, not [e for e in ERRS if e.startswith(who + '-pc')], [e for e in ERRS if e.startswith(who)][:3])
        cx.close()
        # ---------- phone ----------
        cx = ctx(b, phone=True, geo={'latitude': 45.50, 'longitude': -73.60}); p = page(cx, who + '-phone'); login(p, who + '@garage.test', pw[who])
        p.evaluate("(d) => { const A = window.__garageApi, S = A.S; S.day = d; S.mech = 'c1'; A.render(); }", D); p.wait_for_timeout(500)
        check('%s · phone · truck bar « Horaire / Fermer »%s' % (nm, '' if E['trucks'] else ' — none'), has(p, '.tkbar [data-act="truck-close"]') == E['trucks'])
        check('%s · phone · nothing to drag' % nm, not has(p, '[data-drag]'))
        job_page(p, 'k1')
        check('%s · phone · engine choice %s' % (nm, 'there' if E['spec'] else 'not offered'), has(p, '#speccard [data-act="spec-eng"]') == E['spec'], txt(p, '#speccard')[:120])
        check('%s · phone · no sideways scroll on a job' % nm, no_hscroll(p))
        check('%s · phone: no errors' % nm, not [e for e in ERRS if e.startswith(who + '-phone')], [e for e in ERRS if e.startswith(who)][:3])
        cx.close()

    # ---------- « Voir comme » : the owner sees the app as a mechanic ----------
    cx = ctx(b); p = page(cx, 'viewas'); p.set_viewport_size({'width': 1300, 'height': 900}); login(p, 'hassan@garage.test', pw['hassan'])
    p.evaluate("location.hash = 'equipe'"); p.wait_for_selector('#eq-viewas', timeout=10000); p.wait_for_timeout(800)
    p.click('#eq-viewas [data-act="pv-start"][data-mech="Saleh"]'); p.wait_for_timeout(1500)
    show(p, D)
    check('« Voir comme Saleh » : no truck buttons, nothing to drag (as Saleh sees it)', not has(p, '.colh [data-act="truck-close"]') and not has(p, '[data-drag]'))
    job_page(p, 'k2')
    if txt(p, '.nextbtn').startswith('Encaisser'):
        p.click('.nextbtn'); p.wait_for_timeout(400)
    check('« Voir comme Saleh » : no « Laisser partir sans paiement »', not has(p, '#sheet [data-act="pay-waive"]'))
    check('« Voir comme » : no errors', not [e for e in ERRS if e.startswith('viewas')], ERRS[:3])
    b.close()
summary()
