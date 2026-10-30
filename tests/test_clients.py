exec(open('test_carnet.py').read().split("with sync_playwright() as p:")[0])
import datetime
D = datetime.date
t0 = D.today(); td = t0.isoformat()
ago40 = (t0 - datetime.timedelta(days=40)).isoformat(); ago60 = (t0 - datetime.timedelta(days=60)).isoformat()
tom = (t0 + datetime.timedelta(days=1)).isoformat()
mon = t0 - datetime.timedelta(days=t0.weekday()); wk = [(mon + datetime.timedelta(days=i)).isoformat() for i in range(7)]
hours = {str(d): {'open': d != 0, 'start': '08:00', 'end': '17:00'} for d in range(7)}
jean = {'firstName': 'Jean', 'lastName': 'Tremblay', 'phone': '(514) 555-1234', 'email': 'jean@example.com', 'address': '4500 boul. Décarie, Montréal H4P 2B5', 'postal': 'H4P 2B5', 'notes': [], 'createdAt': 1, 'updatedAt': 2}
sophie = {'firstName': 'Sophie', 'lastName': 'Roy', 'phone': '(450) 555-2222', 'email': '', 'address': '12 rue King, Longueuil J4K 1A1', 'postal': 'J4K 1A1', 'notes': [], 'createdAt': 1, 'updatedAt': 1}
def snap(i, c): return {'id': i, 'firstName': c['firstName'], 'lastName': c['lastName'], 'name': c['firstName'] + ' ' + c['lastName'], 'phone': c['phone'], 'email': c['email'], 'address': c['address'], 'postal': c['postal']}
veh = {'year': '2015', 'make': 'Honda', 'model': 'Civic', 'vin': ''}
def inv(no, issued, total, paid):
    return {'lines': [{'type': 'piece', 'desc': 'Batterie', 'qty': 1, 'price': 180}], 'taxesOn': True, 'sub': 180, 'tps': 9, 'tvq': 17.96, 'total': total, 'paid': paid, 'method': 'Débit' if paid else '', 'paidAt': issued if paid else None, 'note': '', 'number': no, 'issuedAt': issued}
seed = {
    'config/main': {'biz': {'name': 'Garage Mobile Test', 'phone': '(514) 555-0000'}, 'taxesOn': True, 'rate': 95, 'mechanics': ['Ali', 'Marc'], 'hours': hours, 'homePostal': 'J7Y 1A1',
                    'services': [{'name': "Changement d'huile", 'price': 89.99}]},
    'meta/invoices': {'next': 4},
    'clients/jean': jean, 'clients/sophie': sophie,
    'jobs/j1': {'client': snap('jean', jean), 'clientId': 'jean', 'vehicle': veh, 'services': ['Batterie'], 'service': 'Batterie', 'date': ago40, 'time': '09:00', 'durationMin': 60, 'mechanic': 'Ali', 'status': 'termine', 'invoice': inv('F-0003', ago40, 206.96, False)},
    'jobs/j2': {'client': snap('jean', jean), 'clientId': 'jean', 'vehicle': veh, 'services': ['Batterie'], 'service': 'Batterie', 'date': ago60, 'time': '09:00', 'durationMin': 60, 'mechanic': 'Ali', 'status': 'termine', 'invoice': inv('F-0002', ago60, 206.96, True)},
    'jobs/j3': {'client': snap('jean', jean), 'clientId': 'jean', 'vehicle': veh, 'services': ['Freins avant'], 'service': 'Freins avant', 'date': tom, 'time': '10:00', 'durationMin': 60, 'mechanic': 'Ali', 'status': 'planifie'},
}
def C(pg): return {k: v for k, v in store(pg).items() if k.startswith('clients/')}
def active(pg): return pg.evaluate('document.activeElement && document.activeElement.id')

