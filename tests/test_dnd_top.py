"""Glisser-déposer : le rendez-vous se pose là où est son HAUT (comme on le voit en le glissant), pas là où est la souris
(copie locale de Supabase, vraies écritures, vraie souris) :
1. semaine (réservation à l'heure) : pris au milieu, son haut sur 11 h → les cases de 11 h à 12 h s'allument, « Après : 11 h » ;
2. jour : pris près du haut → là où est la souris ; la souris par-dessus un autre rendez-vous, ça se pose quand même ;
3. par blocs : le bloc entier s'allume."""
import json, os, time, datetime
from team_seed import *
from playwright.sync_api import sync_playwright
T0 = datetime.date.today()
def wd(start):
    d = T0 + datetime.timedelta(days=start)
    while d.weekday() >= 5: d += datetime.timedelta(days=1)
    return d
D = wd(2).isoformat()
def job(i): return doc('jobs/' + i) or {}
otok, pw = seed()
c = doc('config/main'); c['bookMode'] = 'hours'; c['homePostal'] = 'H4P 2B5'
c['hours'] = {str(x): {'open': True, 'start': '08:00', 'end': '20:00'} for x in range(7)}
c['trucks'] = [{'id': 'c1', 'name': 'Camion 1', 'on': True, 'mech': 'Saleh'}]
doc_set(otok, 'config/main', c)
cl1 = doc('clients/c1')
snap = {'id': 'c1', 'firstName': 'Marie', 'lastName': 'Tremblay', 'name': 'Marie Tremblay', 'phone': cl1['phone'], 'address': cl1['address'], 'postal': cl1['postal'], 'geo': cl1['geo']}
def mk(i, t, extra=None):
    d = {'date': D, 'time': t, 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c1', 'client': snap, 'services': ['Inspection multipoints'], 'status': 'planifie', 'createdAt': 1}
    d.update(extra or {}); doc_set(otok, 'jobs/' + i, d)
mk('a1', '12:00'); mk('a2', '14:30')
def show(p, d, view):
    p.goto(BASE + '#agenda'); p.wait_for_timeout(400)
    p.evaluate("([d, v]) => { const A = window.__garageApi, S = A.S; S.day = d; S.view = v; S.mech = ''; S.screen = null; A.render(); }", [d, view]); p.wait_for_timeout(700)
def slot_sel(view, t): return ('.slot[data-d="%s"][data-t="%s"]' % (D, t)) if view == 'week' else ('.col[data-col="c1"] .slot[data-t="%s"]' % t)
UNDER = ['']
def drag(p, card, grab, view, top_t, hold_check=None):
    """grab the card « grab » px under its top, move so that its top sits on the slot top_t, then let go"""
    a = p.locator(card); a.evaluate("e => e.scrollIntoView({block:'center'})"); p.wait_for_timeout(300); ba = a.bounding_box()
    x = ba['x'] + ba['width'] / 2
    p.mouse.move(x, ba['y'] + grab); p.mouse.down(); p.mouse.move(x + 4, ba['y'] + grab + 12, steps=4)
    sb = p.locator(slot_sel(view, top_t)).bounding_box()
    p.mouse.move(x, sb['y'] + grab + 3, steps=10); p.wait_for_timeout(150)
    p.mouse.move(x, sb['y'] + grab + 4, steps=2); p.wait_for_timeout(150)
    lit = p.evaluate("[...document.querySelectorAll('.slot.drop-on')].map(e => e.dataset.t)")
    UNDER[0] = p.evaluate("([x, y]) => { const e = document.elementFromPoint(x, y), a = e && e.closest('.appt'); return a ? a.dataset.id : ''; }", [x, sb['y'] + grab + 4])
    p.mouse.up(); p.wait_for_timeout(600)
    return lit
with sync_playwright() as pl:
    b = pl.chromium.launch()
    oc = ctx(b); op = page(oc, 'owner'); op.set_viewport_size({'width': 1300, 'height': 1400}); login(op, 'hassan@garage.test', pw['hassan'])
    # ---------- 1. week view, grabbed in the middle ----------
    show(op, D, 'week')
    sm = op.evaluate("window.__garageApi && window.__garageApi.S ? null : null")
    h = op.locator(slot_sel('week', '11:00')).bounding_box()['height']; per = round(op.evaluate("(()=>{const s=[...document.querySelectorAll('.slot[data-d]')].slice(0,2).map(e=>e.dataset.t);const m=t=>+t.split(':')[0]*60+ +t.split(':')[1];return m(s[1])-m(s[0]);})()"))
    span = 60 // per
    lit = drag(op, '.appt[data-drag="a1"]', 40, 'week', '11:00')
    check('week view, grabbed 40 px down: while dragging, the hour from 11 h is lit (%d cases), not the case under the mouse' % span, len(lit) == span and lit[0] == '11:00', lit)
    op.wait_for_selector('#sheet [data-act="drop-yes"]', timeout=5000)
    sh = txt(op, '#sheet')
    check('…let go: « Après » says 11 h (where its top was), not 11 h 40', 'Après' in sh and '11 h ·' in sh.split('Après')[1] and '11 h 40' not in sh, sh[:200])
    op.screenshot(path=os.path.join(SC, 'dnd_top_confirm.png'))
    op.click('#sheet [data-act="drop-yes"]'); op.wait_for_timeout(1500)
    check('…saved at 11:00', job('a1').get('time') == '11:00', job('a1').get('time'))
    # ---------- 2. day view, grabbed near the top; the mouse over another appointment ----------
    show(op, D, 'grid')
    lit = drag(op, '.appt[data-drag="a1"]', 6, 'grid', '12:30')
    check('day view, grabbed near its top: lands at 12 h 30, the hour from there lit', lit[:1] == ['12:30'] and len(lit) == span, lit)
    op.wait_for_selector('#sheet [data-act="drop-yes"]', timeout=5000)
    check('…« Après » 12 h 30', '12 h 30' in txt(op, '#sheet').split('Après')[1], txt(op, '#sheet')[:200])
    op.click('#sheet [data-act="drop-no"]'); op.wait_for_timeout(500)
    show(op, D, 'grid')
    # grab low on the card; its top on 13 h 50 → the mouse is over the 14 h 30 appointment (a2)
    hb = op.locator('.appt[data-drag="a1"]').bounding_box()['height']; g = int(hb * 0.75)
    lit = drag(op, '.appt[data-drag="a1"]', g, 'grid', '13:50')
    check('the mouse over another appointment (the 14 h 30 one): it still drops, top at 13 h 50', lit[:1] == ['13:50'] and UNDER[0] == 'a2', (lit[:1], UNDER[0]))
    op.wait_for_selector('#sheet [data-act="drop-yes"]', timeout=5000)
    op.click('#sheet [data-act="drop-yes"]'); op.wait_for_timeout(1500)
    check('…saved at 13:50', job('a1').get('time') == '13:50', job('a1').get('time'))
    check('no errors', not ERRS, ERRS[:3])
    # ---------- 3. by blocks: the whole block is lit ----------
    c2 = doc('config/main'); c2.pop('bookMode', None); doc_set(otok, 'config/main', c2)
    mk('b1', '08:00', {'block': 'am'})
    show(op, D, 'grid'); op.wait_for_timeout(800)
    lit = drag(op, '.appt[data-drag="b1"]', 10, 'grid', '13:00')
    check('by blocks: dragging into the afternoon lights the whole block (12 h to 16 h)', bool(lit) and lit[0] == '12:00' and lit[-1] < '16:00' and len(lit) == 240 // per, (lit[:1], lit[-1:], len(lit)))
    op.wait_for_selector('#sheet [data-act="drop-yes"]', timeout=5000)
    check('…« Après » : Après-midi (12 h à 16 h)', 'Après-midi (12 h à 16 h)' in txt(op, '#sheet'), txt(op, '#sheet')[:200])
    op.click('#sheet [data-act="drop-no"]')
    check('no errors (blocks)', not ERRS, ERRS[:3])
    b.close()
summary()
