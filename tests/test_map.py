"""Carte de l'équipe : plus grande, Centrale (8255 Mountain Sights), tout le monde y a accès, une couleur et un trajet par mécano,
rendez-vous numérotés avec le nom du client ; la case « Voir la carte » vérifiée par le serveur. Copie locale ; remise à zéro à la fin."""
import json
from team_seed import *
from playwright.sync_api import sync_playwright
def rpc(tok, name, body): return http('POST', API + '/rest/v1/rpc/' + name, body, tok)
OSRM = []
def osrm(route):
    u = route.request.url; OSRM.append(u)
    pts = [list(map(float, p.split(','))) for p in u.split('/driving/')[1].split('?')[0].split(';')]
    geo = []
    for a, b in zip(pts, pts[1:]): geo += [a, [(a[0] + b[0]) / 2 + 0.002, (a[1] + b[1]) / 2], b]
    route.fulfill(status=200, content_type='application/json', headers={'Access-Control-Allow-Origin': '*'}, body=json.dumps({'code': 'Ok', 'routes': [{'distance': 12345.0 * (len(pts) - 1), 'duration': 1260.0 * (len(pts) - 1), 'geometry': {'type': 'LineString', 'coordinates': geo}}]}))
def mk(b, phone=False):
    c = ctx(b, phone=phone); c.route('https://router.project-osrm.org/**', osrm); return c
def leaf(p):
    return p.evaluate("""(() => ({
      stops: [...document.querySelectorAll('.leaflet-marker-pane .tm-stop')].map(e => [e.textContent, getComputedStyle(e).backgroundColor]),
      hq: document.querySelectorAll('.leaflet-marker-pane .tm-hq').length,
      hqTip: [...document.querySelectorAll('.leaflet-tooltip.tm-hq-tip')].map(e => e.textContent),
      mech: document.querySelectorAll('.leaflet-marker-pane .tm-mech').length,
      lines: [...document.querySelectorAll('.leaflet-overlay-pane path')].map(e => [e.getAttribute('stroke'), e.getAttribute('stroke-dasharray')]),
      h: Math.round(document.getElementById('gm-map').getBoundingClientRect().height), w: Math.round(document.getElementById('gm-map').getBoundingClientRect().width)
    }))()""")
