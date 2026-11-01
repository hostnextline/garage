"""The guided tour: the light is the right size (never cut through a card, a row, the map or the agenda),
the words never cover it, nothing waits for a part that is not there, no empty frame at the end."""
import time
from team_seed import *
from tour_walk import center, do_try
from playwright.sync_api import sync_playwright

PROBE = """(() => {
  const ov = document.querySelector('#tour-ov'), h = ov.querySelector('.tt-hole'), t = ov.querySelector('.tt-tip');
  const hr = h.getBoundingClientRect(), tr = t.getBoundingClientRect(), H = innerHeight, W = innerWidth;
  const title = t.querySelector('h3').textContent, shut = h.classList.contains('shut');
  // the lit part: whatever the tour picked for this step
  let cut = [], whole = null;
  const bot = hr.bottom - 8;   // the part's edge inside the light (8 px of air around it)
  const edge = hr.bottom >= H - 40;   // the light goes to the bottom of the screen: the page just goes on below, nothing is cut
  if (!shut && hr.width > 4 && !edge){
    const cands = [...document.querySelectorAll('main .card, main tr, main .sect, main .row, main details, main fieldset, main label, #sched .sch-scroll, #map-slot, .cal')];
    cut = cands.filter(e => !(e.closest('details:not([open])') && !e.closest('summary'))).filter(e => { const r = e.getBoundingClientRect(); return r.height > 8 && r.height < H * .8 && r.left >= hr.left - 2 && r.right <= hr.right + 2 && r.top < bot - 3 && r.bottom > bot + 3 && r.top > hr.top + 12; })
               .map(e => e.tagName + '.' + e.className.toString().slice(0, 20));
  }
  const ms = document.querySelector('#map-slot'), cal = document.querySelector('.cal');
  const covers = el => { if (!el) return null; const r = el.getBoundingClientRect(); return hr.top <= Math.max(r.top, 0) + 12 && hr.bottom >= Math.min(r.bottom, H - 8) - 30; };
  const over = !(tr.bottom <= hr.top + 1 || tr.top >= hr.bottom - 1 || tr.right <= hr.left + 1 || tr.left >= hr.right - 1);
  return {title, kind: ov.dataset.kind, shut, hole:[hr.left, hr.top, hr.width, hr.height].map(Math.round), tip:[tr.left, tr.top, tr.right, tr.bottom].map(Math.round),
          inside: tr.top >= 0 && tr.bottom <= H && tr.left >= 0 && tr.right <= W, over, cut, map: covers(ms), cal: covers(cal),
          empty: shut && hr.width > 4, edge, H};
})()"""

def walk(p, tag):
    p.wait_for_function("!!document.querySelector('#tour-ov[data-ready=\"1\"]')", timeout=9000)
    out = []
    for k in range(90):
        p.wait_for_timeout(350)   # let the light follow anything still moving
        s = p.evaluate(PROBE); s['tag'] = tag; out.append(s)
        if p.locator('#tour-ov [data-act="tt-end"]').count(): break
        kind, part = p.evaluate("[document.querySelector('#tour-ov').dataset.kind, document.querySelector('#tour-ov').dataset.part]")
        if kind == 'try':
            try: s['did'] = do_try(p, {'part': part})
            except TypeError: s['did'] = None; s['covered'] = part   # the thing to try could not be touched (covered by the bubble?)
            p.wait_for_timeout(400); t_ = s['title']; s.update(p.evaluate(PROBE)); s['tag'] = tag   # (measured again: what was tried can open something)
        t0 = time.time(); n0 = p.evaluate("document.querySelector('#tour-ov .tt-n').textContent")
        if kind == 'tap':
            pt = center(p, part)   # the person touches the lit button
            if not pt:
                s['covered'] = part; p.screenshot(path='fit_covered_%s.png' % tag.replace(' ', '_'))
                print('COVERED', tag, s['title'], part, p.evaluate("(sel) => { const e = document.querySelector(sel.split(',')[0]); const r = e && e.getBoundingClientRect(); const t = document.querySelector('#tour-ov .tt-tip').getBoundingClientRect(); return [r && [r.left, r.top, r.right, r.bottom], [t.left, t.top, t.right, t.bottom], innerWidth, innerHeight]; }", part))
                break
            p.mouse.click(*pt)
        else: p.click('#tour-ov [data-act="tt-next"]')
        p.wait_for_function("(n) => { const t = document.querySelector('#tour-ov .tt-tip'); return t && t.querySelector('.tt-n').textContent !== n && !t.classList.contains('gone') && !t.classList.contains('fade'); }", arg=n0, timeout=9000)
        s['wait_next'] = round(time.time() - t0, 2)
        p.wait_for_function("!!document.querySelector('#tour-ov[data-ready=\"1\"]')", timeout=9000)
    return out

