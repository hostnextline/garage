"""Estimé rapide : « Service à prix fixe » par défaut, choisi dans la liste de prix (copie locale de Supabase, vraies écritures) :
1. un nouvel estimé commence avec une ligne « Service à prix fixe » et la liste de prix (services, promos, « Autre ») ;
2. choisir un service met son nom et son prix ; « Autre service » ouvre la case pour l'écrire ;
3. « + Service à prix fixe » ajoute une autre ligne avec la liste ; un clic sur un service (puce) remplit la ligne vide ;
4. le client accepte → la job et sa facture reprennent les lignes (la facture garde ses cases texte) ;
5. téléphone : la même chose, sans défilement de côté ; en anglais, les textes sont traduits."""
import json, os, time
from team_seed import *
from playwright.sync_api import sync_playwright
otok, pw = seed()
def money_txt(p): return p.inner_text('#totdl').replace(' ', ' ').replace('\xa0', ' ')
def opts(p, sel): return p.evaluate("(s) => [...document.querySelectorAll(s + ' option')].map(o => [o.value, o.textContent])", sel)
def open_est(p):
    p.goto(BASE + '#accueil'); p.wait_for_selector('#tiles', timeout=10000)
    p.click('#tiles [data-act="est-new"]'); p.wait_for_selector('#est-box', timeout=8000); p.wait_for_timeout(300)
