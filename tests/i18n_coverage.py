"""English everywhere: every role, phone and computer, every screen, the usual windows, and each role's whole guided tour,
in English. Lists what would still show in French (the test garage's own words left aside). Writes i18n/coverage.json."""
import json, re, sys
from team_seed import *
from tour_walk import walk
from playwright.sync_api import sync_playwright

DATA = re.compile(r"Marie|Tremblay|Paul|Roy|Saint-Denis|Ontario|Montréal|Garage NextLine|Honda|Ford|Civic|F-150|Bruit au freinage|Plaquettes|Rami|Zoé|Test Rendezvous|garage\.test|exemple\.ca|^[A-Z]{2}$|Hassan|Saleh|Ali|Lina|Nadia|Karim|Trésor$|NextLine")
SCREENS = ['jour', 'accueil', 'agenda', 'clients', 'factures', 'tresor', 'stock', 'carte', 'dispos', 'reglages', 'equipe', 'plus', 'heures']
def misses(p):
    return p.evaluate("Object.keys(window.I18N.misses)")
def act(p, sel):
    try:
        if p.locator(sel).count(): p.locator(sel).first.click(timeout=3000); p.wait_for_timeout(700); return True
    except Exception: pass
    return False
def close(p):
    try:
        if p.evaluate("!!window.__garageApi.S.sheet"): p.evaluate("document.querySelector('#sheet [data-act=\"sheet-close\"]').click()"); p.wait_for_timeout(300)
    except Exception: pass
found = {}
otok, pw = seed()
with sync_playwright() as pl:
    b = pl.chromium.launch()
    for who in ('hassan', 'saleh', 'lina', 'nadia'):
        for phone in (True, False):
            c = ctx(b, phone=phone); c.add_init_script("try { localStorage.setItem('gm.lang', 'en'); } catch(e){}"); p = page(c, who)
            if not phone: p.set_viewport_size({'width': 1366, 'height': 860})
            login(p, who + '@garage.test', pw[who]); p.wait_for_timeout(1500)
            for t in SCREENS:
                p.evaluate("location.hash = '%s'" % t); p.wait_for_timeout(700)
                if t == 'tresor': act(p, '[data-act="exp-new"]'); close(p); act(p, '[data-act="tr-view"][data-v="rap"]')
                if t == 'clients': act(p, '[data-act="cl-new"]'); p.evaluate("location.hash = 'clients'"); p.wait_for_timeout(400); act(p, '#main [data-act="cl-open"]')
                if t == 'agenda': act(p, '[data-act="new"]'); close(p)
                if t == 'reglages':
                    for i in range(14):
                        p.evaluate("location.hash = 'reglages'"); p.wait_for_timeout(250)
                        if not act(p, '#ph-setlist [data-act="ph-sec"]:nth-child(%d)' % (i + 1)): break
                if t == 'equipe': act(p, '[data-act="eq-edit"]')
            p.evaluate("location.hash = 'jour'"); p.wait_for_timeout(500)
            if act(p, '#main [data-act="open"]'):
                for sel in ('details.sect summary', '[data-act="xp-new"]', '[data-act="sig"]', '[data-act="invoice"]'):
                    act(p, sel); close(p)
            if phone: act(p, '.tab-new'); close(p); act(p, '.tab[data-t="plus"]'); act(p, '.ph-row[data-act="app-install"]'); close(p)
            else: act(p, '.nf-app [data-act="app-install"]'); close(p)
            # the whole guided tour
            p.evaluate("(() => { const a = window.__garageApi; })()")
            try:
                psql("delete from public.docs where path like 'data/users/%/tour'")
                p.reload(); p.wait_for_timeout(1500)
                if who == 'hassan':
                    if phone: act(p, '.tab[data-t="plus"]'); act(p, '.ph-row[data-act="tour-replay"]')
                    else: act(p, '#navfoot [data-act="tour-replay"]')
                p.wait_for_function("!!document.querySelector('#tour-ov .tt-tip')", timeout=12000)
                walk(p); act(p, '#tour-ov [data-act="tt-end"]')
            except Exception as e:
                found.setdefault('(tour problem)', []).append('%s %s: %s' % (who, 'phone' if phone else 'pc', str(e)[:120]))
            for m in misses(p):
                if DATA.search(m) or not re.search(r'[a-zà-ÿ]{3}', m): continue
                found.setdefault(m, []).append('%s %s' % (who, 'phone' if phone else 'pc'))
            c.close()
    b.close()
psql("insert into public.docs (path, data) select 'data/users/' || user_id || '/tour', '{\"seenAt\": 1}' from public.members on conflict (path) do nothing")
json.dump(found, open('i18n/coverage.json', 'w'), ensure_ascii=False, indent=1)
print('still in French:', len(found))
for k, v in sorted(found.items(), key=lambda x: -len(x[1]))[:150]: print(len(v), '|', k[:150])
print('errors', ERRS[:5])