with sync_playwright() as p:
    br = p.chromium.launch()
    # ---------- empty carnet ----------
    ctx, pg, errs = new_page(br, {})
    check('K0. Tab bar has 5 tabs (Accueil first) including Clients', pg.locator('.tab:not([hidden])').count() == 5 and pg.locator('.tab:not([hidden])').first.get_attribute('data-t') == 'accueil' and pg.locator('.tab[data-t="clients"]').count() == 1)
    pg.click('.tab[data-t="clients"]'); pg.wait_for_timeout(100)
    check('K0b. Empty Clients tab explains the fiche and offers to create the first one', 'Aucune fiche client' in pg.inner_text('main') and pg.locator('main [data-act="cl-new"]').count() == 1)
    ctx.close()

    # ---------- seeded carnet ----------
    ctx, pg, errs = new_page(br, {'seed': seed})
    pg.click('.tab[data-t="clients"]'); pg.wait_for_timeout(120)
    rows = pg.locator('#cl-list .crow')
    check('K1. List: 2 fiches sorted by name, totals (2 fiches, 206,96 à recevoir, 1 avec un solde)', rows.count() == 2 and 'Jean Tremblay' in rows.nth(0).inner_text() and 'Sophie Roy' in rows.nth(1).inner_text()
          and '206,96' in pg.inner_text('.sum') and '1' in pg.locator('.sum .stat').nth(2).inner_text(), pg.inner_text('.sum'))
    check('K1b. Jean shows "206,96 $ dû" and "1 à venir", zone H4P', '206,96' in rows.nth(0).inner_text() and '1 à venir' in rows.nth(0).inner_text() and 'zone H4P' in rows.nth(0).inner_text(), rows.nth(0).inner_text())
    pg.click('#cl-q'); pg.keyboard.type('tremb'); pg.wait_for_timeout(120)
    check('K2. Search by name, cursor stays in the search box', rows.count() == 1 and 'Jean' in rows.nth(0).inner_text() and active(pg) == 'cl-q' and pg.input_value('#cl-q') == 'tremb')
    pg.fill('#cl-q', '450 555'); pg.wait_for_timeout(120)
    check('K2b. Search by phone digits', rows.count() == 1 and 'Sophie' in rows.nth(0).inner_text())
    pg.fill('#cl-q', 'j4k'); pg.wait_for_timeout(120)
    check('K2c. Search by postal code', rows.count() == 1 and 'Sophie' in rows.nth(0).inner_text())
    pg.fill('#cl-q', 'zzz'); pg.wait_for_timeout(120)
    check('K2d. No match explained', rows.count() == 0 and 'Aucun client ne correspond' in pg.inner_text('main'))
    pg.fill('#cl-q', ''); pg.wait_for_timeout(120)

    # new client (page form) + validation
    pg.click('#top [data-act="cl-new"]'); pg.wait_for_timeout(250)
    check('K3. New client page: prénom, nom, téléphone, one address line, optional email', all(pg.locator(s).count() == 1 for s in ['#c-first', '#c-last', '#c-phone', '#c-addr', '#c-email'])
          and 'optionnel' in pg.inner_text('label[for="c-email"]').lower() and pg.locator('#c-postal, #f-postal').count() == 0)
    pg.click('#c-save'); pg.wait_for_timeout(120)
    check('K3b. Empty: lists everything missing', "Il manque le prénom, le nom, le téléphone et l'adresse." in pg.inner_text('#c-err') and active(pg) == 'c-first', pg.inner_text('#c-err'))
    pg.fill('#c-first', 'Luc'); pg.fill('#c-last', 'Gagnon'); pg.fill('#c-phone', '514555'); pg.fill('#c-addr', '100 rue Peel, Montréal')
    pg.click('#c-save'); pg.wait_for_timeout(120)
    check('K3c. Short phone refused', '10 chiffres' in pg.inner_text('#c-err'))
    pg.fill('#c-phone', '514 555 7777'); pg.click('#c-save'); pg.wait_for_timeout(120)
    check('K3d. Address without postal code refused', 'code postal' in pg.inner_text('#c-err') and active(pg) == 'c-addr')
    pg.fill('#c-addr', '100 rue Peel, Montréal h3c2g6'); pg.fill('#c-email', 'luc@'); pg.click('#c-save'); pg.wait_for_timeout(120)
    check('K3e. Bad email refused', 'courriel' in pg.inner_text('#c-err'))
    check('K3f. Nothing saved while invalid', len(C(pg)) == 2)
    pg.fill('#c-email', ''); pg.click('#c-save'); pg.wait_for_timeout(300)
    luc = [(k, v) for k, v in C(pg).items() if v['lastName'] == 'Gagnon']
    check('K4. Saved without email: phone formatted, postal pulled from the address', len(luc) == 1 and luc[0][1]['phone'] == '(514) 555-7777' and luc[0][1]['postal'] == 'H3C 2G6' and luc[0][1]['address'] == '100 rue Peel, Montréal H3C 2G6' and luc[0][1]['email'] == '', luc)
    check('K4b. Lands on the new fiche with the 4 buttons', 'Luc Gagnon' in pg.inner_text('#top') and pg.locator('.tile').count() == 4
          and [pg.locator('.tile').nth(i).inner_text().split('\n')[0] for i in range(4)] == ['Prendre un rendez-vous', 'Facturation', 'Suivi client', 'Comptes recevables'], [pg.locator('.tile').nth(i).inner_text() for i in range(pg.locator('.tile').count())])
    check('K4c. Client draft removed after saving', 'data/users/u_test/draft-client' not in store(pg))
    pg.screenshot(path=os.path.join(SC, 'shot_client_new.png'), full_page=True)
    # delete a fiche with no jobs
    pg.click('[data-act="cl-edit"]'); pg.wait_for_timeout(200)
    pg.click('[data-act="cl-del"]'); pg.wait_for_timeout(120)
    check('K5. Delete asks for confirmation', 'pour de bon' in pg.inner_text('main') and pg.locator('[data-act="cl-del-yes"]').count() == 1)
    pg.click('[data-act="cl-del-yes"]'); pg.wait_for_timeout(250)
    check('K5b. Fiche deleted, back on the list', len(C(pg)) == 2 and pg.locator('#cl-list .crow').count() == 2)

    # duplicate phone
    pg.click('#top [data-act="cl-new"]'); pg.wait_for_timeout(250)
    pg.fill('#c-first', 'Jean'); pg.fill('#c-last', 'Double'); pg.fill('#c-phone', '5145551234'); pg.press('#c-phone', 'Tab'); pg.wait_for_timeout(80)
    check('K6. Known phone number flagged with the existing fiche', 'Jean Tremblay' in pg.inner_text('#c-dup') and pg.locator('#c-dup [data-act="cs-pick"]').count() == 1)
    pg.fill('#c-addr', '1 rue Test, Montréal H4P 2B5'); pg.click('#c-save'); pg.wait_for_timeout(150)
    check('K6b. First save stops and explains', 'existe déjà' in pg.inner_text('#c-err') and len(C(pg)) == 2)
    pg.click('#c-dup [data-act="cs-pick"]'); pg.wait_for_timeout(200)
    check('K6c. "Utiliser cette fiche" opens Jean\'s fiche, nothing created', 'Jean Tremblay' in pg.inner_text('#top') and len(C(pg)) == 2)

    # client page: Suivi (default)
    check('K7. Suivi: 1 upcoming, 2 past visits, vehicle listed', pg.locator('#cl-panel .list').nth(0).locator('.vrow').count() == 1 and pg.locator('#cl-panel .list').nth(1).locator('.vrow').count() == 2 and '2015 Honda Civic' in pg.inner_text('#cl-panel'))
    pg.click('[data-act="cl-note-add"]'); pg.wait_for_timeout(100)
    check('K8. Empty note refused', 'Écris la note' in pg.inner_text('#toast'))
    pg.fill('#cl-note', 'Plaquettes arrière à 4 mm'); pg.fill('#cl-due', tom); pg.click('[data-act="cl-note-add"]'); pg.wait_for_timeout(250)
    nts = store(pg)['clients/jean'].get('notes', [])
    check('K8b. Note saved on the fiche with its reminder date, shown, field cleared', len(nts) == 1 and nts[0]['text'] == 'Plaquettes arrière à 4 mm' and nts[0]['due'] == tom and 'Plaquettes arrière à 4 mm' in pg.inner_text('#cl-panel') and pg.input_value('#cl-note') == '' and '1 note' in pg.inner_text('.tile[data-v="suivi"]'))
    pg.click('[data-act="cl-note-del"]'); pg.wait_for_timeout(250)
    check('K8c. Note deleted', store(pg)['clients/jean'].get('notes') == [] and 'Aucune note' in pg.inner_text('#cl-panel'))

    # Comptes recevables
    pg.click('.tile[data-v="recevables"]'); pg.wait_for_timeout(120)
    check('K9. Receivables: 206,96 due, F-0003, 40 days old flagged', '206,96' in pg.inner_text('.due-big') and 'F-0003' in pg.inner_text('#cl-panel') and 'il y a 40 jours' in pg.inner_text('#cl-panel') and pg.locator('#cl-panel .rec .tight').count() == 1 and 'F-0002' not in pg.inner_text('#cl-panel'))
    pg.click('[data-act="cl-remind"]'); pg.wait_for_timeout(150)
    clip = pg.evaluate('navigator.clipboard.readText().catch(function(){return ""})')
    check('K10. Payment reminder copied (name, invoice, amount, business)', 'Bonjour Jean' in clip and 'F-0003' in clip and '206,96' in clip and 'Garage Mobile Test' in clip, clip)

    # Facturation + invoice on the spot
    pg.click('.tile[data-v="factures"]'); pg.wait_for_timeout(120)
    check('K11. Facturation: both invoices, billed 413,92 / paid 206,96 / due 206,96', pg.locator('#cl-panel .row').count() == 2 and '413,92' in pg.locator('#cl-panel .stat').nth(0).inner_text() and '206,96' in pg.locator('#cl-panel .stat').nth(1).inner_text())
    pg.click('[data-act="cl-quick"]'); pg.wait_for_timeout(300)
    check('K11b. "Facture sur place" opens the form already on Jean (no search step)', pg.is_visible('#sheet') and 'Jean Tremblay' in pg.inner_text('.ccard') and pg.locator('#cs-q').count() == 0)
    pg.type('#f-svc-in', 'huile'); pg.locator('#svc-opts .opt', has_text="Changement d'huile").first.click()
    pg.click('#f-save'); pg.wait_for_timeout(350)
    pg.click('[data-act="finalize"]'); pg.wait_for_timeout(400)
    q = [(k, v) for k, v in jobs(pg).items() if v.get('clientId') == 'jean' and v.get('invoice', {}).get('number') == 'F-0004']
    check('K11c. Invoice F-0004 (103,47) saved on Jean\'s fiche, unpaid', len(q) == 1 and q[0][1]['invoice']['total'] == 103.47 and q[0][1]['invoice']['paid'] is False, [v.get('invoice', {}).get('number') for v in jobs(pg).values()])
    for a in ['back-prev', 'back']:
        if pg.locator(f'#top [data-act="{a}"]').count(): pg.click(f'#top [data-act="{a}"]'); pg.wait_for_timeout(150)
    check('K11d. Back arrows return to Jean\'s fiche', 'Jean Tremblay' in pg.inner_text('#top') and pg.locator('.tile').count() == 4, pg.inner_text('#top'))
    pg.click('.tile[data-v="recevables"]'); pg.wait_for_timeout(120)
    check('K12. Receivables now 310,43 over 2 invoices', '310,43' in pg.inner_text('.due-big') and pg.locator('#cl-panel .rec').count() == 2)
    pg.click(f'[data-act="cl-pay"][data-id="j1"]'); pg.wait_for_timeout(100)
    check('K12b. Mark paid without a method: asks for it', 'mode de paiement' in pg.inner_text('#toast').lower() and store(pg)['jobs/j1']['invoice']['paid'] is False)
    pg.select_option('#pay-j1', 'Débit'); pg.click('[data-act="cl-pay"][data-id="j1"]'); pg.wait_for_timeout(300)
    i1 = store(pg)['jobs/j1']['invoice']
    check('K12c. F-0003 paid by Débit today, lines kept; due drops to 103,47', i1['paid'] is True and i1['method'] == 'Débit' and i1['paidAt'] == td and len(i1['lines']) == 1 and '103,47' in pg.inner_text('.due-big'), i1)
    pg.screenshot(path=os.path.join(SC, 'shot_client_rec.png'), full_page=True)

    # Prendre un rendez-vous from the fiche
    pg.click('[data-act="cl-book"]'); pg.wait_for_timeout(300)
    check('K13. "Prendre un rendez-vous" opens the booking form on Jean, zone and suggestions shown', pg.is_visible('#sheet') and 'Jean Tremblay' in pg.inner_text('.ccard') and 'Zone H4P' in pg.inner_text('.ccard') and pg.locator('#cs-q').count() == 0 and pg.is_visible('#sugbox'))
    pg.fill('#f-date', tom); pg.fill('#f-time', '14:00'); pg.select_option('#f-mech', 'Marc'); pg.click('#f-save'); pg.wait_for_timeout(350)
    nb = [v for v in jobs(pg).values() if v.get('clientId') == 'jean' and v.get('time') == '14:00']
    check('K13b. Booked on Jean\'s fiche (clientId + snapshot); stays on the fiche, 2 à venir', len(nb) == 1 and nb[0]['client']['postal'] == 'H4P 2B5' and nb[0]['client']['phone'] == '(514) 555-1234' and not pg.is_visible('#sheet') and '2 à venir' in pg.inner_text('.tile.book'), (nb, pg.inner_text('.tile.book') if pg.locator('.tile.book').count() else ''))

    # edit fiche: propagates to active jobs only
    pg.click('[data-act="cl-edit"]'); pg.wait_for_timeout(200)
    check('K14. Edit form pre-filled, no delete (fiche has jobs)', pg.input_value('#c-first') == 'Jean' and pg.input_value('#c-addr') == jean['address'] and pg.locator('[data-act="cl-del"]').count() == 0 and 'reste au carnet' in pg.inner_text('main'))
    pg.fill('#c-addr', '88 rue Saint-Denis, Montréal H2X 3K8'); pg.click('#c-save'); pg.wait_for_timeout(400)
    S2 = store(pg)
    check('K14b. Fiche updated; upcoming jobs get the new address, past invoices keep the old one',
          S2['clients/jean']['postal'] == 'H2X 3K8' and S2['jobs/j3']['client']['address'] == '88 rue Saint-Denis, Montréal H2X 3K8' and S2['jobs/j3']['client']['postal'] == 'H2X 3K8'
          and S2['jobs/j1']['client']['postal'] == 'H4P 2B5' and S2['jobs/j2']['client']['postal'] == 'H4P 2B5', (S2['jobs/j3']['client'], S2['jobs/j1']['client']['postal']))

    # job <-> fiche navigation
    pg.click('.tile[data-v="suivi"]'); pg.wait_for_timeout(100)
    pg.locator('#cl-panel .vrow[data-id="j3"]').click(); pg.wait_for_timeout(150)
    check('K15. Visit opens the job; job has "Voir la fiche client"', 'Freins avant' in pg.inner_text('main') and pg.locator('main [data-act="cl-open"]').count() == 1)
    pg.click('#top [data-act="back"]'); pg.wait_for_timeout(120)
    check('K15b. Back from the job returns to the fiche', 'Jean Tremblay' in pg.inner_text('#top') and pg.locator('.tile').count() == 4)
    pg.click('.tab[data-t="agenda"]'); pg.wait_for_timeout(100)
    pg.click(f'.day[data-v="{tom}"]') if pg.locator(f'.day[data-v="{tom}"]').count() else pg.click('[data-act="week"][data-v="7"]')
    pg.wait_for_timeout(100)
    if pg.locator(f'.day[data-v="{tom}"]').count(): pg.click(f'.day[data-v="{tom}"]'); pg.wait_for_timeout(100)
    pg.locator('.appt', has_text='Jean Tremblay').first.click(); pg.wait_for_timeout(150)
    pg.click('main [data-act="cl-open"]'); pg.wait_for_timeout(150)
    check('K15c. From the agenda: job → "Voir la fiche client" opens the fiche', 'Jean Tremblay' in pg.inner_text('#top') and pg.locator('.tile').count() == 4)
    pg.click('#top [data-act="back"]'); pg.wait_for_timeout(120)
    check('K15d. Back from that fiche returns to the job', pg.locator('main [data-act="cl-open"]').count() == 1)
    pg.click('#top [data-act="back"]'); pg.wait_for_timeout(100)

    # booking from the agenda: client step search by phone
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250)
    check('K16. Booking starts with the client step, recent fiches listed', pg.is_visible('#cs-q') and pg.locator('#cs-results .crow').count() == 2 and 'clients récents' in pg.inner_text('#cs-results').lower())
    pg.fill('#cs-q', '450-555'); pg.wait_for_timeout(120)
    check('K16b. Search by phone finds Sophie', pg.locator('#cs-results .crow').count() == 1 and 'Sophie Roy' in pg.inner_text('#cs-results'))
    pg.fill('#cs-q', 'personne'); pg.wait_for_timeout(120)
    check('K16c. No match: invites to create the fiche', 'crée sa fiche' in pg.inner_text('#cs-results'))
    # client draft in the popup
    pg.click('[data-act="cs-new"]'); pg.wait_for_timeout(200)
    pg.fill('#c-first', 'Brouillon'); pg.fill('#c-phone', '5145559999'); pg.wait_for_timeout(1000)
    dr = store(pg).get('data/users/u_test/draft-client')
    check('K17. Half-filled fiche autosaved (private draft)', dr and dr['firstName'] == 'Brouillon' and dr['phone'] == '5145559999', dr)
    pg.click('.sheet-head [data-act="sheet-close"]'); pg.wait_for_timeout(150)
    pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250); pg.click('[data-act="cs-new"]'); pg.wait_for_timeout(250)
    check('K17b. Reopening restores it with a banner', pg.is_visible('#cdraftbanner') and pg.input_value('#c-first') == 'Brouillon')
    pg.click('[data-act="cd-reset"]'); pg.wait_for_timeout(250)
    check('K17c. "Recommencer" empties the form and deletes the draft', pg.input_value('#c-first') == '' and not pg.locator('#cdraftbanner').count() and 'data/users/u_test/draft-client' not in store(pg))
    pg.click('[data-act="cs-back"]'); pg.wait_for_timeout(150)
    check('K17d. "Retour à la recherche" goes back to the search', pg.is_visible('#cs-q'))
    pg.click('.sheet-head [data-act="sheet-close"]'); pg.wait_for_timeout(150)

    # ---------- weekly hours ----------
    pg.click('.chip[data-act="view"][data-v="week"]'); pg.wait_for_timeout(100)
    if wk[0] not in [pg.locator('.dayh').nth(0).get_attribute('data-v')]:
        pg.click('[data-act="today"]') if pg.locator('[data-act="today"]').count() else None; pg.wait_for_timeout(100)
    hb = pg.locator('[data-act="hours-edit"]')
    check('W20. Week view: "Ouvrir / fermer l\'horaire de la semaine" button', hb.count() == 1 and 'de la semaine' in hb.inner_text())
    hb.click(); pg.wait_for_timeout(150)
    chips = pg.locator('#hours-panel [data-act="wday-toggle"]')
    check('W21. Panel lists the 7 days with open/closed (Sunday closed)', chips.count() == 7 and 'fermé' in chips.nth(6).inner_text() and 'ouvert' in chips.nth(2).inner_text() and pg.locator('.cal.week.editing').count() == 1, [chips.nth(i).inner_text() for i in range(chips.count())])
    pg.screenshot(path=os.path.join(SC, 'shot_week_hours.png'), full_page=True)
    wed = wk[2]; sun = wk[6]
    pg.click(f'#hours-panel [data-act="wday-toggle"][data-v="{wed}"]'); pg.wait_for_timeout(200)
    check('W22. Close Wednesday: saved, column all closed', store(pg).get(f'days/{wed}', {}).get('closed') is True and pg.locator(f'.col[data-date="{wed}"] .slot.open').count() == 0 and 'fermé' in pg.locator(f'#hours-panel [data-act="wday-toggle"][data-v="{wed}"]').inner_text())
    pg.click(f'#hours-panel [data-act="wday-toggle"][data-v="{wed}"]'); pg.wait_for_timeout(200)
    check('W22b. Reopen Wednesday: back to normal (no override left)', f'days/{wed}' not in store(pg) and pg.locator(f'.col[data-date="{wed}"] .slot.open').count() > 0)
    pg.click(f'#hours-panel [data-act="wday-toggle"][data-v="{sun}"]'); pg.wait_for_timeout(200)
    check('W23. Open Sunday (normally closed) for this week only', store(pg).get(f'days/{sun}', {}).get('closed') is False and pg.locator(f'.col[data-date="{sun}"] .slot.open').count() > 0)
    pg.click(f'#hours-panel [data-act="wday-toggle"][data-v="{sun}"]'); pg.wait_for_timeout(200)
    # multi-day period
    pg.select_option('#p-from', '12:00'); pg.select_option('#p-to', '13:00')
    for i, d in enumerate(wk):
        cb = pg.locator(f'.p-day[value="{d}"]')
        if (i in (0, 1)) != cb.is_checked(): cb.click()
    pg.click('[data-act="wperiod"][data-v="close"]'); pg.wait_for_timeout(250)
    S3 = store(pg)
    bl0 = S3.get(f'days/{wk[0]}', {}).get('blocked', []); bl1 = S3.get(f'days/{wk[1]}', {}).get('blocked', [])
    check('W24. Lunch 12 h–13 h closed on Monday and Tuesday only (both mechanics, every 10 min)', len(bl0) == 12 and len(bl1) == 12 and 'Ali@12:00' in bl0 and 'Marc@12:50' in bl1 and f'days/{wk[2]}' not in S3
          and 'closed' in pg.locator(f'.col[data-date="{wk[0]}"] .slot[data-t="12:30"]').get_attribute('class') and 'open' in pg.locator(f'.col[data-date="{wk[2]}"] .slot[data-t="12:30"]').get_attribute('class'), (len(bl0), len(bl1)))
    check('W24b. Confirmation names the period and the number of days', 'Fermé de 12' in pg.inner_text('#toast') and '2 jours' in pg.inner_text('#toast'), pg.inner_text('#toast'))
    pg.click('[data-act="wperiod"][data-v="open"]'); pg.wait_for_timeout(250)
    check('W24c. "Ouvrir cette période" puts them back', not store(pg).get(f'days/{wk[0]}', {}).get('blocked') and 'open' in pg.locator(f'.col[data-date="{wk[0]}"] .slot[data-t="12:30"]').get_attribute('class'))
    for d in wk: pg.locator(f'.p-day[value="{d}"]').uncheck() if pg.locator(f'.p-day[value="{d}"]').is_checked() else None
    pg.click('[data-act="wperiod"][data-v="close"]'); pg.wait_for_timeout(120)
    check('W24d. No day ticked: asks to tick one', 'Coche au moins un jour' in pg.inner_text('#toast'))
    pg.select_option('#p-from', '14:00'); pg.select_option('#p-to', '13:00'); pg.locator(f'.p-day[value="{wk[0]}"]').check()
    pg.click('[data-act="wperiod"][data-v="close"]'); pg.wait_for_timeout(120)
    check('W24e. End before start refused', 'après le début' in pg.inner_text('#toast'))
    # single case in the week grid
    thu = wk[3]
    pg.locator(f'.col[data-date="{thu}"] .slot[data-t="15:00"]').click(); pg.wait_for_timeout(200)
    bt = store(pg).get(f'days/{thu}', {}).get('blocked', [])
    check('W25. Tap a case while editing: closes 15:00 for both mechanics, no form opened', sorted(bt) == ['Ali@15:00', 'Marc@15:00'] and not pg.is_visible('#sheet') and 'closed' in pg.locator(f'.col[data-date="{thu}"] .slot[data-t="15:00"]').get_attribute('class'), bt)
    pg.locator(f'.col[data-date="{thu}"] .slot[data-t="15:00"]').click(); pg.wait_for_timeout(200)
    check('W25b. Tap again: reopened', f'days/{thu}' not in store(pg))
    pg.click('.chip[data-act="mech"][data-v="Marc"]'); pg.wait_for_timeout(100)
    pg.locator(f'.col[data-date="{thu}"] .slot[data-t="15:00"]').click(); pg.wait_for_timeout(200)
    check('W25c. With "Marc" selected, only Marc\'s case is closed', store(pg).get(f'days/{thu}', {}).get('blocked') == ['Marc@15:00'] and 'pour Marc' in pg.inner_text('#hours-panel'))
    pg.locator(f'.col[data-date="{thu}"] .slot[data-t="15:00"]').click(); pg.wait_for_timeout(200)
    pg.click('.chip[data-act="mech"][data-v=""]'); pg.wait_for_timeout(100)
    # whole week
    pg.click('[data-act="week-close"]'); pg.wait_for_timeout(300)
    S4 = store(pg)
    check('W26. "Fermer toute la semaine": the 6 open days closed, no free case left', all(S4.get(f'days/{d}', {}).get('closed') is True for d in wk[:6]) and pg.locator('.cal.week .slot.open').count() == 0)
    check('W26b. Week strip and day headers show "fermé"', all('fermé' in pg.locator(f'.dayh[data-v="{d}"]').inner_text() or 'rdv' in pg.locator(f'.dayh[data-v="{d}"]').inner_text() for d in wk))
    pg.click('[data-act="week-reset"]'); pg.wait_for_timeout(300)
    check('W27. "Revenir à l\'horaire normal pour la semaine" removes every override', not [k for k in store(pg) if k.startswith('days/')] and pg.locator('.cal.week .slot.open').count() > 0)
    pg.click('#hours-panel [data-act="hours-edit"]'); pg.wait_for_timeout(150)
    check('W28. "Terminé" closes the panel; tapping a free case books again', pg.locator('#hours-panel').count() == 0 and pg.locator('.cal.week.editing').count() == 0)
    pg.locator(f'.col[data-date="{thu}"] .slot[data-t="15:00"]').click(); pg.wait_for_timeout(250)
    check('W28b. Booking from the week grid starts with the client step, date/time kept', pg.is_visible('#cs-q') and 'jeudi' in pg.inner_text('#sheet-sub').lower() and '15' in pg.inner_text('#sheet-sub'))
    sheet_pick_client(pg, 'sophie')
    check('W28c. After choosing the client, the form has that date and time', pg.input_value('#f-date') == thu and pg.input_value('#f-time') == '15:00' and 'Sophie Roy' in pg.inner_text('.ccard'))
    pg.click('.sheet-head [data-act="sheet-close"]'); pg.wait_for_timeout(150)
    check('K18. No script errors; no page side-scroll', not errs and no_hscroll(pg), errs[:3])
    ctx.close()

    # ---------- contributor (not admin) ----------
    ctx, pg, errs = new_page(br, {'seed': seed, 'notAdmin': True})
    pg.click('.chip[data-act="view"][data-v="week"]'); pg.wait_for_timeout(100)
    check('K19. Contributor: no hours button in week or day view', pg.locator('[data-act="hours-edit"]').count() == 0)
    pg.click('.tab[data-t="clients"]'); pg.wait_for_timeout(100)
    pg.click('#top [data-act="cl-new"]'); pg.wait_for_timeout(250)
    pg.fill('#c-first', 'Ana'); pg.fill('#c-last', 'Lopez'); pg.fill('#c-phone', '4385551212'); pg.fill('#c-addr', '9 av. du Parc, Montréal H2V 4E7'); pg.click('#c-save'); pg.wait_for_timeout(300)
    check('K19b. Contributor can create a fiche', any(v['lastName'] == 'Lopez' for v in C(pg).values()) and 'Ana Lopez' in pg.inner_text('#top'))
    check('K19c. No script errors (contributor)', not errs, errs[:3])
    ctx.close()

    # ---------- visuals: dark + wide ----------
    for scheme, w in (('dark', 390), ('light', 1100)):
        ctx, pg, errs = new_page(br, {'seed': seed}, scheme=scheme, width=w)
        pg.click('.tab[data-t="clients"]'); pg.wait_for_timeout(100)
        pg.screenshot(path=os.path.join(SC, f'shot_clients_{scheme}_{w}.png'), full_page=True)
        pg.locator('#cl-list .crow').first.click(); pg.wait_for_timeout(150)
        pg.click('.tile[data-v="recevables"]'); pg.wait_for_timeout(100)
        pg.screenshot(path=os.path.join(SC, f'shot_client_{scheme}_{w}.png'), full_page=True)
        ok = no_hscroll(pg)
        pg.click('.tab[data-t="agenda"]'); pg.click('.chip[data-act="view"][data-v="week"]'); pg.click('[data-act="hours-edit"]'); pg.wait_for_timeout(150)
        pg.screenshot(path=os.path.join(SC, f'shot_weekhours_{scheme}_{w}.png'), full_page=False)
        check(f'K20. {scheme} {w}px: no errors, no side-scroll', not errs and ok and no_hscroll(pg), errs[:3])
        ctx.close()
    br.close()
print('\n%d/%d passed' % (sum(1 for r in results if r[1]), len(results)))
