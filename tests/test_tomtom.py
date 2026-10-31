exec(open('test_carnet.py').read().split("with sync_playwright() as p:")[0])
import json, math
FSA = json.loads(open('pcdata/fsa_qc.js', encoding='utf8').read()[len('var FSA = '):-1])
def feat(kind, num, street, city, pc, lon, lat, hood=''):
    a = {'streetNumber': num, 'streetName': street, 'municipality': city, 'countrySubdivision': 'QC', 'postalCode': pc[:3], 'countryCode': 'CA', 'country': 'Canada', 'freeformAddress': f'{num} {street}, {city} QC {pc}'}
    if hood: a['neighbourhood'] = hood
    return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]}, 'id': 'x' + num, 'properties': {'type': kind, 'address': a}}
FIX = {'type': 'FeatureCollection', 'properties': {'numResults': 3}, 'features': [
    feat('Point Address', '1200', 'Rue Essai-Sud', 'Montréal', 'H4P 2B5', -73.651, 45.501, 'Quartier Test'),
    feat('Point Address', '1200', 'Avenue Exemple', 'Montréal', 'H2X 3K8', -73.571, 45.511),
    feat('Address Range', '1200', 'Boul Modèle', 'Montréal', 'H3X 2H5', -73.622, 45.480, 'Snowdon'),
]}
FIX['features'].append(json.loads(json.dumps(FIX['features'][0])))  # duplicate, must be shown once
T1 = '1200 Rue Essai-Sud, Montréal QC H4P 2B5'; T2 = '1200 Avenue Exemple, Montréal QC H2X 3K8'
seed = {'config/main': {'biz': {'name': 'Garage Mobile Test'}, 'trucks': [], 'mechanics': ['Ali', 'Marc'], 'homePostal': 'J7Y 1A1'}}
def C(pg): return {k: v for k, v in store(pg).items() if k.startswith('clients/')}
def calls(pg): return pg.evaluate('JSON.parse(JSON.stringify(window.__mcpCalls))')
def new_client_page(pg):
    pg.click('.tab[data-t="clients"]'); pg.wait_for_timeout(100); pg.click('#top [data-act="cl-new"]'); pg.wait_for_timeout(250)
def fill_rest(pg, first, last, phone):
    pg.fill('#c-first', first); pg.fill('#c-last', last); pg.fill('#c-phone', phone)

