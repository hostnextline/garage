"""App simplifiée pour débutants : guide « Par où commencer », bulles « ? », un seul gros bouton, mots simples."""
exec(open('test_dash.py', encoding='utf8').read().split("with sync_playwright() as p:")[0])
seed['config/main']['services'] = [{'name': "Changement d'huile et filtre", 'price': 89.95}, {'name': 'Inspection multipoints', 'price': 59}]
IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
def open_raw(br, width=1280, phone=False, hash='', keep=None):
    kw = dict(viewport={'width': width, 'height': 900 if not phone else 844}, timezone_id='America/Toronto', locale='fr-CA')
    if phone: kw.update(user_agent=IPHONE, has_touch=True, is_mobile=True)
    ctx = keep or br.new_context(**kw); pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=harness({'seed': seed})) if r.request.url == 'https://local.test/' else r.abort())
    pg.goto('https://local.test/' + hash); pg.wait_for_timeout(700)
    return ctx, pg, errs
def vis_text(pg): return pg.evaluate("document.body.innerText")
def open_job(pg, i): pg.evaluate("id => { const A = window.__garageApi; A.S.screen = 'job'; A.S.jobId = id; A.S.inv = null; A.render(); window.scrollTo(0, 0); }", i); pg.wait_for_timeout(400)
BAD = ['No-show', 'no-show', 'Brouillon', 'brouillon', 'Finaliser', 'unités', ' rdv', 'North', 'Corriger le statut', '1 unité']
seen_bad = set()
def scan(pg, where):
    t = vis_text(pg)
    for w in BAD:
        if w in t: seen_bad.add(w + ' @ ' + where)
