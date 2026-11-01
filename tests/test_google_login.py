"""Sign in with Google (Gmail): the button shows only once Google is turned on for the garage's server; it goes to Google
with the right return address; back from Google, the session opens; errors say what to do; an account not invited gets
« Pas d'accès » with its address. (Google itself is simulated: the real Google can't be reached from the test machine.)"""
import json, re, urllib.parse
from team_seed import *
from playwright.sync_api import sync_playwright

def settings_route(on):
    def h(r):
        if '/auth/v1/settings' in r.request.url:
            return r.fulfill(status=200, content_type='application/json', headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*'},
                             body=json.dumps({'external': {'email': True, 'google': on}, 'disable_signup': False}))
        return r.continue_()
    return h

otok, pw = seed()
with sync_playwright() as pl:
    b = pl.chromium.launch()
    # 1. Google not turned on (the real state of a new server): no button, nothing changes for anyone
    c = ctx(b, phone=True); p = page(c, 'off')
    p.goto(BASE + '#jour'); p.wait_for_selector('#gate #g-email', timeout=15000); p.wait_for_timeout(1200)
    check('Google not turned on yet: no Google button on the sign-in screen (nothing that does not work)', p.locator('#g-google').count() == 1 and p.locator('#g-google').is_hidden())
    c.close()
    # 2. turned on: the button shows, under « ou »
    c = ctx(b, phone=True); c.route(API + '/auth/v1/settings**', settings_route(True)); p = page(c, 'on')
    went = []
    def authz(r):
        went.append(r.request.url); r.fulfill(status=200, content_type='text/html', body='<p>Google (simulé)</p>')
    c.route(API + '/auth/v1/authorize**', authz)
    p.goto(BASE + '#jour'); p.wait_for_selector('#gate #g-email', timeout=15000)
    ok = wait_for(p, "!document.querySelector('#g-google').hidden", 5000)
    p.screenshot(path='google_login.png')
    check('Google turned on: « Continuer avec Google » shows under « ou », the password stays possible', ok and txt(p, '#g-google-go') == 'Continuer avec Google' and p.locator('#g-email').count() == 1)
    p.click('#g-google-go'); p.wait_for_timeout(1500)
    u = urllib.parse.urlparse(went[0]) if went else None; q = urllib.parse.parse_qs(u.query) if u else {}
    check('…it goes to Google with the return address of the app, safely (PKCE code challenge, choose the account)', bool(went) and q.get('provider') == ['google'] and q.get('redirect_to', [''])[0].startswith(BASE.rstrip('/')) and bool(q.get('code_challenge')) and 'select_account' in went[0], went[:1])
    # 3. back from Google with an error / cancelled / not turned on
    for qs, want in (('?error=access_denied&error_description=User+cancelled', 'annulée'),
                     ('?error=server_error&error_description=Unsupported+provider%3A+provider+is+not+enabled', 'pas encore activée'),
                     ('?error=server_error&error_description=Signups+not+allowed+for+this+instance', 'pas invité'),
                     ('?code=pas-un-vrai-code', 'n\'a pas marché')):
        p.goto(BASE + qs); p.wait_for_selector('#gate #g-msg:not([hidden])', timeout=15000)
        m = txt(p, '#g-msg')
        check('back from Google (%s): « %s… », the address is cleaned' % (qs.split('&')[0], m[:60]), want in m and '?' not in p.evaluate('location.href'), [m, p.evaluate('location.href')])
    c.close()
    # 4. the invitation page: Google offered only for that same address
    r = fn(otok, 'members', {'action': 'invite', 'name': 'Gabriel Test', 'email': 'gabriel.test@gmail.com', 'role': 'bureau', 'base': BASE})
    link = r.get('link', '') if isinstance(r, dict) else ''
    if not link: print('invite answer:', str(r)[:300])
    c = ctx(b, phone=True); c.route(API + '/auth/v1/settings**', settings_route(True)); p = page(c, 'inv')
    if link:
        p.goto(BASE + '#' + link.split('#', 1)[1]); p.wait_for_selector('#g-pw2', timeout=15000)
        ok = wait_for(p, "!document.querySelector('#g-google').hidden", 5000)
        p.screenshot(path='google_invite.png')
    check('invitation page: « Continuer avec Google » too, only if that address is the Google account (no password then)', bool(link) and ok and 'gabriel.test@gmail.com' in txt(p, '#g-google') and 'pas besoin de mot de passe' in txt(p, '#g-google'), link[:40])
    c.close()
    # 5. someone signed in with an account that is not in the team: « Pas d'accès », with the address and what to do
    stranger = 'inconnu.test@gmail.com'
    psql("delete from auth.users where email='%s'" % stranger)
    sr = fn(otok, 'members', {'action': 'create', 'name': 'Inconnu Test', 'email': stranger, 'role': 'bureau', 'password': 'Inconnu-12345'})
    psql("delete from public.members where name='Inconnu Test'")   # an account that exists, but is not (or no longer) in the team
    c = ctx(b, phone=True); p = page(c, 'stranger')
    p.goto(BASE + '#jour'); p.wait_for_selector('#gate #g-email', timeout=15000)
    p.fill('#g-email', stranger); p.fill('#g-pw', 'Inconnu-12345'); p.click('#g-go')
    ok = wait_for(p, "document.querySelector('#g-title') && document.querySelector('#g-title').textContent.includes('accès')", 10000)
    check('an account that is not in the team (e.g. a Gmail never invited): « Pas d\'accès » with its address, nothing of the garage shows', ok and stranger in txt(p, '#gate') and p.locator('#main .ph-job, #main .nrow').count() == 0, txt(p, '#gate')[:120])
    c.close()
    b.close()
# back to the start
psql("delete from public.invites where email='gabriel.test@gmail.com'"); psql("delete from public.members where name='Gabriel Test'"); psql("delete from auth.users where email in ('gabriel.test@gmail.com', 'inconnu.test@gmail.com')")
check('back to the start (test accounts removed)', psql("select count(*) from auth.users where email in ('gabriel.test@gmail.com', 'inconnu.test@gmail.com')") == '0')
check('no page errors', not [e for e in ERRS if 'authorize' not in e], ERRS[:5])
summary()
