exec(open("test_tomtom.py").read().split("\nwith sync_playwright() as p:")[0])
def F(*fs): return {'type': 'FeatureCollection', 'features': list(fs)}
def pad(num, street, city, pc, lon, lat, prov='QC', hood=''):
    a = {'streetNumber': num, 'streetName': street, 'municipality': city, 'countrySubdivision': prov, 'postalCode': pc[:3], 'countryCode': 'CA', 'country': 'Canada', 'freeformAddress': f'{num} {street}, {city} {prov} {pc}'}
    if hood: a['neighbourhood'] = hood
    return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]}, 'properties': {'type': 'Point Address', 'address': a}}
def strt(street, city, pc, lon, lat):
    a = {'streetName': street, 'municipality': city, 'countrySubdivision': 'QC', 'postalCode': pc[:3], 'countryCode': 'CA', 'country': 'Canada', 'freeformAddress': f'{street}, {city} QC {pc}'}
    return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]}, 'properties': {'type': 'Street', 'address': a}}
ESSAI = pad('1200', 'Rue Essai-Sud', 'Montréal', 'H4P 2B5', -73.651, 45.501, hood='Quartier Test')
ONT = pad('1200', 'Rue Essai', 'Ottawa', 'K1A 0B1', -75.70, 45.42, prov='ON')
DECOY = pad('1200', 'Rue Autre', 'Montréal', 'H2T 1T5', -73.586, 45.520)
STR = F(strt('Rue Essai-Sud', 'Montréal', 'H4P 2B1', -73.650, 45.500), strt('Rue Essai-Sud', 'Montréal', 'H4P 2B9', -73.652, 45.502), strt('Rue Essai-Nord', 'Laval', 'H7N 1A1', -73.72, 45.56))
EMPTY = F()
AT = '1200 Rue Essai-Sud, Montréal QC H4P 2B5'
MCP = {'mode': 'ok', 'fixture': EMPTY,
       'byQuery': {'1200 essai|PAD,Addr': F(ESSAI, ONT), 'rue essai|Str': STR, '1200 Rue Essai-Sud, Montréal QC|PAD,Addr': F(ESSAI), '99999 rue essai|PAD,Addr': EMPTY, '1200 H4P 2B5|PAD,Addr': F(ESSAI)},
       'verify': {'1200 rue essai-sud montreal': F(DECOY, ESSAI), '1200 rue essai-sud, montréal H2X 3K8': F(ESSAI), '1200 rue essai-sud, montréal H4P 2B5': F(ESSAI), '77 rue essai-sud, montréal': EMPTY}}
seedS = {'config/main': {'biz': {'name': 'Garage Mobile Test'}, 'mechanics': ['Ali'], 'homePostal': 'J7Y 1A1'},
         'clients/jean': {'firstName': 'Jean', 'lastName': 'Tremblay', 'phone': '(514) 555-1234', 'email': '', 'address': AT, 'postal': 'H4P 2B5', 'notes': [], 'createdAt': 1, 'updatedAt': 1}}
def hav(a, b):
    r = math.pi/180; dla = (b[0]-a[0])*r; dlo = (b[1]-a[1])*r
    h = math.sin(dla/2)**2 + math.cos(a[0]*r)*math.cos(b[0]*r)*math.sin(dlo/2)**2
    return 2*6371*math.asin(math.sqrt(h))
home = FSA['J7Y']; km_essai = round(hav((home[0], home[1]), (45.501, -73.651))*1.3)
def addr_type(pg, text, wait=450):
    pg.fill('#c-addr', ''); pg.click('#c-addr'); pg.keyboard.type(text); pg.wait_for_timeout(wait)
