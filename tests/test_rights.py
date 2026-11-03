"""Droits par personne et plusieurs rôles (Équipe et accès) : à l'invitation et en modifiant une personne,
ce que l'écran montre et ce que le serveur accepte ; + les couleurs de l'app suivies par toute l'équipe.
Copie locale de Supabase ; tout est remis comme au départ."""
import datetime as dt
from team_seed import *
from playwright.sync_api import sync_playwright
def rpc(tok, name, body): return http('POST', API + '/rest/v1/rpc/' + name, body, tok)
def refused(r): return isinstance(r, dict) and r.get('_status', 200) >= 400
TABS = ['accueil', 'agenda', 'jour', 'clients', 'factures', 'tresor', 'carte', 'reglages', 'plus']
def tabs(p): return [t for t in TABS if p.locator('.tab[data-t="%s"]' % t).count() and p.is_visible('.tab[data-t="%s"]' % t)]
def rights(p, pre):
    """the person's rights list: {key: [checked, disabled, state text]}"""
    return p.evaluate("""(pre) => { const o = {}; document.querySelectorAll('#' + pre + '-rights input[data-k]').forEach(e => { o[e.dataset.k] = [e.checked, e.disabled, e.closest('label').querySelector('.small').textContent.split(' · ')[0]]; }); return o; }""", pre)
