"""Walk a guided tour like a person: read, touch the lit button when asked, try what is offered. Used by the tour tests."""
import time

STEP = r"""(() => { const o = document.querySelector('#tour-ov'); if (!o) return null; const t = o.querySelector('.tt-tip'), a = window.__garageApi, S = a ? a.S : {};
  const nb = s => (s || '').replace(/ /g, ' ');
  return {t: nb(t.querySelector('h3').textContent), n: t.querySelector('.tt-n').textContent, ch: nb(t.querySelector('.tt-ch').textContent).replace(/ · \d+\/\d+$/, ''),
    kind: o.dataset.kind, part: o.dataset.part || '', open: o.classList.contains('open'), tried: t.classList.contains('tried'), pulse: o.querySelector('.tt-hole').classList.contains('tap'),
    next: !!t.querySelector('[data-act="tt-next"]'), end: !!t.querySelector('[data-act="tt-end"]'), words: nb(t.innerText),
    where: [location.hash, S.screen || '', document.querySelector('#sched') ? 'sched' : '', S.sheet ? 'sheet' : '', S.tab === 'tresor' ? (S.trView || '') : '', S.tab === 'reglages' ? String(S.setSec == null ? '' : S.setSec) : ''].join('|')}; })()"""
STATE = "(() => { const S = window.__garageApi.S; return {view: S.view, invFilter: S.invFilter, cq: S.cq, trView: S.trView, day: S.day, mech: S.mech, lux: document.documentElement.getAttribute('data-lux') || ''}; })()"

def ready(p, ms=9000):
    p.wait_for_function("!!document.querySelector('#tour-ov[data-ready=\"1\"]') || !document.querySelector('#tour-ov')", timeout=ms)

def center(p, sel):
    """the middle of the first visible element of a selector list, not covered by the bubble"""
    return p.evaluate("""(sel) => { const tip = document.querySelector('#tour-ov .tt-tip').getBoundingClientRect();
      for (const s of sel.split(',')) for (const e of document.querySelectorAll(s.trim())) { const r = e.getBoundingClientRect();
        if (!(r.width > 0 && r.height > 0) || e.closest('#tour-ov')) continue;
        const pts = [[r.left + r.width / 2, r.top + r.height / 2], [r.left + 12, r.top + r.height / 2], [r.right - 12, r.top + r.height / 2], [r.left + r.width / 2, r.top + 10]];
        for (const [x, y] of pts) { if (x >= tip.left && x <= tip.right && y >= tip.top && y <= tip.bottom) continue; const h = document.elementFromPoint(x, y); if (h && !(h.closest('.qhelp') && !s.includes('qhelp')) && (e.contains(h) || h.closest(s.trim()))) return [x, y]; } }
      return null; }""", sel)

