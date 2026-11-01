"""Layout scan: every screen x role x (phone, small PC, big PC). Anything wider than the screen, text cut off,
page errors, time to show each screen. Screenshots in scan/. Prints a table and writes scan/out.json."""
import json, os, time
from team_seed import *
from playwright.sync_api import sync_playwright
os.makedirs('scan', exist_ok=True)
PROBE = r"""() => {
  const W = innerWidth, out = {hscroll: document.documentElement.scrollWidth > W + 1, wide: [], cut: []};
  const vis = e => { const r = e.getBoundingClientRect(); if (!(r.width > 0 && r.height > 0)) return false; const s = getComputedStyle(e); return s.visibility !== 'hidden' && s.display !== 'none'; };
  const inScroller = e => { for (let x = e.parentElement; x && x !== document.body; x = x.parentElement) { const s = getComputedStyle(x); if (/(auto|scroll|hidden|clip)/.test(s.overflowX) || x.classList.contains('leaflet-container')) return true; } return false; };
  const scope = [document.getElementById('top'), document.getElementById('main'), document.querySelector('#sheet:not([hidden])'), document.getElementById('tabbar')].filter(Boolean);
  scope.forEach(sc => sc.querySelectorAll('*').forEach(e => {
    if (!vis(e) || e.closest('.leaflet-container') || e.closest('[hidden]') || e.closest('details:not([open])') && !e.closest('summary')) return;
    const r = e.getBoundingClientRect();
    if ((r.right > W + 1 || r.left < -1) && !inScroller(e)) out.wide.push((e.tagName + '.' + String(e.className).split(' ')[0] + ' ' + (e.innerText || '').trim().slice(0, 30)).replace(/\s+/g, ' ') + ' [' + Math.round(r.left) + '→' + Math.round(r.right) + ']');
    const s = getComputedStyle(e);
    if (e.children.length === 0 && (e.innerText || '').trim() && /hidden|clip/.test(s.overflowX) && s.textOverflow !== 'ellipsis' && e.scrollWidth > e.clientWidth + 2 && !/INPUT|SELECT|TEXTAREA|svg/i.test(e.tagName))
      out.cut.push((e.tagName + '.' + String(e.className).split(' ')[0] + ' « ' + e.innerText.trim().slice(0, 30) + ' »').replace(/\s+/g, ' '));
  }));
  out.wide = out.wide.slice(0, 6); out.cut = out.cut.slice(0, 6);
  return out;
}"""
SIZES = {'phone': None, 'pc1024': (1024, 768), 'pc1440': (1440, 900)}
ROLES = (('hassan', 'owner'), ('lina', 'bureau'), ('nadia', 'tresorier'), ('saleh', 'mecano'))
otok, pw = seed()
R = []
with sync_playwright() as pl:
    b = pl.chromium.launch()
    for who, role in ROLES:
        for size, wh in SIZES.items():
            c = ctx(b, phone=size == 'phone'); p = page(c, who + '/' + size)
            if wh: p.set_viewport_size({'width': wh[0], 'height': wh[1]})
            n0 = len(ERRS)
            login(p, who + '@garage.test', pw[who]); p.wait_for_timeout(1200)
            tabs = p.evaluate("[...document.querySelectorAll('#tabbar .tab[data-t]')].filter(t => !t.hidden).map(t => t.dataset.t)")
            if size == 'phone':   # the screens behind « Plus » on the phone
                tabs += [t for t in ('carte', 'dispos', 'stock', 'tresor', 'equipe', 'reglages', 'factures', 'clients', 'agenda') if t not in tabs]
            screens = [('tab', t) for t in tabs if t != 'plus'] + [('job', None), ('invoice', None)]
            for kind, t in screens:
                t0 = time.time()
                if kind == 'tab':
                    ok = p.evaluate("(t) => { const a = window.__garageApi; location.hash = t; return true; }", t)
                elif kind == 'job':
                    p.evaluate("location.hash = 'jour'" if role == 'mecano' else "location.hash = 'agenda'"); p.wait_for_timeout(500)
                    ok = p.evaluate("(() => { const b = document.querySelector('#main [data-act=\"open\"]'); if (b) { b.click(); return true; } return false; })()")
                else:
                    ok = p.evaluate("(() => { const b = document.querySelector('#main [data-act=\"invoice\"]'); if (!b) return false; const d = b.closest('details'); if (d) d.open = true; b.click(); return true; })()")
                if not ok: continue
                p.wait_for_timeout(700)
                ms = round((time.time() - t0) * 1000) - 700
                hs = p.evaluate('location.hash'); name = '%s_%s_%s' % (role, size, t or kind)
                m = p.evaluate(PROBE); m.update({'who': role, 'size': size, 'screen': t or kind, 'hash': hs})
                p.evaluate("window.scrollTo(0,0)"); p.screenshot(path='scan/%s.png' % name, full_page=False)
                R.append(m)
                if kind == 'invoice':   # leave the invoice editor without saving
                    p.evaluate("(() => { const b = document.querySelector('[data-act=\"back-inv\"], [data-act=\"inv-back\"], .backrow button'); if (b) b.click(); })()"); p.wait_for_timeout(400)
            R.append({'who': role, 'size': size, 'screen': '(errors)', 'errs': ERRS[n0:]})
            c.close()
    b.close()
json.dump(R, open('scan/out.json', 'w'), ensure_ascii=False, indent=1)
bad = [r for r in R if r.get('hscroll') or r.get('wide') or r.get('cut') or r.get('errs')]
print('screens checked:', len([r for r in R if r['screen'] != '(errors)']), '| with a problem:', len(bad))
for r in bad: print(' ', r['who'], r['size'], r['screen'], 'HSCROLL' if r.get('hscroll') else '', r.get('wide') or '', r.get('cut') or '', r.get('errs') or '')
