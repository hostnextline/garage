/* Version équipe : rôles, journée de travail (position), bouton « En route », carte des mécanos, équipe et accès.
   S'appuie sur supa.js (connexion, carnet partagé) et sur window.__garageApi (le carnet). */
(function(){
  var T = window.__supa; if (!T) return;
  function A(){ return window.__garageApi; }
  var me = null;
  /* « Voir comme… » : the owner sees the app exactly as a mechanic, the treasurer or the office sees it.
     His own account stays behind it: what he changes is saved under his name. */
  var VA = null;
  try { VA = JSON.parse(sessionStorage.getItem('gm.viewas') || 'null'); } catch(e){ VA = null; }
  /* a person can have several roles (members.roles); members.role is the main one (owner > bureau > mecano > tresorier) */
  function rolesOf(m){ return m ? (m.roles && m.roles.length ? m.roles.slice() : [m.role]) : []; }
  function hasR(m, r){ return rolesOf(m).indexOf(r) >= 0; }
  function mainRole(rs){ return rs.indexOf('owner') >= 0 ? 'owner' : rs.indexOf('bureau') >= 0 ? 'bureau' : rs.indexOf('mecano') >= 0 ? 'mecano' : 'tresorier'; }
  function rolesLabel(m){ return rolesOf(m).sort(function(a, b){ return ['owner','bureau','mecano','tresorier'].indexOf(a) - ['owner','bureau','mecano','tresorier'].indexOf(b); }).map(function(r){ return ROLE[r]; }).join(' + '); }
  function previewing(){ return !!(me && VA && hasR(me, 'owner')); }
  function eff(){
    if (!previewing()) return me;
    var rs = VA.roles && VA.roles.length ? VA.roles.slice() : [VA.role || 'mecano'];
    return {role:mainRole(rs), roles:rs, mechanic:VA.mechanic || null, name:VA.name, perms:VA.perms || {}, user_id:me.user_id, active:true, preview:true};
  }
  var X = {tracks:{}, trackLoading:{}, trackSt:{}, busy:{}, quiet:{}, live:[], members:[], active:[], showPath:{}, paths:{}, pathBusy:{}, eq:{list:null, err:'', created:null, secrets:null, confirm:null, editing:null, draft:{}}, enRoute:null, near:false, warnedNear:false, roles:{}};
  var ROLE = {owner:'Propriétaire', bureau:'Bureau', mecano:'Mécano', tresorier:'Trésorier'};

  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function norm(s){ return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim(); }
  function toast(m){ var a = A(); if (a && m) a.toast(m); }
  function render(){ var a = A(); if (a) a.render(); }
  function lsGet(k){ try { return localStorage.getItem(k); } catch(e){ return null; } }
  function lsSet(k, v){ try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch(e){} }
  var TF = new Intl.DateTimeFormat('fr-CA', {hour:'numeric', minute:'2-digit'});
  function clock(iso){ if (!iso) return ''; return TF.format(new Date(iso)).replace(/\s/g, ' '); }
  function ago(t){ if (!t) return 'jamais'; var s = Math.max(0, Math.round((Date.now() - (typeof t === 'number' ? t : Date.parse(t))) / 1000)); return s < 45 ? 'il y a ' + Math.max(s, 1) + ' s' : s < 3600 ? 'il y a ' + Math.round(s / 60) + ' min' : 'il y a ' + Math.floor(s / 3600) + ' h ' + String(Math.round((s % 3600) / 60)).padStart(2, '0'); }
  function km(x){ return (Math.round(x * 10) / 10).toLocaleString('fr-CA') + ' km'; }
  function dist(a, b){ var R = 6371000, r = Math.PI / 180, x = Math.pow(Math.sin((b.lat - a.lat) * r / 2), 2) + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.pow(Math.sin((b.lon - a.lon) * r / 2), 2); return 2 * R * Math.asin(Math.sqrt(x)); }
  function first(s){ return String(s || '').trim().split(/\s+/)[0] || ''; }
  /* no answer after a while: stop waiting, so a stuck request never blocks the screen (« Envoi du texto… ») or the position.
     ac (optional): the request is also cancelled. ms: 15 s for a quick read; the server's own work (an invitation, a client link,
     a courriel or a texto sent from there) gets 40 s, as it can start slowly after a quiet moment. */
  var WAIT_MS = 15000, WORK_MS = 40000;
  function timed(p, ac, ms){
    var w = ms || WAIT_MS, t, late = new Promise(function(res, rej){ t = setTimeout(function(){
      if (ac) try { ac.abort(); } catch(x){}
      var e = new Error('pas de réponse du serveur après ' + Math.round(w / 1000) + ' secondes'); e.code = 'timeout'; rej(e);
    }, w); });
    return Promise.race([Promise.resolve(p), late]).then(function(v){ clearTimeout(t); return v; }, function(e){ clearTimeout(t); throw e; });
  }
  function lng(){ return window.I18N && window.I18N.lang === 'en' ? 'en' : 'fr'; }   /* the language the person sees: his invitations are written in it */
  function invoke(name, body){
    return timed(T.sb.functions.invoke(name, {body:body}), null, WORK_MS).then(function(r){
      if (!r.error) return r.data;
      var ctx = r.error.context;
      return (ctx && typeof ctx.json === 'function' ? ctx.json().catch(function(){ return null; }) : Promise.resolve(null)).then(function(j){
        var e = new Error((j && j.message) || (/fetch|network/i.test(r.error.message) ? 'pas de connexion au serveur' : r.error.message)); e.code = j && j.error; throw e;
      });
    });
  }
  function mineOf(m, j){ return !!(m && m.mechanic && (norm(j.mechanic) === norm(m.mechanic) || (!j.mechanic && hasR(m, 'mecano')))); }
  function mineJob(j){ return mineOf(me, j); }          /* the real account (position, texts) */
  function mineView(j){ return mineOf(eff(), j); }      /* what the screen shows (« Voir comme ») */
  /* a job without a mechanic: whoever presses « En route » on his phone goes himself — if he can be the one driving (the office does not) */
  /* who drives there when this person presses « En route »: a mechanic, always himself (his job, or helping on another
     truck's job: everyone sees every route); someone else (owner, office): himself only for a job without a mechanic */
  function goesHimself(j){ return !!me && !previewing() && canTrack() && (hasR(me, 'mecano') || (!j.mechanic && (hasR(me, 'owner') || !!me.mechanic))); }
  function onPhone(){ var a = A(); return !!(a && a.phone && a.phone()); }
  function isStaff(){ return !!me && (hasR(me, 'owner') || hasR(me, 'bureau')); }
  function worksShifts(){ return !!(me && (hasR(me, 'mecano') || me.mechanic)); }
  function staffView(){ var m = eff(); return !!(m && (hasR(m, 'owner') || hasR(m, 'bureau'))); }
  function shiftsView(){ var m = eff(); return !!(m && (hasR(m, 'mecano') || m.mechanic || (m === me && G.on))); }   /* (someone else who went himself: his day card shows until he closes it) */

  /* THE RIGHTS: one list for everyone. Each role ticks some of them at the start (« Ce que chaque rôle donne au départ »,
     changeable); then a right can be added or removed for ONE person (Équipe et accès → Modifier).
     on: the roles that always have it; r: the roles where it is a choice (d: ticked at the start).
     The server also checks « Trésorerie », « Modifier les factures » (treasurer), « Voir la carte » and « Changer l'horaire des autres ». */
  var RIGHTS = [
    {k:'agenda', t:'Voir l\'agenda de toute l\'équipe', s:'Tous les rendez-vous, sans rien y changer.', on:['bureau'], r:['tresorier'], d:{}},
    {k:'book', t:'Prendre des rendez-vous', s:'Un mécano : dans son agenda. Le bureau : pour tout le monde.', on:[], r:['bureau', 'mecano'], d:{bureau:true}},
    {k:'clients', t:'Voir les clients', s:'Un mécano : tous les clients (il voit toutes les routes).', on:[], r:['bureau', 'mecano', 'tresorier'], d:{bureau:true, mecano:true, tresorier:true}},
    {k:'factures', t:'Voir les factures', s:'Un mécano : les factures de toutes les jobs.', on:[], r:['bureau', 'mecano', 'tresorier'], d:{bureau:true, mecano:true, tresorier:true}},
    {k:'editinv', t:'Modifier les factures et les marquer payées', s:'Un mécano : les factures de toutes les jobs, toujours (il encaisse avant de partir). Le trésorier : la facture seulement, rien d\'autre dans la job.', on:['mecano'], r:['bureau', 'tresorier'], d:{bureau:true}},
    {k:'money', t:'Voir les chiffres du garage', s:'Ventes du mois et factures payées, sur l\'écran d\'accueil.', on:[], r:['bureau', 'mecano', 'tresorier'], d:{bureau:true, tresorier:true}},
    {k:'tresor', t:'Trésorerie : dépenses, reçus, rapport, taxes', s:'', on:['tresorier'], r:['bureau', 'mecano'], d:{}},
    {k:'stock', t:'Voir et changer l\'inventaire', s:'', on:[], r:['bureau', 'mecano', 'tresorier'], d:{bureau:true, mecano:true, tresorier:true}},
    {k:'map', t:'Voir la carte de l\'équipe', s:'Les mécanos, leurs trajets et tous les rendez-vous du jour (avec le nom du client).', on:[], r:['bureau', 'mecano', 'tresorier'], d:{bureau:true, mecano:true, tresorier:true}},
    {k:'hours_others', t:'Changer l\'horaire du garage et des autres', s:'Heures d\'ouverture et horaire de chaque camion.', on:[], r:['bureau', 'mecano'], d:{bureau:true}}
  ];
  function right(k){ return RIGHTS.filter(function(x){ return x.k === k; })[0] || null; }
  /* what a role gives: the owner everything; then « always », then the role template (config/roles), then the start */
  function perm(role, k){
    if (role === 'owner') return true;
    var p = right(k); if (!p) return false;
    if (p.on.indexOf(role) >= 0) return true;
    if (p.r.indexOf(role) < 0) return false;
    var t = X.roles && X.roles[role], v = t && t[k]; if (typeof v === 'boolean') return v;
    return !!p.d[role];
  }
  function roleDefault(rs, k){ return rs.some(function(r){ return perm(r, k); }); }
  /* what THIS person may do: always-rights of his roles, then what was set for him, then what his roles give */
  function permOf(m, k){
    if (!m) return false; if (hasR(m, 'owner')) return true;
    var p = right(k), rs = rolesOf(m); if (!p) return false;
    if (rs.some(function(r){ return p.on.indexOf(r) >= 0; })) return true;
    if (!rs.some(function(r){ return p.r.indexOf(r) >= 0; })) return false;
    var o = m.perms && m.perms[k]; return typeof o === 'boolean' ? o : roleDefault(rs, k);
  }
  function trackBase(){ return location.origin + location.pathname.replace(/[^\/]*$/, ''); }
  function trackLink(t){ return t && t.token ? trackBase() + 'suivi.html#t=' + t.token : ''; }

  /* ================= journée de travail : position du téléphone ================= */
  var G = {on:false, since:null, watch:null, last:null, sentAt:0, sentPos:null, err:null, sendErr:null, wake:null, wakeWant:lsGet('gm.team.wake') === '1', beat:null, sending:false, starting:false};
  function gpsStart(){
    if (!navigator.geolocation){ G.err = 'none'; return; }
    if (G.watch == null) G.watch = navigator.geolocation.watchPosition(onPos, onGpsErr, {enableHighAccuracy:true, maximumAge:5000, timeout:30000});
    if (!G.beat) G.beat = setInterval(beat, 5000);
    if (G.wakeWant) wake(true);
  }
  function gpsStop(){
    if (G.watch != null && navigator.geolocation) navigator.geolocation.clearWatch(G.watch);
    G.watch = null; clearInterval(G.beat); clearTimeout(G.later); G.beat = null; G.last = null; G.sentPos = null; wake(false, true);
  }
  function onPos(p){
    var c = p.coords; G.err = null;
    G.last = {lat:c.latitude, lon:c.longitude, acc:c.accuracy, speed:c.speed, heading:c.heading, t:Date.now()};
    maybeSend(false); shiftLine(); checkTrip();
  }
  function onGpsErr(e){ G.err = e && e.code === 1 ? 'denied' : e && e.code === 3 ? 'timeout' : 'unavailable'; shiftLine(); }
  function maybeSend(force){
    if (!G.on || !G.last || G.sending) return;
    var now = Date.now(), iv = X.enRoute ? 8000 : 15000, moved = G.sentPos ? dist(G.sentPos, G.last) : 1e9;
    /* not more than one send every 4 s (moving) or every 8–15 s (standing); a skipped position goes out when the wait is over */
    var due = force ? now : G.sentAt + (moved >= 60 ? 4000 : iv);
    clearTimeout(G.later);
    if (now < due){ G.later = setTimeout(function(){ maybeSend(false); }, due - now + 50); return; }
    var pos = G.last, ac = window.AbortController ? new AbortController() : null;
    var q = T.sb.rpc('report_position', {p_lat:pos.lat, p_lon:pos.lon, p_acc:pos.acc == null ? null : Math.round(pos.acc), p_speed:pos.speed, p_heading:pos.heading});
    if (ac && q && typeof q.abortSignal === 'function') q = q.abortSignal(ac.signal); else ac = null;
    G.sending = true;
    /* a send stuck on a weak signal is dropped after 15 s: the next position can go out */
    timed(q, ac).then(function(r){
      G.sending = false;
      if (r.error){ G.sendErr = r.error.message; shiftLine(); return; }
      G.sendErr = null; G.sentAt = Date.now(); G.sentPos = pos;
      if (r.data && r.data.ok === false){ G.on = false; gpsStop(); toast('Ta journée a été fermée.'); render(); return; }
      shiftLine();
    }, function(){ G.sending = false; G.sendErr = 'réseau'; shiftLine(); });
  }
  /* some phones go quiet when they think nothing moves: ask again every 15 s (8 s on the way to a client) */
  function beat(){
    if (!G.on) return;
    var now = Date.now();
    if (G.last && now - G.sentAt > 55000) maybeSend(true);
    if ((!G.last || now - G.last.t > (X.enRoute ? 8000 : 15000)) && navigator.geolocation && !G.asking){
      G.asking = true;
      navigator.geolocation.getCurrentPosition(function(p){ G.asking = false; onPos(p); }, function(e){ G.asking = false; onGpsErr(e); }, {enableHighAccuracy:true, maximumAge:4000, timeout:15000});
    }
    shiftLine();
  }
  function wake(on, quiet){
    if (on){
      if (!('wakeLock' in navigator)){ if (!quiet) toast('Ce téléphone ne permet pas de garder l\'écran allumé.'); return; }
      if (G.wake) return;
      navigator.wakeLock.request('screen').then(function(l){ G.wake = l; l.addEventListener('release', function(){ G.wake = null; shiftLine(); }); shiftLine(); }, function(){ G.wake = null; });
    } else if (G.wake){ try { G.wake.release(); } catch(e){} G.wake = null; }
  }
  document.addEventListener('visibilitychange', function(){ if (document.visibilityState === 'visible' && G.on){ if (G.wakeWant) wake(true, true); beat(); } });
  function shiftStart(){
    if (G.starting) return Promise.resolve();
    G.starting = true;
    return timed(T.sb.rpc('shift_start')).then(function(r){
      G.starting = false;
      if (r.error){ toast('La journée n\'a pas commencé : ' + r.error.message); render(); return; }
      G.on = true; G.since = r.data && r.data.shift_started_at; lsSet('gm.team.gpsok', '1');
      gpsStart(); render();
    }, function(e){ G.starting = false; toast(e && e.code === 'timeout' ? 'Pas de réponse du serveur après 15 secondes. Réessaie.' : 'Pas de connexion au serveur. Réessaie.'); render(); });
  }
  function shiftEnd(quiet){
    return T.sb.rpc('shift_end').then(function(r){
      if (r.error){ toast('La journée n\'a pas été fermée : ' + r.error.message); return; }
      G.on = false; G.since = null; X.enRoute = null; X.autoShift = false; gpsStop(); toast(quiet ? 'Le client ne voit plus ta position.' : 'Bonne soirée ! Ta position n\'est plus envoyée.'); render();
    }, function(){ toast('Pas de connexion au serveur. Réessaie.'); });
  }
  function freshPos(ms){
    if (G.last && Date.now() - G.last.t < 20000) return Promise.resolve(G.last);
    if (!navigator.geolocation) return Promise.resolve(G.last);
    return new Promise(function(res){
      var done = false, t = setTimeout(function(){ if (!done){ done = true; res(G.last); } }, ms);
      navigator.geolocation.getCurrentPosition(function(p){ if (done) return; done = true; clearTimeout(t); onPos(p); res(G.last); }, function(){ if (done) return; done = true; clearTimeout(t); res(G.last); }, {enableHighAccuracy:true, maximumAge:10000, timeout:ms});
    });
  }
  function gpsProblem(){
    if (G.err === 'denied') return /iPhone|iPad|iPod/i.test(navigator.userAgent || '')
      ? 'Le téléphone refuse de donner ta position. Va dans Réglages → Confidentialité et sécurité → Service de localisation → Sites web Safari, choisis « Lorsque l\'app est active », puis ferme et rouvre l\'app.'
      : 'Le téléphone refuse de donner ta position. Touche le cadenas à côté de l\'adresse (ou, dans l\'app : ⋮ → Infos sur l\'app), autorise « Position », puis ferme et rouvre l\'app.';
    if (G.err === 'none') return 'Ce téléphone ne donne pas la position ici. Ouvre l\'app dans Safari (iPhone) ou Chrome (Android).';
    if (G.err && !G.last) return 'Position introuvable pour l\'instant (signal GPS faible). On réessaie tout seul.';
    if (G.sendErr && G.sentAt && Date.now() - G.sentAt > 90000) return 'La position ne part plus (connexion). On réessaie tout seul.';
    return '';
  }
  function shiftLine(){
    var el = document.getElementById('sh-line'); if (!el) return;
    var p = gpsProblem();
    el.textContent = !G.on ? '' : p ? p : !G.last ? 'Recherche de ta position…' : (G.sentAt ? 'Position envoyée ' + ago(G.sentAt) : 'Position trouvée, envoi en cours…') + (G.last.acc ? ' · précision ±' + Math.round(G.last.acc) + ' m' : '');
    el.className = 'sh-line' + (p ? ' warn' : '');
    var w = document.getElementById('sh-wake'); if (w){ w.setAttribute('aria-pressed', String(!!G.wake)); w.textContent = G.wake ? 'Écran gardé allumé ✓' : 'Garder l\'écran allumé'; }
  }
  setInterval(shiftLine, 5000);

  /* while on the way: faster position, route redone if he leaves it, « arrivé ? » when he is there */
  function offRoute(p, route){
    if (!route || route.length < 2) return 0;
    var best = 1e9; for (var i = 0; i < route.length; i++){ var d = dist(p, {lat:route[i][1], lon:route[i][0]}); if (d < best) best = d; } return best;
  }
  function checkTrip(){
    var r = X.enRoute; if (!r || !G.last) return;
    var t = X.tracks[r.jobId];
    if (t && t.dest_lat != null){
      var near = dist(G.last, {lat:t.dest_lat, lon:t.dest_lon}) < 120;
      if (near !== X.near){ X.near = near; render(); }
      if (near && !X.warnedNear){ X.warnedNear = true; toast('Tu es arrivé ? Touche « Je suis arrivé » sur la job.'); }
    }
    if (t && t.route && offRoute(G.last, t.route) > 300 && Date.now() - (r.refreshedAt || 0) > 60000){
      r.refreshedAt = Date.now();
      invoke('en-route', {jobId:r.jobId, action:'refresh', self:true, pos:{lat:G.last.lat, lon:G.last.lon, acc:G.last.acc}, force:true}).then(function(res){
        if (res && res.route){ Object.assign(t, {route:res.route, minutes:res.minutes, km:res.km, eta_at:res.eta_at}); render(); }
      }, function(){});
    }
  }

  /* ================= « En route » ================= */
  /* true when a read started (false: one is already on its way) */
  function fetchTrack(jobId){
    if (X.trackLoading[jobId]) return false;
    X.trackLoading[jobId] = true;
    timed(T.sb.from('tracks').select('*').eq('job_id', jobId).order('created_at', {ascending:false}).limit(1)).then(function(r){
      X.trackLoading[jobId] = false;
      if (r.error) return;
      X.tracks[jobId] = r.data[0] || null; render();
    }, function(){ X.trackLoading[jobId] = false; });
    return true;
  }
  function smsText(j, t){
    var c = A().cl(j), name = first(c.firstName || c.name), cc = j.clientId ? A().findClient(j.clientId) : null;
    if (((cc && cc.lang) || c.lang) === 'en' && window.I18N){   /* an English-speaking client: the text in English, the page too */
      var mE = first((t && t.mech_name) || j.mechanic || (me && me.name)) || 'Your mechanic';
      return 'Hello' + (name ? ' ' + name : '') + ', ' + mE + ' from ' + A().bizName() + ' is on the way to you' + (t && t.eta_at ? ': arriving around ' + I18N.t(clock(t.eta_at), 'en') : '') + '. Follow the trip live: ' + trackLink(t) + (t && t.token ? '&l=en' : '');
    }
    var mech = first((t && t.mech_name) || j.mechanic || (me && me.name)) || 'Votre mécano';
    return 'Bonjour' + (name ? ' ' + name : '') + ', ' + mech + ' de ' + A().bizName() + ' est en route vers chez vous' + (t && t.eta_at ? ' : arrivée prévue vers ' + clock(t.eta_at) : '') + '. Suivez son trajet en direct : ' + trackLink(t);
  }
  function smsHref(phone, text){ var d = String(phone || '').replace(/\D/g, ''); return 'sms:' + (d ? (d.length === 10 ? '+1' : '+') + d : '') + '?&body=' + encodeURIComponent(text); }
  function startEnRoute(j, opt){
    opt = opt || {};
    if (X.busy[j.id]) return;
    X.busy[j.id] = true; render();
    /* who the client follows (same rule as the server): the job's mechanic; a job without a mechanic follows whoever presses
       « En route », when he has his phone or tablet in hand (a desk computer has no position worth sending) and can be the one driving */
    var mine = mineJob(j) || goesHimself(j), p = Promise.resolve();
    if (mine && !G.on){ p = shiftStart(); if (!shiftsView()) X.autoShift = true; }   /* not a mechanic: his position stops when the trip ends */
    p.then(function(){ return mine ? freshPos(7000) : null; }).then(function(pos){
      return invoke('en-route', {jobId:j.id, action:'start', resend:!!opt.resend, notify:!X.quiet[j.id], self:!!mine, base:trackBase(), pos:pos ? {lat:pos.lat, lon:pos.lon, acc:pos.acc} : null});
    }).then(function(res){
      X.busy[j.id] = false;
      var t = Object.assign({}, X.tracks[j.id] || {}, {token:res.token, job_id:j.id, status:'active', route:res.route, minutes:res.minutes, km:res.km, eta_at:res.eta_at, dest_lat:res.dest ? res.dest.lat : null, dest_lon:res.dest ? res.dest.lon : null, sms_status:res.sms.status === 'already' ? 'sent' : res.sms.status, sms_error:res.sms.error || null, sms_at:res.sms.status === 'sent' ? new Date().toISOString() : (X.tracks[j.id] || {}).sms_at, mech_name:(X.tracks[j.id] || {}).mech_name});
      X.tracks[j.id] = t;
      if (mine){ X.enRoute = {jobId:j.id, refreshedAt:Date.now()}; X.near = false; X.warnedNear = false; maybeSend(true); }
      var c = A().cl(j), who = first(c.firstName || c.name) || 'le client';
      toast(res.sms.status === 'quiet' ? 'Parti sans texto : ' + who + ' n\'est pas avisé' : res.sms.status === 'sent' ? 'Texto envoyé à ' + who + ' ✓' : res.sms.status === 'already' ? who + ' a déjà le lien de suivi' : res.sms.status === 'error' ? 'Texto pas envoyé : envoie le lien toi-même' : 'Lien de suivi prêt : envoie-le à ' + who);
      render();
      fetchTrack(j.id);
    }, function(e){
      X.busy[j.id] = false;
      /* no answer: the text may have left anyway, so read the real state again (a second try does not text him twice) */
      if (e && e.code === 'timeout'){ toast('Pas de réponse du serveur après 15 secondes : le client n\'a peut-être pas été avisé. Vérifie ta connexion, puis réessaie.'); fetchTrack(j.id); }
      else toast('Le client n\'a pas été avisé : ' + e.message + '.');
      render();
    });
  }
  function endTrack(j, reason){
    invoke('en-route', {jobId:j.id, action:'end', reason:reason, self:!!(mineJob(j) || goesHimself(j))}).then(function(){
      if (X.tracks[j.id]) X.tracks[j.id].status = reason;
      if (X.enRoute && X.enRoute.jobId === j.id){ X.enRoute = null; X.near = false; if (X.autoShift && G.on){ X.autoShift = false; shiftEnd(true); } }
      fetchTrack(j.id);
    }, function(){});
  }
  /* the tracking kept here no longer matches the job (changed on another phone): « En route » goes with an active tracking.
     Read again when the status changed since the last read, otherwise not more than once every 15 s. */
  function trackStale(j, st, t){
    if (t === undefined) return true;
    if (!!(t && t.status === 'active') === (st === 'route')) return false;
    var w = X.trackSt[j.id];
    return !w || w.st !== st || Date.now() - w.at > 15000;
  }
  function jobExtra(j){
    if (!me || !A().canWrite()) return '';
    var st = j.status || 'planifie', t = X.tracks[j.id];
    if (st === 'annule' || st === 'noshow' || st === 'termine') return '';   /* finished or cancelled: nothing to follow, nothing to read */
    if (trackStale(j, st, t) && fetchTrack(j.id)) X.trackSt[j.id] = {st:st, at:Date.now()};
    var c = A().cl(j), who = first(c.firstName || c.name) || 'le client', phone = c.phone || '', mine = mineView(j), busy = X.busy[j.id];
    var h = '<section class="sect er" aria-labelledby="er-h"><h3 id="er-h">' + (st === 'route' ? 'En route vers ' + esc(who) : st === 'place' ? 'Sur place' : 'Départ vers le client') + '</h3>';
    if (st === 'planifie'){
      if (busy) h += '<p class="er-line">Envoi du texto…</p>';
      h += '<p class="muted small">' + (phone ? (X.quiet[j.id] ? 'Au départ, pas de texto : ' + esc(who) + ' ne sera pas avisé (le suivi marche quand même).' : 'Au départ, ' + esc(who) + ' reçoit un texto pour suivre le camion.') : 'Pas de téléphone au dossier : le lien de suivi sera prêt à partager.') + '</p>';
      /* (to test, or a client who asked not to be texted: off for this departure only, back on for the next job) */
      if (phone && !busy) h += '<label class="check er-notify"><input type="checkbox" data-act="er-notify" data-id="' + esc(j.id) + '"' + (X.quiet[j.id] ? '' : ' checked') + '> Aviser ' + esc(who) + ' par texto</label>';
      if (!mine && j.mechanic && !goesHimself(j)) h += '<p class="muted small">Le client suivra la position de ' + esc(j.mechanic) + '.</p>';
      else if (!mine && j.mechanic) h += '<p class="muted small">C\'est la job de ' + esc(j.mechanic) + ' : si tu pars, le client suivra ta position.</p>';
      else if (!mine && !j.mechanic && !goesHimself(j)) h += '<p class="muted small">Pas de mécano sur cette job : appuie « En route » sur le téléphone de celui qui part, pour que le client voie le camion avancer.</p>';
    } else if (st === 'route'){
      var act = t && t.status === 'active';
      if (busy) h += '<p class="er-line">Envoi en cours…</p>';
      else if (!act){
        h += '<p class="muted">Le client n\'a pas encore le lien de suivi.</p><button type="button" class="btn primary block" data-act="er-start" data-id="' + esc(j.id) + '">Aviser ' + esc(who) + '</button>';
      } else {
        if (t.eta_at) h += '<p class="er-eta"><span class="eyebrow">Arrivée prévue</span><b>' + esc(clock(t.eta_at)) + '</b>' + (t.minutes ? '<span class="muted">≈ ' + Math.max(1, Math.round(t.minutes)) + ' min' + (t.km ? ' · ' + esc(km(t.km)) : '') + '</span>' : '') + '</p>';
        else h += '<p class="muted small">Heure d\'arrivée inconnue : ' + (t.dest_lat == null ? 'l\'adresse du client n\'a pas été trouvée sur la carte.' : 'la position du mécano n\'est pas encore connue.') + '</p>';
        if (t.sms_status === 'sent') h += '<p class="er-line ok">Texto envoyé' + (t.sms_at ? ' à ' + esc(clock(t.sms_at)) : '') + ' ✓</p>';
        else if (t.sms_status === 'error') h += '<div class="banner warn"><p>Texto pas envoyé : ' + esc(t.sms_error || 'erreur') + '</p></div>';
        else h += '<p class="er-line">Texto automatique pas configuré. Envoie le lien toi-même :</p>';
        h += '<div class="er-acts">' +
          '<a class="btn sm steel" target="_blank" rel="noopener" href="' + esc(trackLink(t)) + '">Voir le suivi</a>' +
          (phone ? '<a class="btn sm" href="' + esc(smsHref(phone, smsText(j, t))) + '">Texter moi-même</a>' : '') +
          '<button type="button" class="btn sm" data-act="er-copy" data-id="' + esc(j.id) + '">Copier le lien</button>' +
          (t.sms_status !== 'off' && t.sms_status ? '<button type="button" class="btn sm" data-act="er-resend" data-id="' + esc(j.id) + '">Renvoyer le texto</button>' : '') + '</div>';
      }
      if (X.near && X.enRoute && X.enRoute.jobId === j.id) h += '<div class="banner ok"><p>Tu sembles arrivé chez ' + esc(who) + '.</p></div>';
    } else if (st === 'place'){
      h += '<p class="muted small">' + (t && t.status === 'arrived' ? 'Le suivi est fermé' + (t.ended_at ? ' depuis ' + esc(clock(t.ended_at)) : '') + ' : le client ne voit plus ta position.' : 'Le client ne voit pas ta position.') + '</p>';
    }
    return h + '</section>';
  }
  function onStatus(j, v, was){
    var ST = A().ST;
    if (v === 'route') return startEnRoute(j);
    /* « arrivé » only when he is there (or done); back to « Planifié », cancelled or absent: the client's page says the trip stopped */
    if (was === 'route') endTrack(j, (v === 'place' || v === 'termine') ? 'arrived' : 'cancelled');
    toast(ST[v]);
  }

  /* ================= haut de l'agenda : compte, journée, trajet en cours ================= */
  function agendaTop(){
    var m = eff(); if (!m) return '';
    /* on a big screen the side menu shows who is signed in; in a small window this line does */
    return (onPhone() ? '' : '<div class="acct"><span>Connecté : <b>' + esc(m.name) + '</b> · ' + esc(rolesLabel(m)) + '</span><button type="button" class="linkbtn" data-act="acct-out">Se déconnecter</button></div>') + shiftCard();
  }
  /* the side menu of a computer ends with who is signed in */
  function navFoot(){ var m = eff(); return m ? '<div class="navfoot"><span><b>' + esc(m.name) + '</b> · ' + esc(rolesLabel(m)) + '</span><button type="button" class="linkbtn" data-act="tour-replay">👋 ' + (tourAuto() ? 'Revoir la visite guidée' : 'Visite guidée de l\'app') + '</button><button type="button" class="linkbtn" data-act="acct-out">Se déconnecter</button>' + leaveBtn('linkbtn danger-t') + '</div>' : ''; }
  /* delete one's own account: asked twice; the jobs, invoices and clients he entered stay in the garage's logbook */
  function leaveBtn(cls){ if (previewing()) return ''; return '<button type="button" class="' + cls + '" data-act="acct-leave">' + (X.leaveArmed ? 'Touche encore pour supprimer ton compte pour de bon' : 'Supprimer mon compte') + '</button>' + (X.leaveArmed ? '<p class="small muted">Ton accès disparaît ; les jobs, factures et clients restent au carnet du garage.</p>' : ''); }
  /* « Commencer ma journée » only where a position can be sent: a phone or a tablet (not a desk computer) */
  function canTrack(){ try { return onPhone() || !!(window.matchMedia && matchMedia('(pointer: coarse)').matches); } catch(e){ return onPhone(); } }
  function shiftCard(){
    var h = '';
    if (shiftsView() && canTrack()){
      if (previewing()){
        h += '<section class="sect shift" aria-labelledby="sh-h"><h3 id="sh-h">Début de journée</h3><p class="small">Touche ce bouton en partant le matin. Le bureau voit où tu es, et le client voit ton trajet quand tu pars chez lui.</p>' +
          '<button type="button" class="btn primary block" data-act="sh-start">Commencer ma journée</button></section>';
      } else if (!G.on){
        var known = lsGet('gm.team.gpsok') === '1';
        h += '<section class="sect shift" aria-labelledby="sh-h"><h3 id="sh-h">Début de journée' + (A().help ? A().help('position', 'ta position') : '') + '</h3>' +
          (known ? '<p class="small">Touche ce bouton en partant le matin. Le bureau voit où tu es jusqu\'à « Fin de journée ».</p>'
            : '<p class="small">Touche ce bouton en partant le matin. Le bureau voit où tu es, et le client voit ton trajet quand tu pars chez lui.</p><p class="muted small">Rien n\'est envoyé avant « Commencer ma journée » ni après « Fin de journée ». Les positions sont gardées 30 jours, puis effacées.</p>') +
          '<button type="button" class="btn primary block" data-act="sh-start"' + (G.starting ? ' disabled' : '') + '>' + (G.starting ? 'Un instant…' : 'Commencer ma journée') + '</button></section>';
      } else {
        var trip = X.enRoute && A().findJob(X.enRoute.jobId), tt = trip && X.tracks[trip.id];
        h += '<section class="sect shift on" aria-labelledby="sh-h"><div class="sh-head"><span class="sh-dot" aria-hidden="true"></span><h3 id="sh-h">Journée en cours' + (G.since ? ' depuis ' + esc(clock(G.since)) : '') + '</h3></div>' +
          '<p class="sh-line" id="sh-line" aria-live="polite"></p>' +
          (trip ? '<div class="banner"><p><b>En route vers ' + esc(first(A().cl(trip).firstName || A().cl(trip).name)) + '</b>' + (tt && tt.eta_at ? ' · arrivée prévue ' + esc(clock(tt.eta_at)) : '') + '</p><button type="button" class="btn sm" data-act="open" data-id="' + esc(trip.id) + '">Ouvrir la job</button></div>' : '') +
          '<p class="muted small">Garde l\'app ouverte pendant ta journée.</p>' +
          '<div class="er-acts"><button type="button" class="btn sm" id="sh-wake" data-act="sh-wake" aria-pressed="false">Garder l\'écran allumé</button><button type="button" class="btn sm" data-act="sh-end">Fin de journée</button></div></section>';
        setTimeout(shiftLine, 0);
      }
    }
    return h;
  }
  function settingsTop(){
    var m = eff(); if (!m || !hasR(m, 'owner') || onPhone()) return '';
    return '<section class="sect"><h3>Équipe et accès</h3><p class="muted small">Les comptes de l\'équipe, les mots de passe, les textos aux clients et le paiement par carte.</p><a class="btn block" href="#equipe">Gérer l\'équipe et les accès</a></section>';
  }

  /* ================= carte des mécanos ================= */
  var M = {el:null, map:null, pins:{}, jobs:null, routes:null, path:null, fitted:false, sig:null};
  var STATE = {route:{lbl:'En route', cls:'p-route'}, shift:{lbl:'En journée', cls:'p-shift'}, stale:{lbl:'Signal perdu', cls:'p-stale'}, off:{lbl:'Hors service', cls:'p-off'}};
  function mechState(l){
    if (!l || !l.on_shift) return 'off';
    if (!l.at || Date.now() - Date.parse(l.at) > 5 * 60000) return 'stale';
    return X.active.some(function(t){ return t.user_id === l.user_id; }) ? 'route' : 'shift';
  }
  function initials(n){ var p = String(n || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p[1] ? p[1][0] : (p[0] || '')[1] || '')).toUpperCase(); }
  function loadLive(){
    if (!isStaff()) return Promise.resolve();
    if (X.liveLoading) return X.liveLoading;
    return X.liveLoading = Promise.all([
      T.sb.from('mech_live').select('*'),
      T.sb.from('tracks').select('token,job_id,user_id,status,eta_at,route,dest_lat,dest_lon,created_at,client_first,sms_status').eq('status', 'active'),
      T.sb.from('members').select('user_id,name,role,roles,mechanic,active')
    ]).then(function(r){
      if (!r[0].error) X.live = r[0].data;
      if (!r[1].error) X.active = r[1].data.filter(function(t){ return !t.created_at || Date.now() - Date.parse(t.created_at) < 4 * 3600000; });
      if (!r[2].error) X.members = r[2].data;
      X.liveAt = Date.now(); X.liveLoading = null;
      drawMap();
      if (A() && (A().S.tab === 'carte' || A().S.tab === 'accueil') && !A().S.screen) render();
    }, function(){ X.liveLoading = null; });
  }
  function crew(){
    var out = X.members.filter(function(m){ return m.active && (hasR(m, 'mecano') || m.mechanic); }).map(function(m){ return {m:m, l:X.live.filter(function(l){ return l.user_id === m.user_id; })[0] || null}; });
    var order = {route:0, shift:1, stale:2, off:3};
    return out.sort(function(a, b){ return order[mechState(a.l)] - order[mechState(b.l)] || String(a.m.name).localeCompare(b.m.name, 'fr'); });
  }
  function ensureMap(){
    if (M.map || !window.L) return !!M.map;
    M.el = document.createElement('div'); M.el.id = 'gm-map'; M.el.className = 'gm-map'; M.el.setAttribute('role', 'region'); M.el.setAttribute('aria-label', 'Carte des mécanos');
    var slot = document.getElementById('map-slot'); if (!slot) return false;
    slot.appendChild(M.el);
    M.map = L.map(M.el, {zoomControl:true}).setView([45.53, -73.62], 11);
    M.map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19, attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'}).addTo(M.map);
    M.jobs = L.layerGroup().addTo(M.map); M.routes = L.layerGroup().addTo(M.map); M.path = L.layerGroup().addTo(M.map);
    return true;
  }
  new MutationObserver(function(){
    var slot = document.getElementById('map-slot');
    if (!slot) return;
    if (!M.map){ if (ensureMap()){ drawMap(); } return; }
    if (M.el.parentNode !== slot){ slot.appendChild(M.el); setTimeout(function(){ M.map.invalidateSize(); }, 0); }
  }).observe(document.documentElement, {childList:true, subtree:true});
  /* ---- the team map: everybody sees the mechanics, their route of the day and every appointment (numbered, client's name) ---- */
  var CENTRALE = {name:'Centrale', address:'8255 Avenue Mountain Sights, Montréal QC H4P 2B5', lat:45.5005053, lon:-73.6577429};
  function centrale(){ var c = (A() && A().cfg().central) || {}; return c.geo && isFinite(+c.geo.lat) && isFinite(+c.geo.lon) ? {name:c.name || 'Centrale', address:c.address || '', lat:+c.geo.lat, lon:+c.geo.lon} : CENTRALE; }
  var PAL = ['#E4572E', '#2E86AB', '#2BA84A', '#8E44AD', '#D99A00', '#D7263D', '#14A098', '#5C6B7A'];
  function mechColor(name){ var ms = (A() && A().mechanics()) || [], i = ms.map(norm).indexOf(norm(name)); return !name ? '#7A8794' : i < 0 ? PAL[(ms.length + Math.abs(String(name).length)) % PAL.length] : PAL[i % PAL.length]; }
  function loadTeamMap(){
    if (X.tmLoading) return X.tmLoading;
    return X.tmLoading = T.sb.rpc('team_map', {p_day:A().today()}).then(function(r){
      X.tmLoading = null;
      if (r.error){ X.tmErr = /not_granted|42501/.test(r.error.message + (r.error.code || '')) ? 'Tu n\'as pas accès à la carte. Parle au propriétaire.' : 'La carte ne répond pas (' + r.error.message + ').'; X.tmSig = null; render(); return; }
      X.tm = r.data; X.tmAt = Date.now(); X.tmErr = '';
      tmRefresh();
    }, function(e){ X.tmLoading = null; X.tmErr = 'La carte ne répond pas (' + (e && e.message || e) + ').'; X.tmSig = null; render(); });
  }
  /* what the map and the list under it are drawn from. When none of it changed, nothing is redrawn:
     the pins stay, an open popup stays open and the screen does not jump.
     Positions are rounded to about 10 m (a phone standing still wobbles); an age is counted once it reads in minutes. */
  function tmSig(){
    var a = A(), now = Date.now();
    var gs = teams().map(function(g){
      var l = g.live, line = dayLine(g), t = trackOf(g), ll = l && l.lat != null ? [+l.lat, +l.lon] : null, age = l && l.at ? now - Date.parse(l.at) : null;
      var next = g.jobs.filter(function(j){ return j.status !== 'termine' && geoOf(j); })[0];
      return [g.key, g.name, g.color, g.member && g.member.name, g.member && g.member.user_id,
        g.jobs.map(function(j){ var c = j.client || {}; return [j.id, j.n, j.time, j.status, c.name, c.address, geoOf(j), !!a.findJob(j.id)]; }),
        line.length > 1 ? [!!X.roads[roadKey(line)], X.roadsMeta[roadKey(line)] || null] : null,
        l ? [ll && [Math.round(ll[0] * 1e4), Math.round(ll[1] * 1e4)], age == null || age > 5 * 60000, age != null && age < 45000 ? 'live' : ago(l.at)] : null,
        t ? [t.job_id, t.eta_at, t.route || null] : null,
        ll && next ? !!X.roads[roadKey([ll, geoOf(next)])] : null];
    });
    var ps = Object.keys(X.showPath).filter(function(u){ return X.showPath[u]; }).map(function(u){ var p = X.paths[u] || []; return [u, p.length, p.length ? p[p.length - 1].at : null]; });
    return JSON.stringify([centrale(), X.tmHide || {}, X.tmErr || '', gs, ps]);
  }
  /* new data arrived: redraw the map and the screen only if something they show changed */
  function tmRefresh(){
    var s = tmSig(); if (s === X.tmSig) return;
    X.tmSig = s; drawMap();
    var a = A(); if (a && a.S.tab === 'carte' && !a.S.screen) render();
  }
  /* each mechanic: his color, his live position, his appointments of the day in order (1, 2, 3…) */
  function teams(){
    var tm = X.tm || {jobs:[], live:[], members:[]}, ms = A().mechanics(), groups = {}, order = [];
    var add = function(name){ var k = norm(name); if (!groups[k]){ groups[k] = {key:k, name:name || 'Sans mécano', color:mechColor(name), jobs:[], member:null, live:null}; order.push(k); } return groups[k]; };
    ms.forEach(add);
    (tm.jobs || []).forEach(function(j){ add(j.mechanic || '').jobs.push(j); });
    (tm.members || []).forEach(function(m){ if (m.mechanic){ var g = add(m.mechanic); g.member = m; g.live = (tm.live || []).filter(function(l){ return l.user_id === m.user_id; })[0] || null; } });
    return order.map(function(k){ var g = groups[k]; g.jobs.sort(function(a, b){ return String(a.time).localeCompare(String(b.time)); }); g.jobs.forEach(function(j, i){ j.n = i + 1; }); return g; })
      .filter(function(g){ return g.jobs.length || g.live; });   /* a mechanic with nothing today and not on the road: not shown */
  }
  function geoOf(j){ var g = j.client && j.client.geo; return g && isFinite(+g.lat) && isFinite(+g.lon) ? [+g.lat, +g.lon] : null; }
  /* a mechanic's day: from the Centrale (where the trucks leave), then each appointment in order */
  function dayLine(g){ var hq = centrale(), line = [[hq.lat, hq.lon]]; g.jobs.forEach(function(j){ var ll = geoOf(j); if (ll) line.push(ll); }); return line; }
  /* the route on the roads (OpenStreetMap routing); a straight line if it does not answer */
  X.roads = X.roads || {}; X.roadsMeta = X.roadsMeta || {};
  function roadKey(pts){ return pts.map(function(p){ return (+p[0]).toFixed(5) + ',' + (+p[1]).toFixed(5); }).join(';'); }
  function roads(pts, cb){
    var key = roadKey(pts);
    if (X.roads[key]) return cb(X.roads[key]);
    if (X.roads[key] === null) return cb(pts);
    X.roads[key] = null;
    var url = 'https://router.project-osrm.org/route/v1/driving/' + pts.map(function(p){ return p[1] + ',' + p[0]; }).join(';') + '?overview=full&geometries=geojson';
    fetch(url).then(function(r){ return r.ok ? r.json() : null; }).then(function(d){
      var rt = d && d.routes && d.routes[0], c = rt && rt.geometry && rt.geometry.coordinates;
      if (c && c.length > 1){
        X.roads[key] = c.map(function(x){ return [x[1], x[0]]; });
        if (isFinite(+rt.distance) && isFinite(+rt.duration)) X.roadsMeta[key] = {km:+rt.distance / 1000, min:+rt.duration / 60};
        tmRefresh();
      }
    }, function(){});
    cb(pts);
  }
  /* « En route » : his active trip (link sent to the client), with the time of arrival */
  function trackOf(g){ var uid = g.member && g.member.user_id, tm = X.tm || {}; return uid ? (tm.tracks || []).filter(function(t){ return t.user_id === uid; })[0] || null : null; }
  function etaText(g){
    var t = trackOf(g); if (!t) return '';
    var j = (g.jobs || []).filter(function(x){ return x.id === t.job_id; })[0], who = j && j.client && j.client.name ? String(j.client.name).split(' ')[0] : 'un client';
    return '<p class="small tm-eta">🚚 En route vers <b>' + esc(who) + '</b>' + (t.eta_at ? ' · arrivée vers ' + esc(clock(t.eta_at)) : '') + '</p>';
  }
  function routeText(g){
    var line = dayLine(g), mt = line.length > 1 && X.roadsMeta[roadKey(line)];
    if (!mt) return '';
    var km = mt.km < 10 ? (Math.round(mt.km * 10) / 10).toString().replace('.', ',') : String(Math.round(mt.km)), mn = Math.max(1, Math.round(mt.min));
    return '<p class="small tm-route"><span style="color:' + g.color + '">━━</span> Trajet du jour depuis la Centrale : <b>' + km + ' km</b> · environ <b>' + (mn >= 60 ? Math.floor(mn / 60) + ' h ' + String(mn % 60).padStart(2, '0') : mn + ' min') + '</b> de route</p>';
  }
  function stopIcon(n, color, cls){ return L.divIcon({className:'gm-pin-wrap', html:'<span class="tm-stop ' + (cls || '') + '" style="--c:' + color + '">' + n + '</span>', iconSize:[30, 30], iconAnchor:[15, 15]}); }
  function mechIcon(txt, color, cls){ return L.divIcon({className:'gm-pin-wrap', html:'<span class="tm-mech ' + (cls || '') + '" style="--c:' + color + '">' + esc(txt) + '</span>', iconSize:[42, 42], iconAnchor:[21, 21]}); }
  function drawMap(){
    if (!M.map || !X.tm) return;
    var sig = tmSig(); if (sig === M.sig) return;   /* nothing new to draw: the map is left as it is */
    M.sig = sig;
    var a = A(), pts = [], hq = centrale(), open = null;
    /* the popup someone opened is opened again after the redraw, if its pin is still there */
    M.jobs.eachLayer(function(l){ if (l.gmKey && l.isPopupOpen && l.isPopupOpen()) open = l.gmKey; });
    M.jobs.clearLayers(); M.routes.clearLayers(); M.path.clearLayers();
    Object.keys(M.pins).forEach(function(k){ M.map.removeLayer(M.pins[k]); }); M.pins = {};
    /* the Centrale (the owner's place) */
    pts.push([hq.lat, hq.lon]);
    L.marker([hq.lat, hq.lon], {icon:L.divIcon({className:'gm-pin-wrap', html:'<span class="tm-hq">🏢</span>', iconSize:[44, 44], iconAnchor:[22, 22]}), title:hq.name, zIndexOffset:500}).addTo(M.jobs)
      .bindTooltip('<b>' + esc(hq.name) + '</b>', {permanent:true, direction:'right', offset:[18, 0], className:'tm-hq-tip'}).bindPopup('<b>' + esc(hq.name) + '</b>' + (hq.address ? '<br>' + esc(hq.address) : '')).gmKey = 'hq';
    teams().forEach(function(g){
      if (X.tmHide && X.tmHide[g.key]) return;
      var line = dayLine(g);
      g.jobs.forEach(function(j){
        var ll = geoOf(j); if (!ll) return; pts.push(ll);
        var st = j.status || 'planifie', mine = !!a.findJob(j.id);
        var pop = '<div class="tm-pop"><b>' + j.n + ' · ' + esc(a.hm(j.time)) + '</b> <span class="tm-st">' + esc((a.ST && a.ST[st]) || st) + '</span><br><b>' + esc(j.client.name || 'Client') + '</b>' + (j.client.address ? '<br>' + esc(j.client.address) : '') +
          '<br><span style="color:' + g.color + '">●</span> ' + esc(g.name) + (mine ? '<br><button type="button" class="btn sm" data-act="open" data-id="' + esc(j.id) + '">Ouvrir la job</button>' : '') + '</div>';
        L.marker(ll, {icon:stopIcon(j.n, g.color, st === 'termine' ? 'done' : st === 'route' ? 'go' : st === 'place' ? 'here' : ''), title:j.n + ' · ' + (j.client.name || ''), riseOnHover:true}).addTo(M.jobs)
          .bindTooltip(esc(j.n + ' · ' + a.hm(j.time) + ' · ' + (j.client.name || 'Client')), {direction:'top', offset:[0, -14]}).bindPopup(pop).gmKey = 'j' + j.id;
      });
      if (line.length > 1) roads(line, function(path){ L.polyline(path, {color:g.color, weight:5, opacity:.85, lineCap:'round', lineJoin:'round'}).addTo(M.routes); });
      /* the mechanic himself (only during his workday) and the way to his next stop */
      var l = g.live;
      if (l && l.lat != null){
        var ll2 = [+l.lat, +l.lon], stale = !l.at || Date.now() - Date.parse(l.at) > 5 * 60000; pts.push(ll2);
        M.pins['m' + g.key] = L.marker(ll2, {icon:mechIcon(initials(g.member ? g.member.name : g.name), g.color, stale ? 'stale' : ''), title:g.name, zIndexOffset:800, riseOnHover:true}).addTo(M.map)
          .bindTooltip(esc((g.member ? g.member.name : g.name) + (stale ? ' · signal perdu' : ' · en journée') + ' · ' + ago(l.at)), {direction:'top', offset:[0, -20]});
        var trk = trackOf(g), tr = trk && Array.isArray(trk.route) && trk.route.length > 1 ? trk.route.map(function(c){ return [+c[1], +c[0]]; }) : null;
        var next = g.jobs.filter(function(j){ return j.status !== 'termine' && geoOf(j); })[0];
        if (tr) L.polyline(tr, {color:g.color, weight:4, opacity:.9, dashArray:'2 9', lineCap:'round'}).addTo(M.routes);   /* « En route » : the way the client sees it */
        else if (next) roads([ll2, geoOf(next)], function(path){ L.polyline(path, {color:g.color, weight:4, opacity:.9, dashArray:'2 9', lineCap:'round'}).addTo(M.routes); });
      }
    });
    Object.keys(X.showPath).forEach(function(uid){ var p = X.paths[uid]; if (X.showPath[uid] && p && p.length > 1) L.polyline(p.map(function(x){ return [x.lat, x.lon]; }), {color:'#1E1915', weight:3, opacity:.55}).addTo(M.path); });
    M.pts = pts;
    if (!M.fitted && pts.length){ M.fitted = true; fit(pts); }
    if (open) M.jobs.eachLayer(function(l){ if (l.gmKey === open) l.openPopup(); });
  }
  function fit(pts){ if (!M.map) return; pts = pts || M.pts || []; if (pts.length === 1) M.map.setView(pts[0], 13); else if (pts.length) M.map.fitBounds(L.latLngBounds(pts).pad(0.15), {maxZoom:15}); }
  function selectMech(uid){
    var g = teams().filter(function(x){ return x.member && x.member.user_id === uid; })[0];
    if (M.map && g && g.live) M.map.setView([+g.live.lat, +g.live.lon], Math.max(M.map.getZoom(), 14));
    render();
    if (M.el) M.el.scrollIntoView({block:'nearest'});
  }
  /* « Trajet fait aujourd'hui » : the server gives at most 1000 points at a time, so read page by page.
     After the first time, only the points newer than the last one already here. */
  function loadPath(uid){
    if (X.pathBusy[uid]) return Promise.resolve();
    var d = new Date(); d.setHours(0, 0, 0, 0);
    var had = (X.paths[uid] || []).filter(function(p){ return Date.parse(p.at) >= d.getTime(); }), since = had.length ? had[had.length - 1].at : null, got = [];
    function page(from){
      var q = T.sb.from('mech_positions').select('lat,lon,at').eq('user_id', uid);
      q = since ? q.gt('at', since) : q.gte('at', d.toISOString());
      return timed(q.order('at', {ascending:true}).range(from, from + 999)).then(function(r){
        if (r.error) return;
        got = got.concat(r.data || []);
        if ((r.data || []).length >= 1000) return page(from + 1000);
        X.paths[uid] = had.concat(got); tmRefresh();
      });
    }
    X.pathBusy[uid] = true;
    return page(0).then(function(){ X.pathBusy[uid] = false; }, function(){ X.pathBusy[uid] = false; });
  }
  function viewMap(){
    var a = A();
    if (!X.tmAt || Date.now() - X.tmAt > 8000) loadTeamMap();
    var top = onPhone() ? a.topBack('Carte de l\'équipe', 'ph-back', 'Plus') : '<div class="wrap top-in"><div class="brandrow"><div><div class="eyebrow">' + esc(a.bizName()) + ' · ' + esc(a.dayLong(a.today())) + '</div><h1>Carte de l\'équipe</h1></div><button type="button" class="btn sm" data-act="map-fit">Tout voir</button></div></div>';
    var gs = teams(), body = a.banners();
    if (X.tmErr) body += '<div class="banner warn"><p>' + esc(X.tmErr) + '</p></div>';
    body += '<div class="tm-legend" role="group" aria-label="Mécanos sur la carte">' + gs.map(function(g){
      var off = X.tmHide && X.tmHide[g.key];
      return '<button type="button" class="tm-chip' + (off ? ' off' : '') + '" data-act="tm-mech" data-v="' + esc(g.key) + '" aria-pressed="' + !off + '"><i style="background:' + g.color + '"></i>' + esc(g.name) + ' <span>' + g.jobs.length + '</span></button>'; }).join('') +
      (onPhone() ? '<button type="button" class="tm-chip" data-act="map-fit">Tout voir</button>' : '') + '</div>';
    body += window.L ? '<div id="map-slot" class="mapslot tm-slot"></div>' : '<div class="banner warn"><p>La carte n\'a pas pu se charger. Vérifie Internet et recharge la page.</p></div>';
    body += '<p class="legend small tm-leg"><span><b class="tm-hq mini">🏢</b>Centrale (départ des camions)</span><span><b class="tm-stop mini" style="--c:#7A8794">1</b>Rendez-vous, dans l\'ordre</span><span><b class="tm-line"></b>Son trajet du jour (par les routes)</span><span><b class="tm-mech mini" style="--c:#7A8794">AB</b>Mécano en journée</span><span><b class="tm-dash"></b>Vers son prochain client</span></p>';
    body += '<section class="sect"><div class="sect-head"><h3>La journée de chaque mécano</h3><span class="muted small">' + (X.tmAt ? 'mis à jour ' + ago(X.tmAt) : 'chargement…') + '</span></div>';
    if (!gs.length) body += '<p class="muted">Aucun rendez-vous ni mécano aujourd\'hui.</p>';
    gs.forEach(function(g){
      var l = g.live, uid = g.member && g.member.user_id;
      body += '<div class="mc tm-mc" id="mc-' + esc(uid || g.key) + '"><div class="mc-head"><span class="tm-mech" style="--c:' + g.color + '" aria-hidden="true">' + esc(initials(g.member ? g.member.name : g.name)) + '</span><div class="mc-who"><b>' + esc(g.member ? g.member.name : g.name) + '</b>' +
        '<span class="pillx ' + (l ? 'p-shift' : 'p-off') + '">' + (l ? 'En journée · ' + esc(ago(l.at)) : 'Pas en journée') + '</span></div></div>' + etaText(g);
      if (g.jobs.length) body += '<ol class="tm-stops">' + g.jobs.map(function(j){
        var mine = !!a.findJob(j.id), st = j.status || 'planifie';
        return '<li><span class="tm-stop mini' + (st === 'termine' ? ' done' : '') + '" style="--c:' + g.color + '">' + j.n + '</span><div><b>' + esc(a.hm(j.time)) + ' · ' + esc(j.client.name || 'Client') + '</b><span class="small muted">' + esc(j.client.address || 'Adresse inconnue') + (geoOf(j) ? '' : ' · pas sur la carte') + '</span></div>' +
          '<span class="pillx">' + esc((a.ST && a.ST[st]) || st) + '</span>' + (mine ? '<button type="button" class="btn sm" data-act="open" data-id="' + esc(j.id) + '">Ouvrir</button>' : '') + '</li>'; }).join('') + '</ol>';
      else body += '<p class="small muted">Aucun rendez-vous aujourd\'hui.</p>';
      body += routeText(g);
      if (uid && staffView()) body += '<div class="er-acts">' + (l ? '<button type="button" class="btn sm" data-act="map-sel" data-v="' + esc(uid) + '">Voir sur la carte</button>' : '') +
        '<button type="button" class="btn sm" data-act="map-path" data-v="' + esc(uid) + '" aria-pressed="' + (!!X.showPath[uid]) + '">' + (X.showPath[uid] ? 'Cacher le trajet fait' : 'Trajet fait aujourd\'hui') + '</button></div>';
      body += '</div>';
    });
    body += '</section><p class="muted small">Les positions sont partagées seulement pendant la journée de chaque mécano (gardées 30 jours). Les trajets suivent les routes (OpenStreetMap).</p>';
    return {top:top, body:body};
  }
  /* dashboard: who is working and who is on the way */
  function dashExtra(){
    if (!staffView()) return '';
    if (!X.liveAt || Date.now() - X.liveAt > 30000) loadLive();
    var c = crew(), on = c.filter(function(x){ return mechState(x.l) !== 'off'; });
    var h = '<section class="sect" aria-labelledby="d-road"><div class="sect-head"><h3 id="d-road">Sur la route</h3><button type="button" class="btn sm" data-act="tab" data-t="carte">Voir la carte</button></div>';
    if (!c.length) return h + '<p class="muted">Aucun mécano n\'a encore de compte.' + (hasR(eff(), 'owner') ? ' <a href="#equipe">Ajouter l\'équipe</a>' : '') + '</p></section>';
    if (!on.length) h += '<p class="muted small">Personne n\'a commencé sa journée.</p>';
    h += '<div class="qrows">' + c.map(function(x){
      var st = mechState(x.l), t = X.active.filter(function(a){ return a.user_id === x.m.user_id; })[0];
      return '<div class="qrow"><span class="qicon" aria-hidden="true">' + esc(initials(x.m.name)) + '</span><div><b>' + esc(x.m.name) + '</b><span>' + (t ? 'En route vers ' + esc(t.client_first || 'un client') + (t.eta_at ? ' · ' + esc(clock(t.eta_at)) : '') : st === 'off' ? 'Pas en journée' : 'Position ' + esc(ago(x.l.at))) + '</span></div><span class="pillx ' + STATE[st].cls + '">' + STATE[st].lbl + '</span></div>';
    }).join('') + '</div></section>';
    return h;
  }
  setInterval(function(){ if (document.visibilityState !== 'hidden' && A() && A().S.tab === 'carte' && !A().S.screen){ loadTeamMap(); if (isStaff()) Object.keys(X.showPath).forEach(function(uid){ if (X.showPath[uid]) loadPath(uid); }); } }, 12000);

  /* ================= équipe et accès (propriétaire) ================= */
  function eqLoad(){
    X.eq.loading = true;
    return Promise.all([invoke('members', {action:'list'}), invoke('members', {action:'secrets'})]).then(function(r){
      X.eq.loading = false; X.eq.list = r[0].members; X.eq.secrets = r[1]; X.eq.err = ''; render();
    }, function(e){ X.eq.loading = false; X.eq.err = e.message; render(); });
  }
  /* what this person may open or do (true / false / undefined = as usual) */
  function gate(m, w){
    if (hasR(m, 'owner')) return (w === 'tab:tresor' || w === 'expenses') ? true : undefined;
    var rs = rolesOf(m), mec = rs.indexOf('mecano') >= 0, bur = rs.indexOf('bureau') >= 0, works = mec || bur;
    switch (w){
      case 'tab:tresor': case 'expenses': return permOf(m, 'tresor');
      case 'money': return permOf(m, 'money');
      case 'tab:clients': return permOf(m, 'clients');
      case 'tab:factures': return permOf(m, 'factures');
      case 'tab:stock': case 'stock': return permOf(m, 'stock');
      case 'tab:carte': return permOf(m, 'map');
      case 'tab:agenda': case 'tab:jour': return works || permOf(m, 'agenda');
      case 'tab:plus': return true;
      case 'tab:reglages': case 'tab:equipe': return false;
      case 'book': return works ? permOf(m, 'book') : false;
      case 'deleteJob': return bur;
      case 'hours': return permOf(m, 'hours_others');
      case 'invoice': return permOf(m, 'editinv') ? true : mec ? undefined : false;
      default: return works ? undefined : false;   /* the treasurer alone: only what is listed above */
    }
  }
  /* roles: boxes (a person can have several) */
  var ROLE_HINT = {mecano:'toutes les routes, « En route », la facture sur place', bureau:'agenda, clients, factures, carte', tresorier:'dépenses, rapport, taxes', owner:'tout, y compris les accès'};
  function roleBoxes(pre, sel){
    return '<fieldset class="rbox"><legend>Rôles' + (A().help ? A().help('roles', 'les rôles') : '') + '</legend>' + ['mecano', 'bureau', 'tresorier', 'owner'].map(function(r){
      return '<label class="check" for="' + pre + '-r-' + r + '"><input type="checkbox" id="' + pre + '-r-' + r + '" data-act="rb" data-pre="' + pre + '" data-role="' + r + '"' + (sel.indexOf(r) >= 0 ? ' checked' : '') + '><span><b>' + ROLE[r] + '</b> <span class="small muted">· ' + esc(ROLE_HINT[r]) + '</span></span></label>'; }).join('') + '</fieldset>';
  }
  function rolesFrom(pre){ return ['owner', 'bureau', 'mecano', 'tresorier'].filter(function(r){ var e = document.getElementById(pre + '-r-' + r); return e && e.checked; }); }
  /* the rights of one person, with what his roles give; a change is kept for him only */
  function rightKeys(rs){ return RIGHTS.filter(function(p){ return rs.some(function(r){ return p.r.indexOf(r) >= 0 || p.on.indexOf(r) >= 0; }); }); }
  function rightsHTML(pre, m, rs, who){
    if (rs.indexOf('owner') >= 0) return '<p class="small muted rights-own" id="' + pre + '-rights">Propriétaire : il peut tout faire, y compris les accès.</p>';
    if (!rs.length) return '<p class="small muted" id="' + pre + '-rights">Coche au moins un rôle.</p>';
    return '<fieldset class="rbox rights" id="' + pre + '-rights"><legend>Ses droits' + (who ? ' (' + esc(who) + ')' : '') + '</legend>' + rightKeys(rs).map(function(p){
      var always = rs.some(function(r){ return p.on.indexOf(r) >= 0; }), def = roleDefault(rs, p.k), o = !always && m && m.perms && typeof m.perms[p.k] === 'boolean' ? m.perms[p.k] : null, on = always || (o === null ? def : o), id = pre + '-p-' + p.k;
      return '<label class="check rp-row" for="' + id + '"><input type="checkbox" id="' + id + '" data-k="' + p.k + '" data-def="' + (def ? 1 : 0) + '"' + (on ? ' checked' : '') + (always ? ' disabled' : '') + '><span><b>' + esc(p.t) + '</b>' +
        '<span class="small muted">' + (always ? 'Toujours, avec son rôle' : o === null ? 'Comme son rôle' : o ? '<b class="r-add">Ajouté pour cette personne</b>' : '<b class="r-del">Enlevé pour cette personne</b>') + (p.s ? ' · ' + esc(p.s) : '') + '</span></span></label>'; }).join('') +
      '<p class="small muted">Ça ne change que pour cette personne.</p></fieldset>';
  }
  /* what was ticked in a form ('nw' = invite, 'ed' = change a person) is kept in X.eq.draft: when the screen is drawn again
     (the people list arriving, a colleague's change, the network banner), the boxes come from it, not from the start values.
     Forgotten after a save or an invitation, on « Annuler », and when leaving the screen. */
  function draftOf(pre, uid){ var d = X.eq.draft[pre]; return d && (pre !== 'ed' || d.uid === uid) ? d : null; }
  function rightsList(m){ var d = draftOf('ed', m.user_id); return rightsHTML('ed', d ? {perms:d.perms} : m, d ? d.roles : rolesOf(m), first(m.name)); }
  /* roles or a box changed: the list follows (what the boxes say now is what counts) */
  function rightsRedraw(pre, focusId){
    var bx = document.getElementById(pre + '-rights'); if (!bx) return;
    var who = pre === 'ed' ? (X.eq.list || []).filter(function(x){ return x.user_id === X.eq.editing; })[0] : null;
    var keep = {}; bx.querySelectorAll('input[data-k]').forEach(function(e){ if (!e.disabled && e.checked !== (e.dataset.def === '1')) keep[e.dataset.k] = e.checked; });
    var rs = rolesFrom(pre);
    bx.outerHTML = rightsHTML(pre, {perms:keep}, rs, who ? first(who.name) : '');
    X.eq.draft[pre] = {roles:rs, perms:keep, uid:pre === 'ed' ? X.eq.editing : null};
    var f = focusId && document.getElementById(focusId); if (f) try { f.focus({preventScroll:true}); } catch(e){}
  }
  window.addEventListener('hashchange', function(){ if (location.hash.slice(1) !== 'equipe') X.eq.draft = {}; });
  document.addEventListener('toggle', function(ev){ if (ev.target && ev.target.id === 'eq-roles') X.rolesOpen = ev.target.open; }, true);   /* the table stays open while you tick boxes */
  document.addEventListener('change', function(ev){ var e = ev.target; if (e && e.matches && e.matches('.rights input[data-k]')){ var bx = e.closest('.rights'); rightsRedraw(bx.id.replace(/-rights$/, ''), e.id); } });
  function permsFrom(rs, pre){
    var out = {};
    rightKeys(rs).forEach(function(p){ var e = document.getElementById((pre || 'ed') + '-p-' + p.k); if (!e || e.disabled) return; if (e.checked !== roleDefault(rs, p.k)) out[p.k] = e.checked; });
    return out;
  }
  /* (no more: nobody assigns a truck — each mechanic picks his own every day, in his app) */
  function truckPick(id, mech){
    return '';
    var a = A(), ts = a.truckMode && a.truckMode() ? a.trucks() : [], cur = mech && a.truckOfUsual(mech);
    if (!ts.length) return '';
    var opts = '<option value=""' + (cur ? '' : ' selected') + '>Aucun camion</option>' + ts.map(function(t){
      var mine = cur && cur.id === t.id, other = !mine && t.mech;
      return '<option value="' + esc(t.id) + '"' + (mine ? ' selected' : '') + '>' + esc((t.name || 'Camion') + (mine ? '' : other ? ' · à la place de ' + t.mech : t.on === false ? ' · fermé' : ' · libre')) + '</option>';
    }).join('');
    return '<div class="field"><label for="' + id + '">Son camion <span class="small muted">(ses rendez-vous sont ceux du camion)</span></label><select id="' + id + '">' + opts + '</select></div>';
  }
  /* names typed in the agenda before the accounts: pick one so the person gets the appointments already booked under that name */
  function orphans(){ var list = X.eq.list || []; return A().mechanics().filter(function(n){ return !list.some(function(m){ return m.mechanic && norm(m.mechanic) === norm(n); }); }); }
  function orphanPick(id){
    var os = orphans(); if (!os.length) return '';
    return '<div class="field"><label for="' + id + '">Déjà dans l\'agenda sous un autre nom ?</label><select id="' + id + '"><option value="">Non</option>' + os.map(function(n){ return '<option value="' + esc(n) + '">Oui : ' + esc(n) + '</option>'; }).join('') + '</select></div>';
  }
  function truckLine(m){ if (!m.mechanic) return ''; var t = A().truckMode() ? A().truckOfUsual(m.mechanic) : null; return (t ? '🚚 ' + esc(t.name || 'Camion') + ' aujourd\'hui · ' : '') + (norm(m.mechanic) !== norm(m.name) ? 'Dans l\'agenda : ' + esc(m.mechanic) + ' · ' : ''); }   /* (the truck he picked today, if any: nobody assigns one) */
  function moveJobs(r){ try { if (r && r.moved && Object.keys(r.moved).length) A().retarget(r.moved); } catch (e){} }
  function viewEquipe(){
    var a = A();
    if (!eff() || !hasR(eff(), 'owner')) return {top:a.topBack('Équipe et accès', 'eq-back'), body:'<div class="banner"><p>Seul le propriétaire gère les accès.</p></div>'};
    if (!X.eq.list && !X.eq.loading && !X.eq.err) eqLoad();
    var top = a.topBack('Équipe et accès', 'eq-back', onPhone() ? 'Plus' : 'Réglages');
    var b = '';
    if (X.eq.err) b += '<div class="banner warn"><p>' + esc(X.eq.err) + '</p><button type="button" class="btn sm" data-act="eq-reload">Réessayer</button></div>';
    if (X.eq.created){
      var cr = X.eq.created, txt = a.bizName() + ' : ton accès au carnet du garage\n' + trackBase() + '\nCourriel : ' + cr.email + '\nMot de passe temporaire : ' + cr.password;
      b += '<section class="sect created" aria-live="polite"><h3>' + (cr.reset ? 'Nouveau mot de passe pour ' : 'Compte créé pour ') + esc(cr.name) + '</h3><p class="small">Envoie-lui ces infos (le mot de passe ne sera plus affiché après) :</p>' +
        '<dl class="credl"><div><dt>Adresse</dt><dd class="sel">' + esc(trackBase()) + '</dd></div><div><dt>Courriel</dt><dd class="sel">' + esc(cr.email) + '</dd></div><div><dt>Mot de passe</dt><dd class="pw sel">' + esc(cr.password) + '</dd></div></dl>' +
        '<pre class="cred" hidden>' + esc(txt) + '</pre>' +
        '<div class="er-acts"><button type="button" class="btn sm steel" data-act="eq-copycred">Copier</button><a class="btn sm" href="' + esc('sms:?&body=' + encodeURIComponent(txt)) + '">Texter</a><a class="btn sm" href="' + esc('mailto:' + cr.email + '?subject=' + encodeURIComponent('Accès au carnet du garage') + '&body=' + encodeURIComponent(txt)) + '">Courriel</a><button type="button" class="btn sm" data-act="eq-hidecred">C\'est envoyé</button></div></section>';
    }
    if (X.eq.invited){
      var iv = X.eq.invited, sent = iv.mail && iv.mail.status === 'sent', ms = iv.message || {};
      b += '<section class="sect created" id="eq-invited" aria-live="polite"><h3>' + (sent ? 'Invitation envoyée à ' : 'Invitation prête pour ') + esc(iv.name) + '</h3>' +
        (sent ? '<p class="small">Un courriel est parti à <b>' + esc(iv.email) + '</b>. ' + esc(first(iv.name)) + ' touche « Activer mon compte », choisit son mot de passe, et c\'est fait. Il verra aussi comment mettre l\'app sur son téléphone.</p>'
          : '<p class="small">' + (iv.mail && iv.mail.status === 'error' ? 'Le courriel automatique n\'est pas parti (' + esc(iv.mail.error) + '). ' : 'Les courriels automatiques ne sont pas branchés (textos automatiques, GoHighLevel). ') + 'Envoie-la toi-même avec un de ces boutons : le message est déjà écrit.</p>' +
            '<div class="er-acts"><a class="btn sm steel" id="inv-mail" href="' + esc('mailto:' + iv.email + '?subject=' + encodeURIComponent(ms.subject || '') + '&body=' + encodeURIComponent(ms.body || iv.link)) + '">Envoyer par courriel</a>' +
            '<a class="btn sm" href="' + esc('sms:?&body=' + encodeURIComponent((ms.body || iv.link))) + '">Envoyer par texto</a><button type="button" class="btn sm" data-act="eq-copylink">Copier le lien</button></div>') +
        '<p class="muted small">Le lien marche une seule fois, pendant 7 jours.</p><button type="button" class="linkbtn" data-act="eq-hideinv">Fermer</button></section>';
    }
    b += viewAsCard() + rolesCard();
    b += '<section class="sect"><h3>Personnes</h3>';
    if (!X.eq.list) b += '<p class="muted">Chargement…</p>';
    else X.eq.list.forEach(function(m){
      var self = m.user_id === me.user_id;
      b += '<div class="eqp' + (m.active ? '' : ' off') + '"><div class="eqp-head"><div><b>' + esc(m.name) + '</b>' + (self ? ' <span class="muted small">(toi)</span>' : '') + '<div class="small muted sel">' + esc(m.email) + '</div></div><span class="pills">' + rolesOf(m).map(function(r){ return '<span class="pillx r-' + r + '">' + ROLE[r] + '</span>'; }).join('') + '</span></div>' +
        '<p class="small muted">' + truckLine(m) + (m.active ? (m.last_sign_in_at ? 'dernière connexion ' + esc(ago(m.last_sign_in_at)) : m.invite ? '<b>' + (m.invite.expired ? 'Invitation expirée' : 'Invitation envoyée ' + esc(ago(m.invite.at))) + '</b> · pas encore activé' : 'jamais connecté') : '<b>Accès désactivé</b>') + '</p>';
      if (X.eq.editing === m.user_id){
        b += '<div class="eq-form"><div class="field"><label for="ed-name">Nom</label><input id="ed-name" value="' + esc(m.name) + '" autocomplete="off"></div>' +
          roleBoxes('ed', (draftOf('ed', m.user_id) || {roles:rolesOf(m)}).roles) + truckPick('ed-truck', m.mechanic) + (m.mechanic ? '' : orphanPick('ed-mech')) +
          rightsList(m) +
          '<div class="er-acts"><button type="button" class="btn sm primary" data-act="eq-save" data-v="' + esc(m.user_id) + '">Enregistrer</button><button type="button" class="btn sm" data-act="eq-cancel">Annuler</button></div></div>';
      } else if (X.eq.confirm === m.user_id){
        b += '<div class="banner warn"><p>Supprimer le compte de ' + esc(m.name) + ' ? Ses jobs restent au carnet.</p></div><div class="er-acts"><button type="button" class="btn sm" data-act="eq-cancel">Garder</button><button type="button" class="btn sm danger solid" data-act="eq-remove" data-v="' + esc(m.user_id) + '">Supprimer</button></div>';
      } else {
        b += '<div class="er-acts"><button type="button" class="btn sm" data-act="eq-edit" data-v="' + esc(m.user_id) + '">Modifier</button>' +
          (self || !m.active || hasR(m, 'owner') ? '' : '<button type="button" class="btn sm" data-act="pv-person" data-v="' + esc(m.user_id) + '">👁 Voir comme ' + esc(first(m.name)) + '</button>') +
          (self ? '' : (!m.last_sign_in_at && m.active ? '<button type="button" class="btn sm" data-act="eq-reinvite" data-v="' + esc(m.user_id) + '">' + (m.invite ? 'Renvoyer l\'invitation' : 'Envoyer une invitation') + '</button>' : '') + '<button type="button" class="btn sm" data-act="eq-pw" data-v="' + esc(m.user_id) + '">Nouveau mot de passe</button>') + '</div>' +
          (self ? '' : (m.active ? '<div class="eq-more-x">' : '') + '<div class="er-acts"><button type="button" class="btn sm" data-act="eq-active" data-v="' + esc(m.user_id) + '">' + (m.active ? 'Bloquer l\'accès (garder le compte)' : 'Redonner l\'accès') + '</button><button type="button" class="btn sm danger" data-act="eq-confirm" data-v="' + esc(m.user_id) + '">Supprimer le compte</button></div>' + (m.active ? '</div>' : ''));
      }
      b += '</div>';
    });
    b += '</section>';
    var nwd = draftOf('nw'), nwr = nwd ? nwd.roles : ['mecano'];
    b += '<section class="sect" id="eq-new"><h3>Inviter une personne</h3><p class="small">Écris son courriel : elle reçoit un lien, choisit elle-même son mot de passe, et son compte est activé.</p>' +
      '<div class="field"><label for="nw-name">Nom</label><input id="nw-name" autocomplete="off"></div>' +
      '<div class="field"><label for="nw-email">Courriel</label><input id="nw-email" type="email" inputmode="email" autocapitalize="off" spellcheck="false" autocomplete="off"></div>' +
      roleBoxes('nw', nwr) + truckPick('nw-truck', '') + orphanPick('nw-mech') +
      rightsHTML('nw', nwd ? {perms:nwd.perms} : null, nwr, '') +
      '<ul class="roles small"><li><b>Mécano</b> : toutes les routes (il peut aller aider un autre), le bouton « En route », la facture sur place. Sa position est partagée pendant sa journée.</li><li><b>Bureau</b> : agenda, clients, factures et carte des mécanos. Pas les réglages.</li><li><b>Trésorier</b> : son propre écran, la trésorerie (dépenses avec photo des reçus, rapport, taxes à remettre, Excel).</li><li><b>Propriétaire</b> : tout, y compris les accès.</li></ul><p class="small muted">Ce que le mécano et le trésorier voient de plus : plus haut, « Ce que chaque rôle peut faire ».</p>' +
      '<p class="formerr" id="nw-err" role="alert" hidden></p><button type="button" class="btn primary block" data-act="eq-invite">Envoyer l\'invitation</button>' +
      '<details class="small eq-more"><summary>Autre façon : créer un mot de passe temporaire</summary><p class="small">Pour quelqu\'un qui ne lit pas ses courriels : tu lui donnes toi-même un mot de passe.</p><button type="button" class="btn block" data-act="eq-add">Créer le compte avec un mot de passe temporaire</button></details></section>';
    var s = X.eq.secrets || {};
    b += '<section class="sect"><h3>Textos automatiques aux clients' + (A().help ? A().help('textos', 'les textos') : '') + '</h3>' +
      '<p class="small">' + (s.ghl ? '<span class="badge ok">Branché</span> Clé ' + esc(s.ghlToken) + ' · compte ' + esc(s.ghlLocation) : '<span class="badge warn">Pas branché</span> Sans GoHighLevel, le bouton « En route » prépare le texto et tu l\'envoies toi-même.') + '</p>' +
      '<div class="field"><label for="gh-token">Clé GoHighLevel (commence par pit-)</label><input id="gh-token" type="password" autocomplete="off" spellcheck="false" placeholder="' + (s.ghl ? 'Laisse vide pour garder la clé actuelle' : 'pit-…') + '"></div>' +
      '<div class="field"><label for="gh-loc">Numéro du compte GoHighLevel (Location ID)</label><input id="gh-loc" autocomplete="off" spellcheck="false" placeholder="' + (s.ghl ? 'Laisse vide pour garder l\'ID actuel' : '') + '"></div>' +
      '<details class="small"><summary>Où trouver ça dans GoHighLevel ?</summary><ol><li>Paramètres → <b>Private Integrations</b> → Créer. Coche « View/Edit Contacts » et « View/Edit Conversation Messages ». Copie la clé (elle commence par pit-).</li><li>Paramètres → <b>Business Profile</b> : copie le « Location ID ».</li><li>Colle les deux ici. La clé va directement dans ta base : personne ne peut la relire, même pas dans l\'app.</li></ol></details>' +
      '<div class="er-acts"><button type="button" class="btn sm primary" data-act="gh-save">Enregistrer</button>' + (s.ghl ? '<button type="button" class="btn sm danger" data-act="gh-clear">Débrancher</button>' : '') + '</div>' +
      (s.ghl ? '<div class="field"><label for="gh-test">Envoyer un texto test au numéro</label><div class="er-acts"><input id="gh-test" type="tel" inputmode="tel" autocomplete="off" placeholder="514 555-0123"><button type="button" class="btn sm" data-act="gh-test">Envoyer</button></div></div>' : '') + '</section>';
    b += '<section class="sect"><h3>Paiement par carte (Stripe)' + (A().help ? A().help('carte', 'le paiement par carte') : '') + '</h3>' +
      '<p class="small">' + (s.stripe ? '<span class="badge ok">Branché</span>' + (s.stripeMode === 'test' ? ' <span class="badge warn">mode test</span>' : '') + ' Clé ' + esc(s.stripeKey) + (s.stripeHook ? ' · confirmation automatique des paiements ✓' : ' · paiement confirmé quand le client revient sur sa page') :
        '<span class="badge warn">Pas branché</span> Sans Stripe, la facture envoyée au client n\'a pas de bouton « Payer ».') + '</p>' +
      '<div class="field"><label for="st-key">Clé secrète Stripe (commence par sk_live_)</label><input id="st-key" type="password" autocomplete="off" spellcheck="false" placeholder="' + (s.stripe ? 'Laisse vide pour garder la clé actuelle' : 'sk_live_…') + '"></div>' +
      '<details class="small"><summary>Où trouver la clé ?</summary><ol><li>Stripe → <b>Développeurs</b> → <b>Clés API</b>.</li><li>Ligne « Clé secrète » → <b>Révéler</b> → copie (elle commence par sk_live_).</li><li>Colle-la ici. Elle reste sur le serveur du garage : jamais dans les téléphones, jamais affichée en entier.</li></ol><p>Pour essayer sans vrai argent : la clé sk_test_ et la carte 4242 4242 4242 4242.</p></details>' +
      '<div class="er-acts"><button type="button" class="btn sm primary" data-act="st-save">Enregistrer</button>' + (s.stripe ? '<button type="button" class="btn sm danger" data-act="st-clear">Débrancher</button>' : '') + '</div></section>';
    b += '<details class="sect fold"' + (s.tomtom ? ' open' : '') + '><summary>Options avancées : cartes plus précises</summary><div class="stack"><p class="small muted">Facultatif. Avec une clé TomTom, l\'heure d\'arrivée tient compte du trafic. Sans clé, les cartes gratuites suffisent.</p>' +
      '<p class="small">' + (s.tomtom ? '<span class="badge ok">TomTom branché</span> ' + esc(s.tomtom) : '<span class="badge">Cartes gratuites</span>') + '</p>' +
      '<div class="field"><label for="tt-key">Clé TomTom</label><input id="tt-key" type="password" autocomplete="off" spellcheck="false" placeholder="' + (s.tomtom ? 'Laisse vide pour garder la clé actuelle' : 'Clé de developer.tomtom.com') + '"></div>' +
      '<div class="er-acts"><button type="button" class="btn sm primary" data-act="tt-save">Enregistrer</button>' + (s.tomtom ? '<button type="button" class="btn sm danger" data-act="tt-clear">Retirer</button>' : '') + '</div></div></details>';
    b += '<section class="sect"><h3>Ton compte</h3><p class="small">' + esc(eff().name) + ' · ' + esc(rolesLabel(eff())) + '</p><button type="button" class="btn" data-act="acct-out">Se déconnecter</button></section>';
    return {top:top, body:b};
  }
  /* « Voir l'app comme… » : one button per mechanic in the agenda, the treasurer, the office */
  function viewAsCard(){
    var list = X.eq.list || [], ms = A().mechanics(), out = [];
    ms.forEach(function(n){ if (me && me.mechanic && norm(n) === norm(me.mechanic)) return; out.push({role:'mecano', mechanic:n, name:n}); });
    ['tresorier', 'bureau'].forEach(function(r){
      var m = list.filter(function(x){ return x.role === r && x.active; })[0];
      out.push({role:r, name:m ? m.name : ROLE[r]});
    });
    return '<section class="sect" id="eq-viewas"><h3>Voir l\'app comme…' + (A().help ? A().help('voircomme', 'voir comme') : '') + '</h3><p class="small">Tu vois exactement son écran. Tu peux corriger des choses : c\'est enregistré à ton nom. Un bandeau en haut te ramène à ton compte.</p>' +
      '<div class="pv-btns">' + out.map(function(o){ return '<button type="button" class="btn sm" data-act="pv-start" data-role="' + o.role + '" data-mech="' + esc(o.mechanic || '') + '" data-name="' + esc(o.name) + '">👁 ' + esc(o.name) + (o.role === 'mecano' ? ' <span class="muted">(mécano)</span>' : o.name !== ROLE[o.role] ? ' <span class="muted">(' + ROLE[o.role].toLowerCase() + ')</span>' : '') + '</button>'; }).join('') + '</div></section>';
  }
  /* « Ce que chaque rôle donne au départ » : a table (rights × roles), saved right away in config/roles */
  function rolesCard(){
    var cols = ['mecano', 'bureau', 'tresorier'];
    var h = '<details class="sect fold" id="eq-roles"' + (X.rolesOpen ? ' open' : '') + '><summary>Ce que chaque rôle donne au départ' + (A().help ? A().help('droits', 'les droits') : '') + '</summary><div class="stack">' +
      '<p class="small muted">Les cases de départ quand tu choisis un rôle. Coche ou décoche : c\'est enregistré tout de suite pour toutes les personnes de ce rôle (sauf ce que tu as changé pour une personne).</p>' +
      '<div class="rt-wrap"><table class="rt"><thead><tr><th scope="col">Droit</th>' + cols.map(function(r){ return '<th scope="col">' + ROLE[r] + '</th>'; }).join('') + '</tr></thead><tbody>' +
      RIGHTS.map(function(p){
        return '<tr><th scope="row">' + esc(p.t) + '</th>' + cols.map(function(r){
          var id = 'rp-' + r + '-' + p.k;
          if (p.on.indexOf(r) >= 0) return '<td class="rt-on" title="Toujours">✓</td>';
          if (p.r.indexOf(r) < 0) return '<td class="rt-na" title="Pas pour ce rôle">—</td>';
          return '<td><input type="checkbox" id="' + id + '" data-act="rp" data-role="' + r + '" data-k="' + p.k + '" aria-label="' + esc(ROLE[r] + ' : ' + p.t) + '"' + (perm(r, p.k) ? ' checked' : '') + (X.rolesLoaded ? '' : ' disabled') + '></td>';
        }).join('') + '</tr>';
      }).join('') + '</tbody></table></div>' +
      '<p class="small muted">✓ = toujours avec ce rôle · — = pas pour ce rôle. Le mécano fait toujours les jobs (« En route », décharge, facture sur place), les siennes ou celles d\'un autre camion.</p>' +
      '<div class="er-acts"><button type="button" class="linkbtn" data-act="pv-role" data-role="mecano">👁 Voir ce que voit un mécano</button><button type="button" class="linkbtn" data-act="pv-role" data-role="tresorier">👁 Voir ce que voit le trésorier</button></div></div></details>';
    return h;
  }
  function saveRole(role, k, on, box){
    if (!X.rolesLoaded){ if (box) box.checked = !on; return; }
    if (box) box.disabled = true;
    /* start from what is saved now (another screen may have changed another box) */
    var ref = T.db.doc('config/roles'), next;
    ref.get().then(function(sn){
      next = JSON.parse(JSON.stringify(sn.exists ? (sn.data() || {}) : {}));
      next[role] = Object.assign({}, next[role] || {}); next[role][k] = !!on;
      return ref.set(next);
    }).then(function(){ X.roles = next; toast('Enregistré : ' + ROLE[role].toLowerCase() + ', ' + (on ? 'oui' : 'non') + ' — ' + right(k).t.toLowerCase()); render(); },
      function(e){ if (box){ box.checked = !on; box.disabled = false; } toast('Pas enregistré : ' + (e && e.message || 'erreur')); render(); });
  }
  /* start / stop the preview */
  function startView(v){
    var a = A(); if (!a || !me || !hasR(me, 'owner')) return;
    if (!VA) { try { X.uiBefore = sessionStorage.getItem('gm.ui'); } catch(e){ X.uiBefore = null; } try { sessionStorage.setItem('gm.ui.before', X.uiBefore || ''); } catch(e){} }
    /* a mechanic works on his phone: on a computer, show his phone screen first (a button switches to the computer screen) */
    var vr = v.roles && v.roles.length ? v.roles : [v.role];
    VA = {role:mainRole(vr), roles:vr, perms:v.perms || {}, mechanic:v.mechanic || null, name:v.name || ROLE[v.role], fmt:vr.indexOf('mecano') >= 0 ? 'phone' : 'pc'};
    saveVA(); applyView(); goHome();
  }
  function saveVA(){ try { sessionStorage.setItem('gm.viewas', JSON.stringify(VA)); } catch(e){} }
  function switchFmt(){ if (!previewing()) return; VA.fmt = VA.fmt === 'phone' ? 'pc' : 'phone'; saveVA(); applyView(); goHome(); }
  /* « Version ordinateur » (Plus) or « Version simple pour téléphone » chosen inside a preview: the preview follows */
  function onUi(){ if (!previewing()) return; VA.fmt = A().phone() ? 'phone' : 'pc'; saveVA(); applyView(); }
  function stopView(){
    var a = A(); VA = null;
    try { sessionStorage.removeItem('gm.viewas'); var u = sessionStorage.getItem('gm.ui.before'); sessionStorage.removeItem('gm.ui.before'); a.setUi(u || null); } catch(e){ a.setUi(null); }
    applyView();
    location.hash = 'equipe'; if (a.S.tab === 'equipe'){ a.S.screen = null; render(); }
    toast('De retour sur ton compte');
  }
  /* one place decides the look of the preview, every time (also after a reload): never half phone, half computer */
  function applyView(){
    var a = A(), pc = !a.phoneDevice();
    if (T.setView) T.setView(previewing() ? eff() : null);
    if (previewing() && pc) a.setUi(VA.fmt === 'phone' ? 'phone' : null);
    document.body.classList.toggle('pv-on', previewing());
    document.body.classList.toggle('pv-narrow', previewing() && pc && a.phone());
    pvBar(); render();
  }
  function goHome(){ var a = A(), t = a.defTab(); a.S.screen = null; a.S.inv = null; a.S.backTo = null; if (location.hash.slice(1) !== t) location.hash = t; else { a.S.tab = t; render(); } window.scrollTo(0, 0); }
  function pvBar(){
    var el = document.getElementById('pv-bar');
    if (!previewing()){ if (el) el.remove(); return; }
    if (!el){ el = document.createElement('div'); el.id = 'pv-bar'; el.setAttribute('role', 'status'); document.body.insertBefore(el, document.body.firstChild); }
    var v = eff();
    el.innerHTML = '<span class="pv-t"><span aria-hidden="true">👁 </span><span class="pv-long">Tu vois l\'app comme </span><span class="pv-short">Comme </span><b>' + esc(v.name) + '</b> (' + esc(ROLE[v.role].toLowerCase()) + ')</span>' +
      '<button type="button" class="btn sm pv-fmt" data-act="tour-replay">👋 <span class="pv-long">Sa première visite</span><span class="pv-short">1re visite</span></button>' +
      (A().phoneDevice() ? '' : '<button type="button" class="btn sm pv-fmt" data-act="pv-fmt">' + (A().phone() ? '🖥 Voir sur ordinateur' : '📱 Voir sur téléphone') + '</button>') +
      '<button type="button" class="btn sm" data-act="pv-exit">Revenir à mon compte</button>';
    pvFit();
  }
  /* the page starts below the bar, whatever its height */
  function pvFit(){ var el = document.getElementById('pv-bar'); if (el) document.documentElement.style.setProperty('--pvh', el.offsetHeight + 'px'); }
  window.addEventListener('resize', pvFit);
  /* ---- the guided tour, for each role (a person with several roles gets each part once) ----
     The person does it. To go to another screen, HE touches it: the menu, « Plus », a tab, a button. The tour lights where to
     touch and says where it leads; the visit goes on when he touches it (no « Passer »). On each screen he tries things
     (search, filters, sections, the schedule grid…): nothing tried is saved, and his view comes back as it was.
     The app's color is the exception: the one the owner picks during the visit stays (it is saved like any other time).
     A step: t title, p words, icon, x a tip, sel what is lit, go its screen (put back when he goes back with ‹ Retour; going forward it
     is already open after his touch, except the job and the schedule window, opened for him where nothing can be touched), tap he touches it, nav that touch opens this screen (skipped if he is already there),
     try he plays with it (tryT what to try, done what it showed), after lit with it once tried, need skip it when not there. */
  function standalone(){ try { return !!(navigator.standalone || (window.matchMedia && matchMedia('(display-mode: standalone)').matches)); } catch(e){ return false; } }
  function tourAuto(){ var m = eff(); return !!m && !hasR(m, 'owner'); }
  function tourSteps(){
    var m = eff(); if (!m) return [];
    var inst = !!window.__webDownloads && !standalone();   /* (already opened from its icon: nothing to install) */
    var own = hasR(m, 'owner'), mec = hasR(m, 'mecano'), tre = hasR(m, 'tresorier'), bur = hasR(m, 'bureau') || own, ph = onPhone(), nm = first(m.name);
    var can = function(k){ return own || permOf(m, k); }, mr = mainRole(rolesOf(m));
    var solo = mec && !bur;   /* a mechanic alone sees his own jobs, clients and invoices */
    var inBar = function(t){ var e = document.querySelector('#tabbar .tab[data-t="' + t + '"]'); return !!e && !e.hidden && e.getBoundingClientRect().width > 0; };
    var barName = function(t, d){ var e = document.querySelector('#tabbar .tab[data-t="' + t + '"] span'); return (e && e.textContent.trim()) || d; };
    var BLK = !!(A().blockMode && A().blockMode()), TRK = !!(A().truckMode && A().truckMode());   /* (rendez-vous by block: the texts about booking say so; by truck: no mechanics' availability, each truck's schedule) */
    var PLUS = {accueil:'Tableau de bord', carte:'Carte de l\'équipe', dispos:solo ? 'Mes disponibilités' : 'Disponibilités des mécanos', tresor:'Trésorerie', stock:'Inventaire', reglages:'Réglages', equipe:'Équipe et accès', heures:'Heures d\'ouverture'};
    var where = ph ? 'en bas' : 'dans le menu à gauche';
    /* going to a screen, by touching: the bar (or the menu on the computer); on the phone, « Plus » then the line;
       on the computer, a screen without a menu item is reached from the screen that links to it */
    function nav(t, label, why){
      if (inBar(t)) return [{icon:'👆', nav:t, tap:'#tabbar .tab[data-t="' + t + '"]', t:label, p:why, do:'Touche « ' + barName(t, label) + ' » ' + where + '.'}];
      if (ph && inBar('plus')) return [
        {icon:'👆', nav:t, tap:'#tabbar .tab[data-t="plus"]', t:label, p:why + ' C\'est rangé dans « Plus ».', do:'Touche « Plus » en bas.'},
        {icon:'👆', nav:t, tap:'#tiles a.tile[href="#' + t + '"]', need:true, t:label, p:'« Plus » : la journée en haut, puis une tuile pour chaque partie de l\'app.', do:'Touche « ' + (PLUS[t] || label) + ' ».'}];
      var via = t === 'equipe' ? 'reglages' : t === 'stock' && can('tresor') ? 'tresor' : 'accueil', vn = {reglages:'Réglages', tresor:'Trésorerie', accueil:'Accueil'}[via];
      if (via === t) return [];   /* (never round in circles) */
      return nav(via, label, '« ' + (PLUS[t] || label) + ' » se trouve dans « ' + vn + ' ».').concat([
        {icon:'👆', nav:t, tap:'#main [data-act="tab"][data-t="' + t + '"], #main a[href="#' + t + '"], #top a[href="#' + t + '"]', need:true, t:label, p:why, do:'Touche « ' + (PLUS[t] || label) + ' ».'}]);
    }
    /* the schedule window: he opens it, tries the grid with his finger, then closes it himself (nothing saved) */
    function sched(kind, openSel, openDo, title, words){
      return [
        {icon:'🗓', tap:openSel, need:true, t:title, p:words, do:openDo},
        {icon:'👆', go:'sched:' + kind, try:'#sched .sch-scroll', need:true, t:'La grille', p:kind === 'avail' ? 'Une case foncée, c\'est une heure où tu travailles.' : 'Une case foncée est ouverte, une case pâle est fermée.',
          tryT:(ph ? 'Essaie : glisse ton doigt vers le bas sur quelques cases.' : 'Essaie : clique et glisse vers le bas sur quelques cases.') + ' C\'est un essai.', done:'Voilà : des heures ouvertes ou fermées d\'un seul geste (une pause, un congé). Rien n\'est enregistré pendant la visite.'},
        {icon:'✅', go:'sched:' + kind, sel:'#sched .sch-apply', need:true, t:'Pour combien de temps ?', p:kind === 'avail' ? '<b>Seulement ce jour-là</b> (un rendez-vous chez le dentiste), <b>pendant quelques semaines</b> ou <b>en permanence</b> (ton horaire habituel). Puis « Enregistrer ».' : (ph ? '<b>Seulement ce jour-là</b> (un congé)' : '<b>Seulement cette semaine</b> (un congé)') + ', <b>pendant quelques semaines</b> (l\'horaire d\'été) ou <b>en permanence</b>. Puis « Enregistrer ».'},
        {icon:'👆', go:'sched:' + kind, tap:'#sched .btn[data-act="sc-close"]', need:true, t:'Fermer sans enregistrer', p:'Pendant la visite, on n\'enregistre rien.', do:'Touche « Annuler ».'}];
    }
    var dayTry = ph ? [
        {icon:'👉', go:'home', try:'[data-act="ph-day"][data-v="1"]', need:true, t:'Changer de jour', p:'‹ et › changent de jour. Après la visite, tu pourras aussi glisser l\'écran du doigt.', tryT:'Essaie : touche › pour voir demain.', done:'Voilà demain.'},
        {icon:'👆', go:'home', tap:'[data-act="today"]', need:true, t:'Revenir à aujourd\'hui', p:'Pas perdu : un bouton te ramène toujours à la journée en cours.', do:'Touche « Aujourd\'hui ».'}]
      : [{icon:'👉', go:'tab:agenda', try:'#top .days', need:true, t:'Changer de jour', p:'La semaine en haut : touche un jour pour le voir ; ‹ et › changent de semaine.', tryT:'Essaie : touche un autre jour.', done:'L\'agenda montre ce jour-là.'}];
    var P = {
      hello:['Bienvenue', [{icon:'👋', go:'home', t:'Bienvenue' + (nm ? ', ' + nm : '') + ' !',
        p:'On fait le tour de l\'app ensemble. Ici, c\'est toi qui touches : je t\'éclaire le bouton, tu le touches, et je t\'explique ce qui s\'ouvre.',
        x:'Rien de ce que tu essaies pendant la visite n\'est enregistré' + (own ? ', sauf la couleur de l\'app si tu en choisis une : elle reste' : '') + '. Le ✕ en haut arrête la visite ; elle reste dans « Plus ».'}]],
      install:inst && [ph ? 'L\'app sur ton téléphone' : 'L\'app sur ton ordinateur', (ph ? [
          {icon:'📲', t:'D\'abord : l\'app sur ton écran d\'accueil', p:'Avec son icône sur ton écran d\'accueil, l\'app s\'ouvre d\'un seul geste, comme une vraie app : plus besoin de chercher la page.'}
        ].concat(nav('plus', 'L\'app sur ton écran d\'accueil', 'C\'est dans « Plus ».'), [
          {icon:'👆', tap:'.ph-row[data-act="app-install"]', need:true, t:'Mettre l\'app sur l\'écran d\'accueil', p:'Les étapes pour ton téléphone.', do:'Touche « Mettre l\'app sur l\'écran d\'accueil ».'}])
        : [
          {icon:'💻', t:'D\'abord : l\'app sur ton bureau', p:'Une icône Garage sur ton bureau (et sur ton téléphone) : l\'app s\'ouvre d\'un clic, dans sa propre fenêtre.'},
          {icon:'👆', tap:'.nf-app [data-act="app-install"]', need:true, t:'Installer l\'app', p:'En bas du menu, à gauche.', do:'Touche « Installer l\'app » en bas du menu.'}]).concat([
          {icon:'📲', try:'#sheet .inst-main', need:true, t:'Fais-le maintenant', p:ph ? 'Suis les étapes de ton téléphone : 2 ou 3 gestes. La visite t\'attend ici.' : 'Le bouton (ou les étapes) met l\'app sur ton bureau. Plus bas : la même chose pour ton téléphone.',
            tryT:'Fais-le maintenant, ou touche « Suivant » pour le faire plus tard.', done:'Super ! La prochaine fois, ouvre l\'app avec son icône Garage.'},
          {icon:'👆', tap:'#sheet .sheet-head [data-act="sheet-close"]', need:true, t:'Fermer', p:'Ces étapes restent dans « ' + (ph ? 'Plus' : 'Installer l\'app') + ' » si tu veux les revoir.', do:'Touche ✕ en haut pour fermer.'}]).concat(ph ? nav(A().defTab(), 'Maintenant, la visite', 'On revient à ta page de départ : c\'est là que la visite commence.') : [])],   /* (back where the visit goes on: by his own touch) */
      dash:(own || bur) && ['Le tableau de bord', nav('accueil', 'Le tableau de bord', 'Ton tableau de bord : la journée et le mois d\'un coup d\'œil.').concat([
        {icon:'🏠', go:'tab:accueil', sel:'main .rings, main .ringcard, main', t:'D\'un coup d\'œil', p:'Les jobs du jour, ce qui est réservé cette semaine, l\'argent encaissé ce mois-ci et ce qui reste à recevoir.' + (own ? ' Seuls toi et le bureau voyez ces chiffres (sauf si tu le permets à quelqu\'un).' : '')},
        {icon:'🚚', go:'tab:accueil', sel:'.mcard, .qrow', need:true, t:'Tes mécanos aujourd\'hui', p:'Une carte par mécano : ses jobs du jour, ce qui est fait, et s\'il est en route vers un client.'}].concat(ph ? [] : [{icon:'🧩', go:'tab:accueil', sel:'#tiles', need:true, t:'Les tuiles', p:'Une tuile pour chaque partie de l\'app, avec ce qui attend : les factures à recevoir, le stock à racheter…'}]))],
      day:mec && ['Ta journée', [
        {icon:'📅', go:'home', sel:'.dayhead, #top', t:'Ta journée', p:'Ton écran de tous les jours : la date en haut, tes rendez-vous en dessous.'}].concat(ph ? dayTry : [], [
        {icon:'☀️', go:'home', sel:'.shift', need:true, t:'Commencer ma journée', p:'Le matin, en partant : <b>« Commencer ma journée »</b>. Ta position est partagée pendant ta journée seulement ; le soir, <b>« Fin de journée »</b> arrête tout.', x:'Pendant la visite, on n\'y touche pas.'},
      ].concat(ph ? [] : nav('agenda', 'Tes rendez-vous', 'Sur l\'ordinateur, tous tes rendez-vous sont dans l\'agenda.'), [   /* (on the computer, his day is in the schedule: he goes there himself) */
        {icon:'🔧', go:ph ? 'home' : 'tab:agenda', sel:'.ph-list, .cal, .list, #main .nrow', t:'Tes rendez-vous', p:'Une ligne par client : l\'heure, l\'auto, le travail. L\'étiquette dit où tu en es : <b>Planifié</b>, <b>En route</b>, <b>Sur place</b>, <b>Terminé</b>.'},
        {icon:'👆', go:ph ? 'home' : 'tab:agenda', tap:'.ph-job, .ticket, #main .nrow, .appt', need:true, t:'Ouvre un rendez-vous', p:'Pour voir une job, tu touches sa ligne.', do:'Touche le rendez-vous éclairé.'}]))],
      job:mec && ['Une job, du début à la fin', [
        {icon:'📋', go:'job', sel:'.pjob, #main .sect', t:'La fiche de la job', p:'L\'auto, les travaux à faire, et les boutons pour <b>appeler</b> le client, lui <b>texter</b> ou ouvrir l\'<b>itinéraire</b> dans ton GPS.'},
        {icon:'⚫', go:'job', sel:'.nextbtn', need:true, t:'Le gros bouton', p:'Il dit toujours la prochaine étape : <b>« Je pars »</b> (le client reçoit un texto avec ton heure d\'arrivée), puis <b>« Je suis arrivé »</b>, puis <b>« Travaux terminés »</b>.', x:'Pendant la visite, on n\'y touche pas : il enverrait un vrai texto.'},
        {icon:'👆', go:'job', tap:'#veh-fold:not([open]) > summary', need:true, t:'Les sections', p:'La fiche est rangée en sections : chacune s\'ouvre d\'un toucher.', do:'Touche « Véhicule et fiche technique ».'},
        {icon:'🔎', go:'job', sel:'#veh-fold, #veh-sect', need:true, t:'Le VIN et la fiche du moteur', p:'<b>« Scanner le VIN »</b> : la caméra lit le numéro, et l\'année, la marque, le modèle et le moteur se remplissent. La fiche du moteur (huile, filtres) est gardée pour la prochaine fois.'},
        {icon:'👆', go:'job', tap:'#wv-fold:not([open]) > summary', need:true, t:'La décharge du client', p:'À toi : la décharge.', do:'Touche « Décharge du client ».'},
        {icon:'✍️', go:'job', sel:'#wv-fold, #wv-sect', need:true, t:'La décharge du client', p:'Avant de commencer, le client lit la décharge et signe directement sur ton écran. Pas de photos à prendre.'},
        {icon:'➕', go:'job', sel:'#xp-fold, #xp-sect', need:true, t:'Travaux supplémentaires', p:'Tu trouves autre chose à réparer ? Écris-le avec son prix : le client accepte en signant ou par texto, et ça s\'ajoute à la facture. Rien sans son accord.'},
        {icon:'👆', go:'job', tap:'#inv-fold:not([open]) > summary', need:true, t:'La facture', p:'Dernière section : la facture.', do:'Touche « Facture ».'},
        {icon:'🧾', go:'job', sel:'#inv-fold, [data-act="invoice"]', need:true, t:'La facture sur place', p:'Quand c\'est fini : <b>« Faire la facture »</b>. Services, pièces et taxes se calculent tout seuls ; le client paie par carte, comptant ou virement, et reçoit sa facture par texto.'}]],
      plusbtn:mec && ph && ['Le bouton « + »', [
        {icon:'👆', tap:'#tabbar .tab-new:not([hidden])', need:true, t:'Le bouton « + »', p:'Le « + » au milieu de la barre : pour un client qui arrive sans rendez-vous.', do:'Touche le « + ».'},
        {icon:'➕', sel:'#sheet .ph-menu', need:true, t:'Ajouter', p:'<b>« Facture sur place »</b> pour un client sans rendez-vous, <b>« Nouveau client »</b> pour créer sa fiche' + (can('book') ? ', <b>« Nouvelle réservation »</b>' : '') + '.'},
        {icon:'👆', tap:'#sheet .sheet-head [data-act="sheet-close"]', need:true, t:'Fermer', p:'On ne crée rien pendant la visite.', do:'Touche ✕ pour fermer.'}]],
      /* (a mechanic who may only book: on the phone, the « + » already shows « Nouvelle réservation ») */
      agenda:(own || bur || can('agenda') || (can('book') && !ph)) && ['L\'agenda', (ph ? nav('jour', 'L\'agenda', 'L\'agenda de l\'équipe.') : nav('agenda', 'L\'agenda', 'L\'agenda de l\'équipe.')).concat(
        (own || bur || can('agenda')) ? (ph ? [
          {icon:'📅', go:'home', sel:'.ph-list, #main .ph-job, #main', t:'L\'agenda', p:BLK ? 'La journée en trois blocs (matin, après-midi, soir), avec les rendez-vous dans l\'ordre de la route.' + (own || bur || can('book') ? ' « + Réserver » dans un bloc pour réserver ; touche un rendez-vous pour l\'ouvrir.' : '') : 'La journée de toute l\'équipe : un rendez-vous par ligne, dans l\'ordre.' + (own || bur || can('book') ? ' Touche un moment libre pour réserver ; touche un rendez-vous pour l\'ouvrir.' : '')},
          {icon:'👉', go:'home', try:'.chips.trucks', need:true, t:'Un camion à la fois', p:'Les boutons en haut montrent un seul camion, avec son mécano.', tryT:'Essaie : touche « Camion 1 », puis « Tous ».', done:'La journée suit le camion que tu choisis.'}]
          : [{icon:'📅', go:'tab:agenda', sel:'.cal, .list, main', t:'L\'agenda', p:(own || bur ? (BLK ? 'Chaque colonne, c\'est un camion. Les rendez-vous sont par bloc (matin, après-midi, soir) : l\'app répartit les jobs entre les camions et fait la route la plus courte. Touche un rendez-vous pour l\'ouvrir.' : 'Chaque colonne, c\'est un camion (ou un mécano). Touche une case libre pour réserver à cette heure-là ; touche un rendez-vous pour l\'ouvrir.') : 'Les rendez-vous de toute l\'équipe' + (can('book') ? '.' : ', en lecture seulement.'))}]) : [],
        mec && ph ? [] : dayTry,   /* (the mechanic tried the days on his phone screen already) */
        ph ? [] : [{icon:'👉', go:'tab:agenda', try:'[data-g="affichage"]', need:true, t:'Jour, semaine ou liste', p:'Trois façons de voir l\'agenda.', tryT:'Essaie : touche « Semaine », puis « Jour ».', done:'La vue change tout de suite.'}],
        (own || bur || can('book')) ? [{icon:'➕', go:ph ? 'home' : 'tab:agenda', sel:'#top [data-act="new"]', need:true, t:'« + Réservation »', p:BLK ? 'Choisis le client, le service, puis le bloc (matin, après-midi ou soir) : l\'app propose les meilleurs blocs, près des autres jobs du coin. Personne n\'est assigné : l\'app fait les routes.' : 'Choisis le client et le service : l\'app propose les moments libres, près des autres jobs du même coin. Le client reçoit sa confirmation.', x:'On ne réserve pas pendant la visite.'}] : [],
        can('hours_others') ? (ph ? nav('heures', 'Les heures d\'ouverture', 'Les heures d\'ouverture du garage.') : []).concat(sched('garage', '[data-act="sched"][data-v="garage"]', 'Touche « Modifier l\'horaire ».', 'Modifier l\'horaire', A().truckMode && A().truckMode() ? 'Chaque camion a son horaire, dans une grande grille : un onglet par camion, et « De base » pour les heures du garage.' : 'Les heures d\'ouverture du garage s\'ouvrent dans une grande grille.')) : [])],
      clients:can('clients') && ['Les clients', nav('clients', solo ? 'Tes clients' : 'Les clients', 'Les fiches des clients.').concat([
        {icon:'👤', go:'tab:clients', sel:'main', t:solo ? 'Tes clients' : 'Les clients', p:'La fiche de chaque client : téléphone, adresse, ses autos et l\'historique de ses visites.'},
        {icon:'🔎', go:'tab:clients', try:'#cl-q', after:'#cl-list', need:true, t:'Chercher', p:'Par nom, téléphone ou code postal.', tryT:'Essaie : touche la case et écris les premières lettres d\'un nom.', done:'La liste se raccourcit pendant que tu écris.'},
        {icon:'👆', go:'tab:clients', tap:'#cl-list .crow', need:true, t:'Ouvre une fiche', p:'Touche un client pour voir sa fiche.', do:'Touche un client de la liste.'},
        {icon:'📇', sel:'#main .sect, #main', t:'La fiche du client', p:'Ses coordonnées, ses autos, ses visites et ce qu\'il doit. De là, tu l\'appelles ou tu lui textes d\'un toucher.', x:'Pour revenir à la liste : la flèche ‹ en haut.'}])],
      factures:can('factures') && ['Les factures', nav('factures', solo && !tre ? 'Tes factures' : 'Les factures', 'Les factures ont leur propre écran.').concat([
        {icon:'💵', go:'tab:factures', sel:'main', t:solo && !tre ? 'Tes factures' : 'Les factures', p:'Celles à recevoir et celles déjà payées. ' + (own || bur || can('editinv') ? 'Ouvre une facture pour la revoir, la renvoyer au client ou la marquer payée.' : 'Ouvre une facture pour la revoir ou la renvoyer au client.')},
        {icon:'👉', go:'tab:factures', try:'[data-g="filtrer"] .chip', sel:'[data-g="filtrer"]', need:true, t:'Les filtres', p:'Tu choisis ce que tu veux voir.', tryT:'Essaie : touche « Payées », puis « Non payées ».', done:'La liste change selon le filtre.'},
        {icon:'❓', go:'tab:factures', try:'[data-g="filtrer"] .qhelp', after:'.helptip', need:true, t:'Les petits « ? »', p:'Partout dans l\'app, un <b>?</b> à côté d\'un mot donne une explication simple.', tryT:'Essaie : touche le ? à côté des filtres.', done:'Touche-le encore pour fermer l\'explication.'}])],
      tresor:can('tresor') && ['La trésorerie', nav('tresor', 'La trésorerie', 'L\'argent du garage.').concat([
        {icon:'💼', go:'view:dep', sel:'#top', t:'La trésorerie', p:'Ce qui entre (les factures payées), ce qui sort (les dépenses) et ce qui reste.'},
        {icon:'👆', go:'view:dep', tap:'[data-act="exp-new"]', need:true, t:'Ajouter une dépense', p:'Chaque reçu devient une dépense.', do:'Touche « + Dépense ».'},
        {icon:'📷', sel:'.x-scan', need:true, t:'Scanner le reçu', p:'Le plus rapide : prends le reçu en photo, bien à plat. La date, le magasin, le total, la TPS, la TVQ et le paiement se remplissent ; tu vérifies les cases marquées et tu corriges au besoin.', x:'Pendant la visite, on ne prend pas de photo : essaie plutôt d\'écrire un montant.'},
        {icon:'✍️', try:'#x-total', after:'#x-taxes', need:true, t:'Le montant', p:'Tu peux aussi l\'écrire toi-même : le total payé, taxes comprises.', tryT:'Essaie : écris 57,49 dans « Total payé ».', done:'La TPS et la TVQ se calculent toutes seules. Ici aussi : la photo du reçu, le fournisseur, la catégorie.'},
        {icon:'👆', tap:'#sheet .sheet-head [data-act="sheet-close"]', need:true, t:'Fermer sans enregistrer', p:'On n\'enregistre rien pendant la visite.', do:'Touche ✕ pour fermer.'},
        {icon:'📑', go:'view:dep', sel:'main', t:'Les dépenses', p:'Toutes les dépenses de la période, avec la photo de leurs reçus. Touche une ligne pour la voir, la corriger ou la supprimer.'},
        {icon:'👆', go:'view:dep', tap:'[data-act="tr-view"][data-v="rap"]', need:true, t:'Le rapport', p:'Le rapport est juste à côté des dépenses.', do:'Touche « Rapport et taxes ».'},
        {icon:'📊', go:'view:rap', sel:'main', t:'Le rapport et les taxes', p:'Revenus, dépenses et profit, par camion. Et les <b>taxes à remettre</b> : la TPS et la TVQ perçues sur les factures, moins celles payées sur les dépenses.'},
        {icon:'👉', go:'view:rap', try:'.trbar', need:true, t:'La période', p:'Le mois, le trimestre ou l\'année ; ‹ et › reculent ou avancent d\'une période.', tryT:'Essaie : touche « Trimestre », puis ‹.', done:'Les chiffres suivent la période que tu choisis.'},
        {icon:'📥', go:'view:rap', sel:'[data-act="tr-xlsx"]', need:true, t:'Pour le comptable', p:'Un fichier Excel avec tout le détail (revenus, dépenses, taxes), prêt à envoyer.'}])],
      /* (right after the treasury, its own « Inventaire » button is right there) */
      stock:can('stock') && ['L\'inventaire', (can('tresor') && (own || mr === 'tresorier') ? [{icon:'👆', nav:'stock', tap:'#top a[href="#stock"], #main a[href="#stock"]', need:true, t:'L\'inventaire', p:'L\'inventaire est juste à côté, dans la trésorerie.', do:'Touche « Inventaire ».'}] : nav('stock', 'L\'inventaire', 'Les pièces du garage.')).concat([
        {icon:'📦', go:'stock', sel:'main', need:true, t:'L\'inventaire', p:'Toutes les pièces du garage, dans une seule liste. Quand une pièce sert pour une job, elle se retire toute seule de l\'inventaire.'}])],
      map:can('map') && ['La carte de l\'équipe', nav('carte', 'La carte de l\'équipe', 'Où est chacun, et ses rendez-vous du jour.').concat([
        {icon:'🗺️', go:'carte', try:'#map-slot', t:'La carte de l\'équipe', p:'La <b>Centrale</b>, d\'où partent les camions. Chaque mécano a sa couleur, ses rendez-vous <b>numérotés dans l\'ordre</b> (1, 2, 3…) et son trajet de la journée, par les routes.', tryT:'Essaie : touche un numéro, ou glisse la carte avec ton doigt.', done:'Le numéro montre le client, l\'adresse et l\'heure.'},
        {icon:'📍', go:'carte', sel:'.tm-mc', need:true, t:'La journée de chacun', p:'Sous la carte : les arrêts de chaque mécano, la longueur de son trajet depuis la Centrale, et qui est en route vers quel client.'}])],
      avail:mec && !TRK && ['Ton horaire', nav('dispos', 'Tes disponibilités', 'Quand tu travailles.').concat(
        sched('avail', '[data-act="sched"][data-v="avail"]', 'Touche « Modifier mes disponibilités ».', 'Tes disponibilités', 'Tu dis au bureau quand tu travailles : l\'agenda ne te donne des rendez-vous que dans tes heures.'))],
      dispos:(own || bur) && !TRK && ['Les disponibilités', nav('dispos', 'Les disponibilités', 'Quand chaque mécano travaille.').concat([
        {icon:'🗓', go:'dispos', sel:'main', t:'Les disponibilités des mécanos', p:'Quand chaque mécano travaille. L\'agenda ne propose que ses heures.' + (can('hours_others') ? ' Tu changes l\'horaire de chacun avec la même grille.' : '')},
        {icon:'👉', go:'dispos', try:'#main [data-g="mecano"]', need:true, t:'Un mécano à la fois', p:'Les noms en haut : la semaine de chacun.', tryT:'Essaie : touche le nom d\'un autre mécano.', done:'Voilà sa semaine : ses jours, ses heures, ses congés.'}])],
      settings:own && ['Les réglages', nav('reglages', 'Les réglages', 'Les réglages du garage.').concat([
        {icon:'👆', go:'set:', tap:'[data-act="ph-sec"][data-for="lux-sect"]', need:true, t:'Les couleurs de l\'app', p:'Les réglages sont rangés en sections.', do:'Touche « Couleurs de l\'app ».'},
        {icon:'🎨', go:'set:Couleurs', try:'#lux-sect', t:'Les couleurs', p:'Le mode vitrine : des panneaux en verre sur un fond de couleur. Toute l\'équipe voit celle que tu choisis.', tryT:'Choisis : touche une couleur, elle s\'applique tout de suite à toute l\'app.', done:'Elle reste : c\'est maintenant la couleur de l\'app pour toute l\'équipe. Tu peux en choisir une autre ici quand tu veux.'},
        {icon:'👆', go:'set:Couleurs', tap:'#lux-sect .ph-secback', need:true, t:'Tous les réglages', p:'Pour revenir à la liste des sections.', do:'Touche « ‹ Tous les réglages ».'},
        {icon:'⚙️', go:'set:', sel:'#ph-setlist, #setform', t:'Le reste des réglages', p:'Le nom du garage, les taxes, ton taux horaire, tes prix, l\'horaire, les mécanos et les camions, le bas des factures.'}])],
      team:own && ['L\'équipe et les accès', nav('equipe', 'L\'équipe et les accès', 'Les comptes de ton équipe.').concat([
        {icon:'✉️', go:'equipe', sel:'#eq-new', t:'Inviter une personne', p:'Son nom et son courriel, ses rôles et, pour un mécano, son camion (ses rendez-vous sont ceux du camion). Elle reçoit un lien et choisit son mot de passe (ou se connecte avec Google).'},
        {icon:'👉', go:'equipe', try:'#eq-new .rbox', need:true, t:'Les rôles', p:'Plusieurs rôles à la fois si tu veux (mécano et trésorier, par exemple).', tryT:'Essaie : coche « Trésorier ».', done:'Juste en dessous, « Ses droits » montre ce que ça lui donne : tu peux cocher ou décocher pour cette personne seulement. On n\'invite personne pendant la visite.'},
        {icon:'👥', go:'equipe', sel:'.eqp', need:true, t:'Les personnes', p:'<b>« Modifier »</b> change les rôles et les droits d\'une personne, ou bloque son accès.'},
        {icon:'👁', go:'equipe', sel:'#eq-viewas', need:true, t:'Voir l\'app comme…', p:'Tu vois exactement l\'écran d\'un mécano ou du trésorier, et sa visite guidée. Un bandeau en haut te ramène à ton compte.'},
        {icon:'☑️', go:'equipe', sel:'#eq-roles', need:true, t:'Ce que chaque rôle donne au départ', p:'Les cases de départ de chaque rôle. Un changement ici vaut pour toutes les personnes de ce rôle.'}])],
      end:['C\'est tout', [{icon:'✅', t:'C\'est tout !', p:'Tu connais l\'app. Si tu oublies quelque chose : <b>' + (ph ? 'Plus' : 'en bas du menu') + ' → « ' + (own ? 'Visite guidée de l\'app' : 'Revoir la visite guidée') + ' »</b>.' + (mec ? ' Bonne journée sur la route !' : '')}]]
    };
    /* the person's main job first, then what the other roles add (each part once) */
    var ORDER = {owner:['dash', 'agenda', 'clients', 'factures', 'tresor', 'stock', 'map', 'dispos', 'settings', 'team'],
      bureau:['dash', 'agenda', 'clients', 'factures', 'map', 'dispos', 'stock'],
      mecano:['day', 'job', 'plusbtn', 'clients', 'factures', 'map', 'avail', 'agenda', 'stock'],
      tresorier:['tresor', 'stock', 'factures', 'clients', 'agenda', 'map']};
    var keys = ['hello', 'install'];   /* first of all: the app on the home screen (or the desktop) */
    rolesOf(m).slice().sort(function(a, b){ return (a === mr ? -1 : 0) - (b === mr ? -1 : 0); }).forEach(function(r){ (ORDER[r] || []).forEach(function(k){ if (keys.indexOf(k) < 0) keys.push(k); }); });
    ['tresor', 'agenda', 'map', 'stock'].forEach(function(k){ if (keys.indexOf(k) < 0) keys.push(k); });   /* rights given to this person */
    keys.push('end');
    var out = [];
    keys.forEach(function(k){ var pt = P[k]; if (!pt) return; pt[1].filter(Boolean).forEach(function(x){ x.ch = pt[0]; out.push(x); }); });
    return out;
  }
  function val(id){ var e = document.getElementById(id); return e ? e.value.trim() : ''; }
  function eqErr(m){ var e = document.getElementById('nw-err'); if (e){ e.textContent = m; e.hidden = !m; if (m) e.scrollIntoView({block:'nearest'}); } else if (m) toast(m); }
  function keysDoc(patch){ return T.db.doc('config/keys').get().then(function(s){ var d = Object.assign({}, s.exists ? s.data() : {}, patch); return T.db.doc('config/keys').set(d); }); }

  function onAction(a, b){
    var id = b.dataset.id, v = b.dataset.v, api = A();
    /* in a preview, the buttons that act as that person (his workday, his position) are only shown */
    if (previewing() && (a === 'sh-start' || a === 'sh-end' || a === 'sh-wake')){ toast('Aperçu : ce bouton marche seulement sur le téléphone de ' + first(eff().name) + '.'); return; }
    if (previewing() && a === 'acct-out'){ stopView(); return; }
    switch (a){
      case 'pv-start': startView({role:b.dataset.role, mechanic:b.dataset.mech || null, name:b.dataset.name}); break;
      case 'pv-role': {
        var r = b.dataset.role, list = X.eq.list || [], mm = list.filter(function(x){ return x.role === r && x.active; })[0];
        if (r === 'mecano'){ var mn = mm && mm.mechanic ? mm.mechanic : api.mechanics()[0]; if (!mn){ toast('Invite d\'abord un mécano (Équipe et accès).'); break; } startView({role:'mecano', mechanic:mn, name:mm && mm.mechanic === mn ? mm.name : mn}); }
        else startView({role:r, name:mm ? mm.name : ROLE[r]});
        break;
      }
      case 'pv-person': { var pm = (X.eq.list || []).filter(function(x){ return x.user_id === v; })[0]; if (pm) startView({role:pm.role, roles:rolesOf(pm), perms:pm.perms || {}, mechanic:pm.mechanic || null, name:pm.name}); break; }
      case 'pv-exit': stopView(); break;
      case 'pv-fmt': switchFmt(); break;
      case 'rp': saveRole(b.dataset.role, b.dataset.k, b.checked, b); break;
      case 'rb': rightsRedraw(b.dataset.pre); break;
      case 'app-reload': location.reload(); break;
      case 'acct-out': {
        var pend = T.pending ? T.pending() : 0;
        if (pend && !X.outArmed){ X.outArmed = true; A().toast(pend + (pend > 1 ? ' changements pas encore envoyés' : ' changement pas encore envoyé') + ' : attends le retour du signal. Touche encore « Se déconnecter » pour les perdre.'); setTimeout(function(){ X.outArmed = false; }, 8000); break; }
        T.signOut(); break;
      }
      case 'acct-leave': {
        if (!X.leaveArmed){ X.leaveArmed = true; render(); clearTimeout(X.leaveT); X.leaveT = setTimeout(function(){ X.leaveArmed = false; render(); }, 8000); break; }
        clearTimeout(X.leaveT); X.leaveArmed = false; b.disabled = true;
        invoke('members', {action:'leave'}).then(function(){ A().toast('Ton compte est supprimé.'); setTimeout(function(){ T.signOut(); }, 600); },
          function(e){ b.disabled = false; render(); A().toast(e.message); });
        break;
      }
      case 'net-send': if (T.flush) T.flush(); break;
      case 'net-ok': if (T.clearFailed) T.clearFailed(); break;
      case 'sh-start': shiftStart(); break;
      case 'sh-end': shiftEnd(); break;
      case 'sh-wake': G.wakeWant = !G.wake; lsSet('gm.team.wake', G.wakeWant ? '1' : null); wake(G.wakeWant); setTimeout(shiftLine, 300); break;
      case 'er-start': { var j1 = api.findJob(id); if (j1) startEnRoute(j1); break; }
      case 'er-resend': { var j2 = api.findJob(id); if (j2) startEnRoute(j2, {resend:true}); break; }
      case 'er-notify': X.quiet[id] = typeof b.checked === 'boolean' ? !b.checked : !X.quiet[id]; render(); break;
      case 'er-copy': { var t = X.tracks[id]; if (t && navigator.clipboard) navigator.clipboard.writeText(trackLink(t)).then(function(){ toast('Lien copié'); }, function(){ toast(trackLink(t)); }); else if (t) toast(trackLink(t)); break; }
      case 'map-fit': fit(); break;
      case 'tm-mech': X.tmHide = X.tmHide || {}; X.tmHide[v] = !X.tmHide[v]; drawMap(); render(); break;
      case 'map-sel': selectMech(v); break;
      case 'map-path': X.showPath[v] = !X.showPath[v]; drawMap(); render(); if (X.showPath[v]) loadPath(v); break;   /* (the button changes at once; the path is drawn when it arrives) */
      case 'eq-back': location.hash = onPhone() ? 'plus' : 'reglages'; break;
      case 'eq-reload': X.eq.err = ''; X.eq.list = null; eqLoad(); render(); break;
      case 'eq-edit': X.eq.editing = v; X.eq.confirm = null; delete X.eq.draft.ed; render(); break;
      case 'eq-confirm': X.eq.confirm = v; X.eq.editing = null; delete X.eq.draft.ed; render(); break;
      case 'eq-cancel': X.eq.editing = null; X.eq.confirm = null; delete X.eq.draft.ed; render(); break;
      case 'eq-hidecred': X.eq.created = null; render(); break;
      case 'eq-copycred': { var pre = document.querySelector('.cred'); if (pre && navigator.clipboard) navigator.clipboard.writeText(pre.textContent).then(function(){ toast('Copié'); }, function(){}); break; }
      case 'eq-save': {
        var ers = rolesFrom('ed'), name = val('ed-name'), eb = {action:'update', user_id:v, name:name, roles:ers, perms:permsFrom(ers, 'ed')};
        if (!ers.length){ toast('Coche au moins un rôle.'); break; }
        if (document.getElementById('ed-truck')) eb.truck = val('ed-truck');
        if (val('ed-mech')) eb.mechanic = val('ed-mech');
        if (v === me.user_id && ers.indexOf('owner') < 0){ toast('Tu ne peux pas enlever ton propre rôle de propriétaire.'); break; }
        b.disabled = true;
        invoke('members', eb).then(function(r){ moveJobs(r); X.eq.list = r.members; X.eq.editing = null; delete X.eq.draft.ed; toast('Enregistré'); if (v === me.user_id) refreshMe(); render(); }, function(e){ b.disabled = false; toast(e.message); });
        break;
      }
      case 'eq-active': {
        var m = (X.eq.list || []).filter(function(x){ return x.user_id === v; })[0]; if (!m) break; b.disabled = true;
        invoke('members', {action:'update', user_id:v, active:!m.active}).then(function(r){ X.eq.list = r.members; toast(m.active ? 'Accès désactivé : ' + m.name + ' ne peut plus se connecter.' : 'Accès réactivé'); render(); }, function(e){ b.disabled = false; toast(e.message); });
        break;
      }
      case 'eq-pw': {
        var mp = (X.eq.list || []).filter(function(x){ return x.user_id === v; })[0]; if (!mp) break; b.disabled = true;
        invoke('members', {action:'password', user_id:v}).then(function(r){ X.eq.created = {name:mp.name, email:mp.email, password:r.password, reset:true}; render(); window.scrollTo(0, 0); }, function(e){ b.disabled = false; toast(e.message); });
        break;
      }
      case 'eq-remove': b.disabled = true; invoke('members', {action:'remove', user_id:v}).then(function(r){ moveJobs(r); X.eq.list = r.members; X.eq.confirm = null; toast('Compte supprimé'); render(); }, function(e){ b.disabled = false; toast(e.message); }); break;
      case 'eq-invite': {
        var inm = val('nw-name'), iem = val('nw-email'), irs = rolesFrom('nw'), imc = val('nw-mech'), itk = document.getElementById('nw-truck') ? val('nw-truck') : undefined;
        if (!inm) return eqErr('Écris le nom de la personne.');
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(iem)) return eqErr('Écris un courriel valide.');
        if (!irs.length) return eqErr('Coche au moins un rôle.');
        eqErr(''); b.disabled = true; b.textContent = 'Envoi…';
        invoke('members', {action:'invite', lang:lng(), name:inm, email:iem, roles:irs, perms:permsFrom(irs, 'nw'), mechanic:imc || undefined, truck:itk, base:trackBase()}).then(function(r){
          moveJobs(r); X.eq.list = r.members; X.eq.created = null; X.eq.invited = {name:inm, email:r.email || iem, link:r.link, mail:r.mail, message:r.message}; X.liveAt = 0; delete X.eq.draft.nw;
          ['nw-name', 'nw-email', 'nw-mech', 'nw-truck'].forEach(function(i){ var e = document.getElementById(i); if (e) e.value = ''; });
          render(); window.scrollTo(0, 0);
        }, function(e){ b.disabled = false; b.textContent = 'Envoyer l\'invitation'; eqErr(e.message); });
        break;
      }
      case 'eq-reinvite': {
        var rm = (X.eq.list || []).filter(function(x){ return x.user_id === v; })[0];
        b.disabled = true; b.textContent = 'Envoi…';
        invoke('members', {action:'invite-resend', lang:lng(), user_id:v, base:trackBase()}).then(function(r){
          X.eq.list = r.members; X.eq.created = null; X.eq.invited = {name:rm ? rm.name : '', email:r.email, link:r.link, mail:r.mail, message:r.message};
          render(); window.scrollTo(0, 0);
        }, function(e){ b.disabled = false; b.textContent = rm && rm.invite ? 'Renvoyer l\'invitation' : 'Envoyer une invitation'; toast(e.message); });
        break;
      }
      case 'eq-copylink': { var lk = X.eq.invited && X.eq.invited.link; if (lk && navigator.clipboard) navigator.clipboard.writeText(lk).then(function(){ toast('Lien copié'); }, function(){ toast(lk); }); else if (lk) toast(lk); break; }
      case 'eq-hideinv': X.eq.invited = null; render(); break;
      case 'eq-add': {
        var nm = val('nw-name'), em = val('nw-email'), rls = rolesFrom('nw'), mc = val('nw-mech'), tk0 = document.getElementById('nw-truck') ? val('nw-truck') : undefined;
        if (!nm) return eqErr('Écris le nom de la personne.');
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(em)) return eqErr('Écris un courriel valide.');
        if (!rls.length) return eqErr('Coche au moins un rôle.');
        eqErr(''); b.disabled = true; b.textContent = 'Création…';
        invoke('members', {action:'create', name:nm, email:em, roles:rls, perms:permsFrom(rls, 'nw'), mechanic:mc || undefined, truck:tk0}).then(function(r){
          moveJobs(r); X.eq.list = r.members; X.eq.invited = null; X.eq.created = {name:nm, email:em, password:r.password}; X.liveAt = 0; delete X.eq.draft.nw;
          ['nw-name', 'nw-email', 'nw-mech', 'nw-truck'].forEach(function(i){ var e = document.getElementById(i); if (e) e.value = ''; });
          render(); window.scrollTo(0, 0);
        }, function(e){ b.disabled = false; b.textContent = 'Créer le compte'; eqErr(e.message); });
        break;
      }
      case 'gh-save': case 'gh-clear': {
        var body = a === 'gh-clear' ? {ghlToken:'', ghlLocation:''} : {};
        if (a === 'gh-save'){
          var tk = val('gh-token'), lc = val('gh-loc');
          if (!tk && !lc){ toast('Colle la clé et l\'ID du compte.'); break; }
          if (!(X.eq.secrets || {}).ghl && (!tk || !lc)){ toast('Il faut la clé ET l\'ID du compte.'); break; }
          if (tk) body.ghlToken = tk; if (lc) body.ghlLocation = lc;
        }
        b.disabled = true; body.action = 'secrets-set';
        invoke('members', body).then(function(r){ X.eq.secrets = r; ['gh-token', 'gh-loc'].forEach(function(i){ var e = document.getElementById(i); if (e) e.value = ''; }); toast(a === 'gh-clear' ? 'GoHighLevel débranché' : r.ghl ? 'GoHighLevel branché ✓ Envoie un texto test.' : 'Enregistré (il manque encore une info)'); render(); }, function(e){ b.disabled = false; toast(e.message); });
        break;
      }
      case 'gh-test': {
        var ph = val('gh-test'); if (!ph){ toast('Écris ton numéro.'); break; }
        b.disabled = true; b.textContent = 'Envoi…';
        invoke('members', {action:'sms-test', lang:lng(), phone:ph}).then(function(){ b.disabled = false; b.textContent = 'Envoyer'; toast('Texto test envoyé ✓ Vérifie ton téléphone.'); }, function(e){ b.disabled = false; b.textContent = 'Envoyer'; toast(e.message); });
        break;
      }
      case 'st-save': case 'st-clear': {
        var sk = a === 'st-clear' ? '' : val('st-key'); if (a === 'st-save' && !sk){ toast('Colle ta clé secrète Stripe.'); break; }
        b.disabled = true;
        invoke('members', {action:'secrets-set', stripeKey:sk}).then(function(r){
          X.eq.secrets = r; X.payOnline = !!r.stripe;
          return keysDoc({payOnline:!!r.stripe}).then(function(){ return r; });
        }).then(function(r){ var e = document.getElementById('st-key'); if (e) e.value = ''; toast(r.warn ? r.warn : !sk ? 'Stripe débranché' : r.stripeMode === 'test' ? 'Stripe branché en mode test ✓' : 'Stripe branché ✓ Les factures envoyées auront « Payer ».'); render(); },
          function(e){ b.disabled = false; toast(e.message); });
        break;
      }
      case 'tt-save': case 'tt-clear': {
        var k = a === 'tt-clear' ? '' : val('tt-key'); if (a === 'tt-save' && !k){ toast('Colle ta clé TomTom.'); break; }
        b.disabled = true;
        invoke('members', {action:'secrets-set', tomtomKey:k}).then(function(r){ X.eq.secrets = r; return keysDoc({tomtom:k || null}); }).then(function(){ var e = document.getElementById('tt-key'); if (e) e.value = ''; toast(k ? 'Clé TomTom enregistrée ✓' : 'Clé TomTom retirée'); render(); }, function(e){ b.disabled = false; toast(e.message); });
        break;
      }
    }
  }
  function refreshMe(){ return T.sb.from('members').select('*').eq('user_id', me.user_id).maybeSingle().then(function(r){ if (r.data){ me = T.member = r.data; render(); } }); }

  /* ================= styles ================= */
  var css = document.createElement('style');
  css.textContent =
    '.acct{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:4px 12px;font-size:14.5px;color:var(--muted);margin-bottom:10px}.acct b{color:var(--ink)}' +
    '.linkbtn{background:none;border:0;color:var(--steel);font-weight:600;text-decoration:underline;cursor:pointer;min-height:40px;padding:0 2px}' +
    '.shift{margin-bottom:12px;border-left:4px solid var(--line-strong)}.shift.on{border-left-color:var(--ok)}.sh-head{display:flex;align-items:center;gap:10px}' +
    '.sh-dot{width:12px;height:12px;border-radius:50%;background:var(--ok);flex:none;box-shadow:0 0 0 4px var(--ok-bg)}' +
    '@media (prefers-reduced-motion:no-preference){.sh-dot{animation:shp 2s ease-in-out infinite}@keyframes shp{50%{box-shadow:0 0 0 8px var(--ok-bg)}}}' +
    '.sh-line{font-weight:600;color:var(--ok);min-height:1.4em}.sh-line.warn{color:var(--warn)}' +
    '.er-acts{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.er-acts input{flex:1 1 160px;min-width:0}.er-line{font-weight:600}.er-line.ok{color:var(--ok)}' +
    '.er-eta{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px}.er-eta b{font-family:var(--f-display);font-size:34px;line-height:1}' +
    '.banner.ok{background:var(--ok-bg)}.btn.solid.danger,.btn.danger.solid{background:var(--bad);border-color:var(--bad);color:#fff}' +
    '.mapslot{margin:0 0 10px;border-radius:12px;overflow:hidden;border:1px solid var(--line);background:var(--sunk)}' +
    '.gm-map{height:calc(100vh - 230px);min-height:440px;width:100%;isolation:isolate}.ui-phone .gm-map{height:calc(100dvh - 268px);min-height:380px}' +
    '.ui-phone .tm-slot{margin-left:-12px;margin-right:-12px;border-radius:18px}' +
    '.tm-legend{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}.tm-chip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line-strong);background:var(--card);border-radius:999px;padding:6px 12px;font:600 14px/1 var(--f-body);color:var(--ink);cursor:pointer;min-height:38px}' +
    '.tm-chip i{width:12px;height:12px;border-radius:50%;display:inline-block}.tm-chip span{color:var(--muted);font-weight:500}.tm-chip.off{opacity:.45;text-decoration:line-through}' +
    '.tm-stop{display:grid;place-items:center;width:100%;height:100%;border-radius:50%;background:var(--c);color:#fff;font:800 14px/1 var(--f-body);border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.35)}' +
    '.tm-stop.done{opacity:.5}.tm-stop.go{box-shadow:0 0 0 4px rgba(242,178,0,.65),0 2px 6px rgba(0,0,0,.35)}.tm-stop.here{outline:3px solid var(--c);outline-offset:2px}' +
    '.tm-stop.mini,.tm-mech.mini,.tm-hq.mini{display:inline-grid;width:22px;height:22px;font-size:11px;border-width:2px;vertical-align:-6px;margin-right:6px}' +
    '.tm-mech{display:grid;place-items:center;width:100%;height:100%;border-radius:12px;background:var(--c);color:#fff;font:800 14px/1 var(--f-body);border:3px solid #fff;box-shadow:0 0 0 3px var(--c),0 3px 10px rgba(0,0,0,.4)}.tm-mech.stale{filter:grayscale(.8);opacity:.75}' +
    '.mc-head .tm-mech{width:40px;height:40px;flex:none}' +
    '.tm-hq{display:grid;place-items:center;width:100%;height:100%;border-radius:14px;background:#1E1915;color:#fff;font-size:22px;border:3px solid #F7C873;box-shadow:0 4px 14px rgba(0,0,0,.45)}.tm-hq.mini{font-size:12px;border-radius:6px}' +
    '.tm-hq-tip{font-weight:800;background:#1E1915;color:#F7C873;border:0}.tm-hq-tip::before{border-right-color:#1E1915}' +
    '.tm-dash{display:inline-block;width:26px;height:0;border-top:3px dotted var(--ink);vertical-align:4px;margin-right:6px}' +
    '.tm-line{display:inline-block;width:26px;height:0;border-top:5px solid #7A8794;border-radius:3px;vertical-align:3px;margin-right:6px}.tm-leg b.tm-line{width:26px;height:0}.tm-route{margin:6px 0 2px}' +
    '.tm-leg b.mini{width:22px;height:22px;flex:none;margin:0}.tm-leg b.tm-mech.mini{border-radius:7px;font-size:9px;box-shadow:0 0 0 2px var(--c)}.tm-leg b.tm-dash{width:26px;height:0}' +
    '.tm-pop{display:grid;gap:2px;font-size:14px}.tm-pop .btn{margin-top:6px;justify-self:start}.tm-st{color:#6B5E55;font-size:12.5px}' +
    '.tm-stops{list-style:none;margin:6px 0 0;padding:0;display:grid;gap:8px}.tm-stops li{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;gap:4px 10px;align-items:center}.tm-stops li>div{display:grid;min-width:0}.tm-stops .tm-stop.mini{margin:0;width:26px;height:26px;font-size:12px}' +
    '.gm-pin-wrap{background:none;border:0}' +
    '.legend{display:flex;flex-wrap:wrap;gap:6px 14px;color:var(--muted);margin:0 0 12px}.legend span{display:inline-flex;align-items:center;gap:6px}' +
    '.mc{border-top:1px solid var(--line);padding-top:12px;display:grid;gap:6px}.mc:first-of-type{border-top:0;padding-top:0}' +
    '.mc-head{display:flex;align-items:center;gap:10px}.mc-who{display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px}' +
    '.pillx{display:inline-block;border-radius:999px;padding:2px 10px;font-size:13px;font-weight:600;background:var(--idle-bg);color:var(--idle)}' +
    '.pillx.p-route{background:var(--warn-bg);color:var(--warn)}.pillx.p-shift{background:var(--steel-soft);color:var(--steel)}.pillx.p-stale{background:var(--idle-bg);color:var(--idle)}' +
    '.pillx.r-owner{background:var(--warn-bg);color:var(--warn)}.pillx.r-bureau{background:var(--info-bg);color:var(--info)}.pillx.r-mecano{background:var(--steel-soft);color:var(--steel)}' +
    '.eqp{border-top:1px solid var(--line);padding-top:12px;display:grid;gap:8px}.eqp:first-of-type{border-top:0;padding-top:0}.eqp.off{opacity:.7}' +
    '.eqp-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}.eqp-head>div{min-width:0;overflow-wrap:anywhere}.eq-form{display:grid;gap:10px}' +
    '.roles{margin:0;padding-left:18px;display:grid;gap:4px;color:var(--muted)}' +
    '.credl{margin:0;background:var(--sunk);border-radius:10px;padding:12px;display:grid;gap:8px}.credl div{display:grid;gap:1px}.credl dt{font:600 12.5px/1.2 var(--f-display);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}' +
    '.credl dd{margin:0;overflow-wrap:anywhere;font-weight:600}.credl dd.pw{font:600 22px/1.2 var(--f-mono);letter-spacing:.04em;white-space:nowrap;overflow-wrap:normal}' +
    '.created{border:2px solid var(--ok)}details summary{cursor:pointer;font-weight:600;min-height:36px;display:flex;align-items:center}details ol{margin:6px 0 0;padding-left:18px;display:grid;gap:4px}' +
    '.badge{display:inline-block;border-radius:6px;padding:1px 8px;font-weight:600;background:var(--idle-bg);color:var(--idle)}.badge.ok{background:var(--ok-bg);color:var(--ok)}.badge.warn{background:var(--warn-bg);color:var(--warn)}' +
    '.leaflet-container{font:inherit}.leaflet-control-attribution{font-size:11px}' +
    '.rbox{border:1px solid var(--line);border-radius:14px;padding:8px 12px 6px;margin:0;display:grid;gap:2px}.rbox legend{font-weight:700;padding:0 6px}.rbox .check{align-items:flex-start;padding:4px 0}.rbox .check>span{display:grid;gap:1px}' +
    '.rt-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:14px}.rt{width:100%;border-collapse:collapse;font-size:14px}.rt th,.rt td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:center}' +
    '.rt thead th{font-weight:700;background:var(--sunk)}.rt tbody th{text-align:left;font-weight:600}.rt tr:last-child>*{border-bottom:0}.rt input{width:22px;height:22px;min-height:0;accent-color:var(--signal)}.rt-on{color:var(--ok);font-weight:800}.rt-na{color:var(--muted)}' +
    '.r-add{color:var(--ok)}.r-del{color:var(--bad)}.pills{display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end}.pillx.r-tresorier{background:var(--ok-bg);color:var(--ok)}' +
    '.pv-btns{display:flex;flex-wrap:wrap;gap:8px}' +
    '.rp-row{align-items:flex-start;padding:6px 0}.rp-row input{margin-top:2px;flex:none}.rp-row>span{display:grid;gap:1px}' +
    '#pv-bar{position:fixed;top:0;left:0;right:0;z-index:50;display:flex;align-items:center;gap:6px 12px;flex-wrap:wrap;justify-content:center;padding:calc(6px + env(safe-area-inset-top,0px)) 10px 6px;background:#1E1915;color:#F7F1EA;font-size:14.5px;box-shadow:0 4px 14px rgba(0,0,0,.25)}' +
    '#pv-bar .btn{min-height:34px;padding:0 12px;background:#F7F1EA;color:#1E1915;border-color:#F7F1EA}#pv-bar b{color:#FFB37A}.pv-short{display:none}' +
    '@media (max-width:560px){#pv-bar .pv-long{display:none}#pv-bar .pv-short{display:inline}#pv-bar{font-size:14px}}' +
    'body.pv-on{padding-top:var(--pvh,48px)}body.pv-on .top{top:calc(var(--pvh,48px) + 6px)}body.pv-on.ui-pc .tabbar{top:calc(var(--pvh,48px) + 12px)}' +
    'body.pv-narrow.ui-phone .top{max-width:450px;margin-left:auto;margin-right:auto}body.pv-narrow.ui-phone .wrap{max-width:430px}body.pv-narrow.ui-phone .tabbar{width:min(430px,calc(100% - 20px))}body.pv-narrow.ui-phone .sheet{max-width:430px}' +
    '#pv-bar .pv-fmt{background:transparent;color:#F7F1EA;border-color:rgba(247,241,234,.5)}';
  document.head.appendChild(css);

  var MAP_ICON = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/></svg>';
  /* ---------- hors ligne : bandeau d'état ---------- */
  var COLNAME = {jobs:'une job', clients:'une fiche client', days:'l\'horaire', avail:'des dispos', config:'les réglages', specs:'une fiche technique', expenses:'une dépense', receipts:'un reçu', photos:'une photo', stock:'le stock'};
  function netBanner(){
    var n = T.net; if (!n || !me) return '';
    var h = '', p = n.pending, s = p > 1 ? 's' : '';
    if (X.newVersion) h += '<div class="banner ok" role="status" id="upd-banner"><p><b>Nouvelle version de l\'app prête.</b></p><button type="button" class="btn sm primary" data-act="app-reload">Mettre à jour</button></div>';
    if (n.offlineMode || n.online === false)
      h += '<div class="banner warn net" role="status"><p><b>Hors ligne.</b> ' + (p ? p + ' changement' + s + ' gardé' + s + ' sur le téléphone, envoyé' + s + ' au retour du signal.' : 'Tu travailles avec la copie du téléphone ; tes changements seront envoyés au retour du signal.') + '</p></div>';
    else if (p) h += '<div class="banner net" role="status"><p>' + (n.sending ? 'Envoi de ' + p + ' changement' + s + '…' : p + ' changement' + s + ' en attente d\'envoi.') + '</p>' + (n.sending ? '' : '<button type="button" class="btn sm" data-act="net-send">Envoyer maintenant</button>') + '</div>';
    if (n.failed && n.failed.length){
      h += '<div class="banner warn net" role="alert"><p><b>' + n.failed.length + (n.failed.length > 1 ? ' changements refusés' : ' changement refusé') + ' par le serveur</b> (fait sans réseau) : ' +
        n.failed.slice(-3).map(function(f){ var c = f.path.split('/')[0]; return (COLNAME[c] || c) + ' (' + esc(/permission|row-level|not_granted/i.test(f.msg) ? 'pas permis' : /not_found/i.test(f.msg) ? 'n\'existe plus' : f.msg.slice(0, 60)) + ')'; }).join(', ') +
        '. Le carnet montre la version du serveur.</p><button type="button" class="btn sm" data-act="net-ok">OK</button></div>';
    }
    /* the phone could not keep a change made without signal (private browsing, memory full) */
    if (n.storeErr && (n.offlineMode || n.online === false || p))
      h += '<div class="banner warn net" role="alert"><p><b>Ce téléphone ne peut pas garder tes changements</b> (navigation privée ou mémoire pleine). Ne ferme pas l\'app avant le retour du signal : ils seraient perdus.</p></div>';
    return h;
  }
  var netT = null, lastNet = '';
  if (T.onNet) T.onNet(function(n){
    var k = [n.offlineMode, n.online, n.pending, n.sending, n.failed.length].join('|');
    if (k === lastNet) return; lastNet = k;
    clearTimeout(netT); netT = setTimeout(function(){ var a = A(); if (a && a.render) a.render(); }, 120);
  });

  /* the page and its tools are kept on the phone: it opens even without network (« ?nosw » turns it off) */
  if ('serviceWorker' in navigator && /^(https:|http:\/\/(127\.0\.0\.1|localhost)(:|\/))/.test(location.href)){
    if (/[?&]nosw\b/.test(location.search)) navigator.serviceWorker.getRegistrations().then(function(rs){ rs.forEach(function(r){ r.unregister(); }); });
    else window.addEventListener('load', function(){
      /* an app left open on the phone for days still learns about a new version: check when it comes back to the screen */
      navigator.serviceWorker.register('sw.js').then(function(reg){
        var had = !!navigator.serviceWorker.controller;
        navigator.serviceWorker.addEventListener('controllerchange', function(){ if (had){ X.newVersion = true; var a = A(); if (a) a.render(); } had = true; });
        document.addEventListener('visibilitychange', function(){ if (document.visibilityState === 'visible') reg.update().catch(function(){}); });
        setInterval(function(){ reg.update().catch(function(){}); }, 30 * 60000);
      }).catch(function(){});
    });
  }
  window.__garageExt = {
    tabs:[{key:'carte', label:'Carte', icon:MAP_ICON, view:viewMap}, {key:'equipe', label:'Équipe', hidden:true, view:viewEquipe}],
    can:function(w){
      var m = eff(); if (!m) return undefined;
      return gate(m, w);
    },
    netBanner:netBanner,
    /* the client's page: invoice (and « Payer »), work to approve; texted through GoHighLevel */
    clientLink:function(j, what, extraId){ return invoke('client', {action:'link', jobId:j.id, send:what || null, extraId:extraId || null, base:trackBase()}); },
    payOn:function(){ return !!X.payOnline; },
    myMechanic:function(){ var m = eff(); return m && hasR(m, 'mecano') && !hasR(m, 'owner') && !hasR(m, 'bureau') ? m.mechanic : null; },
    homeTab:function(){ var m = eff(); return m && rolesOf(m).join() === 'tresorier' ? 'tresor' : null; },
    greetName:function(){ var m = eff(); return m ? first(m.name) : ''; },
    tellsClient:true, quietFor:function(j){ return !!(j && X.quiet[j.id]); }, isMine:function(j){ return mineView(j) || goesHimself(j); }, previewing:previewing, onUi:onUi, tourSteps:tourSteps, tourAuto:tourAuto,
    decodeVin:function(vin){ return invoke('vehicle', {vin:vin}).then(function(d){ return (d && d.r) || {}; }); },
    phoneTop:function(){ return me ? shiftCard() : ''; },
    navFoot:navFoot,
    guideItems:function(){
      if (!eff() || !hasR(eff(), 'owner')) return [];
      if (!X.eq.list && !X.eq.loading && !X.eq.err) eqLoad();
      var s = X.eq.secrets || {}, n = (X.eq.list || []).filter(function(m){ return m.active; }).length;
      return [
        {t:'Les comptes de ton équipe', sub:'Invite chaque personne avec son courriel.', done:n > 1, href:'#equipe'},
        {t:'Les textos automatiques aux clients', sub:'À brancher une seule fois, dans Équipe et accès.', done:!!s.ghl, href:'#equipe'},
        {t:'Le paiement par carte (facultatif)', sub:'Le client paie avec le lien reçu par texto.', done:!!s.stripe, href:'#equipe'}
      ];
    },
    plusItems:function(){
      var out = [];
      if (permOf(eff(), 'map')) out.push({href:'#carte', label:'Carte de l\'équipe', sub:'Les mécanos, leurs trajets et les rendez-vous du jour'});
      if (eff() && hasR(eff(), 'owner')) out.push({href:'#equipe', label:'Équipe et accès', sub:'Comptes, voir comme…, mots de passe, textos'});
      return out;
    },
    accountRow:function(){ var m = eff(); return m ? '<section class="sect"><p class="small">Connecté : <b>' + esc(m.name) + '</b> · ' + esc(rolesLabel(m)) + '</p><button type="button" class="btn block" data-act="acct-out">Se déconnecter</button>' + leaveBtn('btn ghost block danger-t') + '</section>' : ''; },
    dashTop:agendaTop, dashExtra:dashExtra,
    agendaTop:agendaTop, settingsTop:settingsTop, jobExtra:jobExtra, onStatus:onStatus, onAction:onAction,
    /* the next invoice number (without network: no number, the invoice waits for it — asked again when the signal is back) */
    nextInvoiceNo:function(start){
      if ((T.net && T.net.offlineMode) || navigator.onLine === false) return Promise.reject(new Error('offline'));
      var ask = T.sb.rpc('next_invoice_number', {p_start:start}).then(function(r){ if (r.error || typeof r.data !== 'number') throw r.error || new Error('no number'); return r.data; });
      return Promise.race([ask, new Promise(function(res, rej){ setTimeout(function(){ rej(new Error('timeout')); }, 8000); })]);
    },
    pickTruck:function(d, k){ if ((T.net && T.net.offlineMode) || navigator.onLine === false) return Promise.reject(Object.assign(new Error('offline'), {code:'unavailable'})); return T.pickTruck(d, k); },
    numberInvoice:function(id){ if ((T.net && T.net.offlineMode) || navigator.onLine === false) return Promise.reject(new Error('offline')); return T.numberInvoice(id); },
    /* booking in a block: the count of the block, and the bookings as they are on the server now */
    blockMark:function(key){ if ((T.net && (T.net.offlineMode || T.pending())) || navigator.onLine === false) return Promise.reject(Object.assign(new Error('offline'), {code:'unavailable'})); return T.blockMark(key); },
    fresh:function(col){ return T.fresh(col); }
  };

  /* at the start: is his workday already running (app reopened during the day)? With a weak signal the answer may not come:
     ask again when the network is back and every 30 s, until the server answers */
  var shiftAsk = {done:false, busy:false, timer:null};
  function shiftCheck(){
    if (shiftAsk.done || shiftAsk.busy || !me) return;
    shiftAsk.busy = true;
    timed(T.sb.from('mech_live').select('*').eq('user_id', me.user_id).maybeSingle()).then(function(r){
      shiftAsk.busy = false;
      if (r.error){ shiftRetry(); return; }
      shiftAsk.done = true; clearInterval(shiftAsk.timer); window.removeEventListener('online', shiftCheck);
      var l = r.data; if (!l || !l.on_shift) { render(); return; }
      if (!G.on){ G.on = true; G.since = l.shift_started_at; gpsStart(); }   /* (he may have started it by hand in the meantime) */
      if (l.job_id && !X.enRoute){ X.enRoute = {jobId:l.job_id, refreshedAt:0}; fetchTrack(l.job_id); }
      render();
    }, function(){ shiftAsk.busy = false; shiftRetry(); });
  }
  function shiftRetry(){
    if (shiftAsk.timer) return;
    shiftAsk.timer = setInterval(shiftCheck, 30000);
    window.addEventListener('online', shiftCheck);
  }

  /* once signed in: role, workday already running, address keys of the garage */
  T.onReady(function(){
    me = T.member;
    if (VA && !hasR(me, 'owner')){ VA = null; try { sessionStorage.removeItem('gm.viewas'); } catch(e){} }
    T.db.doc('config/roles').onSnapshot(function(s){ X.roles = s.exists ? (s.data() || {}) : {}; X.rolesLoaded = true; render(); }, function(){ X.rolesLoaded = true; render(); });
    if (previewing()) setTimeout(applyView, 0);
    if (worksShifts()) shiftCheck();
    /* one listener for the garage's keys: « Payer » on the invoices (Stripe) and the address keys */
    T.db.doc('config/keys').onSnapshot(function(s){
      var d = s.exists ? (s.data() || {}) : {}, pay = !!d.payOnline;
      lsSet('gm.web.ttkey', d.tomtom || null);
      if (d.google !== undefined) lsSet('gm.web.gkey', d.google || null);
      if (pay !== X.payOnline){ X.payOnline = pay; render(); }
    });
    if (isStaff()) loadLive();
    render();
  });
})();
