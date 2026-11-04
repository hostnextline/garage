"""Glisser-déposer les rendez-vous sur l'ordi (copie locale de Supabase, vraies écritures) :
1. on glisse un rendez-vous dans une autre colonne / un autre bloc → « Déplacer ce rendez-vous ? » (avant / après) ;
   « Annuler » ne change rien ; « Oui, déplacer » : le camion, le bloc, et le client reçoit un texto (nouveau bloc) ;
2. même bloc, autre camion : déplacé, le client n'est pas avisé (il voit seulement le bloc) ;
3. vue semaine : vers un autre jour ; un bloc complet ou un camion qui ne roule pas : refusé, rien ne bouge ;
4. ni le mécano, ni le téléphone, ni une job commencée ne se glissent."""
import json, os, re, time, datetime
from team_seed import *
from playwright.sync_api import sync_playwright

def sms(): return [x['body']['message'] for x in json.loads(urllib.request.urlopen('http://127.0.0.1:9200/__log').read()) if x['path'] == '/conversations/messages']
T0 = datetime.date.today()
def wd(start):
    d = T0 + datetime.timedelta(days=start)
    while d.weekday() >= 5: d += datetime.timedelta(days=1)
    return d
DD = T0 + datetime.timedelta(days=2)
while DD.weekday() > 3: DD += datetime.timedelta(days=1)   # (Monday to Thursday: the next day is in the same week, for the week view)
D = DD.isoformat()
DD2 = DD + datetime.timedelta(days=1); D2 = DD2.isoformat()
def job(i): return doc('jobs/' + i) or {}
def dnd(p, src, dst):
    """the drag as the browser sends it (dragstart → dragover → drop → dragend), for targets far down the scrolling grid"""
    p.evaluate("""([s, d]) => { const a = document.querySelector(s), b = document.querySelector(d), dt = new DataTransfer();
      a.dispatchEvent(new DragEvent('dragstart', {bubbles:true, dataTransfer:dt}));
      b.dispatchEvent(new DragEvent('dragover', {bubbles:true, cancelable:true, dataTransfer:dt}));
      b.dispatchEvent(new DragEvent('drop', {bubbles:true, cancelable:true, dataTransfer:dt}));
      a.dispatchEvent(new DragEvent('dragend', {bubbles:true, dataTransfer:dt})); }""", [src, dst]); p.wait_for_timeout(500)
def mouse_drag(p, src, dst):
    """a real drag with the mouse (source and target both on screen)"""
    a = p.locator(src); a.scroll_into_view_if_needed(); ba = a.bounding_box()
    p.mouse.move(ba['x'] + ba['width'] / 2, ba['y'] + 12); p.mouse.down(); p.mouse.move(ba['x'] + ba['width'] / 2 + 15, ba['y'] + 30, steps=4)
    bb = p.locator(dst).bounding_box(); p.mouse.move(bb['x'] + 10, bb['y'] + bb['height'] / 2, steps=8); p.mouse.up(); p.wait_for_timeout(500)
def show(p, d, view='grid'):
    p.goto(BASE + '#agenda'); p.wait_for_timeout(400)
    p.evaluate("([d, v]) => { const A = window.__garageApi, S = A.S; S.day = d; S.view = v; S.mech = ''; S.screen = null; A.render(); }", [d, view]); p.wait_for_timeout(600)