def member(uid): return json.loads(psql("select json_build_object('roles', roles, 'role', role, 'perms', perms, 'mechanic', mechanic) from public.members where user_id='%s'" % uid))
otok, pw = seed()
uid = {k: psql("select id from auth.users where email='%s@garage.test'" % k) for k in ('hassan', 'saleh', 'ali', 'nadia', 'lina')}
CFG0 = doc('config/main')
doc_set(otok, 'config/main', dict(CFG0, mechanics=CFG0['mechanics'] + ['Rami']))   # a new mechanic name in the agenda for the new person
EXP = {'date': TODAY, 'amount': 42.5, 'category': 'Pièces', 'note': 'test droits', 'createdAt': 1}
with sync_playwright() as pl:
    b = pl.chromium.launch()
    oc = ctx(b); op = page(oc, 'owner'); op.set_viewport_size({'width': 1280, 'height': 900}); login(op, 'hassan@garage.test', pw['hassan'])
    op.evaluate("location.hash = 'equipe'"); op.wait_for_selector('#eq-new', timeout=10000); op.wait_for_timeout(1000)
    # ---------- 1. inviting: roles (several) + this person's rights ----------
    rb = op.evaluate("[...document.querySelectorAll('#eq-new .rbox input[data-act=\"rb\"]')].map(e => [e.dataset.role, e.checked])")
    check('invite form: role boxes (Mécano, Bureau, Trésorier, Propriétaire), Mécano ticked to start', rb == [['mecano', True], ['bureau', False], ['tresorier', False], ['owner', False]], rb)
    r0 = rights(op, 'nw')
    check('…« Ses droits » under the roles: what a mechanic gets (clients, invoices, stock, map ticked; edit invoices and mark them paid ALWAYS; booking, money, treasury, hours not)', {k: v[0] for k, v in r0.items()} == {'book': False, 'clients': True, 'factures': True, 'editinv': True, 'money': False, 'tresor': False, 'stock': True, 'map': True, 'hours_others': False} and all(v[2] == 'Comme son rôle' for k, v in r0.items() if k != 'editinv') and r0['editinv'][2] == 'Toujours, avec son rôle', r0)
    op.check('#nw-r-tresorier'); op.wait_for_timeout(300)
    r1 = rights(op, 'nw')
    check('tick « Trésorier » too: the list adds what the treasurer gets (treasury always ✓, the figures, the agenda and invoice boxes)', r1.get('tresor') == [True, True, 'Toujours, avec son rôle'] and r1.get('money', [None])[0] is True and 'agenda' in r1 and 'editinv' in r1, r1)
    op.uncheck('#nw-p-map'); op.wait_for_timeout(250); op.check('#nw-p-book'); op.wait_for_timeout(250)
    r2 = rights(op, 'nw')
    check('untick « Voir la carte », tick « Prendre des rendez-vous »: each line says it is changed for this person', r2['map'][2] == 'Enlevé pour cette personne' and r2['book'][2] == 'Ajouté pour cette personne' and not r2['map'][0] and r2['book'][0], r2)
    op.check('#nw-p-map'); op.wait_for_timeout(250)
    check('tick it back: « Comme son rôle » again', rights(op, 'nw')['map'][2] == 'Comme son rôle')
    op.uncheck('#nw-p-map'); op.wait_for_timeout(250)
    op.fill('#nw-name', 'Rami Deux-Rôles'); op.fill('#nw-email', 'rami@garage.test')
    op.select_option('#nw-mech', 'Rami')
    op.click('#eq-new summary'); op.click('[data-act="eq-add"]'); op.wait_for_selector('.created', timeout=15000)
    rami = psql("select id from auth.users where email='rami@garage.test'")
    mr = member(rami)
    check('account created with BOTH roles and HIS rights (no map, booking yes) — the main role is mechanic', sorted(mr['roles']) == ['mecano', 'tresorier'] and mr['role'] == 'mecano' and mr['perms'] == {'map': False, 'book': True}, mr)
    row = op.locator('.eqp', has_text='rami@garage.test')
    check('the list shows his two roles', row.locator('.pillx.r-mecano').count() == 1 and row.locator('.pillx.r-tresorier').count() == 1, row.inner_text()[:120])
    rpw = op.evaluate("document.querySelector('.created .pw').textContent")
    # ---------- 2. what Rami gets: screen and server ----------
    rtok = token('rami@garage.test', rpw)
    check('server: his treasury (expenses) — the treasurer role', not refused(rpc(rtok, 'doc_set', {'p_path': 'expenses/zz-rami', 'p_data': EXP})) and doc('expenses/zz-rami') is not None)
    check('server: the team map is refused to him (his box unticked)', refused(rpc(rtok, 'team_map', {'p_day': TODAY})))
    rc = ctx(b); rp = page(rc, 'rami'); rp.set_viewport_size({'width': 1280, 'height': 900}); login(rp, 'rami@garage.test', rpw); rp.wait_for_timeout(1500)
    t = tabs(rp)
    check('his screen: Trésorerie and the agenda, no map tab', 'tresor' in t and 'agenda' in t and 'carte' not in t, t)
    rc.close()
    # ---------- 3. changing someone: add a role, take a right away ----------
    op.reload(); op.wait_for_timeout(800); op.evaluate("location.hash = 'equipe'"); op.wait_for_selector('.eqp', timeout=10000); op.wait_for_timeout(600)
    op.locator('.eqp', has_text='ali@garage.test').locator('[data-act="eq-edit"]').click(); op.wait_for_timeout(400)
    check('« Modifier » Ali: his roles (Mécano) and his rights, as his role gives', op.is_checked('#ed-r-mecano') and not op.is_checked('#ed-r-tresorier') and all(v[2] == 'Comme son rôle' for k, v in rights(op, 'ed').items() if k != 'editinv') and rights(op, 'ed')['editinv'][2] == 'Toujours, avec son rôle')
    op.check('#ed-r-tresorier'); op.wait_for_timeout(300); op.uncheck('#ed-p-clients'); op.wait_for_timeout(250)
    op.click('[data-act="eq-save"]'); op.wait_for_timeout(1500)
    ma = member(uid['ali'])
    check('saved: Ali is mechanic + treasurer, without « Voir les clients »', sorted(ma['roles']) == ['mecano', 'tresorier'] and ma['perms'] == {'clients': False}, ma)
    atok = token('ali@garage.test', pw['ali'])
    check('server: Ali may now add an expense', not refused(rpc(atok, 'doc_set', {'p_path': 'expenses/zz-ali', 'p_data': EXP})) and doc('expenses/zz-ali') is not None)
    ac = ctx(b, phone=True); ap = page(ac, 'ali'); login(ap, 'ali@garage.test', pw['ali']); ap.wait_for_timeout(1500)
    check('Ali\'s phone: no Clients tab any more (his box), still his day', 'clients' not in tabs(ap) and 'jour' in tabs(ap), tabs(ap))
    ap.click('.tab[data-t="plus"]'); ap.wait_for_timeout(400)
    check('…and « Trésorerie » in his Plus', ap.locator('#tiles .tile', has_text='Trésorerie').count() >= 1)
    ac.close()
    op.locator('.eqp', has_text='ali@garage.test').locator('[data-act="eq-edit"]').click(); op.wait_for_timeout(400)
    ra = rights(op, 'ed')
    check('opening Ali again: « Enlevé pour cette personne » on « Voir les clients »', ra['clients'][2] == 'Enlevé pour cette personne' and not ra['clients'][0], ra.get('clients'))
    op.check('#ed-p-clients'); op.wait_for_timeout(250)
    op.uncheck('#ed-r-tresorier'); op.wait_for_timeout(300)
    check('take « Trésorier » away: the treasurer lines leave the list (« edit invoices » stays: always for a mechanic), « Voir les clients » stays as you set it', rights(op, 'ed').get('editinv', [None, None, ''])[2] == 'Toujours, avec son rôle' and rights(op, 'ed')['clients'] == [True, False, 'Comme son rôle'], rights(op, 'ed'))
    op.click('[data-act="eq-save"]'); op.wait_for_timeout(1500)
    ma = member(uid['ali'])
    check('saved: Ali back to mechanic only, nothing special', ma['roles'] == ['mecano'] and ma['perms'] == {}, ma)
    check('server: no more expenses for Ali', refused(rpc(atok, 'doc_set', {'p_path': 'expenses/zz-ali2', 'p_data': EXP})) and doc('expenses/zz-ali2') is None)
    # ---------- 4. one right for one mechanic: the garage hours ----------
    op.locator('.eqp', has_text='saleh@garage.test').locator('[data-act="eq-edit"]').click(); op.wait_for_timeout(400)
    op.check('#ed-p-hours_others'); op.wait_for_timeout(250); op.click('[data-act="eq-save"]'); op.wait_for_timeout(1500)
    stok = token('saleh@garage.test', pw['saleh'])
    day = (dt.date.fromisoformat(TODAY) + dt.timedelta(days=9)).isoformat()
    check('Saleh with « Changer l\'horaire du garage et des autres »: the server lets him close a day and change Ali\'s hours', not refused(rpc(stok, 'doc_set', {'p_path': 'days/' + day, 'p_data': {'closed': True}})) and not refused(rpc(stok, 'doc_set', {'p_path': 'avail/ali', 'p_data': {'mechanic': 'Ali', 'week': {'1': {'on': True, 'start': '09:00', 'end': '15:00'}}}})))
    op.locator('.eqp', has_text='saleh@garage.test').locator('[data-act="eq-edit"]').click(); op.wait_for_timeout(400)
    op.uncheck('#ed-p-hours_others'); op.wait_for_timeout(250); op.click('[data-act="eq-save"]'); op.wait_for_timeout(1500)
    check('box taken away: refused again (another day, Ali\'s hours)', refused(rpc(stok, 'doc_set', {'p_path': 'days/' + (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat(), 'p_data': {'closed': True}})) and refused(rpc(stok, 'doc_set', {'p_path': 'avail/ali', 'p_data': {'mechanic': 'Ali'}})))
    check('…his own availability: still his', not refused(rpc(stok, 'doc_set', {'p_path': 'avail/saleh', 'p_data': {'mechanic': 'Saleh', 'week': {'1': {'on': True, 'start': '08:00', 'end': '17:00'}}}})))
    # ---------- 5. the owner keeps his own owner role ----------
    op.locator('.eqp', has_text='hassan@garage.test').locator('[data-act="eq-edit"]').click(); op.wait_for_timeout(400)
    check('the owner\'s own rights: « il peut tout faire »', 'peut tout faire' in txt(op, '#ed-rights'))
    op.uncheck('#ed-r-owner'); op.check('#ed-r-bureau'); op.click('[data-act="eq-save"]'); op.wait_for_timeout(800)
    check('he cannot take away his own owner role (screen), nor through the server', member(uid['hassan'])['role'] == 'owner' and toast_has(op, 'propriétaire') and fn(otok, 'members', {'action': 'update', 'user_id': uid['hassan'], 'roles': ['bureau']}).get('error') is not None and member(uid['hassan'])['role'] == 'owner')
    op.click('[data-act="eq-cancel"]'); op.wait_for_timeout(300)
    # ---------- 6. the colors of the app, for the whole team ----------
    sc = ctx(b, phone=True); sp = page(sc, 'saleh'); login(sp, 'saleh@garage.test', pw['saleh']); sp.wait_for_timeout(1500)
    check('Saleh\'s phone: Sable to start', sp.evaluate("document.documentElement.getAttribute('data-lux')") is None)
    op.evaluate("location.hash = 'reglages'"); op.wait_for_timeout(700)
    op.locator('.ph-row[data-act="ph-sec"]', has_text='Couleurs').first.click(); op.wait_for_timeout(300)
    op.click('.lux-sw[data-v="emeraude"]'); op.wait_for_timeout(1500)
    check('the owner picks « Émeraude »: saved for the garage', (doc('config/main') or {}).get('lux') == 'emeraude')
    try: sp.wait_for_function("document.documentElement.getAttribute('data-lux') === 'emeraude'", timeout=22000); ok = True
    except Exception: ok = False
    check('…Saleh\'s phone changes by itself (no reload; here within 15 s), dark emerald and gold', ok and sp.evaluate("document.documentElement.getAttribute('data-theme')") == 'dark')
    sp.screenshot(path='rights_saleh_emeraude.png')
    sp.reload(); sp.wait_for_timeout(300)
    check('…and opens in those colors next time, right away', sp.evaluate("document.documentElement.getAttribute('data-lux')") == 'emeraude')
    check('Saleh cannot change the colors (server refuses the settings)', refused(rpc(stok, 'doc_merge', {'p_path': 'config/main', 'p_patch': {'lux': 'noir'}})) and (doc('config/main') or {}).get('lux') == 'emeraude')
    op.click('.lux-sw[data-v="sable"]'); op.wait_for_timeout(1500)
    try: sp.wait_for_function("document.documentElement.getAttribute('data-lux') === null", timeout=22000); ok = True
    except Exception: ok = False
    check('back to Sable: Saleh\'s phone follows', ok)
    sc.close(); oc.close()
    b.close()
# back to the start
fn(otok, 'members', {'action': 'remove', 'user_id': rami}) if rami else None
for pth in ('expenses/zz-rami', 'expenses/zz-ali', 'days/' + day, 'avail/ali', 'avail/saleh'): rpc(otok, 'doc_delete', {'p_path': pth})
doc_set(otok, 'config/main', CFG0)
check('back to the start: Rami removed, test expenses and hours removed, settings as before', psql("select count(*) from auth.users where email='rami@garage.test'") == '0' and doc('expenses/zz-rami') is None and doc('expenses/zz-ali') is None and doc('days/' + day) is None and doc('config/main') == CFG0 and member(uid['saleh'])['perms'] == {} and member(uid['ali'])['roles'] == ['mecano'], [psql("select count(*) from auth.users where email='rami@garage.test'"), doc('config/main') == CFG0])
check('no page errors', not ERRS, ERRS[:5])
summary()
