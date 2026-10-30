/* Version équipe du carnet : connexion par personne + carnet partagé (Supabase).
   Remplace le runtime claude.ai par :
   - db : les mêmes documents (jobs, clients, days, config…), gardés dans Supabase, avec les droits de chaque rôle,
   - user : la personne connectée et son rôle,
   - downloads / mcp : comme la version rapide (téléchargement normal, recherche d'adresse en direct). */
(function(){
  var CFG = window.GARAGE_CFG || {};
  var ready, setReady, failReady;
  ready = new Promise(function(res, rej){ setReady = res; failReady = rej; });
  var T = {sb:null, session:null, member:null, uid:null, ready:ready, listeners:[]};
  window.__supa = T;

  function clone(o){ return o == null ? o : JSON.parse(JSON.stringify(o)); }
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function lsGet(k){ try { return localStorage.getItem(k); } catch(e){ return null; } }
  function lsSet(k, v){ try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch(e){} }
  function err(code, msg){ var e = new Error(msg || code); e.code = code; return e; }
  function mapErr(e){
    if (!e) return err('unknown');
    var m = String(e.message || e.details || e), c = e.code;
    if (c === '42501' || /row-level security|not_granted|permission denied/i.test(m)) return err('not_granted', m);
    if (c === 'P0002') return err('invalid_argument', m);
    if (/fetch|network|Failed to|timeout|Load failed/i.test(m)) return err('unavailable', m);
    return err('invalid_argument', m);
  }

  /* ---------- the shared notebook: same calls as claude.use('db') ---------- */
  var cols = {};       // col -> {docs:{id:data}, loaded, since, listeners:[], docListeners:{id:[fn]}, loading}
  var seq = 0;
  function colOf(path){ return path.split('/').slice(0, -1).join('/'); }
  function idOf(path){ return path.split('/').pop(); }
  function C(col){ return cols[col] || (cols[col] = {docs:{}, loaded:false, since:null, listeners:[], docListeners:{}, loading:null, full:0}); }
  function freeze(o){ if (o && typeof o === 'object'){ Object.freeze(o); Object.keys(o).forEach(function(k){ freeze(o[k]); }); } return o; }
  function snapDoc(col, id){ var d = C(col).docs[id]; return {id:id, exists:d !== undefined, data:function(){ return d === undefined ? undefined : freeze(clone(d)); }, metadata:{fromCache:false, hasPendingWrites:false}}; }
  function snapCol(col){ var c = C(col), docs = Object.keys(c.docs).sort().map(function(id){ return snapDoc(col, id); }); return {docs:docs, size:docs.length, empty:!docs.length, docChanges:function(){ return []; }, metadata:{fromCache:false, hasPendingWrites:false}}; }
  function notify(col, ids){
    var c = C(col);
    setTimeout(function(){
      c.listeners.slice().forEach(function(f){ try { f(snapCol(col)); } catch(e){} });
      (ids || Object.keys(c.docListeners)).forEach(function(id){ (c.docListeners[id] || []).slice().forEach(function(f){ try { f(snapDoc(col, id)); } catch(e){} }); });
    }, 0);
  }
  function since(c){ return c.since ? new Date(Date.parse(c.since) - 30000).toISOString() : null; }
  /* first time: everything (page by page); after: only what changed, plus what was deleted */
  function load(col, full){
    var c = C(col);
    if (c.loading) return c.loading.then(function(){ return full ? load(col, true) : null; });
    var sb = T.sb, start = (full || !c.loaded) ? null : since(c), changed = {}, maxAt = c.since;
    function page(from){
      var q = sb.from('docs').select('id,data,updated_at').eq('col', col).order('updated_at', {ascending:true}).order('path', {ascending:true}).range(from, from + 999);
      if (start) q = q.gte('updated_at', start);
      return q.then(function(r){
        if (r.error) throw mapErr(r.error);
        r.data.forEach(function(x){ changed[x.id] = x.data; if (!maxAt || x.updated_at > maxAt) maxAt = x.updated_at; });
        if (r.data.length === 1000) return page(from + 1000);
      });
    }
    var gone = [];
    var p = page(0).then(function(){
      if (!start) return;
      return sb.from('docs_deleted').select('path,deleted_at').eq('col', col).gte('deleted_at', start).then(function(r){
        if (r.error) return;
        r.data.forEach(function(x){ gone.push({id:idOf(x.path), at:x.deleted_at}); });
      });
    }).then(function(){
      var ids = [];
      if (!start){ Object.keys(c.docs).forEach(function(id){ if (!(id in changed)){ delete c.docs[id]; ids.push(id); } }); }
      Object.keys(changed).forEach(function(id){ if (JSON.stringify(c.docs[id]) !== JSON.stringify(changed[id])){ c.docs[id] = changed[id]; ids.push(id); } });
      /* a deletion counts only if the document was not saved again after it */
      gone.forEach(function(g){ if (c.docs[g.id] !== undefined && !(g.id in changed)){ delete c.docs[g.id]; ids.push(g.id); } });
      c.since = maxAt || c.since || new Date().toISOString();
      var first = !c.loaded; c.loaded = true; if (!start) c.full = Date.now();
      if (ids.length || first) notify(col, first ? null : ids);
      c.err = null;
    }, function(e){ c.err = e; if (!c.loaded) c.listeners.forEach(function(f){ if (f.__onErr) f.__onErr(e); }); throw e; });
    c.loading = p.then(function(){ c.loading = null; }, function(){ c.loading = null; });
    return p;
  }
  var timers = {};
  function soon(col){ clearTimeout(timers[col]); timers[col] = setTimeout(function(){ if (C(col).listeners.length || Object.keys(C(col).docListeners).length) load(col, false).catch(function(){}); }, 150); }
  function watched(){ return Object.keys(cols).filter(function(k){ var c = cols[k]; return c.listeners.length || Object.keys(c.docListeners).some(function(i){ return c.docListeners[i].length; }); }); }

  function rpc(name, args){ return T.sb.rpc(name, args).then(function(r){ if (r.error) throw mapErr(r.error); return r.data; }, function(e){ throw mapErr(e); }); }
  function docRef(path){
    var col = colOf(path), id = idOf(path);
    return {
      id:id, path:path,
      get:function(){
        var c = C(col);
        if (c.loaded) return Promise.resolve(snapDoc(col, id));
        return T.sb.from('docs').select('data').eq('path', path).maybeSingle().then(function(r){
          if (r.error) throw mapErr(r.error);
          return {id:id, exists:!!r.data, data:function(){ return r.data ? freeze(clone(r.data.data)) : undefined; }, metadata:{fromCache:false, hasPendingWrites:false}};
        });
      },
      set:function(d){ var data = clone(d); return rpc('doc_set', {p_path:path, p_data:data}).then(function(){ C(col).docs[id] = data; notify(col, [id]); }); },
      update:function(d){ return rpc('doc_merge', {p_path:path, p_patch:clone(d)}).then(function(out){ C(col).docs[id] = out; notify(col, [id]); }); },
      delete:function(){ return rpc('doc_delete', {p_path:path}).then(function(){ if (C(col).docs[id] !== undefined){ delete C(col).docs[id]; notify(col, [id]); } }); },
      acquire:function(){ return Promise.resolve({acquired:true, version:1}); },
      onSnapshot:function(n, onErr){
        var c = C(col); (c.docListeners[id] = c.docListeners[id] || []).push(n);
        if (c.loaded) setTimeout(function(){ n(snapDoc(col, id)); }, 0); else load(col, true).catch(function(e){ if (onErr) onErr(e); });
        return function(){ c.docListeners[id] = (c.docListeners[id] || []).filter(function(f){ return f !== n; }); };
      },
      collection:function(p){ return colRef(path + '/' + p); }
    };
  }
  function newId(){ var a = 'abcdefghijklmnopqrstuvwxyz0123456789', b = new Uint8Array(20), s = ''; (window.crypto || {}).getRandomValues ? crypto.getRandomValues(b) : b.forEach(function(_, i){ b[i] = Math.random() * 256; }); for (var i = 0; i < 20; i++) s += a[b[i] % 36]; return s; }
  function colRef(path){
    return {
      path:path,
      doc:function(id){ return docRef(path + '/' + (id || newId())); },
      onSnapshot:function(n, onErr){
        var c = C(path); if (onErr) n.__onErr = onErr; c.listeners.push(n);
        if (c.loaded) setTimeout(function(){ n(snapCol(path)); }, 0); else load(path, true).catch(function(e){ if (onErr) onErr(e); });
        return function(){ c.listeners = c.listeners.filter(function(f){ return f !== n; }); };
      },
      get:function(){ return load(path, !C(path).loaded).then(function(){ return snapCol(path); }); }
    };
  }
  var db = Object.freeze({doc:docRef, collection:colRef});
  T.db = db;
  T.resync = function(full){ return Promise.all(watched().map(function(col){ return load(col, !!full).catch(function(){}); })); };

  /* live updates: instant when the realtime service answers, otherwise every 15 s */
  var live = false, hiddenAt = 0;
  function startSync(){
    try {
      T.sb.channel('carnet').on('postgres_changes', {event:'*', schema:'public', table:'docs'}, function(p){
        var path = (p.new && p.new.path) || (p.old && p.old.path); if (path) soon(colOf(path));
      }).subscribe(function(st){ live = st === 'SUBSCRIBED'; });
    } catch(e){ live = false; }
    setInterval(function(){
      if (document.visibilityState === 'hidden') return;
      watched().forEach(function(col){ var c = C(col), full = Date.now() - c.full > 10 * 60000; if (full || !live || Date.now() % 60000 < 15000) load(col, full).catch(function(){}); });
    }, 15000);
    document.addEventListener('visibilitychange', function(){
      if (document.visibilityState === 'hidden'){ hiddenAt = Date.now(); return; }
      T.resync(hiddenAt && Date.now() - hiddenAt > 5 * 60000);
    });
    window.addEventListener('online', function(){ T.resync(false); });
  }

  /* ---------- the person who is signed in ---------- */
  var user = Object.freeze({
    id:function(){ return Promise.resolve(T.uid); },
    isOwner:function(){ return Promise.resolve(!!T.member && T.member.role === 'owner'); },
    canEdit:function(){ return Promise.resolve(!!T.member && T.member.role === 'owner'); },
    can:function(){ return Promise.resolve(!!T.member); }
  });

  var caps = {db:db, user:user, downloads:window.__webDownloads || null, mcp:window.__addrMcp || null};
  window.claude = Object.freeze({use:function(name){ return ready.then(function(){ return caps[name] || null; }, function(){ return null; }); }});

  /* ---------- sign-in screen ---------- */
  function css(){
    var st = document.createElement('style');
    st.textContent =
      '#gate{position:fixed;inset:0;z-index:60;background:var(--paper);overflow-y:auto;padding:max(24px,env(safe-area-inset-top)) 16px 32px}' +
      '#gate .g-box{max-width:420px;margin:6vh auto 0;display:grid;gap:16px}' +
      '#gate .g-brand{display:flex;align-items:center;gap:12px}#gate .g-logo{width:48px;height:48px;border-radius:12px;background:var(--steel);display:grid;place-items:center;flex:none}' +
      '#gate h1{font-size:30px}#gate form{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px;display:grid;gap:14px}' +
      '#gate label{font-weight:600}#gate input{width:100%;min-height:48px;padding:10px 12px;border:1px solid var(--line-strong);border-radius:10px;background:var(--surface);color:var(--ink);font-size:17px}' +
      '#gate input:focus-visible,#gate button:focus-visible{outline:3px solid var(--signal);outline-offset:2px}' +
      '#gate .g-f{display:grid;gap:6px}#gate .g-msg{border-radius:10px;padding:10px 12px;background:var(--bad-bg);color:var(--bad);font-weight:600}#gate .g-msg.ok{background:var(--ok-bg);color:var(--ok)}' +
      '#gate .g-help{color:var(--muted);font-size:14.5px}#gate .g-link{background:none;border:0;color:var(--steel);font-weight:600;text-decoration:underline;padding:6px 0;cursor:pointer;justify-self:start;min-height:40px}' +
      '#gate .g-go{min-height:50px;border-radius:10px;border:1px solid var(--signal);background:var(--signal);color:var(--on-signal);font-weight:700;font-size:17px;cursor:pointer}' +
      '#gate .g-go[disabled]{opacity:.6;cursor:wait}';
    document.head.appendChild(st);
  }
  var LOGO = '<svg viewBox="0 0 64 64" width="30" height="30" aria-hidden="true"><path d="M18 44l8-8m10-10l10-10M26 36a8 8 0 1 0 10-10" stroke="#F2B200" stroke-width="6" fill="none" stroke-linecap="round"/></svg>';
  function gate(html){
    var g = document.getElementById('gate');
    if (!g){ g = document.createElement('div'); g.id = 'gate'; g.setAttribute('role', 'dialog'); g.setAttribute('aria-modal', 'true'); g.setAttribute('aria-labelledby', 'g-title'); document.body.appendChild(g); }
    g.innerHTML = '<div class="g-box"><div class="g-brand"><div class="g-logo">' + LOGO + '</div><div><div class="eyebrow">Garage mobile · équipe</div><h1 id="g-title">' + html.title + '</h1></div></div>' + html.body + '</div>';
    g.hidden = false; document.body.classList.add('locked');
    var f = g.querySelector('input'); if (f) setTimeout(function(){ try { f.focus(); } catch(e){} }, 30);
    return g;
  }
  function closeGate(){ var g = document.getElementById('gate'); if (g) g.remove(); document.body.classList.remove('locked'); }
  function msg(text, ok){ var m = document.getElementById('g-msg'); if (!m) return; m.textContent = text || ''; m.hidden = !text; m.className = 'g-msg' + (ok ? ' ok' : ''); }
  function busy(on){ var b = document.getElementById('g-go'); if (b){ b.disabled = on; b.textContent = on ? 'Un instant…' : b.dataset.label; } }

  function showLogin(note){
    gate({title:'Connexion', body:
      '<form id="g-form" novalidate><div class="g-f"><label for="g-email">Courriel</label><input id="g-email" type="email" autocomplete="username" inputmode="email" autocapitalize="off" spellcheck="false" value="' + esc(lsGet('gm.team.email') || '') + '"></div>' +
      '<div class="g-f"><label for="g-pw">Mot de passe</label><input id="g-pw" type="password" autocomplete="current-password"></div>' +
      '<p class="g-msg" id="g-msg" role="alert" hidden></p><button class="g-go" id="g-go" data-label="Se connecter" type="submit">Se connecter</button>' +
      '<button type="button" class="g-link" id="g-forgot">Mot de passe oublié ?</button><p class="g-help" id="g-forgot-help" hidden>Demande au propriétaire du garage : il te donne un nouveau mot de passe dans Réglages → Équipe et accès.</p></form>'});
    if (note) msg(note, false);
    document.getElementById('g-forgot').onclick = function(){ document.getElementById('g-forgot-help').hidden = false; };
    document.getElementById('g-form').onsubmit = function(e){
      e.preventDefault();
      var email = document.getElementById('g-email').value.trim(), pw = document.getElementById('g-pw').value;
      if (!email || !pw){ msg('Écris ton courriel et ton mot de passe.'); return; }
      busy(true); msg('');
      T.sb.auth.signInWithPassword({email:email, password:pw}).then(function(r){
        busy(false);
        if (r.error){ msg(/invalid/i.test(r.error.message) ? 'Courriel ou mot de passe incorrect.' : /banned/i.test(r.error.message) ? 'Ton accès est désactivé. Parle au propriétaire du garage.' : /fetch|network/i.test(r.error.message) ? 'Pas de connexion au serveur. Vérifie Internet.' : 'Connexion refusée : ' + r.error.message); return; }
        lsSet('gm.team.email', email);
        afterSession(r.data.session);
      }, function(){ busy(false); msg('Pas de connexion au serveur. Vérifie Internet.'); });
    };
  }
  function showSetup(){
    gate({title:'Première mise en route', body:
      '<p class="g-help">Crée le compte du propriétaire. Tu ajouteras ensuite ton équipe (bureau, mécanos) dans Réglages → Équipe et accès.</p>' +
      '<form id="g-form" novalidate><div class="g-f"><label for="g-code">Code de mise en route</label><input id="g-code" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="XXXX-XXXX-XXXX"></div>' +
      '<div class="g-f"><label for="g-name">Ton nom</label><input id="g-name" autocomplete="name"></div>' +
      '<div class="g-f"><label for="g-mech">Ton nom dans l\'agenda des mécanos <span class="g-help">(si tu fais aussi des jobs)</span></label><input id="g-mech" autocomplete="off"></div>' +
      '<div class="g-f"><label for="g-email">Courriel</label><input id="g-email" type="email" autocomplete="username" inputmode="email" autocapitalize="off" spellcheck="false"></div>' +
      '<div class="g-f"><label for="g-pw">Mot de passe <span class="g-help">(8 caractères ou plus)</span></label><input id="g-pw" type="password" autocomplete="new-password"></div>' +
      '<p class="g-msg" id="g-msg" role="alert" hidden></p><button class="g-go" id="g-go" data-label="Créer le compte du propriétaire" type="submit">Créer le compte du propriétaire</button>' +
      '<button type="button" class="g-link" id="g-have">J\'ai déjà un compte</button></form>'});
    document.getElementById('g-have').onclick = function(){ showLogin(); };
    document.getElementById('g-form').onsubmit = function(e){
      e.preventDefault();
      var v = function(id){ return document.getElementById(id).value.trim(); }, pw = document.getElementById('g-pw').value;
      if (!v('g-code') || !v('g-name') || !v('g-email') || !pw){ msg('Remplis le code, ton nom, ton courriel et le mot de passe.'); return; }
      busy(true); msg('');
      T.sb.functions.invoke('members', {body:{action:'setup', code:v('g-code'), name:v('g-name'), mechanic:v('g-mech'), email:v('g-email'), password:pw}}).then(function(r){
        if (r.error) return (r.error.context && r.error.context.json ? r.error.context.json() : Promise.resolve({})).then(function(j){ busy(false); msg((j && j.message) || 'La mise en route n\'a pas passé. Réessaie.'); if (j && j.error === 'already_setup') setTimeout(function(){ showLogin('Le garage est déjà configuré : connecte-toi.'); }, 1500); });
        return T.sb.auth.signInWithPassword({email:v('g-email'), password:pw}).then(function(s){ busy(false); if (s.error){ showLogin('Compte créé. Connecte-toi.'); return; } lsSet('gm.team.email', v('g-email')); afterSession(s.data.session); });
      }, function(){ busy(false); msg('Pas de connexion au serveur. Vérifie Internet.'); });
    };
  }
  function showNoAccess(){
    gate({title:'Pas d\'accès', body:'<div class="g-msg">Ce compte n\'a pas (ou plus) accès au carnet du garage. Parle au propriétaire.</div><button class="g-go" id="g-go" data-label="Changer de compte" type="button">Changer de compte</button>'});
    document.getElementById('g-go').onclick = function(){ T.sb.auth.signOut().then(function(){ showLogin(); }, function(){ showLogin(); }); };
  }
  function showConfigMissing(){
    gate({title:'Pas encore branché', body:'<div class="g-msg">Cette copie n\'est pas encore reliée à la base de données du garage.</div><p class="g-help">Il manque l\'adresse du serveur (fichier config.js).</p>'});
  }

  var started = false;
  function afterSession(session){
    T.session = session; T.uid = session.user.id;
    return T.sb.from('members').select('*').eq('user_id', T.uid).maybeSingle().then(function(r){
      if (r.error){ showLogin(/fetch|network/i.test(r.error.message) ? 'Pas de connexion au serveur. Vérifie Internet.' : 'Connexion refusée : ' + r.error.message); return; }
      if (!r.data || !r.data.active){ showNoAccess(); return; }
      T.member = r.data;
      closeGate();
      if (!started){ started = true; startSync(); setReady(T); T.listeners.forEach(function(f){ try { f(T); } catch(e){} }); }
    }, function(){ showLogin('Pas de connexion au serveur. Vérifie Internet.'); });
  }
  T.onReady = function(f){ if (started) f(T); else T.listeners.push(f); };
  T.signOut = function(){ return T.sb.auth.signOut().then(function(){ location.reload(); }, function(){ location.reload(); }); };

  function start(){
    css();
    if (!CFG.url || !CFG.key || !window.supabase){ showConfigMissing(); failReady(err('no_config')); return; }
    T.sb = window.supabase.createClient(CFG.url, CFG.key, {auth:{persistSession:true, autoRefreshToken:true, storageKey:'gm.team.auth', detectSessionInUrl:false}});
    T.sb.auth.onAuthStateChange(function(ev){ if (ev === 'SIGNED_OUT' && started) location.reload(); });
    T.sb.auth.getSession().then(function(r){
      var s = r.data && r.data.session;
      if (s) return afterSession(s);
      return T.sb.rpc('setup_needed').then(function(x){ if (x.data === true) showSetup(); else showLogin(); }, function(){ showLogin(); });
    }, function(){ showLogin(); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