otok, pw = seed()
c = doc('config/main'); c.pop('bookMode', None); c['homePostal'] = 'H4P 2B5'
c['hours'] = {str(x): {'open': True, 'start': '08:00', 'end': '20:00'} for x in range(7)}
c['trucks'] = [{'id': 'c1', 'name': 'Saleh', 'on': True, 'mech': 'Saleh'}, {'id': 'c2', 'name': 'Ali', 'on': True, 'mech': 'Ali'}, {'id': 'c3', 'name': 'Camion 3', 'on': True, 'mech': ''}]
doc_set(otok, 'config/main', c)
for dd in (D, D2): doc_set(otok, 'days/' + dd, {'date': dd, 'opened': [], 'blocked': [], 'crew': {'c1': 'Saleh', 'c2': 'Ali'}})   # (who picked which truck those days, in their app)
doc_set(otok, 'hours/c2', {'week': None, 'dates': {D2: {'on': False}}})                       # (each truck's schedule)
doc_set(otok, 'hours/c3', {'week': None, 'dates': {D: {'on': False}, D2: {'on': False}}})
cl1 = doc('clients/c1')
snap = {'id': 'c1', 'firstName': 'Marie', 'lastName': 'Tremblay', 'name': 'Marie Tremblay', 'phone': cl1['phone'], 'address': cl1['address'], 'postal': cl1['postal'], 'geo': cl1['geo']}
doc_set(otok, 'jobs/m1', {'date': D, 'time': '08:00', 'block': 'am', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c1', 'client': snap, 'services': ['Inspection multipoints'], 'status': 'planifie', 'createdAt': 1,
                          'rdvSms': {'key': D + '|am', 'status': 'sent', 'at': 1}})