otok, pw = seed()
psql("delete from public.docs where path like 'data/users/%/tour'")
runs = []
with sync_playwright() as pl:
    b = pl.chromium.launch()
    for who, phone, size in (('nadia', False, (1720, 1283)), ('nadia', False, (2000, 1184)), ('hassan', False, (1720, 1283)), ('hassan', False, (1366, 768)), ('saleh', True, None), ('hassan', True, None)):
        c = ctx(b, phone=phone); p = page(c, who)
        if size: p.set_viewport_size({'width': size[0], 'height': size[1]})
        login(p, who + '@garage.test', pw[who], tour=True)
        if who == 'hassan':
            p.wait_for_timeout(2000)
            if phone: p.click('.tab[data-t="plus"]'); p.wait_for_timeout(400); p.click('.ph-row[data-act="tour-replay"]')
            else: p.click('#navfoot [data-act="tour-replay"]')
        tag = who + (' phone' if phone else ' %dx%d' % size)
        st = walk(p, tag); runs.append((tag, st))
        c.close()
    b.close()

allst = [s for _, st in runs for s in st]
def by(tag, title): return next((s for t, st in runs if t == tag for s in st if s['title'] == title), None)

check('the light never stops through the middle of a card, a row or a field (%d steps, 6 screens)' % len(allst),
      all(not s['cut'] for s in allst), [(s['tag'], s['title'], s['cut'][:2], s['hole'], s['H']) for s in allst if s['cut']][:8])
check('what the person is asked to try is never covered by the bubble', not [x for x in allst if x.get('covered')], [(x['tag'], x['title'], x.get('covered')) for x in allst if x.get('covered')])
check('the words always stay on the screen', all(s['inside'] for s in allst), [(s['tag'], s['title'], s['tip']) for s in allst if not s['inside']][:5])
r = by('nadia 1720x1283', 'Le rapport et les taxes')
check('treasurer, report: the light stops cleanly under a whole card, the words under it', bool(r) and not r['cut'] and not r['over'], r)
r = by('nadia 2000x1184', 'Le rapport et les taxes')
check('…on a wide screen: the words go BESIDE the report (nothing covered)', bool(r) and not r['over'] and (r['tip'][2] <= r['hole'][0] or r['tip'][0] >= r['hole'][0] + r['hole'][2]), r)
maps = [s for s in allst if s['title'] == "La carte de l'équipe" and s.get('kind') == 'try']   # (not the « touch Carte in the menu » step)
check('the map is always lit whole (never cut in two), on PC and phone', len(maps) >= 4 and all(s['map'] for s in maps), [(s['tag'], s['hole'], s['map']) for s in maps])
ag = [s for s in allst if s['title'] == "L'agenda" and s['cal'] is not None]
check('the agenda grid is lit whole', len(ag) >= 2 and all(s['cal'] for s in ag), [(s['tag'], s['hole'], s['cal']) for s in ag])
sg = [s for s in allst if s['title'] == "La grille de l'horaire" or s['title'] == 'La grille']
check('the schedule grid (glass window) is lit whole', len(sg) >= 2 and all(not s['cut'] for s in sg), [(s['tag'], s['hole']) for s in sg])
inv = by('saleh phone', 'La facture sur place')
check('mechanic, « La facture sur place »: the « Facture » section is lit (not an empty spot)', bool(inv) and not inv['shut'] and inv['hole'][3] > 30, inv)
waits = [(s['tag'], s['title'], s['wait_next']) for s in allst if 'wait_next' in s]
slow = [w for w in waits if w[2] > (1.9 if 'grille' in w[1].lower() else 1.75)]
check('no wait after « Suivant »: every next explanation shows in under 1.75 s, even when a new screen loads (1.9 s when the schedule window slides in) (the slowest: %.2f s)' % max(w[2] for w in waits), not slow, slow)
q = [w for w in waits if w[1] == 'Les petits « ? »'] if False else [s for s in allst if s['title'] == 'Les petits « ? »']
prev = [w for t, st in runs for i, s in enumerate(st) if i + 1 < len(st) and st[i + 1]['title'] == 'Les petits « ? »' for w in [s.get('wait_next')]]
check('…including going to « Les petits ? » (was about 3 s)', all(w is not None and w < 1.0 for w in prev), prev)
check('no empty frame on the screen when a step has nothing to light (end of the visit)', all(not s['empty'] for s in allst), [(s['tag'], s['title'], s['hole']) for s in allst if s['empty']])
check('no page errors', not ERRS, ERRS[:5])
psql("insert into public.docs (path, data) select 'data/users/' || user_id || '/tour', '{\"seenAt\": 1}' from public.members on conflict (path) do nothing")
summary()