with sync_playwright() as p:
    br = p.chromium.launch()
    # no connector capability at all
    ctx, pg, errs = new_page(br, {'seed': seed})
    new_client_page(pg)
    pg.click('#c-addr'); pg.keyboard.type('1200 essai'); pg.wait_for_timeout(500)
    check('T0. Without TomTom: no suggestions, no call, manual hint kept', calls(pg) == [] and not pg.is_visible('#c-addrsug') and 'Ajoute le code postal' in pg.inner_text('#c-addrmsg') and 'Ex. 8255' in pg.get_attribute('#c-addr', 'placeholder'))
    ctx.close()

    ctx, pg, errs = new_page(br, {'seed': seed, 'mcp': {'mode': 'ok', 'fixture': FIX, 'delays': {'1200 ex': 400}}})
    new_client_page(pg)
    check('T1. With TomTom: placeholder invites to type', 'Commence à taper' in pg.get_attribute('#c-addr', 'placeholder'))
    pg.click('#c-addr'); pg.keyboard.type('120'); pg.wait_for_timeout(450)
    check('T2. Under 4 characters: no call', calls(pg) == [])
    pg.keyboard.type('0 essai'); pg.wait_for_timeout(500)
    cs = calls(pg)
    z = FSA['J7Y']
    check('T3. One call after typing stops (debounced), right connector, tool and arguments',
          len(cs) == 1 and cs[0]['server'] == 'TomTom Maps' and cs[0]['tool'] == 'tomtom-fuzzy-search' and cs[0]['input']['query'] == '1200 essai' and cs[0]['input']['typeahead'] is True
          and cs[0]['input']['countries'] == ['CA'] and cs[0]['input']['idxSet'] == 'PAD,Addr' and cs[0]['input']['limit'] == 5 and abs(cs[0]['input']['position'][0] - z[1]) < 1e-6 and abs(cs[0]['input']['position'][1] - z[0]) < 1e-6, cs)
    opts = pg.locator('#c-addrsug .opt')
    check('T4. 3 addresses proposed (duplicate removed), with neighbourhood, TomTom credited', pg.is_visible('#c-addrsug') and opts.count() == 3 and T1 in opts.nth(0).inner_text() and 'Quartier Test' in opts.nth(0).inner_text()
          and 'TomTom' in pg.inner_text('#c-addrsug .src') and pg.get_attribute('#c-addr', 'aria-expanded') == 'true', [opts.nth(i).inner_text() for i in range(opts.count())])
    pg.screenshot(path=os.path.join(SC, 'shot_tt_light.png'))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(50)
    check('T5. Escape closes the list', not pg.is_visible('#c-addrsug'))
    pg.keyboard.type('-'); pg.wait_for_timeout(450); pg.keyboard.press('ArrowDown'); pg.keyboard.press('Enter'); pg.wait_for_timeout(150)
    check('T6. Arrow + Enter picks the address (form not submitted)', pg.input_value('#c-addr') == T1 and not pg.is_visible('#c-addrsug') and len(C(pg)) == 0 and pg.locator('#clientform').count() == 1, pg.input_value('#c-addr'))
    check('T7. Hint confirms TomTom + postal + zone', 'Adresse trouvée sur TomTom · Code postal H4P 2B5 · zone H4P' in pg.inner_text('#c-addrmsg') and pg.evaluate('document.activeElement.id') == 'c-addr', pg.inner_text('#c-addrmsg'))
    # stale answer must not overwrite a newer one
    pg.fill('#c-addr', ''); pg.click('#c-addr'); pg.keyboard.type('1200 ex'); pg.wait_for_timeout(300); pg.keyboard.type('emple'); pg.wait_for_timeout(700)
    cs = calls(pg)
    check('T8. Only the latest typed query is shown (slow older answer ignored)', [c['input']['query'] for c in cs[-2:]] == ['1200 ex', '1200 exemple'] and pg.is_visible('#c-addrsug') and pg.input_value('#c-addr') == '1200 exemple', [c['input']['query'] for c in cs])
    pg.locator('#c-addrsug .opt').nth(1).click(); pg.wait_for_timeout(150)
    check('T9. Tap picks too', pg.input_value('#c-addr') == T2 and 'zone H2X' in pg.inner_text('#c-addrmsg'))
    pg.click('#c-first'); pg.wait_for_timeout(200)
    pg.wait_for_timeout(900)
    dr = store(pg).get('data/users/u_test/draft-client', {})
    check('T10. Draft keeps the exact position', dr.get('address') == T2 and dr.get('geo') == {'lat': 45.511, 'lon': -73.571}, dr)
    fill_rest(pg, 'Tom', 'Tom', '5145550001'); pg.click('#c-save'); pg.wait_for_timeout(350)
    cl = [v for v in C(pg).values() if v['lastName'] == 'Tom']
    check('T11. Fiche saved with the TomTom address, postal and position', len(cl) == 1 and cl[0]['address'] == T2 and cl[0]['postal'] == 'H2X 3K8' and cl[0]['geo'] == {'lat': 45.511, 'lon': -73.571}, cl)
    cid = [k for k, v in C(pg).items() if v['lastName'] == 'Tom'][0]
    pg.click('[data-act="cl-edit"]'); pg.wait_for_timeout(200)
    check('T12. Edit: position kept, hint says TomTom', 'Adresse trouvée sur TomTom' in pg.inner_text('#c-addrmsg'))
    pg.fill('#c-email', 'tom@example.com'); pg.click('#c-save'); pg.wait_for_timeout(300)
    check('T12b. Saving other fields keeps the position', store(pg)[cid]['geo'] == {'lat': 45.511, 'lon': -73.571} and store(pg)[cid]['email'] == 'tom@example.com')
    pg.click('[data-act="cl-edit"]'); pg.wait_for_timeout(200)
    pg.fill('#c-addr', '5 rue Écrite, Montréal H2X 3K8'); pg.click('#c-save'); pg.wait_for_timeout(300)
    check('T13. Address typed by hand: old position cleared', store(pg)[cid]['geo'] is None and store(pg)[cid]['address'] == '5 rue Écrite, Montréal H2X 3K8')
    # booking popup
    pg.click('.tab[data-t="agenda"]'); pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250); pg.click('[data-act="cs-new"]'); pg.wait_for_timeout(250)
    fill_rest(pg, 'Ana', 'Popup', '5145550002')
    pg.click('#c-addr'); pg.keyboard.type('1200 essai'); pg.wait_for_timeout(500)
    check('T14. Same suggestions inside the booking popup', pg.locator('#sheet #c-addrsug .opt').count() == 3)
    pg.locator('#c-addrsug .opt').nth(0).click(); pg.wait_for_timeout(100); pg.click('#c-save'); pg.wait_for_timeout(400)
    check('T14b. Booking form shows the picked address and its zone', T1 in pg.inner_text('.ccard') and 'Zone H4P' in pg.inner_text('.ccard') and pg.is_visible('#sugbox'))
    pg.fill('#f-time', '09:00'); pg.click('#f-save'); pg.wait_for_timeout(350)
    jb = [v for k, v in store(pg).items() if k.startswith('jobs/') and v['client']['name'] == 'Ana Popup']
    check('T14c. Job keeps the client position in its snapshot', len(jb) == 1 and jb[0]['client']['geo'] == {'lat': 45.501, 'lon': -73.651}, jb)
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250); pg.click('[data-act="cs-new"]'); pg.wait_for_timeout(250)
    pg.click('#c-addr'); pg.keyboard.type('zzzz rue'); pg.wait_for_timeout(500)
    check('T15. Nothing found: list stays closed, typing still works', not pg.is_visible('#c-addrsug') and pg.input_value('#c-addr') == 'zzzz rue')
    pg.click('.sheet-head [data-act="sheet-close"]'); pg.wait_for_timeout(100)
    check('T16. No script errors; no side-scroll', not errs and no_hscroll(pg), errs[:3])
    ctx.close()

    # dark screenshot
    ctx, pg, errs = new_page(br, {'seed': seed, 'mcp': {'mode': 'ok', 'fixture': FIX}}, scheme='dark')
    new_client_page(pg); pg.click('#c-addr'); pg.keyboard.type('1200 essai'); pg.wait_for_timeout(500)
    pg.screenshot(path=os.path.join(SC, 'shot_tt_dark.png'))
    check('T17. Dark mode list renders, no errors', pg.locator('#c-addrsug .opt').count() == 3 and not errs, errs[:3])
    ctx.close()

    # failure states
    for mode, needle, name in [('not_connected', 'ajoute TomTom Maps', 'not connected'), ('reauth', 'reconnecte TomTom Maps', 'needs reauth'), ('declined', 'non permises', 'declined for this page')]:
        ctx, pg, errs = new_page(br, {'seed': seed, 'mcp': {'mode': mode, 'fixture': FIX}})
        new_client_page(pg); pg.click('#c-addr'); pg.keyboard.type('1200 essai'); pg.wait_for_timeout(500)
        note = pg.inner_text('#c-ttnote'); n1 = len(calls(pg)); pg.keyboard.type(' sud'); pg.wait_for_timeout(500)
        pg.fill('#c-addr', '9 rue Manuelle, Montréal H4P 2B5'); fill_rest(pg, 'Man', 'Uel', '5145550003'); pg.click('#c-save'); pg.wait_for_timeout(300)
        saved = [v for v in C(pg).values() if v['lastName'] == 'Uel']
        check(f'T18. {name}: clear message, no more calls, manual address still saves', needle in note and n1 == 1 and len(calls(pg)) == 1 and len(saved) == 1 and saved[0]['geo'] is None and saved[0]['postal'] == 'H4P 2B5', (note, n1, len(calls(pg)), saved))
        ctx.close()
    # message text visible before saving
    ctx, pg, errs = new_page(br, {'seed': seed, 'mcp': {'mode': 'not_connected', 'fixture': FIX}})
    new_client_page(pg); pg.click('#c-addr'); pg.keyboard.type('1200 essai'); pg.wait_for_timeout(500)
    check('T18b. Not connected: note tells where to add TomTom Maps', 'ajoute TomTom Maps dans claude.ai' in pg.inner_text('#c-ttnote'), pg.inner_text('#c-ttnote'))
    ctx.close()
    ctx, pg, errs = new_page(br, {'seed': seed, 'mcp': {'mode': 'approval', 'fixture': FIX}})
    new_client_page(pg); pg.click('#c-addr'); pg.keyboard.type('1200 essai'); pg.wait_for_timeout(500)
    check('T19. Needs approval: note with "Activer les suggestions"', pg.locator('#c-ttnote [data-act="tt-allow"]').count() == 1 and not pg.is_visible('#c-addrsug'))
    pg.click('#c-ttnote [data-act="tt-allow"]'); pg.wait_for_timeout(300)
    check('T19b. Button asks once more and shows the addresses', len(calls(pg)) == 2 and pg.locator('#c-addrsug .opt').count() == 3 and pg.locator('#c-ttnote button').count() == 0)
    ctx.close()
    ctx, pg, errs = new_page(br, {'seed': seed, 'mcp': {'mode': 'unavailable', 'fixture': FIX}})
    new_client_page(pg); pg.click('#c-addr'); pg.keyboard.type('1200 essai'); pg.wait_for_timeout(500)
    check('T20. TomTom down: soft note, still enabled', 'ne répond pas' in pg.inner_text('#c-ttnote'))
    pg.keyboard.type(' s'); pg.wait_for_timeout(500)
    check('T20b. Next keystrokes try again and the note clears', len(calls(pg)) == 2 and pg.locator('#c-addrsug .opt').count() == 3 and pg.inner_text('#c-ttnote').strip() == '')
    check('T21. No script errors in failure modes', not errs, errs[:3])
    ctx.close()
    br.close()
print('\n%d/%d passed' % (sum(1 for r in results if r[1]), len(results)))
