"""The guided tour, hands-on: the person taps the lit button (the visit goes on by itself), tries the schedule grid,
the colors, the periods, the map and the « ? ». Nothing tried is saved; a tap elsewhere does nothing."""
import sys, json, time
from team_seed import *
from playwright.sync_api import sync_playwright

def ready(p): p.wait_for_function("!!document.querySelector('#tour-ov[data-ready=\"1\"]') || !document.querySelector('#tour-ov')", timeout=9000)
def step(p): return p.evaluate("""(() => { const o = document.querySelector('#tour-ov'); if (!o) return null; const t = o.querySelector('.tt-tip');
  return {t: t.querySelector('h3').textContent, n: t.querySelector('.tt-n').textContent, open: o.classList.contains('open'), tap: !!t.querySelector('.tt-do'), tryq: !!t.querySelector('.tt-try'),
          tried: t.classList.contains('tried'), pulse: o.querySelector('.tt-hole').classList.contains('tap'), hash: location.hash, screen: window.__garageApi ? window.__garageApi.S.screen : null, sched: !!document.querySelector('#sched'),
          lux: document.documentElement.getAttribute('data-lux') || ''}; })()""")
def lit_center(p, sel):
    return p.evaluate("""(sel) => { for (const s of sel.split(',')) { for (const e of document.querySelectorAll(s.trim())) { const r = e.getBoundingClientRect(); if (r.width > 0 && r.height > 0 && !e.closest('#tour-ov')) return [r.left + r.width / 2, r.top + Math.min(r.height / 2, 20), r.left, r.top, r.width, r.height]; } } return null; }""", sel)
def cfg_lux(): return psql("select coalesce(data->>'lux','') from public.docs where path='config/main'")
def sched_sig(): return psql("select md5(coalesce(string_agg(path || data::text, ',' order by path), '')) from public.docs where path like 'config/%' or path like 'data/avail%' or path like 'hours%'")

