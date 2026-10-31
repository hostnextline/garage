exec(open('test_carnet.py').read().split("with sync_playwright() as p:")[0])
import datetime, math, json, urllib.parse
FSA = json.loads(open('pcdata/fsa_qc.js', encoding='utf8').read()[len('var FSA = '):-1])
def pt(f): z = FSA[f]; return (z[0], z[1], f)
def hav(a, b):
    r = math.pi / 180; dla = (b[0]-a[0])*r; dlo = (b[1]-a[1])*r
    h = math.sin(dla/2)**2 + math.cos(a[0]*r)*math.cos(b[0]*r)*math.sin(dlo/2)**2
    return 2*6371*math.asin(math.sqrt(h))
def km(a, b): return 2 if a[2] == b[2] else round(hav(a, b)*1.3*10)/10
def drive(k): return math.ceil(k/35*60 + 5)
td = datetime.date.today(); D1 = (td + datetime.timedelta(days=1)).isoformat(); D2 = (td + datetime.timedelta(days=2)).isoformat()
hours = {str(d): {'open': True, 'start': '08:00', 'end': '17:00'} for d in range(7)}
base_cfg = {'biz': {'name': 'Garage Mobile Test'}, 'trucks': [], 'mechanics': ['Ali', 'Marc'], 'hours': hours, 'rate': 95}
def job(d, t, m, name, pc, dur=60): return {'client': {'name': name, 'phone': '(514) 555-0000', 'address': '1 rue Test', 'postal': pc}, 'vehicle': {}, 'services': ['Diagnostic (lecture des codes)'], 'date': d, 'time': t, 'durationMin': dur, 'mechanic': m, 'status': 'planifie'}
seed = {'config/main': dict(base_cfg, homePostal='J7Y 1A1'),
        'jobs/a1': job(D1, '09:00', 'Ali', 'Luc Gagnon', 'H4N 1B2'), 'jobs/a2': job(D1, '09:00', 'Marc', 'Marie Côté', 'J4K 1A1'),
        'jobs/a3': job(D2, '09:00', 'Ali', 'Sophie Roy', 'H4N 2C3'), 'jobs/a4': job(D2, '10:00', 'Ali', 'Paul Lavoie', 'J4K 3B4')}