for i in range(4):   # D2 evening: Saleh (the only one running that day) is full
    doc_set(otok, 'jobs/f%d' % i, {'date': D2, 'time': '16:00', 'block': 'eve', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c1', 'client': dict(snap, firstName='Plein %d' % i, name='Plein %d' % i), 'services': ['Inspection multipoints'], 'status': 'planifie', 'createdAt': 1})
doc_set(otok, 'jobs/r1', {'date': T0.isoformat(), 'time': '10:00', 'block': 'am', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c1', 'client': snap, 'services': ['Inspection multipoints'], 'status': 'route', 'createdAt': 1})

with sync_playwright() as pl:
    b = pl.chromium.launch()
    oc = ctx(b); op = page(oc, 'owner'); op.set_viewport_size({'width': 1300, 'height': 900}); login(op, 'hassan@garage.test', pw['hassan'])
    show(op, D)
    check('computer: a planned appointment can be grabbed', op.locator('.appt[data-drag="m1"]').count() == 1)
    n0 = len(sms())
    dnd(op, '.appt[data-drag="m1"]', '.col[data-col="c2"] .slot[data-t="13:00"]'); op.wait_for_timeout(500)
    sh = txt(op, '#sheet')
    check('dropped in Ali at 13 h → « Déplacer ce rendez-vous ? » before / after', 'Déplacer ce rendez-vous' in sh and 'Matin (8 h à 12 h) · Saleh' in sh and 'Après-midi (12 h à 16 h) · Ali' in sh, sh[:300])
    check('…says Marie gets a text with the new appointment', 'Marie reçoit un texto' in sh, sh)
    op.screenshot(path=os.path.join(SC, 'dnd_confirm.png'))
    op.click('#sheet [data-act="drop-no"]'); op.wait_for_timeout(800)
    check('« Annuler » : nothing moved', job('m1').get('truck') == 'c1' and job('m1').get('block') == 'am' and len(sms()) == n0)
    show(op, D)
    dnd(op, '.appt[data-drag="m1"]', '.col[data-col="c2"] .slot[data-t="13:00"]'); op.wait_for_selector('#sheet [data-act="drop-yes"]', timeout=5000)
    op.evaluate("() => { window.__toasts = []; const t = document.getElementById('toast'); if (t) new MutationObserver(() => window.__toasts.push(t.textContent)).observe(t, {childList:true, characterData:true, subtree:true}); }")   # (every message shown: a slow machine may show the next one before we look)
    op.click('#sheet [data-act="drop-yes"]')
    seen = wait_for(op, "(window.__toasts || []).some(x => x.includes('Rendez-vous déplacé'))", 8000)
    check('« Oui, déplacer » : « Rendez-vous déplacé »', seen, op.evaluate("window.__toasts"))
    for _ in range(30):
        if len(sms()) > n0: break
        time.sleep(0.5)
    m1 = job('m1')
    check('…saved: Ali, afternoon, kept in that truck', m1.get('truck') == 'c2' and m1.get('block') == 'pm' and m1.get('pin') is True and m1.get('mechanic') == 'Ali', {k: m1.get(k) for k in ('truck', 'block', 'pin', 'mechanic', 'time')})
    check('…Marie got the text « a changé … entre 12 h et 16 h »', len(sms()) == n0 + 1 and 'a changé' in sms()[-1] and 'entre 12 h et 16 h' in sms()[-1], sms()[-1:])

    # ---------- 2. same block, another truck ----------
    show(op, D); op.wait_for_timeout(500)
    n1 = len(sms())
    mouse_drag(op, '.appt[data-drag="m1"]', '.col[data-col="c1"] .slot[data-t="13:00"]'); op.wait_for_selector('#sheet [data-act="drop-yes"]', timeout=5000)
    check('a real mouse drag (same block, Saleh): « il n\'est pas avisé »', 'pas avisé' in txt(op, '#sheet'), txt(op, '#sheet'))
    op.click('#sheet [data-act="drop-yes"]'); op.wait_for_timeout(2000)
    check('…moved to Saleh, no text', job('m1').get('truck') == 'c1' and job('m1').get('block') == 'pm' and len(sms()) == n1, (job('m1').get('truck'), len(sms()) - n1))
    dnd(op, '.appt[data-drag="m1"]', '.col[data-col="c3"] .slot[data-t="14:00"]'); op.wait_for_timeout(600)
    check('a truck that does not run that day: refused (« Camion 3 ne roule pas »), nothing moves', toast_has(op, 'Camion 3 ne roule pas') and job('m1').get('truck') == 'c1', txt(op, '#toast'))

    # ---------- 3. week view: another day ----------
    show(op, D, 'week')
    tgt = '.slot[data-d="%s"][data-t="17:00"]' % D2
    check('week view: the appointment can be grabbed too', op.locator('.appt[data-drag="m1"]').count() == 1 and op.locator(tgt).count() == 1)
    dnd(op, '.appt[data-drag="m1"]', tgt); op.wait_for_timeout(600)
    check('to a full block (%s evening): refused, « complet »' % D2, toast_has(op, 'complet') and job('m1').get('date') == D, txt(op, '#toast'))
    show(op, D, 'week')
    dnd(op, '.appt[data-drag="m1"]', '.slot[data-d="%s"][data-t="13:00"]' % D2); op.wait_for_selector('#sheet [data-act="drop-yes"]', timeout=5000)
    op.click('#sheet [data-act="drop-yes"]'); op.wait_for_timeout(2500)
    check('to another day with room: moved (%s, afternoon)' % D2, job('m1').get('date') == D2 and job('m1').get('block') == 'pm', (job('m1').get('date'), job('m1').get('block')))
    show(op, T0.isoformat())
    check('a job already on the way cannot be grabbed', op.locator('.appt[data-drag="r1"]').count() == 0 and op.locator('.appt[data-id="r1"]').count() == 1)
    check('computer: no errors', not ERRS, ERRS[:3])

    # ---------- 4. who cannot ----------
    sc = ctx(b); sp = page(sc, 'saleh-pc'); sp.set_viewport_size({'width': 1300, 'height': 900}); login(sp, 'saleh@garage.test', pw['saleh'])
    show(sp, D2)
    check('a mechanic cannot move appointments (nothing to grab)', sp.locator('[data-drag]').count() == 0)
    pc = ctx(b, phone=True); pp = page(pc, 'owner-phone'); login(pp, 'hassan@garage.test', pw['hassan'])
    pp.evaluate("(d) => { const A = window.__garageApi; A.S.day = d; A.render(); }", D2); pp.wait_for_timeout(500)
    check('phone: nothing to drag (« Modifier » stays the way)', pp.locator('[data-drag]').count() == 0)
    b.close()
summary()