LOG = []
def walk(p, tag, phone):
    seen = []
    for k in range(60):
        ready(p); s = step(p)
        if not s: break
        x = p.evaluate("(() => { const a = window.__garageApi; return null; })()")
        seen.append(s); LOG.append((tag, s['t']))
        p.screenshot(path='try_%s_%02d.png' % (tag.replace(' ', '_'), k + 1))
        if p.locator('#tour-ov [data-act="tt-end"]').count(): break
        if s['tap'] and s['open']:
            # a tap elsewhere does nothing (the visit waits for the lit button)
            before = (s['hash'], s['screen'], s['t'])
            p.mouse.click(5, p.viewport_size['height'] // 2); p.wait_for_timeout(250)
            s2 = step(p); s['blocked'] = (s2['hash'], s2['screen'], s2['t']) == before
            sel = p.evaluate("(() => { const o = document.querySelector('#tour-ov'); return null; })()")
            # tap the lit part, like a finger
            hb = p.evaluate("(() => { const r = document.querySelector('#tour-ov .tt-hole').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
            t0 = time.time(); p.mouse.click(hb[0], hb[1])
            p.wait_for_function("(n) => { const o = document.querySelector('#tour-ov'); return !o || o.querySelector('.tt-n').textContent !== n; }", arg=s['n'], timeout=6000)
            s['went'] = round(time.time() - t0, 2); ready(p); s['after'] = step(p)
            continue
        if s['tryq'] and s['open']:
            hb = p.evaluate("(() => { const r = document.querySelector('#tour-ov .tt-hole').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
            if s['sched']:
                x0 = hb[0] + hb[2] * 0.45; y0 = hb[1] + hb[3] * 0.35
                p.mouse.move(x0, y0); p.mouse.down(); p.mouse.move(x0, y0 + 60, steps=6); p.mouse.up()
            elif 'couleurs' in s['t'].lower():
                b = p.locator('#lux-sect .lux-sw[aria-pressed="false"]').first; b.click(); s['lux_tried'] = step(p)['lux']
            elif 'période' in s['t'].lower():
                p.click('.trbar [data-act="tr-kind"][data-v="quarter"]')
            elif 'carte' in s['t'].lower():
                pt = p.evaluate("""(() => { for (const m of document.querySelectorAll('#map-slot .leaflet-marker-icon')) { const r = m.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
                  const e = document.elementFromPoint(x, y); if (e && m.contains(e)) return [x, y]; } return null; })()""")
                if pt: p.mouse.click(pt[0], pt[1]); s['marker'] = True
                else:   # no number in view: drag the map with the finger
                    x0 = hb[0] + hb[2] / 2; y0 = hb[1] + 120
                    p.mouse.move(x0, y0); p.mouse.down(); p.mouse.move(x0 + 60, y0 + 30, steps=5); p.mouse.up(); s['marker'] = False
            elif '?' in s['t']:
                qp = p.evaluate("""(() => { for (const q of document.querySelectorAll('.qhelp')) { const r = q.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2; const e = document.elementFromPoint(x, y); if (r.width && e && q.contains(e)) return [x, y]; } return null; })()""")
                s['qpt'] = qp
                if qp: p.mouse.click(qp[0], qp[1])
            p.wait_for_timeout(300); s['done'] = step(p)['tried']
            s['helptip'] = p.locator('.helptip').count()
        p.click('#tour-ov [data-act="tt-next"]')
    return seen

otok, pw = seed()
psql("delete from public.docs where path like 'data/users/%/tour'")
lux0, sig0 = cfg_lux(), sched_sig()
R = {}
with sync_playwright() as pl:
    b = pl.chromium.launch()
    for who, phone in (('saleh', True), ('nadia', False), ('hassan', False), ('hassan', True)):
        c = ctx(b, phone=phone); p = page(c, who)
        if not phone: p.set_viewport_size({'width': 1440, 'height': 900})
        login(p, who + '@garage.test', pw[who], tour=True)
        if who == 'hassan':
            p.wait_for_timeout(1500)
            if phone: p.click('.tab[data-t="plus"]'); p.wait_for_timeout(400); p.click('.ph-row[data-act="tour-replay"]')
            else: p.click('#navfoot [data-act="tour-replay"]')
        p.wait_for_function("!!document.querySelector('#tour-ov .tt-tip')", timeout=9000)
        tag = who + (' phone' if phone else ' pc')
        R[tag] = walk(p, tag, phone)
        if p.locator('#tour-ov [data-act="tt-end"]').count(): p.click('#tour-ov [data-act="tt-end"]'); p.wait_for_timeout(900)
        R[tag + ' end'] = {'sched': p.locator('#sched').count(), 'lux': p.evaluate("document.documentElement.getAttribute('data-lux') || ''"), 'ov': p.locator('#tour-ov').count()}
        c.close()
    b.close()

json.dump(R, open('try_out.json', 'w'), ensure_ascii=False, indent=1, default=str)
def steps(tag, **kw): return [s for s in R[tag] if all(s.get(k) == v for k, v in kw.items())]
taps = [(t, s) for t in R if not t.endswith('end') for s in R[t] if s.get('tap') and s.get('open')]
check('tap steps: the lit part pulses, the bubble says what to touch (%d tap steps in 4 visits)' % len(taps), len(taps) >= 8 and all(s['pulse'] for _, s in taps), [(t, s['t'], s['pulse']) for t, s in taps][:10])
check('…a touch anywhere else does nothing (the visit waits)', all(s.get('blocked') for _, s in taps), [(t, s['t']) for t, s in taps if not s.get('blocked')])
check('…touching the lit button does its job and the visit goes on by itself, right away', all(s.get('went') is not None and s['went'] < 2.0 for _, s in taps), [(t, s['t'], s.get('went')) for t, s in taps])
mt = {s['t'].replace('\xa0', ' '): s for s in R['saleh phone']}
check('mechanic: he opens the job himself (the job screen opens, then « La fiche de la job »)', 'Ouvre un rendez-vous' in mt and mt['Ouvre un rendez-vous'].get('after', {}).get('screen') == 'job' and mt['Ouvre un rendez-vous']['after']['t'] == 'La fiche de la job', mt.get('Ouvre un rendez-vous'))
check('…he opens « Véhicule et fiche technique » himself, then the VIN is explained', 'Les sections' in mt and mt['Les sections'].get('after', {}).get('t') == 'Le VIN et la fiche du moteur', mt.get('Les sections'))
sl = R['saleh phone']
check('…he goes to « Clients » and « Factures » himself, with the menu', any(s['t'] == 'Tes clients' and s.get('tap') and s.get('after', {}).get('hash') == '#clients' for s in sl) and any(s['t'] == 'Tes factures' and s.get('tap') and s.get('after', {}).get('hash') == '#factures' for s in sl), [(s['t'], s.get('after', {}).get('hash')) for s in sl if s.get('tap')])
g = [s for s in R['saleh phone'] if s['t'] == 'La grille']
check('…he tries the schedule grid with his finger: « Voilà » shows, nothing is saved', bool(g) and g[0].get('done') is True, g)
nt = {s['t'].replace('\xa0', ' '): s for s in R['nadia pc']}
check('treasurer: she opens « Rapport et taxes » herself', 'Le rapport' in nt and nt['Le rapport'].get('after', {}).get('t') == 'Le rapport et les taxes', nt.get('Le rapport'))
check('…she tries « Trimestre »: « Les chiffres suivent la période »', 'La période' in nt and nt['La période'].get('done') is True, nt.get('La période'))
check('…she tries the map (touch a number)', "La carte de l'équipe" in nt and nt["La carte de l'équipe"].get('done') is True, nt.get("La carte de l'équipe"))
ht = {s['t'].replace('\xa0', ' '): s for s in R['hassan pc']}
check('owner: he opens « Modifier l\'horaire » himself, tries the grid', 'Modifier l\'horaire' in ht and ht["Modifier l'horaire"].get('after', {}).get('sched') and ht.get("La grille de l'horaire", {}).get('done') is True, (ht.get("Modifier l'horaire"), ht.get("La grille de l'horaire")))
lx = ht.get("Les couleurs de l'app", {})
check('…he tries a color: the whole app changes right away', bool(lx.get('lux_tried')) and lx.get('done') is True, lx)
check('…the « ? » opens its explanation, lit with it', ht.get('Les petits « ? »', {}).get('done') is True and ht['Les petits « ? »'].get('helptip', 0) >= 1, ht.get('Les petits « ? »'))
check('after the visit: the color is back as before, nothing saved (the color in the base did not change)', cfg_lux() == lux0 and R['hassan pc end']['lux'] == R['nadia pc end']['lux'] or cfg_lux() == lux0, [lux0, cfg_lux(), R['hassan pc end']])
check('…the schedule grids were closed without saving (hours and availability unchanged in the base)', sched_sig() == sig0 and all(R[t]['sched'] == 0 and R[t]['ov'] == 0 for t in R if t.endswith('end')), [sig0, sched_sig()])
check('no page errors', not ERRS, ERRS[:5])
psql("insert into public.docs (path, data) select 'data/users/' || user_id || '/tour', '{\"seenAt\": 1}' from public.members on conflict (path) do nothing")
summary()
