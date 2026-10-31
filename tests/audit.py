# Scan « comme un débutant » : chaque écran, chaque rôle, téléphone et ordinateur.
import json, os, re
from team_seed import *
from playwright.sync_api import sync_playwright
OUT = 'audit'
METRICS = r"""() => {
  const vis = e => { const r = e.getBoundingClientRect(); if (!(r.width > 0 && r.height > 0)) return false; for (let x = e; x; x = x.parentElement) { const s = getComputedStyle(x); if (s.display === 'none' || s.visibility === 'hidden' || x.hidden) return false; } return true; };
  const sheet = document.querySelector('#sheet:not([hidden]) .sheet');
  const scope = sheet ? [sheet] : [document.getElementById('top'), document.getElementById('main')].filter(Boolean);
  const btns = [], inputs = [], small = []; let text = '';
  const lab = i => { const l = i.id && document.querySelector('label[for="' + i.id + '"]'); return (l ? l.innerText : (i.getAttribute('aria-label') || i.placeholder || i.name || i.type)).trim().replace(/\s+/g, ' ').slice(0, 50); };
  scope.forEach(sc => {
    sc.querySelectorAll('button, a[href], [role=button], summary, input[type=checkbox], input[type=radio]').forEach(b => {
      if (!vis(b)) return; const t = (b.innerText || b.getAttribute('aria-label') || b.value || '').trim().replace(/\s+/g, ' ').slice(0, 45); btns.push(t);
      const r = b.getBoundingClientRect(); if (r.height < 40 && b.type !== 'checkbox' && b.type !== 'radio') small.push(t + ' (' + Math.round(r.height) + 'px)'); });
    sc.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea').forEach(i => { if (vis(i)) inputs.push(lab(i)); });
    text += sc.innerText + '\n';
  });
  const scr = sheet ? (sheet.querySelector('.sheet-body') || sheet) : document.documentElement;
  return { sheet: !!sheet, btns, inputs, small, words: text.split(/\s+/).filter(Boolean).length, screens: Math.round(scr.scrollHeight / window.innerHeight * 10) / 10, text };
}"""
JARGON = ['VIN', 'OSRM', 'TomTom', 'OpenStreetMap', 'Photon', 'GoHighLevel', 'GHL', 'Location ID', 'API', 'Stripe', 'webhook', 'intégration', 'synchro', 'cache', 'unité', 'token', 'sk_live', 'pit-', 'JSON', 'serveur', 'base de données', 'navigateur', 'stockage', 'Contributeur', 'lecture seule', 'géolocalisation', 'préfixe', 'numérotation', 'viscosité', 'cylindrée', 'identifiant', 'ID ', 'clé', 'lien secret', 'brouillon', 'finaliser', 'Finaliser', 'statut', 'no-show', 'No-show', 'trésorerie', 'version complète', 'Version complète', 'service worker', 'hors-ligne', 'PDF', 'Excel', 'code de mise en route', 'connecteur', 'estimation', 'Estimation']
results = []
def snap(p, role, dev, name):
    p.wait_for_timeout(500)
    m = p.evaluate(METRICS)
    key = f'{role}_{dev}_{name}'
    p.screenshot(path=f'{OUT}/{key}.png', full_page=not m['sheet'])
    open(f'{OUT}/txt/{key}.txt', 'w', encoding='utf8').write(m.pop('text'))
    txt = open(f'{OUT}/txt/{key}.txt', encoding='utf8').read()
    m['jargon'] = sorted({j.strip() for j in JARGON if j in txt})
    m.update(role=role, dev=dev, screen=name, nbtn=len(m['btns']), ninp=len(m['inputs']))
    results.append(m); print(f"{key:40s} boutons={m['nbtn']:3d} champs={m['ninp']:3d} mots={m['words']:4d} écrans={m['screens']:4.1f} jargon={','.join(m['jargon'])}")
def close_sheet(p):
    if p.locator('#sheet:not([hidden])').count(): p.keyboard.press('Escape'); p.wait_for_timeout(300)
    if p.locator('#sheet:not([hidden])').count():
        b = p.locator('#sheet [data-act="sheet-close"]').last
        try: b.click(timeout=2000)
        except Exception: pass
        p.wait_for_timeout(300)
def go(p, h): p.evaluate("location.hash = '%s'" % h); p.wait_for_timeout(700)
def try_click(p, sel):
    l = p.locator(sel)
    for i in range(l.count()):
        if l.nth(i).is_visible():
            l.nth(i).click(); p.wait_for_timeout(600); return True
    return False
otok, pw = seed()
with sync_playwright() as pl:
    b = pl.chromium.launch()
    plan = [('proprio', 'hassan@garage.test', pw['hassan']), ('mecano', 'saleh@garage.test', pw['saleh']), ('bureau', 'lina@garage.test', pw['lina']), ('tresorier', 'nadia@garage.test', pw['nadia'])]
    for role, email, pwd in plan:
        for dev in ('tel', 'pc'):
            if role in ('bureau', 'tresorier') and dev == 'tel': continue
            c = ctx(b, phone=(dev == 'tel')); p = page(c, role + dev)
            login(p, email, pwd); snap(p, role, dev, 'accueil_connexion')
            tabs = p.eval_on_selector_all('#tabbar .tab:not([hidden])', 'els => els.map(e => e.dataset.t || e.dataset.act)')
            for t in tabs:
                if t == 'ph-new':
                    try_click(p, '#tabbar .tab-new'); snap(p, role, dev, 'bouton_plus'); close_sheet(p); continue
                go(p, t); snap(p, role, dev, 'onglet_' + t)
            # a job
            for h in (['jour'] if dev == 'tel' else ['agenda']):
                go(p, h)
                if try_click(p, '[data-act="open"]'):
                    snap(p, role, dev, 'job')
                    if try_click(p, '[data-act="invoice"]'):
                        snap(p, role, dev, 'facture_editeur'); try_click(p, '[data-act="back-inv"], [data-act="back"]')
            close_sheet(p)
            if role == 'proprio':
                for h in ['reglages', 'equipe', 'stock', 'tresor', 'carte'] + (['accueil', 'agenda'] if dev == 'tel' else []):
                    go(p, h); snap(p, role, dev, 'page_' + h)
                go(p, 'agenda' if dev == 'pc' else 'jour')
                if try_click(p, '[data-act="new"], [data-act="ph-book"]'): snap(p, role, dev, 'nouvelle_reservation'); close_sheet(p)
                go(p, 'clients')
                if try_click(p, '[data-act="cl-open"]'): snap(p, role, dev, 'fiche_client')
            c.close()
    b.close()
for r in results: r.pop('btns_all', None)
json.dump(results, open(f'{OUT}/metrics.json', 'w', encoding='utf8'), ensure_ascii=False, indent=1)
print('erreurs page :', ERRS[:10])
