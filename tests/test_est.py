exec(open('test_carnet.py').read().split("with sync_playwright() as p:")[0])
import datetime
td = datetime.date.today().isoformat()
hours = {str(d): {'open': True, 'start': '07:00', 'end': '20:00'} for d in range(7)}
cfgm = {'biz': {'name': 'Garage Test'}, 'trucks': [], 'mechanics': ['Ali'], 'hours': hours, 'rate': 95, 'taxesOn': False, 'services': [{'name': "Changement d'huile et filtre", 'price': 89.99}]}
seed = {'config/main': cfgm,
        'clients/c1': {'firstName': 'Jean', 'lastName': 'Test', 'phone': '(514) 555-0000', 'address': '1 rue Test, Montréal H4P 2B5', 'postal': 'H4P 2B5', 'notes': []},
        'jobs/old': {'client': {'name': 'Jean Test', 'postal': 'H4P 2B5'}, 'clientId': 'c1', 'vehicle': {}, 'services': ["Remplacement de l'alternateur"], 'date': td, 'time': '08:00', 'durationMin': 60, 'mechanic': 'Ali', 'status': 'planifie'}}
def pick(pg, word, label):
    pg.click('#f-svc-in'); pg.fill('#f-svc-in', ''); pg.keyboard.type(word); pg.wait_for_timeout(60)
    pg.locator('#svc-opts .opt', has_text=label).first.click(); pg.wait_for_timeout(80)