with sync_playwright() as pl:
    b = pl.chromium.launch()
    oc = ctx(b); op = page(oc, 'owner'); op.set_viewport_size({'width': 1300, 'height': 900}); login(op, 'hassan@garage.test', pw['hassan'])
    open_est(op)
    # ---------- 1. starts on « Service à prix fixe » ----------
    check('a new estimate starts with one line, type « Service à prix fixe »', op.locator('#lines .line').count() == 1 and op.input_value('#l0-type') == 'forfait')
    o = opts(op, '#l0-svc')
    names = [x[1] for x in o]
    check('…with the price list to choose from: « Choisir dans la liste de prix… », each service with its price, the promos, « Autre service »', o[0] == ['', 'Choisir dans la liste de prix…'] and any(n.startswith("Changement d'huile et filtre · 89,95") for n in names) and any(n.startswith('Promo') for n in names) and o[-1][0] == 'other', names)
    check('…no text box to type in until « Autre »', op.locator('#l0-desc').count() == 0)
    op.screenshot(path=os.path.join(SC, 'est_svc_start.png'))
    # ---------- 2. choose a service ----------
    op.select_option('#l0-svc', label=[n for n in names if n.startswith('Freins avant')][0]); op.wait_for_timeout(300)
    check('choosing « Freins avant (plaquettes) » puts its price (249 $) and the total with taxes (286,29 $)', op.input_value('#l0-price') == '249' and '249,00' in money_txt(op) and '286,29' in money_txt(op), (op.input_value('#l0-price'), money_txt(op)))
    # ---------- 3. « + Service à prix fixe », « Autre », the chips ----------
    op.click('#est-box [data-act="addline"][data-v="forfait"]'); op.wait_for_timeout(300)
    check('« + Service à prix fixe » adds a line with the list, ready to choose', op.locator('#lines .line').count() == 2 and op.locator('#l1-svc').count() == 1 and op.evaluate("document.activeElement && document.activeElement.id") == 'l1-svc')
    op.select_option('#l1-svc', 'other'); op.wait_for_timeout(300)
    check('« Autre service (écrire le nom) » : a text box to write it, ready to type', op.locator('#l1-desc').count() == 1 and op.evaluate("document.activeElement && document.activeElement.id") == 'l1-desc')
    op.fill('#l1-desc', 'Nettoyage des freins'); op.fill('#l1-price', '25'); op.wait_for_timeout(300)
    check('…written and priced: total 274 $ before taxes', '274,00' in money_txt(op), money_txt(op))
    op.select_option('#l1-svc', 'other'); op.wait_for_timeout(200)
    check('…what was written stays (« Autre » chosen again)', op.input_value('#l1-desc') == 'Nettoyage des freins')
    op.click('#est-box [data-act="addline"][data-v="forfait"]'); op.wait_for_timeout(200)
    op.evaluate("[...document.querySelectorAll('#est-box [data-act=\"addsvc\"]')].filter(b => /^Inspection multipoints ·/.test(b.textContent.trim()))[0].click()"); op.wait_for_timeout(300)
    check('a service chip fills the empty line (no extra line): 3 lines, the 3rd « Inspection multipoints »', op.locator('#lines .line').count() == 3 and op.input_value('#l2-svc') == 's:2', (op.locator('#lines .line').count(), op.input_value('#l2-svc') if op.locator('#l2-svc').count() else None))
    op.select_option('#l2-svc', ''); op.wait_for_timeout(200)
    check('« Choisir dans la liste… » again empties that line (price gone)', op.input_value('#l2-price') == '' and '274,00' in money_txt(op), money_txt(op))
    op.click('#est-box [data-act="addline"][data-v="piece"]'); op.wait_for_timeout(200)
    check('« + Pièce » still gives a part line with its text box', op.input_value('#l3-type') == 'piece' and op.locator('#l3-desc').count() == 1 and op.locator('#l3-svc').count() == 0)
    op.click('#lines .line[data-i="3"] [data-act="delline"]'); op.wait_for_timeout(200)
    # ---------- 4. accepted → the job and its invoice ----------
    op.click('[data-act="est-yes"]'); op.wait_for_timeout(400)
    check('« Le client accepte » : estimate of 315,03 $', '315,03' in txt(op, '#sheet').replace(' ', ' ').replace('\xa0', ' '), txt(op, '#sheet')[:120])
    op.click('#sheet [data-act="est-go"][data-v="now"]'); op.wait_for_selector('#cs-q', timeout=8000)
    op.fill('#cs-q', 'Marie'); op.wait_for_timeout(400); op.locator('#cs-results .crow').first.click(); op.wait_for_selector('#jobform', timeout=8000); op.wait_for_timeout(400)
    check('…the job has the services of the estimate', 'Freins avant (plaquettes)' in op.inner_text('#jobform') and 'Nettoyage des freins' in op.inner_text('#jobform'))
    op.evaluate("document.getElementById('jobform').requestSubmit()"); op.wait_for_selector('#lines .line', timeout=10000); op.wait_for_timeout(500)
    descs = op.evaluate("[...document.querySelectorAll('#lines .line input[data-f=\"desc\"]')].map(i => i.value)")
    check('…its invoice starts from the estimate (the empty line left out), with its usual text boxes', descs == ['Freins avant (plaquettes)', 'Nettoyage des freins'] and op.locator('#lines [data-f="svc"]').count() == 0 and op.locator('[data-act="addline"][data-v="forfait"]').count() == 0, descs)
    ej = json.loads(psql("select coalesce(json_agg(data->'estimate'), '[]') from public.docs where path like 'jobs/%' and data ? 'estimate'"))
    check('…saved on the job: 2 lines, both « Service à prix fixe », total 315,03 $', len(ej) == 1 and [l['type'] for l in ej[0]['lines']] == ['forfait', 'forfait'] and ej[0]['total'] == 315.03, ej)
    op.click('[data-act="back-inv"]'); op.wait_for_timeout(400)
    check('computer: no errors', not ERRS, ERRS[:3])
    # ---------- 5. phone, English ----------
    pc = ctx(b, phone=True); pp = page(pc, 'owner-phone'); login(pp, 'hassan@garage.test', pw['hassan'])
    pp.goto(BASE + '#jour'); pp.wait_for_timeout(700)
    pp.evaluate("() => { window.__garageApi.S.est = null; }")
    pp.click('.tab-new'); pp.wait_for_timeout(400)
    pp.click('#sheet [data-act="ph-go"][data-v="est"]')
    pp.wait_for_selector('#est-box', timeout=8000); pp.wait_for_timeout(300)
    check('phone: the estimate starts on « Service à prix fixe » with the price list', pp.input_value('#l0-type') == 'forfait' and pp.locator('#l0-svc').count() == 1)
    check('phone: no sideways scroll', no_hscroll(pp))
    pp.screenshot(path=os.path.join(SC, 'est_svc_phone.png'))
    check('phone: no errors', not ERRS, ERRS[:3])
    ec = ctx(b); ec.add_init_script("try { localStorage.setItem('gm.lang', 'en'); } catch(e){}"); ep = page(ec, 'owner en'); ep.set_viewport_size({'width': 1300, 'height': 900}); login(ep, 'hassan@garage.test', pw['hassan'])
    open_est(ep)
    eo = [x[1] for x in opts(ep, '#l0-svc')]
    check('English: « Fixed-price service », « Choose from the price list… », « Other service (type the name) », « + Fixed-price service »', 'Fixed-price service' in txt(ep, '#l0-type') and eo[0] == 'Choose from the price list…' and eo[-1] == 'Other service (type the name)' and '+ Fixed-price service' in txt(ep, '#est-box'), (eo[:1], eo[-1:], txt(ep, '#l0-type')))
    check('English: the services in the list are in English (« Oil and filter change · $89.95 »)', any(n.startswith('Oil and filter change · $89.95') for n in eo), eo)
    check('English: no errors', not ERRS, ERRS[:3])
    b.close()
summary()