def last(pg): return calls(pg)[-1] if calls(pg) else {}
def blur(pg):
    pg.keyboard.press('Escape'); pg.click('#c-email'); pg.wait_for_timeout(400)

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx, pg, errs = new_page(br, {'seed': seedS, 'mcp': MCP})
    new_client_page(pg)
    check('S0. Empty field explains what can be typed', '180-8255' in pg.inner_text('#c-addrmsg') and '8255 H4P 2B5' in pg.inner_text('#c-addrmsg'))
    # unit kept
    addr_type(pg, '180-1200 essai')
    opts = pg.locator('#c-addrsug .opt:not(.local)')
    check('S1. "180-1200 essai": TomTom gets the address without the 180, list keeps it', last(pg).get('input', {}).get('query') == '1200 essai' and opts.count() == 2 and opts.nth(0).locator('b').inner_text() == '180-' + AT
          and 'App./bureau 180 gardé' in pg.inner_text('#c-addrsug .src'), (last(pg).get('input'), [opts.nth(i).inner_text() for i in range(opts.count())]))
    check('S2. Each address shows the km from the start point; Ottawa flagged "hors Québec"', f'≈ {km_essai} km du point de départ' in opts.nth(0).inner_text() and 'hors Québec' in opts.nth(1).inner_text() and 'hors Québec' not in opts.nth(0).inner_text(), [opts.nth(i).inner_text() for i in range(opts.count())])
    pg.screenshot(path=os.path.join(SC, 'shot_smart_unit.png'))
    opts.nth(0).click(); pg.wait_for_timeout(150)
    check('S3. Picked with the unit; hint shows TomTom + unit + postal', pg.input_value('#c-addr') == '180-' + AT and 'Adresse trouvée sur TomTom · App./bureau 180 · Code postal H4P 2B5' in pg.inner_text('#c-addrmsg'), (pg.input_value('#c-addr'), pg.inner_text('#c-addrmsg')))
    check('S4. Same building as an existing fiche: says so, with "Utiliser cette fiche"', 'Même immeuble que' in pg.inner_text('#c-sameaddr') and 'Jean Tremblay' in pg.inner_text('#c-sameaddr') and pg.locator('#c-sameaddr [data-act="cs-pick"]').count() == 1)
    addr_type(pg, '1200 essai app 3')
    check('S5. "… app 3" at the end: same search, unit put in front', last(pg)['input']['query'] == '1200 essai' and pg.locator('#c-addrsug .opt:not(.local) b').first.inner_text() == '3-' + AT)
    pg.locator('#c-addrsug .opt:not(.local)').first.click(); pg.wait_for_timeout(100)
    # street without number
    addr_type(pg, 'rue essai')
    opts = pg.locator('#c-addrsug .opt:not(.local)')
    check('S6. Street without number: searches streets, one line per street (postal removed), asks for the number',
          last(pg)['input']['idxSet'] == 'Str' and opts.count() == 2 and opts.nth(0).locator('b').inner_text() == 'Rue Essai-Sud, Montréal QC' and 'ajoute ensuite le numéro civique' in opts.nth(0).inner_text()
          and 'numéro civique au début' in pg.inner_text('#c-addrmsg'), ([opts.nth(i).inner_text() for i in range(opts.count())], pg.inner_text('#c-addrmsg')))
    pg.screenshot(path=os.path.join(SC, 'shot_smart_street.png'))
    opts.nth(0).click(); pg.wait_for_timeout(100)
    check('S7. Picking the street: text filled, cursor at the start for the number', pg.input_value('#c-addr') == 'Rue Essai-Sud, Montréal QC' and pg.evaluate("document.activeElement.id === 'c-addr' && document.activeElement.selectionStart === 0"))
    pg.keyboard.type('1200 '); pg.wait_for_timeout(450)
    check('S8. Typing the number: the exact address with postal code appears', last(pg)['input']['query'] == '1200 Rue Essai-Sud, Montréal QC' and pg.locator('#c-addrsug .opt b').first.inner_text() == AT, last(pg).get('input'))
    pg.keyboard.press('ArrowDown'); pg.keyboard.press('Enter'); pg.wait_for_timeout(100)
    check('S8b. Exact address picked, same address as Jean flagged', pg.input_value('#c-addr') == AT and 'Cette adresse est déjà à la fiche de' in pg.inner_text('#c-sameaddr'))
    # number not found
    addr_type(pg, '99999 rue essai', 700)
    cs = calls(pg)
    check('S9. Unknown number: second try on the street, says the number is not found', [c['input']['idxSet'] for c in cs[-2:]] == ['PAD,Addr', 'Str'] and cs[-1]['input']['query'] == 'rue essai' and 'Le numéro 99999 est introuvable' in pg.inner_text('#c-addrsug'))
    pg.locator('#c-addrsug .opt:not(.local)').first.click(); pg.wait_for_timeout(100)
    check('S9b. Picking it keeps the number and explains what to check', pg.input_value('#c-addr') == '99999 Rue Essai-Sud, Montréal QC' and '99999' in pg.inner_text('#c-ttnote'))
    # postal only / number + postal
    n0 = len(calls(pg)); addr_type(pg, 'H4P 2B5')
    check('S10. Postal code alone: looks up that code, and asks for the number if nothing is found', any(c['tool'] == 'tomtom-geocode' and c['input']['query'] == 'H4P 2B5' for c in calls(pg)) and 'ajoute le numéro civique devant' in pg.inner_text('#c-addrmsg'))
    addr_type(pg, '1200 H4P 2B5')
    check('S11. Number + postal code is enough', last(pg)['input']['query'] == '1200 H4P 2B5' and pg.locator('#c-addrsug .opt b').first.inner_text() == AT)
    # typed by hand, then checked
    addr_type(pg, '1200 rue essai-sud montreal', 450); blur(pg)
    vc = [c for c in calls(pg) if c['input'].get('typeahead') is False]
    check('S12. Typed without postal code: TomTom check finds it (right street, not the other 1200)', vc and vc[-1]['input']['query'] == '1200 rue essai-sud montreal' and 'Code postal trouvé par TomTom' in pg.inner_text('#c-addrfix') and AT in pg.inner_text('#c-addrfix'), (pg.inner_text('#c-addrfix'), [c['input'] for c in vc]))
    pg.screenshot(path=os.path.join(SC, 'shot_smart_fix.png'))
    pg.click('#c-addrfix [data-act="addr-fix"]'); pg.wait_for_timeout(100)
    check('S12b. "Utiliser cette adresse" fills it with the position', pg.input_value('#c-addr') == AT and 'Adresse trouvée sur TomTom' in pg.inner_text('#c-addrmsg') and pg.inner_text('#c-addrfix').strip() == '')
    addr_type(pg, '1200 rue essai-sud, montréal H2X 3K8'); blur(pg)
    check('S13. Wrong postal code typed: TomTom says which one is right, "Corriger"', 'TomTom trouve le code postal H4P 2B5' in pg.inner_text('#c-addrfix') and 'H2X 3K8' in pg.inner_text('#c-addrfix') and pg.inner_text('#c-addrfix [data-act="addr-fix"]') == 'Corriger', pg.inner_text('#c-addrfix'))
    pg.click('#c-addrfix [data-act="addr-fix"]'); pg.wait_for_timeout(100)
    check('S13b. Corrected', pg.input_value('#c-addr') == AT)
    addr_type(pg, '1200 rue essai-sud, montréal H4P 2B5'); blur(pg)
    check('S14. Right postal code typed: quietly marked "vérifiée", no banner', 'Adresse vérifiée sur TomTom' in pg.inner_text('#c-addrmsg') and pg.inner_text('#c-addrfix').strip() == '', pg.inner_text('#c-addrmsg'))
    addr_type(pg, '77 rue essai-sud, montréal'); blur(pg)
    check('S15. Number unknown to TomTom: soft warning', 'ne trouve pas ce numéro' in pg.inner_text('#c-addrfix'))
    # save rules
    fill_rest(pg, 'Lea', 'Smart', '5145557001')
    addr_type(pg, 'Rue Essai-Sud, Montréal QC H4P 2B5', 100); pg.keyboard.press('Escape'); pg.click('#c-save'); pg.wait_for_timeout(200)
    check('S16. No civic number: refused', 'numéro civique' in pg.inner_text('#c-err') and len(C(pg)) == 1)
    addr_type(pg, '1200 rue essai-sud montreal', 100); pg.keyboard.press('Escape'); pg.click('#c-save'); pg.wait_for_timeout(500)
    check('S17. Missing postal code: refused, and TomTom proposes it right away', 'TomTom' in pg.inner_text('#c-err') and AT in pg.inner_text('#c-addrfix') and len(C(pg)) == 1, (pg.inner_text('#c-err'), pg.inner_text('#c-addrfix')))
    pg.click('#c-addrfix [data-act="addr-fix"]'); pg.wait_for_timeout(100); pg.click('#c-save'); pg.wait_for_timeout(400)
    cl = [v for v in C(pg).values() if v['lastName'] == 'Smart']
    check('S18. Then it saves: full address, postal code, position', len(cl) == 1 and cl[0]['address'] == AT and cl[0]['postal'] == 'H4P 2B5' and cl[0]['geo'] == {'lat': 45.501, 'lon': -73.651}, cl)
    # booking popup: same address → use Jean
    pg.click('.tab[data-t="agenda"]'); pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250); pg.click('[data-act="cs-new"]'); pg.wait_for_timeout(250)
    addr_type(pg, '1200 H4P 2B5'); pg.locator('#c-addrsug .opt').first.click(); pg.wait_for_timeout(100)
    check('S19. In the booking popup: "déjà à la fiche de" shows', 'Jean Tremblay' in pg.inner_text('#sheet #c-sameaddr'))
    pg.click('#sheet #c-sameaddr [data-act="cs-pick"][data-id="jean"]'); pg.wait_for_timeout(350)
    check('S19b. "Utiliser cette fiche" continues the booking with Jean', 'Jean Tremblay' in pg.inner_text('.ccard') and pg.locator('#jobform').count() == 1)
    pg.click('.sheet-head [data-act="sheet-close"]'); pg.wait_for_timeout(100)
    check('S20. No script errors; no side-scroll', not errs and no_hscroll(pg), errs[:3])
    ctx.close()
    # dark look
    ctx, pg, errs = new_page(br, {'seed': seedS, 'mcp': MCP}, scheme='dark')
    new_client_page(pg); addr_type(pg, '1200 rue essai-sud montreal'); blur(pg)
    pg.screenshot(path=os.path.join(SC, 'shot_smart_fix_dark.png'))
    check('S21. Dark mode: banner renders, no errors', 'Code postal trouvé' in pg.inner_text('#c-addrfix') and not errs, errs[:3])
    ctx.close()
    # without TomTom: unit + same-address + civic rules still work
    ctx, pg, errs = new_page(br, {'seed': seedS})
    new_client_page(pg)
    addr_type(pg, '180-1200 Rue Essai-Sud, Montréal QC H4P 2B5', 100)
    check('S22. Without TomTom: unit read, same-building warning, postal and zone', 'App./bureau 180 · Code postal H4P 2B5' in pg.inner_text('#c-addrmsg') and 'Même immeuble que' in pg.inner_text('#c-sameaddr') and calls(pg) == [])
    addr_type(pg, 'H4P 2B5', 100)
    check('S22b. Without TomTom: postal alone asks for the number', 'numéro civique devant' in pg.inner_text('#c-addrmsg'))
    check('S23. No script errors (no TomTom)', not errs, errs[:3])
    ctx.close(); br.close()
print('\n%d/%d passed' % (sum(1 for r in results if r[1]), len(results)))