def units(pg): return pg.input_value('#f-units')
def est(pg): return pg.inner_text('#svc-est')
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx, pg, errs = new_page(br, {'seed': seed})
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250); sheet_pick_client(pg, 'jean')
    check('E0. New booking starts at 6 units (1 h), no estimate yet', units(pg) == '6' and est(pg).strip() == '')
    pg.click('#f-svc-in'); pg.keyboard.type('altern'); pg.wait_for_timeout(60)
    check('E1. Each service in the list shows its time ("≈ 1 h 30" for the alternator)', '≈ 1 h 30' in pg.locator('#svc-opts .opt', has_text='alternateur').first.inner_text())
    pg.keyboard.press('Enter'); pg.wait_for_timeout(80)
    check('E2. Chip shows "≈ 1 h 30"; estimate 1 h 30 (between 1 h and 3 h 30), dealership times', '≈ 1 h 30' in pg.inner_text('.pchip') and 'Temps estimé : 1 h 30' in est(pg) and 'entre 1 h et 3 h 30' in est(pg) and 'concessionnaires' in est(pg), est(pg))
    check('E3. Duration filled automatically: 9 units = 1 h 30', units(pg) == '9' and pg.inner_text('#f-units-lbl') == '9 unités = 1 h 30')
    pick(pg, 'huile', "Changement d'huile")
    check('E4. Oil change added: 2 h, 12 units; the oil change shows its price and time', 'Temps estimé : 2 h' in est(pg) and units(pg) == '12' and '89,99' in pg.locator('.pchip', has_text='huile').inner_text() and '≈ 30 min' in pg.locator('.pchip', has_text='huile').inner_text())
    pg.click('#f-svc-in'); pg.keyboard.type('Bruit roue avant gauche'); pg.keyboard.press('Enter'); pg.wait_for_timeout(80)
    check('E5. A service without an estimate is named, total unchanged', 'Sans estimé : Bruit roue avant gauche' in est(pg) and 'Temps estimé : 2 h' in est(pg) and units(pg) == '12', est(pg))
    pg.screenshot(path=os.path.join(SC, 'shot_est.png'))
    pg.click('[data-act="units"][data-v="1"]'); pg.wait_for_timeout(60)
    check('E6. Changing the duration yourself: it stays, and the estimate offers to put it back', units(pg) == '13' and pg.locator('#svc-est [data-act="units-est"]').count() == 1 and 'Mettre la durée à 2 h' in est(pg))
    pick(pg, 'batt', 'batterie')
    check('E7. After a manual change, adding a service does not touch the duration', units(pg) == '13' and 'Temps estimé : 2 h 30' in est(pg) and 'Mettre la durée à 2 h 30' in est(pg))
    pg.click('#svc-est [data-act="units-est"]'); pg.wait_for_timeout(80)
    check('E8. "Mettre la durée à 2 h 30" sets 15 units and the button goes away', units(pg) == '15' and pg.locator('#svc-est [data-act="units-est"]').count() == 0 and 'Durée mise à 2 h 30' in pg.inner_text('#toast'))
    pg.fill('#f-time', '13:00'); pg.click('#f-save'); pg.wait_for_timeout(300)
    nj = [v for k, v in jobs(pg).items() if k != 'jobs/old']
    check('E9. Saved with 2 h 30 (150 min)', len(nj) == 1 and nj[0]['durationMin'] == 150, [v.get('durationMin') for v in nj])
    # timing belt + water pump
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250); sheet_pick_client(pg, 'jean')
    pick(pg, 'distribution', 'distribution'); pick(pg, 'pompe', 'Pompe à eau')
    check('E10. Timing belt + water pump = 5 h (pump counted 1 h, done with the belt), 30 units', 'Temps estimé : 5 h' in est(pg) and 'pompe à eau comptée 1 h' in est(pg) and units(pg) == '30', est(pg))
    pg.click('.sheet-head [data-act="sheet-close"]'); pg.wait_for_timeout(100)
    # editing an existing job keeps its saved duration
    pg.click(f'.day[data-v="{td}"]') if pg.locator(f'.day[data-v="{td}"]').count() else None
    pg.locator('.appt', has_text='Jean Test').first.click(); pg.wait_for_timeout(150)
    pg.click('[data-act="edit"]'); pg.wait_for_timeout(250)
    check('E11. Editing a saved job keeps its duration (6 units) and offers the 1 h 30 estimate', units(pg) == '6' and 'Mettre la durée à 1 h 30' in est(pg), (units(pg), est(pg)))
    pg.click('[data-act="back-edit"]'); pg.wait_for_timeout(100)
    pg.click('#top [data-act="back"]') if pg.locator('#top [data-act="back"]').count() else None
    # invoice on the spot: hours x rate for a service without a set price
    pg.click('.tab[data-t="factures"]'); pg.wait_for_timeout(100); pg.click('[data-act="quick"]'); pg.wait_for_timeout(250); sheet_pick_client(pg, 'jean')
    pick(pg, 'altern', 'alternateur'); pick(pg, 'huile', "Changement d'huile")
    pg.click('#f-save'); pg.wait_for_timeout(400)
    descs = [pg.input_value(f'#l{i}-desc') for i in range(2)]
    qtys = [pg.input_value(f'#l{i}-qty') for i in range(2)]
    prices = [pg.input_value(f'#l{i}-price') for i in range(2)]
    ia = descs.index("Remplacement de l'alternateur"); io = 1 - ia
    check('E12. Invoice: alternator billed 1,5 h × 95 $ (estimated hours); oil change at its set price × 1', qtys[ia] == '1,5' and prices[ia] == '95' and qtys[io] == '1' and prices[io] == '89,99', (descs, qtys, prices))
    pg.click('[data-act="finalize"]'); pg.wait_for_timeout(400)
    inv = [v['invoice'] for v in jobs(pg).values() if v.get('invoice', {}).get('number')]
    check('E12b. Total = 1,5 × 95 + 89,99 = 232,49 (taxes off in this test)', inv and abs(inv[0]['total'] - 232.49) < 0.01, inv and inv[0].get('total'))
    check('E13. No script errors; no side-scroll', not errs and no_hscroll(pg), errs[:3])
    ctx.close()
    # 15-minute units
    s15 = json.loads(json.dumps(seed)); s15['config/main']['slotMin'] = 15
    ctx, pg, errs = new_page(br, {'seed': s15})
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250); sheet_pick_client(pg, 'jean')
    pick(pg, 'serpentin', 'serpentin')
    check('E14. With 15-minute units, 48 min (shown ≈ 50 min) rounds up to 4 units (1 h)', units(pg) == '4' and 'Temps estimé : 50 min' in est(pg), (units(pg), est(pg)))
    check('E15. No script errors (15-minute units)', not errs, errs[:3])
    ctx.close()
    ctx, pg, errs = new_page(br, {'seed': seed}, scheme='dark')
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250); sheet_pick_client(pg, 'jean')
    pick(pg, 'altern', 'alternateur'); pick(pg, 'huile', "Changement d'huile")
    pg.locator('#svc-est').scroll_into_view_if_needed(); pg.screenshot(path=os.path.join(SC, 'shot_est_dark.png'))
    check('E16. Dark mode renders, no errors', 'Temps estimé : 2 h' in est(pg) and not errs, errs[:3])
    ctx.close(); br.close()
print('\n%d/%d passed' % (sum(1 for r in results if r[1]), len(results)))
