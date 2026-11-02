"""The guided tours when the garage books by block (the team version's default): each role walks to the end by his own
touches, the texts speak of blocks and of the waiver, nothing tried is saved."""
import json
from team_seed import *
from tour_walk import *
from playwright.sync_api import sync_playwright

def dbsig():
    return psql("select md5(coalesce(string_agg(path || data::text, ',' order by path), '')) from public.docs where path not like 'data/users/%/tour'")
def start(p, who, phone):
    if who == 'hassan':
        p.wait_for_timeout(1200)
        if phone: p.click('.tab[data-t="plus"]'); p.wait_for_timeout(400); p.click('.ph-row[data-act="tour-replay"]')
        else: p.click('#navfoot [data-act="tour-replay"]')
    p.wait_for_function("!!document.querySelector('#tour-ov .tt-tip')", timeout=9000); ready(p)

otok, pw = seed()
c = doc('config/main'); c.pop('bookMode', None); doc_set(otok, 'config/main', c)   # (booking by block)
psql("delete from public.docs where path like 'data/users/%/tour'")
sig0 = dbsig(); W = {}
with sync_playwright() as pl:
    b = pl.chromium.launch()
    for who, phone, tag in (('hassan', False, 'propriétaire · ordi'), ('hassan', True, 'propriétaire · téléphone'), ('lina', True, 'bureau · téléphone'), ('saleh', True, 'mécano · téléphone')):
        psql("delete from public.docs where path like 'data/users/%/tour'")
        cx = ctx(b, phone=phone); p = page(cx, who)
        if not phone: p.set_viewport_size({'width': 1366, 'height': 860})
        login(p, who + '@garage.test', pw[who], tour=True); start(p, who, phone)
        cfg0 = psql("select data::text from public.docs where path='config/main'")
        W[tag] = walk(p)
        W[tag + ' words'] = p.evaluate("1") and [s.get('words', '') for s in W[tag]]
        p.click('#tour-ov [data-act="tt-end"]'); p.wait_for_timeout(900)
        if who == 'hassan': psql("update public.docs set data = '%s'::jsonb where path = 'config/main'" % cfg0.replace("'", "''"))   # (the color he picked: put back)
        cx.close()
    b.close()
walks = {k: v for k, v in W.items() if isinstance(v, list) and v and isinstance(v[0], dict)}
check('%d visits walked to « C\'est tout ! » with booking by block' % len(walks), all(v[-1]['t'] == "C'est tout !" for v in walks.values()), {k: (len(v), v[-1]['t']) for k, v in walks.items()})
check('the tour never moves by itself', not {k: autonav(v) for k, v in walks.items() if autonav(v)})
txt = ' '.join(s.get('words', '') + ' ' + s['t'] for v in walks.values() for s in v)
check('the texts speak of blocks (matin, après-midi, soir) and of the routes made by the app', 'bloc' in txt and 'matin' in txt and 'route' in txt, txt[:300])
check('…and of the waiver the client signs (no photos)', 'décharge' in txt.lower() and 'photo avant' not in txt.lower())
check('…and of the inventory', 'inventaire' in txt.lower())
check('NOTHING tried during the visits was saved', dbsig() == sig0)
check('no script errors', not ERRS, ERRS[:5])
summary()