H4N, H4P, J4K, J7Y = pt('H4N'), pt('H4P'), pt('J4K'), pt('J7Y')
k_ali = km(H4N, H4P); t_ali = 600 + drive(k_ali); t_ali = math.ceil(t_ali/10)*10
k_marc = km(J4K, H4P); t_marc = math.ceil((600 + drive(k_marc))/10)*10
hmf = lambda m: f"{m//60} h" + (f" {m%60:02d}" if m % 60 else '')
print('expected: Ali', D1, hmf(t_ali), k_ali, 'km | Marc', D1, hmf(t_marc), k_marc, 'km')
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx, pg, errs = new_page(br, {'seed': seed})
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250)
    pg.click('[data-act="cs-new"]'); pg.wait_for_timeout(200)
    check('P0. New client: one address line with a hint (no separate postal field)', pg.locator('#c-addr').count() == 1 and pg.locator('#f-postal, #c-postal').count() == 0 and 'Une seule ligne' in pg.inner_text('#c-addrmsg'))
    pg.fill('#c-first', 'Nouveau'); pg.fill('#c-last', 'Client'); pg.fill('#c-phone', '5145551111')
    pg.fill('#c-addr', '8255 av. Mountain Sights, Montréal h4p2b5'); pg.wait_for_timeout(100)
    check('P1. Postal code found in the address line, zone recognised', 'Code postal H4P 2B5 · zone H4P (Mount Royal South)' in pg.inner_text('#c-addrmsg'), pg.inner_text('#c-addrmsg'))
    pg.press('#c-addr', 'Tab'); pg.wait_for_timeout(50)
    check('P1b. Postal code cleaned up inside the address on blur', pg.input_value('#c-addr') == '8255 av. Mountain Sights, Montréal H4P 2B5', pg.input_value('#c-addr'))
    pg.click('#c-save'); pg.wait_for_timeout(350)
    check('P1c. Booking form shows the client card with its zone and the suggestions', 'Zone H4P · Mount Royal South' in pg.inner_text('.ccard') and pg.is_visible('#sugbox'))
    sugs = pg.locator('.sug')
    first = sugs.nth(0)
    check('P2. Best moment = Ali tomorrow right after Luc Gagnon (Saint-Laurent), allowing drive time',
          sugs.count() >= 3 and first.get_attribute('data-d') == D1 and first.get_attribute('data-t') == f"{t_ali//60:02d}:{t_ali%60:02d}" and first.get_attribute('data-m') == 'Ali'
          and f"+{round(k_ali)} km" in first.inner_text() and 'Après Luc Gagnon (H4N)' in first.inner_text(), [s.inner_text().replace('\n', ' | ') for s in sugs.all()[:5]])
    second = sugs.nth(1)
    check('P3. Next = Marc tomorrow after his Longueuil client (+17 km)', second.get_attribute('data-m') == 'Marc' and second.get_attribute('data-d') == D1 and second.get_attribute('data-t') == f"{t_marc//60:02d}:{t_marc%60:02d}" and f"+{round(k_marc)} km" in second.inner_text(),
          second.inner_text())
    texts = [x.inner_text() for x in sugs.all()]
    far_i = [i for i, t in enumerate(texts) if 'Journée libre' in t]
    check('P3b. Free days ranked after nearby ones, with distance from the start point', all('km du point de départ' in texts[i] for i in far_i) and (not far_i or far_i[0] >= 2), texts)
    pg.locator('#sugbox').scroll_into_view_if_needed(); pg.screenshot(path=os.path.join(SC, 'shot_sug.png'), full_page=False)
    first.click(); pg.wait_for_timeout(120)
    check('P4. Tapping it fills date, time and mechanic; detour shown in green', pg.input_value('#f-date') == D1 and pg.input_value('#f-time') == f"{t_ali//60:02d}:{t_ali%60:02d}" and pg.input_value('#f-mech') == 'Ali'
          and 'ok' in pg.get_attribute('#momentmsg', 'class') and f"≈ {round(k_ali)} km pour Ali" in pg.inner_text('#momentmsg') and 'ali' in pg.inner_text('#sheet-sub').lower(), pg.inner_text('#momentmsg'))
    check('P4b. Chosen suggestion is highlighted', pg.locator('.sug.on').count() == 1)
    pg.fill('#f-time', '09:30'); pg.dispatch_event('#f-time', 'change'); pg.wait_for_timeout(60)
    check('P5. Overlapping time is flagged in red', 'bad' in pg.get_attribute('#momentmsg', 'class') and 'Chevauche le rendez-vous de Luc Gagnon' in pg.inner_text('#momentmsg'), pg.inner_text('#momentmsg'))
    pg.fill('#f-time', '10:00'); pg.dispatch_event('#f-time', 'change'); pg.wait_for_timeout(60)
    check('P6. No time to drive = "Serré" warning with minutes', 'mid' in pg.get_attribute('#momentmsg', 'class') and f"≈ {drive(k_ali)} min de route après Luc Gagnon (H4N)" in pg.inner_text('#momentmsg'), pg.inner_text('#momentmsg'))
    pg.fill('#f-time', f"{t_ali//60:02d}:{t_ali%60:02d}"); pg.dispatch_event('#f-time', 'change')
    pg.click('#f-save'); pg.wait_for_timeout(250)
    nj = [v for v in store(pg).values() if isinstance(v, dict) and v.get('client', {}).get('name') == 'Nouveau Client' and 'date' in v]
    cl = [k for k, v in store(pg).items() if k.startswith('clients/')]
    check('P7. Saved with its postal code and linked to the client file', len(nj) == 1 and nj[0]['client']['postal'] == 'H4P 2B5' and nj[0]['mechanic'] == 'Ali' and nj[0]['date'] == D1 and len(cl) == 1 and nj[0].get('clientId') == cl[0].split('/')[1], nj)
    pg.click(f'.day[data-v="{D1}"]'); pg.wait_for_timeout(100)
    check('P8. Day grid shows the zone on each appointment', 'H4P' in pg.locator('.appt', has_text='Nouveau Client').inner_text() and 'H4P ·' not in pg.locator('.appt', has_text='Nouveau Client').inner_text() and 'H4N ·' in pg.locator('.appt', has_text='Luc Gagnon').inner_text())
    ali_total = round(km(J7Y, H4N) + km(H4N, H4P))
    rt = pg.locator('.trip', has_text='Ali')
    href = rt.locator('a').get_attribute('href')
    q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    check('P9. "Trajets du jour": Ali 2 stops, km from the start point, Google Maps route in time order',
          '2 arrêts' in rt.inner_text() and f"≈ {ali_total} km" in rt.inner_text() and q.get('origin') == ['J7Y 1A1'] and 'H4P 2B5' in q.get('destination', [''])[0] and 'H4N 1B2' in q.get('waypoints', [''])[0],
          (rt.inner_text(), q))
    pg.screenshot(path=os.path.join(SC, 'shot_routes.png'), full_page=True)
    pg.click(f'.day[data-v="{D2}"]'); pg.wait_for_timeout(100)
    need = drive(km(H4N, J4K))
    check('P10. Tight back-to-back across town is flagged', f"Serré entre Sophie Roy (H4N) et Paul Lavoie (J4K) : ≈ {need} min de route, 0 min entre les deux." in pg.inner_text('.routes'), pg.inner_text('.routes'))
    pg.locator('.appt', has_text='Nouveau').count()
    pg.click(f'.day[data-v="{D1}"]'); pg.locator('.appt', has_text='Nouveau Client').click(); pg.wait_for_timeout(80)
    check('P11. Job card shows the address with postal code and zone', '8255 av. Mountain Sights, Montréal H4P 2B5' in pg.inner_text('main') and 'Zone H4P · Mount Royal South' in pg.inner_text('main'))
    pg.click('[data-act="edit"]'); pg.wait_for_timeout(250)
    check('P12. Editing: its own slot is not counted as a clash', 'Chevauche' not in pg.inner_text('#momentmsg') and pg.locator('.sug').count() >= 1)
    pg.click('[data-act="back-edit"]'); pg.click('[data-act="back"]'); pg.wait_for_timeout(80)
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250)
    pg.click('[data-act="cs-new"]'); pg.wait_for_timeout(200)
    pg.fill('#c-addr', '4520 rue Saint-Denis, Montréal QC h2j2l3'); pg.press('#c-addr', 'Tab'); pg.wait_for_timeout(100)
    check('P13. Postal code at the end of the line is picked up and cleaned', pg.input_value('#c-addr') == '4520 rue Saint-Denis, Montréal QC H2J 2L3' and 'zone H2J' in pg.inner_text('#c-addrmsg'), pg.input_value('#c-addr'))
    pg.fill('#c-addr', '4520 rue Saint-Denis, Montréal'); pg.wait_for_timeout(100)
    check('P14. No postal code: asks for it', 'Ajoute le code postal' in pg.inner_text('#c-addrmsg'))
    pg.fill('#c-first', 'Sans'); pg.fill('#c-last', 'Code'); pg.fill('#c-phone', '5145553333'); pg.click('#c-save'); pg.wait_for_timeout(150)
    check('P14b. Saving without a postal code is refused', 'code postal' in pg.inner_text('#c-err') and not [k for k in store(pg) if k.startswith('clients/') and store(pg)[k].get('lastName') == 'Code'], pg.inner_text('#c-err'))
    pg.fill('#c-addr', '1 rue Wellington, Ottawa K1A 0B1'); pg.wait_for_timeout(100)
    check('P15. Zone outside Quebec explained', 'introuvable' in pg.inner_text('#c-addrmsg'))
    pg.click('.sheet-head [data-act="sheet-close"]'); pg.wait_for_timeout(100)
    pg.click('.tab[data-t="reglages"]'); pg.wait_for_timeout(80)
    check('P16. Settings show the start point', pg.input_value('#s-home') == 'J7Y 1A1')
    pg.fill('#s-home', '12345'); pg.click('#s-save'); pg.wait_for_timeout(100)
    check('P17. Invalid start point refused', 'pas valide' in pg.inner_text('#toast') and store(pg)['config/main']['homePostal'] == 'J7Y 1A1')
    pg.fill('#s-home', 'h4p2b5'); pg.click('#s-save'); pg.wait_for_timeout(150)
    check('P18. Start point saved normalised', store(pg)['config/main']['homePostal'] == 'H4P 2B5')
    check('P19. No script errors; no page side-scroll', not errs and no_hscroll(pg), errs[:3])
    ctx.close()
    seed2 = dict(seed); seed2['config/main'] = dict(base_cfg)
    ctx, pg, errs = new_page(br, {'seed': seed2})
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250)
    sheet_new_client(pg, 'Test', 'Départ', '5145554444', '8255 av. Mountain Sights, Montréal H4P 2B5')
    check('P20. Without a start point: still suggests, and asks for it', pg.locator('.sug').count() >= 1 and 'point de départ' in pg.inner_text('#sugbox') and 'Luc Gagnon' in pg.locator('.sug').first.inner_text())
    check('P21. No script errors (no start point)', not errs, errs[:3])
    ctx.close(); br.close()
print('\n%d/%d passed' % (sum(1 for r in results if r[1]), len(results)))