with sync_playwright() as p:
    br = p.chromium.launch()
    # ---------- ordinateur ----------
    ctx, pg, errs = open_raw(br)
    g = pg.locator('#guide')
    check('guide « Par où commencer » on the owner\'s home', g.count() == 1 and 'Par où commencer' in txt(pg, '#guide h3'))
    items = pg.eval_on_selector_all('#guide li', 'els => els.map(e => [e.className, e.innerText.split("\\n")[0].trim()])')
    check('guide: garage name/phone not done (no phone yet), first booking done', items and items[0][0] == '' and items[-1][0] == 'ok', items)
    check('guide: count « x sur y faits »', re.search(r'\d+ sur \d+ fait', txt(pg, '#guide .sect-head span')) is not None, txt(pg, '#guide .sect-head span'))
    scan(pg, 'accueil')
    pg.click('#guide li:first-child a'); pg.wait_for_timeout(500)
    check('guide step opens Réglages right at « Le garage »', pg.is_visible('#s-name') and not pg.is_visible('#s-tps') and pg.locator('.tab[data-t="reglages"][aria-current="page"]').count() == 1)
    # a « ? » bubble
    pg.click('section.cur .ph-secback'); pg.wait_for_timeout(150)
    check('Réglages: a list of parts with a line each (now with « Couleurs de l\'app »)', pg.locator('#ph-setlist .ph-row').count() == 12 and 'Façon de réserver' in txt(pg, '#ph-setlist') and 'Décharge du client' in txt(pg, '#ph-setlist') and 'TPS et TVQ' in txt(pg, '#ph-setlist') and 'Couleurs de l\'app' in txt(pg, '#ph-setlist'), txt(pg, '#ph-setlist'))
    pg.click('#ph-setlist .ph-row:has-text("Taxes")'); pg.wait_for_timeout(150)
    q = pg.locator('section.cur .qhelp').first
    q.click(); pg.wait_for_timeout(100)
    check('« ? » opens a short explanation', pg.locator('.helptip').count() == 1 and 'TPS' in txt(pg, '.helptip') and q.get_attribute('aria-expanded') == 'true', txt(pg, '.helptip'))
    q.click(); pg.wait_for_timeout(100)
    check('« ? » again closes it', pg.locator('.helptip').count() == 0 and q.get_attribute('aria-expanded') == 'false')
    pg.click('section.cur .ph-secback'); pg.click('#ph-setlist .ph-row:has-text("Factures")'); pg.wait_for_timeout(150)
    check('rare settings folded under « Options avancées »', pg.is_visible('#s-footer') and not pg.is_visible('#s-prefix') and pg.locator('section.cur details.adv summary').count() == 1)
    pg.click('section.cur details.adv summary'); pg.wait_for_timeout(100)
    check('« Options avancées » opens', pg.is_visible('#s-prefix') and pg.is_visible('#s-start'))
    scan(pg, 'reglages')
    # guide can be hidden, and stays hidden
    pg.evaluate("location.hash = 'accueil'"); pg.wait_for_timeout(300)
    pg.click('#guide [data-act="guide-off"]'); pg.wait_for_timeout(300)
    check('« Masquer ce guide » hides it', pg.locator('#guide').count() == 0)
    pg.reload(); pg.wait_for_timeout(700)
    check('guide stays hidden after reload', pg.locator('#guide').count() == 0)
    # job planned: ONE big black button, rare actions folded
    open_job(pg, 'a4')
    prim = pg.eval_on_selector_all('#main .btn.primary', 'els => els.filter(e => e.offsetParent).map(e => e.textContent.trim())')
    check('planned job (office): exactly one big black button « Le mécano part »', prim == ['Le mécano part'], prim)
    check('« Faire la facture » is a normal button until the work is done', pg.locator('#main [data-act="invoice"]:not(.primary)').count() == 1)
    mf = pg.locator('#more-fold')
    check('« Autres actions » folded, with Annuler / Client absent / Supprimer inside', mf.count() == 1 and mf.get_attribute('open') is None and not pg.is_visible('[data-act="noshow"]') and mf.locator('[data-act="noshow"]').count() == 1 and mf.locator('[data-act="del"]').count() == 1)
    check('job shows « 1 h 30 », no « unités »', '1 h 30' in txt(pg, '.when') and 'unité' not in txt(pg, '.when'), txt(pg, '.when'))
    check('steps « ? » next to the status', pg.locator('#main .sect-head .qhelp[data-k="etapes"]').count() == 1)
    pg.click('#more-fold summary'); pg.wait_for_timeout(100)
    check('« Autres actions » opens', pg.is_visible('[data-act="noshow"]') and 'Client absent' in txt(pg, '#more-fold'))
    scan(pg, 'job a4')
    open_job(pg, 'a3')
    check('job on site (office), no invoice yet: next = « Travail fini : faire la facture » (paid before leaving)', txt(pg, '.nextbtn') == 'Travail fini : faire la facture', txt(pg, '.nextbtn'))
    # invoice: a fixed-price service = one line with its price
    open_job(pg, 'a4'); pg.click('#main [data-act="invoice"]'); pg.wait_for_timeout(400)
    check('invoice pre-filled: priced services are fixed-price lines', pg.input_value('#l0-type') == 'forfait' and pg.input_value('#l0-price') == '89,95' and pg.text_content('label[for="l0-qty"]') == 'Qté', [pg.input_value('#l0-type'), pg.input_value('#l0-price')])
    n0 = pg.locator('#lines .line').count()
    pg.click('[data-act="addsvc"] >> nth=0'); pg.wait_for_timeout(200)
    last = '#l%d' % n0
    check('fixed-price service: type « Service à prix fixe », Qté × Prix (not hours × rate)',
          pg.input_value(last + '-type') == 'forfait' and 'Service à prix fixe' in pg.eval_on_selector(last + '-type', 'e => e.selectedOptions[0].textContent') and pg.text_content('label[for="%s-qty"]' % last[1:]) == 'Qté' and pg.text_content('label[for="%s-price"]' % last[1:]) == 'Prix ($)')
    check('invoice buttons in plain words', pg.text_content('#i-final').strip() == 'Terminer la facture' and pg.text_content('#i-draft').strip() == 'Finir plus tard')
    scan(pg, 'facture')
    pg.click('[data-act="back-inv"]'); pg.wait_for_timeout(300)
    pg.evaluate("location.hash = 'factures'"); pg.wait_for_timeout(300); scan(pg, 'factures')
    pg.evaluate("location.hash = 'agenda'"); pg.wait_for_timeout(300); scan(pg, 'agenda')
    check('computer agenda says « Clique », not « Touche »', 'Touche une case' not in vis_text(pg))
    check('no page errors (computer)', not errs, errs)
    ctx.close()
    # ---------- téléphone ----------
    ctx, pg, errs = open_raw(br, 390, phone=True)
    check('phone home: guide for the owner too', pg.locator('#guide').count() == 1)
    pg.evaluate("location.hash = 'jour'"); pg.wait_for_timeout(300)
    pg.evaluate("() => { const b = document.querySelector('[data-act=open][data-id=\"a4\"]'); if (b) b.click(); }"); pg.wait_for_timeout(400)
    check('phone job: one big button « Je pars »', txt(pg, '.nextbtn') == 'Je pars' and pg.eval_on_selector_all('#main .btn.primary', 'els => els.filter(e => e.offsetParent).length') == 1)
    check('phone job: step menu moved into « Autres actions »', pg.locator('#more-fold #ph-st').count() == 1 and not pg.is_visible('#ph-st') and 'Changer l\'étape à la main' in pg.text_content('#more-fold'))
    d = pg.locator('#wv-fold')
    d.locator('.qhelp').click(); pg.wait_for_timeout(100)
    check('« ? » in a fold title explains without opening the fold', d.get_attribute('open') is None and pg.locator('.helptip').count() == 1 and 'décharge' in txt(pg, '.helptip').lower())
    scan(pg, 'téléphone job')
    check('no page errors (phone)', not errs, errs)
    ctx.close()
    check('no technical / English words on the screens scanned', not seen_bad, sorted(seen_bad))
    br.close()
ok = sum(1 for r in results if r[1]); print(f'{ok}/{len(results)} passed')