otok, pw = seed()
uid = {k: psql("select id from auth.users where email='%s@garage.test'" % k) for k in ('hassan', 'saleh', 'ali', 'nadia')}
c3 = {'firstName': 'Zoé', 'lastName': 'Gagnon', 'phone': '514 555-0303', 'address': '6000 chemin de la Côte-des-Neiges, Montréal', 'postal': 'H3S 1Z8', 'geo': {'lat': 45.4966, 'lon': -73.6262}}
doc_set(otok, 'clients/c3', c3)
doc_set(otok, 'jobs/j3', {'date': TODAY, 'time': '16:00', 'durationMin': 60, 'mechanic': 'Saleh', 'clientId': 'c3', 'client': dict(c3, id='c3', name='Zoé Gagnon'), 'services': ['Inspection multipoints'], 'status': 'planifie', 'createdAt': 3})
psql("insert into public.mech_live (user_id, name, mechanic, on_shift, shift_started_at, lat, lon, at) values ('%s', 'Saleh Haddad', 'Saleh', true, now(), 45.52, -73.60, now()) on conflict (user_id) do update set on_shift = true, lat = 45.52, lon = -73.60, at = now()" % uid['saleh'])
with sync_playwright() as pl:
    b = pl.chromium.launch()
    # ---------- a mechanic, on his phone ----------
    sc = mk(b, phone=True); sp = page(sc, 'saleh'); login(sp, 'saleh@garage.test', pw['saleh'])
    sp.click('.tab[data-t="plus"]'); sp.wait_for_timeout(500)
    check('mechanic: « Carte de l\'équipe » in Plus (everyone has the map)', sp.locator('.ph-row, a', has_text='Carte de l\'équipe').count() >= 1)
    sp.locator('a[href="#carte"], .ph-row[href="#carte"]').first.click(); sp.wait_for_timeout(2500)
    L = leaf(sp)
    check('big map on the phone (almost the whole screen)', L['h'] >= 560 and L['w'] >= 380, [L['w'], L['h']])
    check('« Centrale » on the map, with its name always shown', L['hq'] == 1 and 'Centrale' in L['hqTip'], L['hqTip'])
    nums = sorted(x[0] for x in L['stops'])
    check('every appointment of the day, numbered per mechanic (Saleh 1-2, Ali 1)', nums == ['1', '1', '2'], L['stops'])
    cols = {}
    for n, c in L['stops']: cols.setdefault(c, []).append(n)
    check('one color per mechanic (2 colors: Saleh 1+2, Ali 1)', len(cols) == 2 and sorted(len(v) for v in cols.values()) == [1, 2], cols)
    m = txt(sp, 'main')
    check('he also sees the other mechanic\'s appointments, with the client\'s name (Paul Roy, Ali)', 'Paul Roy' in m and 'Ali' in m and 'Zoé Gagnon' in m and 'Marie Tremblay' in m, m[:300])
    check('his own route of the day follows the roads (asked once to OpenStreetMap routing)', any('/driving/' in u for u in OSRM) and any(l[1] is None for l in L['lines']), [L['lines'], OSRM[:2]])
    hq = '-73.6577429,45.5005053'
    check('each route of the day starts at the Centrale (where the trucks leave), then the stops in order', any(u.split('/driving/')[1].startswith(hq + ';') and u.count(';') == 2 for u in OSRM) and any(u.split('/driving/')[1].startswith(hq + ';') and u.count(';') == 1 for u in OSRM), [u.split('/driving/')[1][:80] for u in OSRM])
    m = txt(sp, 'main')
    check('under each mechanic: « Trajet du jour depuis la Centrale : 25 km · environ 42 min de route » (Ali : 12 km · 21 min)', 'Trajet du jour depuis la Centrale' in m and '25 km' in m and '42 min' in m and '12 km' in m and '21 min' in m, m[m.find('Trajet'):m.find('Trajet') + 120])
    check('he is on the map during his workday, with a dotted line to his next client', L['mech'] >= 1 and any(l[1] for l in L['lines']), L['lines'])
    check('his own jobs can be opened from the list; the others cannot', sp.locator('.tm-stops [data-act="er-open"][data-id="j1"]').count() == 1 and sp.locator('.tm-stops [data-act="er-open"][data-id="j2"]').count() == 0)
    sp.screenshot(path='map_phone.png')
    sc.close()
    # ---------- the owner, on a computer ----------
    oc = mk(b); op = page(oc, 'owner'); op.set_viewport_size({'width': 1440, 'height': 900}); login(op, 'hassan@garage.test', pw['hassan'])
    op.click('.tab[data-t="carte"]'); op.wait_for_timeout(2500)
    L = leaf(op)
    check('computer: a big map (most of the screen)', L['h'] >= 640 and L['w'] >= 900, [L['w'], L['h']])
    check('same map for the owner: Centrale, 3 numbered appointments, the mechanic', L['hq'] == 1 and len(L['stops']) == 3 and L['mech'] >= 1)
    op.screenshot(path='map_pc.png')
    op.click('.tm-chip[data-v="ali"]'); op.wait_for_timeout(700)
    check('touch a mechanic\'s name above the map: his route and appointments hide / show', len(leaf(op)['stops']) == 2)
    op.click('.tm-chip[data-v="ali"]'); op.wait_for_timeout(700)
    check('…and come back', len(leaf(op)['stops']) == 3)
    op.locator('.leaflet-marker-pane .tm-stop').first.click(); op.wait_for_timeout(500)
    check('touch a number: time, client, address, mechanic', op.locator('.leaflet-popup .tm-pop').count() == 1 and ('Paul Roy' in txt(op, '.tm-pop') or 'Marie' in txt(op, '.tm-pop') or 'Zoé' in txt(op, '.tm-pop')))
    oc.close()
    # ---------- the treasurer: the map too ----------
    nc = mk(b); np_ = page(nc, 'nadia'); np_.set_viewport_size({'width': 1280, 'height': 900}); login(np_, 'nadia@garage.test', pw['nadia'])
    check('treasurer: « Carte » in her menu', np_.locator('.tab[data-t="carte"]').is_visible())
    nc.close()
    # ---------- the box « Voir la carte » removed for Saleh: screen and server ----------
    fn(otok, 'members', {'action': 'update', 'user_id': uid['saleh'], 'perms': {'map': False}})
    stok = token('saleh@garage.test', pw['saleh'])
    r = rpc(stok, 'team_map', {'p_day': TODAY})
    check('server: without the box, the map is refused to him', isinstance(r, dict) and r.get('_status', 200) >= 400, str(r)[:120])
    r2 = rpc(token('ali@garage.test', pw['ali']), 'team_map', {'p_day': TODAY})
    check('…the others still get it (Ali)', isinstance(r2, dict) and len(r2.get('jobs', [])) == 3, str(r2)[:120])
    sc = mk(b, phone=True); sp = page(sc, 'saleh2'); login(sp, 'saleh@garage.test', pw['saleh'])
    sp.click('.tab[data-t="plus"]'); sp.wait_for_timeout(500)
    check('his phone: no « Carte de l\'équipe » any more', sp.locator('a[href="#carte"]').count() == 0)
    sc.close()
    b.close()
# back to the start
fn(otok, 'members', {'action': 'update', 'user_id': uid['saleh'], 'perms': {}})
psql("update public.mech_live set on_shift = false, lat = null, lon = null where user_id = '%s'" % uid['saleh'])
http('POST', API + '/rest/v1/rpc/doc_delete', {'p_path': 'jobs/j3'}, otok); http('POST', API + '/rest/v1/rpc/doc_delete', {'p_path': 'clients/c3'}, otok)
check('back to the start', doc('jobs/j3') is None and psql("select perms::text from public.members where user_id='%s'" % uid['saleh']) == '{}')
check('no page errors', not ERRS, ERRS[:5])
summary()
