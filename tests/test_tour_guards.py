"""The guided visit's safety rails: « ‹ Retour » out of the expense window closes it; a lit button that vanishes leaves a « Suivant »;
trying never leaves the screen; the phone's day swipe waits until the visit is over; the scroll lock of an open window holds."""
import time
from team_seed import *
from tour_walk import STEP, ready, center, do_try
from playwright.sync_api import sync_playwright

def advance_to(p, title, limit=60):
    """go through the visit like a person until the step with that title"""
    for _ in range(limit):
        ready(p); time.sleep(0.15); s = p.evaluate(STEP)
        if s['t'] == title: return s
        n0 = s['n']
        if s['kind'] == 'tap':
            pt = center(p, s['part']); p.mouse.click(*pt)
        else:
            if s['kind'] == 'try': do_try(p, s); time.sleep(0.3)
            p.click('#tour-ov [data-act="tt-next"]')
        p.wait_for_function("(n) => { const o = document.querySelector('#tour-ov'); return !o || o.querySelector('.tt-n').textContent !== n; }", arg=n0, timeout=8000)
    return None

otok, pw = seed()
with sync_playwright() as pl:
    b = pl.chromium.launch()
    # ---------- 1. « ‹ Retour » from inside the expense window ----------
    psql("delete from public.docs where path like 'data/users/%/tour'")
    c = ctx(b, phone=True); p = page(c, 'nadia'); login(p, 'nadia@garage.test', pw['nadia'], tour=True)
    p.wait_for_function("!!document.querySelector('#tour-ov .tt-tip')", timeout=9000)
    s = advance_to(p, 'Scanner le reçu')
    check('the visit reaches « Scanner le reçu » inside the expense window', bool(s) and p.evaluate("!!window.__garageApi.S.sheet"), s and s['t'])
    n0 = s['n']; p.click('#tour-ov [data-act="tt-prev"]')
    p.wait_for_function("(n) => document.querySelector('#tour-ov .tt-n').textContent !== n", arg=n0, timeout=8000); ready(p); time.sleep(0.3)
    s = p.evaluate(STEP)
    vis = p.evaluate("""(() => { const b = document.querySelector('[data-act="exp-new"]'); if (!b) return false; const r = b.getBoundingClientRect(); const h = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!h && (b.contains(h) || h.closest('#tour-ov .tt-hole') !== null || h === b); })()""")
    check('« ‹ Retour » to « Ajouter une dépense »: the window closes by itself, the « + Dépense » button is lit and can be touched again',
          s['t'] == 'Ajouter une dépense' and s['kind'] == 'tap' and not p.evaluate("!!window.__garageApi.S.sheet") and p.locator('#sheet:not([hidden])').count() == 0, s)
    pt = center(p, s['part']); p.mouse.click(*pt)
    p.wait_for_function("(n) => document.querySelector('#tour-ov .tt-n').textContent !== n", arg=s['n'], timeout=8000); ready(p); s = p.evaluate(STEP)
    check('…touching it again opens the window and the visit goes on (« Scanner le reçu »)', s['t'] == 'Scanner le reçu' and p.evaluate("!!window.__garageApi.S.sheet"), s['t'])
    # ---------- 2. trying never leaves the screen ----------
    s = advance_to(p, 'La période')
    check('« La période »: something to try (the period bar)', s and s['kind'] == 'try' and '.trbar' in s['part'], s)
    h0 = p.evaluate("location.hash")
    # a link to another screen inside the part being tried (like « Ouvrir » in a map bubble)
    p.evaluate("""(() => { const a = document.createElement('a'); a.href = '#clients'; a.id = 'zz-link'; a.textContent = 'Clients'; a.className = 'chip'; document.querySelector('.trbar').appendChild(a); })()""")
    p.wait_for_timeout(400); pt = center(p, '#zz-link'); p.mouse.click(*pt); p.wait_for_timeout(600)
    check('a link inside the part being tried does not take him away (same screen, the visit is still on this step, and it counts as tried)',
          p.evaluate("location.hash") == h0 and p.evaluate(STEP)['t'] == 'La période' and p.evaluate(STEP)['tried'], [h0, p.evaluate("location.hash"), p.evaluate(STEP)['t']])
    p.keyboard.press('Escape'); p.wait_for_timeout(700)
    c.close()
    # ---------- 3. a lit button that vanishes: the step explains with « Suivant » ----------
    psql("delete from public.docs where path like 'data/users/%/tour'")
    c = ctx(b, phone=True); p = page(c, 'nadia2'); login(p, 'nadia@garage.test', pw['nadia'], tour=True)
    p.wait_for_function("!!document.querySelector('#tour-ov .tt-tip')", timeout=9000)
    s = advance_to(p, 'Ajouter une dépense')
    check('« Ajouter une dépense »: a touch step, no « Suivant »', s and s['kind'] == 'tap' and not s['next'], s)
    p.evaluate("""document.querySelectorAll('[data-act="exp-new"]').forEach(e => e.remove())""")
    ok = wait_for(p, "!!document.querySelector('#tour-ov [data-act=\"tt-next\"]')", 3000); s2 = p.evaluate(STEP)
    check('…the button disappears (the screen changed by itself): within a moment the step has « Suivant ›» and nothing pulses (no dead end)', ok and s2['kind'] == 'read' and not s2['pulse'], s2)
    p.keyboard.press('Escape'); p.wait_for_timeout(700)
    c.close()
    # ---------- 4. the day swipe on the phone waits until the visit is over ----------
    psql("delete from public.docs where path like 'data/users/%/tour'")
    c = ctx(b, phone=True); p = page(c, 'saleh'); login(p, 'saleh@garage.test', pw['saleh'], tour=True)
    p.wait_for_function("!!document.querySelector('#tour-ov .tt-tip')", timeout=9000); ready(p)
    swipe = """(() => { const S = window.__garageApi.S, d0 = S.day; const el = document.querySelector('#main') || document.body;
      const mk = (x, y) => new Touch({identifier: 1, target: el, clientX: x, clientY: y});
      el.dispatchEvent(new TouchEvent('touchstart', {touches: [mk(300, 400)], changedTouches: [mk(300, 400)], bubbles: true}));
      el.dispatchEvent(new TouchEvent('touchend', {touches: [], changedTouches: [mk(150, 405)], bubbles: true}));
      return [d0 || '', S.day || '']; })()"""
    p.evaluate("location.hash = 'jour'"); p.wait_for_timeout(400)
    d = p.evaluate(swipe)
    check('during the visit, a swipe on « Ma journée » does not change the day (the visit stays in step)', d[0] == d[1], d)
    p.keyboard.press('Escape'); p.wait_for_timeout(1200)
    if p.evaluate("!!window.__garageApi.S.sheet"): p.click('#sheet .sheet-head [data-act="sheet-close"]'); p.wait_for_timeout(400)   # (the « add the app to your screen » help that opens after a visit)
    d = p.evaluate(swipe)
    check('…after the visit, the same swipe goes to the next day as always', d[0] != d[1], d)
    c.close()
    # ---------- 5. an open window keeps the page from scrolling under it, even on a « try » step ----------
    psql("delete from public.docs where path like 'data/users/%/tour'")
    c = ctx(b, phone=True); p = page(c, 'nadia3'); login(p, 'nadia@garage.test', pw['nadia'], tour=True)
    p.wait_for_function("!!document.querySelector('#tour-ov .tt-tip')", timeout=9000)
    s = advance_to(p, 'Le montant')
    ov = p.evaluate("getComputedStyle(document.body).overflow")
    check('« Le montant » (a try step inside the expense window): the page under the window does not scroll (body overflow hidden)', ov == 'hidden' and 'tt-free' in p.evaluate("document.body.className"), [ov, p.evaluate("document.body.className")])
    c.close()
    b.close()
psql("delete from public.docs where path like 'data/users/%/tour'")
check('no page errors', not ERRS, ERRS[:5])
summary()
