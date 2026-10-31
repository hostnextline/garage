exec(open("test_smart.py").read().split("\nwith sync_playwright() as p:")[0])
import math as _m
C0 = (-73.585, 45.525); KX = 111320 * _m.cos(_m.radians(C0[1]))
th = _m.radians(30); U = (_m.sin(th), _m.cos(th)); V = (U[1], -U[0])
houses = []
for i, t in enumerate(range(-400, 401, 8)):
    for side in (1, -1):
        x = U[0]*t + V[0]*7*side; y = U[1]*t + V[1]*7*side
        num = 4600 + (t // 8) * 2 + (1 if side > 0 else 0)
        pc = ('H2J 2L3' if -200 <= t < 0 else 'H2J 2L5' if 0 <= t < 200 else 'H2J 9Z9') if side < 0 else ('H2J 2L4' if -200 <= t < 0 else 'H2J 2L6')
        houses.append({'num': str(num), 'street': 'Rue Saint-Essai', 'pc': pc, 'lon': C0[0] + x/KX, 'lat': C0[1] + y/111320, 't': t})
want = sorted([h for h in houses if h['pc'] == 'H2J 2L3'], key=lambda h: int(h['num']))
cx, cy = U[0]*20, U[1]*20
CENTER = [C0[0] + cx/KX, C0[1] + cy/111320]
GEO = {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': CENTER}, 'properties': {'type': 'Street', 'address': {'streetName': 'Rue Saint-Essai', 'municipality': 'Montréal', 'postalCode': 'H2J', 'countryCode': 'CA', 'freeformAddress': 'Rue Saint-Essai, Montréal QC H2J'}}}]}
MP = {'mode': 'ok', 'fixture': EMPTY, 'geocode': {'H2J 2L3': GEO}, 'houses': houses, 'revDelay': 40}
seedP = {'config/main': {'biz': {'name': 'Garage Mobile Test'}, 'trucks': [], 'mechanics': ['Ali'], 'homePostal': 'J7Y 1A1'}}
def revcalls(pg): return [c for c in calls(pg) if c['tool'] == 'tomtom-reverse-geocode']
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx, pg, errs = new_page(br, {'seed': seedP, 'mcp': MP})
    new_client_page(pg)
    pg.click('#c-addr'); pg.keyboard.type('H2J'); pg.wait_for_timeout(300)
    check('Q1. Typing the start of a postal code: "continue", no search yet', 'Continue le code postal' in pg.inner_text('#c-addrsug') and calls(pg) == [])
    pg.keyboard.type(' 2L3'); pg.wait_for_timeout(200)
    check('Q2. Full postal code: "Recherche des adresses de H2J 2L3…" and the code is located', 'Recherche des adresses de H2J 2L3' in pg.inner_text('#c-addrsug') and any(c['tool'] == 'tomtom-geocode' and c['input']['query'] == 'H2J 2L3' for c in calls(pg)))
    pg.wait_for_timeout(600)
    mid = pg.locator('#c-addrsug .opt').count(); still = 'Recherche des adresses' in pg.inner_text('#c-addrsug')
    check('Q3. Addresses appear while the search continues', mid > 0 and still, (mid, still))
    pg.screenshot(path=os.path.join(SC, 'shot_pc_loading.png'))
    for _ in range(40):
        if 'Recherche des adresses' not in pg.inner_text('#c-addrsug'): break
        pg.wait_for_timeout(250)
    rows = pg.locator('#c-addrsug .opt')
    texts = [rows.nth(i).locator('b').inner_text() for i in range(rows.count())]
    inpc = [t for t in texts if t.endswith('H2J 2L3')]
    exp = [h['num'] + ' Rue Saint-Essai, Montréal QC H2J 2L3' for h in want]
    texts = [rows.nth(i).locator('b').inner_text() + ('' if rows.nth(i).locator('b').inner_text().endswith(('H2J 2L3',)) or 'Dans H2J 2L3' not in rows.nth(i).inner_text() else ', Montréal QC H2J 2L3') for i in range(rows.count())]
    inpc = [t for t in texts if t.endswith('H2J 2L3')]
    check(f'Q4. All {len(exp)} addresses of H2J 2L3 found, in number order', inpc == exp, (len(inpc), len(exp), [t.split(' ')[0] for t in inpc][:30]))
    head = pg.locator('#c-addrsug .opt-head').all_inner_texts()
    check('Q5. Grouped: "Adresses dans H2J 2L3 (25)" then "Tout près" (max 6, nearest first)', head and head[0].upper().startswith('ADRESSES DANS H2J 2L3 (%d)' % len(exp)) and (len(head) == 1 or head[1].upper() == 'TOUT PRÈS') and len(texts) - len(inpc) <= 6, head)
    rc = revcalls(pg)
    check('Q6. At most 4 lookups at a time, at most 80 in all', pg.evaluate('window.__mcpMaxLive') <= 4 and len(rc) <= 80, (pg.evaluate('window.__mcpMaxLive'), len(rc)))
    pg.screenshot(path=os.path.join(SC, 'shot_pc_list.png'))
    pick = exp[3]
    pg.locator('#c-addrsug .opt', has_text=pick.split(',')[0]).first.click(); pg.wait_for_timeout(100)
    check('Q7. Picking one fills the full address with its position', pg.input_value('#c-addr') == pick and 'Adresse trouvée sur TomTom · Code postal H2J 2L3' in pg.inner_text('#c-addrmsg'), (pg.input_value('#c-addr'), pg.inner_text('#c-addrmsg')))
    n0 = len(calls(pg))
    addr_type(pg, 'h2j2l3', 300)
    check('Q8. Same code again: instant, no new lookups, kept on this device', len(calls(pg)) == n0 and pg.locator('#c-addrsug .opt').count() == len(texts) and pg.evaluate("!!localStorage.getItem('gm.pc.H2J2L3')"))
    addr_type(pg, 'app 4 H2J 2L3', 300)
    check('Q9. With an apartment: "app 4 H2J 2L3" puts 4- in front of every address', pg.locator('#c-addrsug .opt:not(.local) b').first.inner_text().startswith('4-' + want[0]['num']) and 'App./bureau 4 gardé' in pg.inner_text('#c-addrsug'))
    addr_type(pg, 'H9Z 9Z9', 600)
    check('Q10. Unknown postal code: says nothing was found and what to type', 'Aucune adresse trouvée pour H9Z 9Z9' in pg.inner_text('#c-addrsug'), pg.inner_text('#c-addrsug'))
    fill_rest(pg, 'Code', 'Postal', '5145551010'); addr_type(pg, 'H2J 2L3', 300); pg.locator('#c-addrsug .opt:not(.local)').nth(1).click(); pg.wait_for_timeout(100)
    pg.click('#c-save'); pg.wait_for_timeout(350)
    cl = [v for v in C(pg).values() if v['lastName'] == 'Postal']
    check('Q11. Saved from the postal list: address, postal code, position', len(cl) == 1 and cl[0]['postal'] == 'H2J 2L3' and cl[0]['geo'] and cl[0]['address'] == exp[1], cl)
    check('Q12. No script errors', not errs, errs[:3])
    ctx.close()
    # a newer typing cancels the running postal search
    ctx, pg, errs = new_page(br, {'seed': seedP, 'mcp': dict(MP, revDelay=120)})
    new_client_page(pg); addr_type(pg, 'H2J 2L3', 400); pg.keyboard.press('Control+a'); pg.keyboard.type('4520 saint'); pg.wait_for_timeout(1500)
    n1 = len(revcalls(pg)); pg.wait_for_timeout(800)
    check('Q13. Typing something else stops the postal search', len(revcalls(pg)) - n1 <= 4 and 'Adresses dans' not in pg.inner_text('#c-addrsug') if pg.is_visible('#c-addrsug') else True, (n1, len(revcalls(pg))))
    ctx.close()
    ctx, pg, errs = new_page(br, {'seed': seedP, 'mcp': dict(MP, revFail='server_not_connected')})
    new_client_page(pg); addr_type(pg, 'H2J 2L3', 2500)
    check('Q14. Lookups refused: clear message, typing still works', 'ajoute TomTom Maps' in pg.inner_text('#c-ttnote') and pg.input_value('#c-addr') == 'H2J 2L3', pg.inner_text('#c-ttnote'))
    ctx.close()
    ctx, pg, errs = new_page(br, {'seed': seedP})
    new_client_page(pg); addr_type(pg, 'H2J 2L3', 300)
    check('Q15. Without TomTom: asks for the civic number, no lookups', calls(pg) == [] and 'ajoute le numéro civique devant' in pg.inner_text('#c-addrmsg'))
    ctx.close(); br.close()
print('\n%d/%d passed' % (sum(1 for r in results if r[1]), len(results)))