def do_try(p, s):
    """try what the step offers, like a finger would"""
    part = s['part']
    if 'sch-scroll' in part:
        r = p.evaluate("(() => { const r = document.querySelector('#sched .sch-scroll').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
        x0 = r[0] + r[2] * 0.55; y0 = r[1] + min(r[3] * 0.35, 160)
        p.mouse.move(x0, y0); p.mouse.down(); p.mouse.move(x0, y0 + 50, steps=6); p.mouse.up(); return 'drag grid'
    if 'lux-sect' in part:
        pt = center(p, '#lux-sect .lux-sw[aria-pressed="false"]'); p.mouse.click(*pt); return 'color'
    if 'trbar' in part:
        pt = center(p, '.trbar [data-act="tr-kind"][data-v="quarter"]'); p.mouse.click(*pt); return 'quarter'
    if 'map-slot' in part:
        pt = center(p, '#map-slot .leaflet-marker-icon')
        if pt: p.mouse.click(*pt); return 'marker'
        r = p.evaluate("(() => { const r = document.querySelector('#map-slot').getBoundingClientRect(); return [r.left, r.top, r.width]; })()")
        p.mouse.move(r[0] + r[2] / 2, r[1] + 80); p.mouse.down(); p.mouse.move(r[0] + r[2] / 2 + 50, r[1] + 110, steps=5); p.mouse.up(); return 'drag map'
    if 'qhelp' in part:
        pt = center(p, part); p.mouse.click(*pt); return '?'
    if 'cl-q' in part:
        pt = center(p, '#cl-q'); p.mouse.click(*pt); p.keyboard.type('mar', delay=40); return 'search'
    if 'Filtrer' in part:
        pt = center(p, '[aria-label="Filtrer"] [data-v="paid"]'); p.mouse.click(*pt); return 'filter'
    if 'x-total' in part:
        pt = center(p, '#x-total'); p.mouse.click(*pt); p.keyboard.type('57,49', delay=40)
        p.keyboard.press('Enter'); time.sleep(0.2)   # « Entrée » would save the expense: during the visit it must not
        s['enter'] = p.evaluate("!!document.getElementById('expform') && !!window.__garageApi.S.sheet"); return 'amount'   # (the window stays open: nothing sent)
    if 'rbox' in part:
        pt = center(p, '#eq-new label[for$="-r-tresorier"]'); p.mouse.click(*pt); return 'role'
    if 'Affichage' in part:
        pt = center(p, '[aria-label="Affichage"] [data-v="week"]'); p.mouse.click(*pt); return 'week'
    if 'Mécano' in part:
        pt = center(p, '#main [aria-label="Mécano"] .chip:not(.on)'); p.mouse.click(*pt); return 'mechanic'
    if 'trucks' in part:
        pt = center(p, '.chips.trucks .chip:not(.on)'); p.mouse.click(*pt); return 'truck'
    if 'ph-day' in part:
        pt = center(p, part); p.mouse.click(*pt); return 'next day'
    if '.days' in part:
        pt = center(p, '#top .days .day:not(.on)'); p.mouse.click(*pt); return 'other day'
    return None

def walk(p, shots=None, record=None):
    """the whole visit from the current step to « C'est tout ! ». Returns the steps seen, each with what happened."""
    out = []
    for k in range(90):
        ready(p); time.sleep(0.15)
        s = p.evaluate(STEP)
        if not s: break
        out.append(s)
        if shots: p.screenshot(path='%s_%02d.png' % (shots, len(out)))
        if s['end']: break
        if s['kind'] == 'tap':
            # a touch elsewhere does nothing: the visit waits for the lit button
            before = s['where']; n0 = s['n']
            p.mouse.click(4, p.viewport_size['height'] // 3); time.sleep(0.25)
            s2 = p.evaluate(STEP); s['blocked'] = bool(s2) and s2['n'] == n0 and s2['where'] == before
            pt = center(p, s['part']); s['pt'] = pt
            t0 = time.time()
            if pt: p.mouse.click(*pt)
            try:
                p.wait_for_function("(n) => { const o = document.querySelector('#tour-ov'); return !o || o.querySelector('.tt-n').textContent !== n; }", arg=n0, timeout=6000)
                s['went'] = round(time.time() - t0, 2)
            except Exception:
                s['went'] = None; break
            continue
        if s['kind'] == 'try':
            s['did'] = do_try(p, s); time.sleep(0.45)
            s['tried_after'] = p.evaluate("document.querySelector('#tour-ov .tt-tip').classList.contains('tried')")
            s['helptip'] = p.locator('.helptip').count()
            if record: record(p, s)
        n0 = s['n']
        p.click('#tour-ov [data-act="tt-next"]')
        p.wait_for_function("(n) => { const o = document.querySelector('#tour-ov'); return !o || o.querySelector('.tt-n').textContent !== n; }", arg=n0, timeout=8000)
    return out

def autonav(steps):
    """screen changes that did NOT come from the person's touch (must be none)"""
    bad = []
    for a, b in zip(steps, steps[1:]):
        if a['where'] != b['where'] and a['kind'] != 'tap':
            bad.append((a['t'], a['where'], '→', b['t'], b['where']))
    return bad
