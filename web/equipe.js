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
  function previewing(){ return !!(me && VA && me.role === 'owner'); }
  function eff(){ return previewing() ? {role:VA.role, mechanic:VA.mechanic || null, name:VA.name, user_id:me.user_id, active:true, preview:true} : me; }
  var X = {tracks:{}, trackLoading:{}, busy:{}, live:[], members:[], active:[], mapSel:null, showPath:{}, paths:{}, eq:{list:null, err:'', created:null, secrets:null, confirm:null, editing:null}, enRoute:null, near:false, warnedNear:false, roles:{}};
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
  function invoke(name, body){
    return T.sb.functions.invoke(name, {body:body}).then(function(r){
      if (!r.error) return r.data;
      var ctx = r.error.context;
      return (ctx && typeof ctx.json === 'function' ? ctx.json().catch(function(){ return null; }) : Promise.resolve(null)).then(function(j){
        var e = new Error((j && j.message) || (/fetch|network/i.test(r.error.message) ? 'pas de connexion au serveur' : r.error.message)); e.code = j && j.error; throw e;
      });
    });
  }
  function mineOf(m, j){ return !!(m && m.mechanic && (norm(j.mechanic) === norm(m.mechanic) || (!j.mechanic && m.role === 'mecano'))); }
  function mineJob(j){ return mineOf(me, j); }          /* the real account (position, texts) */
  function mineView(j){ return mineOf(eff(), j); }      /* what the screen shows (« Voir comme ») */
  function onPhone(){ var a = A(); return !!(a && a.phone && a.phone()); }
  function isStaff(){ return me && (me.role === 'owner' || me.role === 'bureau'); }
  function worksShifts(){ return !!(me && (me.role === 'mecano' || me.mechanic)); }
  function staffView(){ var m = eff(); return !!(m && (m.role === 'owner' || m.role === 'bureau')); }
  function shiftsView(){ var m = eff(); return !!(m && (m.role === 'mecano' || m.mechanic)); }

  /* what the mechanic and the treasurer may do: the owner ticks boxes in Équipe et accès (document config/roles).
     Nothing ticked = as before. « book » (mechanic) and « editinv » (treasurer) are also checked by the server. */
  var PERMS = {
    mecano:[
      {k:'money', t:'Voir les chiffres du garage', s:'Ventes du mois et factures payées, sur l\'écran d\'accueil.', d:false},
      {k:'book', t:'Prendre des rendez-vous', s:'Seulement dans son agenda.', d:false},
      {k:'clients', t:'Voir l\'onglet Clients', s:'Seulement les clients de ses jobs.', d:true},
      {k:'factures', t:'Voir l\'onglet Factures', s:'Seulement les factures de ses jobs.', d:true},
      {k:'stock', t:'Voir et changer le stock', s:'Pièces et produits du camion.', d:true}
    ],
    tresorier:[
      {k:'agenda', t:'Voir l\'agenda', s:'Les rendez-vous de tout le monde, sans rien y changer.', d:false},
      {k:'clients', t:'Voir les clients', s:'Sans rien y changer.', d:true},
      {k:'factures', t:'Voir les factures', s:'', d:true},
      {k:'editinv', t:'Modifier les factures', s:'Les lignes, les rabais, « payée ». Rien d\'autre dans la job.', d:false},
      {k:'stock', t:'Voir et changer le stock', s:'', d:true}
    ]
  };
  function perm(role, k){ var r = X.roles && X.roles[role], v = r && r[k]; if (typeof v === 'boolean') return v; var p = (PERMS[role] || []).filter(function(x){ return x.k === k; })[0]; return p ? p.d : undefined; }
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
    var pos = G.last; G.sending = true;
    T.sb.rpc('report_position', {p_lat:pos.lat, p_lon:pos.lon, p_acc:pos.acc == null ? null : Math.round(pos.acc), p_speed:pos.speed, p_heading:pos.heading}).then(function(r){
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
    return T.sb.rpc('shift_start').then(function(r){
      G.starting = false;
      if (r.error){ toast('La journée n\'a pas commencé : ' + r.error.message); return; }
      G.on = true; G.since = r.data && r.data.shift_started_at; lsSet('gm.team.gpsok', '1');
      gpsStart(); render();
    }, function(){ G.starting = false; toast('Pas de connexion au serveur. Réessaie.'); });
  }
  function shiftEnd(){
    return T.sb.rpc('shift_end').then(function(r){
      if (r.error){ toast('La journée n\'a pas été fermée : ' + r.error.message); return; }
      G.on = false; G.since = null; X.enRoute = null; gpsStop(); toast('Bonne soirée ! Ta position n\'est plus envoyée.'); render();
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
  window.__garageTeamState = function(){ return {on:G.on, last:G.last, sentAt:G.sentAt, sending:G.sending, err:G.err, sendErr:G.sendErr, asking:!!G.asking, watch:G.watch != null, enRoute:X.enRoute}; };

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
      invoke('en-route', {jobId:r.jobId, action:'refresh', pos:{lat:G.last.lat, lon:G.last.lon, acc:G.last.acc}, force:true}).then(function(res){
        if (res && res.route){ Object.assign(t, {route:res.route, minutes:res.minutes, km:res.km, eta_at:res.eta_at}); render(); }
      }, function(){});
    }
  }

  /* ================= « En route » ================= */
  function fetchTrack(jobId){
    if (X.trackLoading[jobId]) return;
    X.trackLoading[jobId] = true;
    T.sb.from('tracks').select('*').eq('job_id', jobId).order('created_at', {ascending:false}).limit(1).then(function(r){
      X.trackLoading[jobId] = false;
      if (r.error) return;
      X.tracks[jobId] = r.data[0] || null; render();
    }, function(){ X.trackLoading[jobId] = false; });
  }
  function smsText(j, t){
    var c = A().cl(j), name = first(c.firstName || c.name), mech = first((t && t.mech_name) || j.mechanic || (me && me.name)) || 'Votre mécano';
    return 'Bonjour' + (name ? ' ' + name : '') + ', ' + mech + ' de ' + A().bizName() + ' est en route vers chez vous' + (t && t.eta_at ? ' : arrivée prévue vers ' + clock(t.eta_at) : '') + '. Suivez son trajet en direct : ' + trackLink(t);
  }
  function smsHref(phone, text){ var d = String(phone || '').replace(/\D/g, ''); return 'sms:' + (d ? (d.length === 10 ? '+1' : '+') + d : '') + '?&body=' + encodeURIComponent(text); }
  function startEnRoute(j, opt){
    opt = opt || {};
    if (X.busy[j.id]) return;
    X.busy[j.id] = true; render();
    var mine = mineJob(j), p = Promise.resolve();
    if (mine && !G.on) p = shiftStart();
    p.then(function(){ return mine ? freshPos(7000) : null; }).then(function(pos){
      return invoke('en-route', {jobId:j.id, action:'start', resend:!!opt.resend, base:trackBase(), pos:pos ? {lat:pos.lat, lon:pos.lon, acc:pos.acc} : null});
    }).then(function(res){
      X.busy[j.id] = false;
      var t = Object.assign({}, X.tracks[j.id] || {}, {token:res.token, job_id:j.id, status:'active', route:res.route, minutes:res.minutes, km:res.km, eta_at:res.eta_at, dest_lat:res.dest ? res.dest.lat : null, dest_lon:res.dest ? res.dest.lon : null, sms_status:res.sms.status === 'already' ? 'sent' : res.sms.status, sms_error:res.sms.error || null, sms_at:res.sms.status === 'sent' ? new Date().toISOString() : (X.tracks[j.id] || {}).sms_at, mech_name:(X.tracks[j.id] || {}).mech_name});
      X.tracks[j.id] = t;
      if (mine){ X.enRoute = {jobId:j.id, refreshedAt:Date.now()}; X.near = false; X.warnedNear = false; maybeSend(true); }
      var c = A().cl(j), who = first(c.firstName || c.name) || 'le client';
      toast(res.sms.status === 'sent' ? 'Texto envoyé à ' + who + ' ✓' : res.sms.status === 'already' ? who + ' a déjà le lien de suivi' : res.sms.status === 'error' ? 'Texto pas envoyé : envoie le lien toi-même' : 'Lien de suivi prêt : envoie-le à ' + who);
      render();
      fetchTrack(j.id);
    }, function(e){
      X.busy[j.id] = false;
      toast('Le client n\'a pas été avisé : ' + e.message + '.');
      render();
    });
  }
  function endTrack(j, reason){
    invoke('en-route', {jobId:j.id, action:'end', reason:reason}).then(function(){
      if (X.tracks[j.id]) X.tracks[j.id].status = reason;
      if (X.enRoute && X.enRoute.jobId === j.id){ X.enRoute = null; X.near = false; }
      fetchTrack(j.id);
    }, function(){});
  }
  function jobExtra(j){
    if (!me || !A().canWrite()) return '';
    var st = j.status || 'planifie', t = X.tracks[j.id];
    if (t === undefined) fetchTrack(j.id);
    if (st === 'annule' || st === 'noshow' || st === 'termine') return '';
    var c = A().cl(j), who = first(c.firstName || c.name) || 'le client', phone = c.phone || '', mine = mineView(j), busy = X.busy[j.id];
    var h = '<section class="sect er" aria-labelledby="er-h"><h3 id="er-h">' + (st === 'route' ? 'En route vers ' + esc(who) : st === 'place' ? 'Sur place' : 'Départ vers le client') + '</h3>';
    if (st === 'planifie'){
      if (busy) h += '<p class="er-line">Envoi du texto…</p>';
      h += '<p class="muted small">' + (phone ? 'Au départ, ' + esc(who) + ' reçoit un texto pour suivre le camion.' : 'Pas de téléphone au dossier : le lien de suivi sera prêt à partager.') + '</p>';
      if (!mine && j.mechanic) h += '<p class="muted small">Le client suivra la position de ' + esc(j.mechanic) + '.</p>';
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
    if (was === 'route') endTrack(j, (v === 'annule' || v === 'noshow') ? 'cancelled' : 'arrived');
    toast(ST[v]);
  }

  /* ================= haut de l'agenda : compte, journée, trajet en cours ================= */
  function agendaTop(){
    var m = eff(); if (!m) return '';
    /* on a big screen the side menu shows who is signed in; in a small window this line does */
    return (onPhone() ? '' : '<div class="acct"><span>Connecté : <b>' + esc(m.name) + '</b> · ' + esc(ROLE[m.role]) + '</span><button type="button" class="linkbtn" data-act="acct-out">Se déconnecter</button></div>') + shiftCard();
  }
  /* the side menu of a computer ends with who is signed in */
  function navFoot(){ var m = eff(); return m ? '<div class="navfoot"><span><b>' + esc(m.name) + '</b> · ' + esc(ROLE[m.role]) + '</span><button type="button" class="linkbtn" data-act="acct-out">Se déconnecter</button></div>' : ''; }
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
          (trip ? '<div class="banner"><p><b>En route vers ' + esc(first(A().cl(trip).firstName || A().cl(trip).name)) + '</b>' + (tt && tt.eta_at ? ' · arrivée prévue ' + esc(clock(tt.eta_at)) : '') + '</p><button type="button" class="btn sm" data-act="er-open" data-id="' + esc(trip.id) + '">Ouvrir la job</button></div>' : '') +
          '<p class="muted small">Garde l\'app ouverte pendant ta journée.</p>' +
          '<div class="er-acts"><button type="button" class="btn sm" id="sh-wake" data-act="sh-wake" aria-pressed="false">Garder l\'écran allumé</button><button type="button" class="btn sm" data-act="sh-end">Fin de journée</button></div></section>';
        setTimeout(shiftLine, 0);
      }
    }
    return h;
  }
  function settingsTop(){
    var m = eff(); if (!m || m.role !== 'owner' || onPhone()) return '';
    return '<section class="sect"><h3>Équipe et accès</h3><p class="muted small">Les comptes de l\'équipe, les mots de passe, les textos aux clients et le paiement par carte.</p><a class="btn block" href="#equipe">Gérer l\'équipe et les accès</a></section>';
  }

  /* ================= carte des mécanos ================= */
  var M = {el:null, map:null, pins:{}, jobs:null, routes:null, path:null, fitted:false, timer:null};
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
      T.sb.from('members').select('user_id,name,role,mechanic,active')
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
    var out = X.members.filter(function(m){ return m.active && (m.role === 'mecano' || m.mechanic); }).map(function(m){ return {m:m, l:X.live.filter(function(l){ return l.user_id === m.user_id; })[0] || null}; });
    var order = {route:0, shift:1, stale:2, off:3};
    return out.sort(function(a, b){ return order[mechState(a.l)] - order[mechState(b.l)] || String(a.m.name).localeCompare(b.m.name, 'fr'); });
  }
  function todaysJobs(){ var a = A(), d = a.today(); return a.S.jobs.filter(function(j){ return j.date === d && j.status !== 'annule' && j.status !== 'noshow'; }).sort(function(x, y){ return String(x.time).localeCompare(String(y.time)); }); }
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
  function pinIcon(cls, txt, big){ return L.divIcon({className:'gm-pin-wrap', html:'<span class="gm-pin ' + cls + '">' + esc(txt) + '</span>', iconSize:big ? [40, 40] : [30, 30], iconAnchor:big ? [20, 20] : [15, 15]}); }
  function drawMap(){
    if (!M.map) return;
    var seen = {}, pts = [];
    crew().forEach(function(c){
      var l = c.l, st = mechState(l); if (!l || l.lat == null || st === 'off') return;
      seen[l.user_id] = 1; var ll = [l.lat, l.lon]; pts.push(ll);
      var tip = esc(c.m.name) + ' · ' + STATE[st].lbl + ' · ' + ago(l.at);
      if (!M.pins[l.user_id]) M.pins[l.user_id] = L.marker(ll, {icon:pinIcon(STATE[st].cls, initials(c.m.name), true), keyboard:true, title:c.m.name, riseOnHover:true}).addTo(M.map).on('click', function(){ selectMech(l.user_id, true); });
      var mk = M.pins[l.user_id]; mk.setLatLng(ll); mk.setIcon(pinIcon(STATE[st].cls + (X.mapSel === l.user_id ? ' sel' : ''), initials(c.m.name), true)); mk.bindTooltip(tip, {direction:'top', offset:[0, -18]});
    });
    Object.keys(M.pins).forEach(function(k){ if (!seen[k]){ M.map.removeLayer(M.pins[k]); delete M.pins[k]; } });
    M.jobs.clearLayers();
    todaysJobs().forEach(function(j){ var g = A().cl(j).geo; if (!g || !isFinite(g.lat)) return; pts.push([g.lat, g.lon]); L.marker([g.lat, g.lon], {icon:pinIcon('p-job' + (j.status === 'termine' ? ' done' : ''), A().hm(j.time).replace(' h', 'h').replace(' ', ''), false), title:(A().cl(j).name || '') + ' ' + A().hm(j.time)}).addTo(M.jobs).bindTooltip(esc(A().hm(j.time) + ' · ' + (A().cl(j).name || 'Client') + (j.mechanic ? ' · ' + j.mechanic : '')), {direction:'top', offset:[0, -14]}); });
    M.routes.clearLayers();
    X.active.forEach(function(t){
      if (t.route && t.route.length > 1) L.polyline(t.route.map(function(c){ return [c[1], c[0]]; }), {color:'#F2B200', weight:5, opacity:.9, dashArray:'2 8', lineCap:'round'}).addTo(M.routes);
      if (t.dest_lat != null) L.marker([t.dest_lat, t.dest_lon], {icon:pinIcon('p-dest', '⌂', false), title:'Chez ' + (t.client_first || 'le client')}).addTo(M.routes);
    });
    M.path.clearLayers();
    Object.keys(X.showPath).forEach(function(uid){ var p = X.paths[uid]; if (X.showPath[uid] && p && p.length > 1){ L.polyline(p.map(function(x){ return [x.lat, x.lon]; }), {color:'#1D4B77', weight:4, opacity:.75}).addTo(M.path); L.circleMarker([p[0].lat, p[0].lon], {radius:6, color:'#1D4B77', fillColor:'#fff', fillOpacity:1, weight:3}).addTo(M.path).bindTooltip('Début ' + clock(p[0].at)); } });
    if (!M.fitted && pts.length){ M.fitted = true; fit(pts); }
  }
  function fit(pts){ if (!M.map) return; pts = pts || []; if (!pts.length){ Object.keys(M.pins).forEach(function(k){ var p = M.pins[k].getLatLng(); pts.push([p.lat, p.lng]); }); todaysJobs().forEach(function(j){ var g = A().cl(j).geo; if (g && isFinite(g.lat)) pts.push([g.lat, g.lon]); }); }
    if (pts.length === 1) M.map.setView(pts[0], 14); else if (pts.length) M.map.fitBounds(L.latLngBounds(pts).pad(0.2), {maxZoom:15}); }
  function selectMech(uid, fromMap){
    X.mapSel = uid; var l = X.live.filter(function(x){ return x.user_id === uid; })[0];
    if (M.map && l && l.lat != null) M.map.setView([l.lat, l.lon], Math.max(M.map.getZoom(), 14));
    drawMap(); render();
    if (fromMap){ var row = document.getElementById('mc-' + uid); if (row) row.scrollIntoView({block:'nearest'}); }
    else if (M.el) M.el.scrollIntoView({block:'nearest'});
  }
  function loadPath(uid){
    var d = new Date(); d.setHours(0, 0, 0, 0);
    return T.sb.from('mech_positions').select('lat,lon,at').eq('user_id', uid).gte('at', d.toISOString()).order('at', {ascending:true}).limit(5000).then(function(r){ if (!r.error){ X.paths[uid] = r.data; drawMap(); render(); } });
  }
  function viewMap(){
    var a = A();
    if (!X.liveAt || Date.now() - X.liveAt > 8000) loadLive();
    var top = onPhone() ? a.topBack('Carte des mécanos', 'ph-back', 'Plus') : '<div class="wrap top-in"><div class="brandrow"><div><div class="eyebrow">' + esc(a.bizName()) + '</div><h1>Carte</h1></div><button type="button" class="btn sm" data-act="map-fit">Tout voir</button></div></div>';
    var body = a.banners() + (onPhone() ? '<button type="button" class="btn sm" data-act="map-fit">Tout voir sur la carte</button>' : '');
    body += window.L ? '<div id="map-slot" class="mapslot"></div>' : '<div class="banner warn"><p>La carte n\'a pas pu se charger. Vérifie Internet et recharge la page.</p></div>';
    body += '<p class="legend small"><span><i class="gm-pin p-route mini"></i>En route</span><span><i class="gm-pin p-shift mini"></i>En journée</span><span><i class="gm-pin p-stale mini"></i>Signal perdu</span><span><i class="gm-pin p-job mini"></i>Job d\'aujourd\'hui</span></p>';
    var list = crew();
    body += '<section class="sect"><div class="sect-head"><h3>Mécanos</h3><span class="muted small">' + (X.liveAt ? 'mis à jour ' + ago(X.liveAt) : 'chargement…') + '</span></div>';
    if (!list.length) body += '<p class="muted">Aucun mécano n\'a encore de compte. ' + (eff().role === 'owner' ? '<a href="#equipe">Ajoute-les dans Équipe et accès</a>.' : 'Le propriétaire peut les ajouter.') + '</p>';
    list.forEach(function(c){
      var l = c.l, st = mechState(l), t = X.active.filter(function(x){ return x.user_id === c.m.user_id; })[0], tj = t && a.findJob(t.job_id);
      var jobs = todaysJobs().filter(function(j){ return c.m.mechanic && norm(j.mechanic) === norm(c.m.mechanic); }), next = jobs.filter(function(j){ return j.status !== 'termine'; })[0];
      body += '<div class="mc' + (X.mapSel === c.m.user_id ? ' sel' : '') + '" id="mc-' + esc(c.m.user_id) + '"><div class="mc-head"><span class="gm-pin ' + STATE[st].cls + '" aria-hidden="true">' + esc(initials(c.m.name)) + '</span><div class="mc-who"><b>' + esc(c.m.name) + '</b><span class="pillx ' + STATE[st].cls + '">' + STATE[st].lbl + '</span></div></div>' +
        '<p class="small muted">' + (st === 'off' ? 'Pas en journée : sa position n\'est pas partagée.' : 'Dernière position ' + esc(ago(l.at)) + (l.shift_started_at ? ' · journée depuis ' + esc(clock(l.shift_started_at)) : '')) + '</p>' +
        (t ? '<p class="small">En route vers <b>' + esc(t.client_first || (tj ? a.cl(tj).name : 'le client')) + '</b>' + (t.eta_at ? ' · arrivée ' + esc(clock(t.eta_at)) : '') + '</p>' : '') +
        '<p class="small">' + (jobs.length ? jobs.length + ' job' + (jobs.length > 1 ? 's' : '') + ' aujourd\'hui' + (next ? ' · prochaine : ' + esc(a.hm(next.time)) + ' ' + esc(a.cl(next).name || '') : ' · toutes terminées') : 'Aucune job aujourd\'hui') + '</p>' +
        '<div class="er-acts">' + (l && l.lat != null && st !== 'off' ? '<button type="button" class="btn sm" data-act="map-sel" data-v="' + esc(c.m.user_id) + '">Voir sur la carte</button>' : '') +
        '<button type="button" class="btn sm" data-act="map-path" data-v="' + esc(c.m.user_id) + '" aria-pressed="' + (!!X.showPath[c.m.user_id]) + '">' + (X.showPath[c.m.user_id] ? 'Cacher le trajet du jour' : 'Trajet du jour') + '</button>' +
        (tj ? '<button type="button" class="btn sm" data-act="er-open" data-id="' + esc(tj.id) + '">Ouvrir la job</button>' : '') + '</div>' +
        (X.showPath[c.m.user_id] && X.paths[c.m.user_id] ? '<p class="small muted">' + (X.paths[c.m.user_id].length ? X.paths[c.m.user_id].length + ' points depuis ' + esc(clock(X.paths[c.m.user_id][0].at)) : 'Pas de trajet aujourd\'hui.') + '</p>' : '') + '</div>';
    });
    body += '</section><p class="muted small">Positions partagées seulement pendant la journée de chaque mécano, gardées 30 jours.</p>';
    return {top:top, body:body};
  }
  /* dashboard: who is working and who is on the way */
  function dashExtra(){
    if (!staffView()) return '';
    if (!X.liveAt || Date.now() - X.liveAt > 30000) loadLive();
    var c = crew(), on = c.filter(function(x){ return mechState(x.l) !== 'off'; });
    var h = '<section class="sect" aria-labelledby="d-road"><div class="sect-head"><h3 id="d-road">Sur la route</h3><button type="button" class="btn sm" data-act="tab" data-t="carte">Voir la carte</button></div>';
    if (!c.length) return h + '<p class="muted">Aucun mécano n\'a encore de compte.' + (eff().role === 'owner' ? ' <a href="#equipe">Ajouter l\'équipe</a>' : '') + '</p></section>';
    if (!on.length) h += '<p class="muted small">Personne n\'a commencé sa journée.</p>';
    h += '<div class="qrows">' + c.map(function(x){
      var st = mechState(x.l), t = X.active.filter(function(a){ return a.user_id === x.m.user_id; })[0];
      return '<div class="qrow"><span class="qicon" aria-hidden="true">' + esc(initials(x.m.name)) + '</span><div><b>' + esc(x.m.name) + '</b><span>' + (t ? 'En route vers ' + esc(t.client_first || 'un client') + (t.eta_at ? ' · ' + esc(clock(t.eta_at)) : '') : st === 'off' ? 'Pas en journée' : 'Position ' + esc(ago(x.l.at))) + '</span></div><span class="pillx ' + STATE[st].cls + '">' + STATE[st].lbl + '</span></div>';
    }).join('') + '</div></section>';
    return h;
  }
  setInterval(function(){ if (document.visibilityState !== 'hidden' && A() && A().S.tab === 'carte' && !A().S.screen) loadLive().then(function(){ Object.keys(X.showPath).forEach(function(uid){ if (X.showPath[uid]) loadPath(uid); }); }); }, 10000);

  /* ================= équipe et accès (propriétaire) ================= */
  function eqLoad(){
    X.eq.loading = true;
    return Promise.all([invoke('members', {action:'list'}), invoke('members', {action:'secrets'})]).then(function(r){
      X.eq.loading = false; X.eq.list = r[0].members; X.eq.secrets = r[1]; X.eq.err = ''; render();
    }, function(e){ X.eq.loading = false; X.eq.err = e.message; render(); });
  }
  function roleSelect(id, val){ return '<select id="' + id + '">' + ['mecano', 'bureau', 'tresorier', 'owner'].map(function(r){ return '<option value="' + r + '"' + (r === val ? ' selected' : '') + '>' + ROLE[r] + '</option>'; }).join('') + '</select>'; }
  function mechSelect(id, val){
    var ms = A().mechanics(), opts = '<option value="">' + (ms.length ? 'Aucun' : 'Ajoute les mécanos dans Réglages') + '</option>' + ms.map(function(m){ return '<option' + (norm(m) === norm(val) ? ' selected' : '') + '>' + esc(m) + '</option>'; }).join('');
    if (val && !ms.some(function(m){ return norm(m) === norm(val); })) opts += '<option selected>' + esc(val) + '</option>';
    return '<select id="' + id + '">' + opts + '</select>';
  }
  function viewEquipe(){
    var a = A();
    if (!eff() || eff().role !== 'owner') return {top:a.topBack('Équipe et accès', 'eq-back'), body:'<div class="banner"><p>Seul le propriétaire gère les accès.</p></div>'};
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
      b += '<div class="eqp' + (m.active ? '' : ' off') + '"><div class="eqp-head"><div><b>' + esc(m.name) + '</b>' + (self ? ' <span class="muted small">(toi)</span>' : '') + '<div class="small muted sel">' + esc(m.email) + '</div></div><span class="pillx r-' + m.role + '">' + ROLE[m.role] + '</span></div>' +
        '<p class="small muted">' + (m.mechanic ? 'Dans l\'agenda : ' + esc(m.mechanic) + ' · ' : '') + (m.active ? (m.last_sign_in_at ? 'dernière connexion ' + esc(ago(m.last_sign_in_at)) : m.invite ? '<b>' + (m.invite.expired ? 'Invitation expirée' : 'Invitation envoyée ' + esc(ago(m.invite.at))) + '</b> · pas encore activé' : 'jamais connecté') : '<b>Accès désactivé</b>') + '</p>';
      if (X.eq.editing === m.user_id){
        b += '<div class="eq-form"><div class="field"><label for="ed-name">Nom</label><input id="ed-name" value="' + esc(m.name) + '" autocomplete="off"></div>' +
          '<div class="grid2"><div class="field"><label for="ed-role">Rôle</label>' + roleSelect('ed-role', m.role) + '</div><div class="field"><label for="ed-mech">Nom dans l\'agenda</label>' + mechSelect('ed-mech', m.mechanic) + '</div></div>' +
          '<div class="er-acts"><button type="button" class="btn sm primary" data-act="eq-save" data-v="' + esc(m.user_id) + '">Enregistrer</button><button type="button" class="btn sm" data-act="eq-cancel">Annuler</button></div></div>';
      } else if (X.eq.confirm === m.user_id){
        b += '<div class="banner warn"><p>Supprimer le compte de ' + esc(m.name) + ' ? Ses jobs restent au carnet.</p></div><div class="er-acts"><button type="button" class="btn sm" data-act="eq-cancel">Garder</button><button type="button" class="btn sm danger solid" data-act="eq-remove" data-v="' + esc(m.user_id) + '">Supprimer</button></div>';
      } else {
        b += '<div class="er-acts"><button type="button" class="btn sm" data-act="eq-edit" data-v="' + esc(m.user_id) + '">Modifier</button>' +
          (self || !m.active || m.role === 'owner' ? '' : '<button type="button" class="btn sm" data-act="pv-person" data-v="' + esc(m.user_id) + '">👁 Voir comme ' + esc(first(m.name)) + '</button>') +
          (self ? '' : (!m.last_sign_in_at && m.active ? '<button type="button" class="btn sm" data-act="eq-reinvite" data-v="' + esc(m.user_id) + '">' + (m.invite ? 'Renvoyer l\'invitation' : 'Envoyer une invitation') + '</button>' : '') + '<button type="button" class="btn sm" data-act="eq-pw" data-v="' + esc(m.user_id) + '">Nouveau mot de passe</button>') + '</div>' +
          (self ? '' : (m.active ? '<details class="small eq-more"><summary>Bloquer ou supprimer l\'accès</summary><div class="er-acts">' : '<div class="er-acts">') + '<button type="button" class="btn sm" data-act="eq-active" data-v="' + esc(m.user_id) + '">' + (m.active ? 'Bloquer l\'accès (garder le compte)' : 'Redonner l\'accès') + '</button><button type="button" class="btn sm danger" data-act="eq-confirm" data-v="' + esc(m.user_id) + '">Supprimer le compte</button></div>' + (m.active ? '</details>' : ''));
      }
      b += '</div>';
    });
    b += '</section>';
    b += '<section class="sect" id="eq-new"><h3>Inviter une personne</h3><p class="small">Écris son courriel : elle reçoit un lien, choisit elle-même son mot de passe, et son compte est activé.</p>' +
      '<div class="field"><label for="nw-name">Nom</label><input id="nw-name" autocomplete="off"></div>' +
      '<div class="field"><label for="nw-email">Courriel</label><input id="nw-email" type="email" inputmode="email" autocapitalize="off" spellcheck="false" autocomplete="off"></div>' +
      '<div class="grid2"><div class="field"><label for="nw-role">Rôle' + (A().help ? A().help('roles', 'les rôles') : '') + '</label>' + roleSelect('nw-role', 'mecano') + '</div><div class="field"><label for="nw-mech">Nom dans l\'agenda</label>' + mechSelect('nw-mech', '') + '</div></div>' +
      '<ul class="roles small"><li><b>Mécano</b> : seulement ses jobs, le bouton « En route », la facture sur place. Sa position est partagée pendant sa journée.</li><li><b>Bureau</b> : agenda, clients, factures et carte des mécanos. Pas les réglages.</li><li><b>Trésorier</b> : son propre écran, la trésorerie (dépenses avec photo des reçus, rapport, taxes à remettre, Excel).</li><li><b>Propriétaire</b> : tout, y compris les accès.</li></ul><p class="small muted">Ce que le mécano et le trésorier voient de plus : plus haut, « Ce que chaque rôle peut faire ».</p>' +
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
    b += '<section class="sect"><h3>Ton compte</h3><p class="small">' + esc(eff().name) + ' · ' + ROLE[eff().role] + '</p><button type="button" class="btn" data-act="acct-out">Se déconnecter</button></section>';
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
  /* « Ce que chaque rôle peut faire » : boxes saved right away in config/roles */
  function rolesCard(){
    var h = '<section class="sect" id="eq-roles"><h3>Ce que chaque rôle peut faire' + (A().help ? A().help('droits', 'les droits') : '') + '</h3><p class="small muted">Coche ou décoche : c\'est enregistré tout de suite, et ça change sur leur téléphone en quelques secondes.</p>';
    ['mecano', 'tresorier'].forEach(function(r){
      h += '<fieldset class="rp"><legend>' + (r === 'mecano' ? 'Le mécano' : 'Le trésorier') + '</legend>' +
        (r === 'mecano' ? '<p class="small muted">Toujours : ses jobs du jour, le bouton « En route », les photos et la facture sur place.</p>' : '<p class="small muted">Toujours : la trésorerie (dépenses, reçus, rapport, taxes).</p>') +
        PERMS[r].map(function(p){ var id = 'rp-' + r + '-' + p.k;
          return '<label class="check rp-row" for="' + id + '"><input type="checkbox" id="' + id + '" data-act="rp" data-role="' + r + '" data-k="' + p.k + '"' + (perm(r, p.k) ? ' checked' : '') + (X.rolesLoaded ? '' : ' disabled') + '><span><b>' + esc(p.t) + '</b>' + (p.s ? '<span class="small muted">' + esc(p.s) + '</span>' : '') + '</span></label>'; }).join('') +
        '<button type="button" class="linkbtn" data-act="pv-role" data-role="' + r + '">👁 Voir ce qu\'il voit</button></fieldset>';
    });
    return h + '</section>';
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
    }).then(function(){ X.roles = next; toast('Enregistré : ' + (on ? 'oui' : 'non') + ' — ' + PERMS[role].filter(function(p){ return p.k === k; })[0].t.toLowerCase()); render(); },
      function(e){ if (box){ box.checked = !on; box.disabled = false; } toast('Pas enregistré : ' + (e && e.message || 'erreur')); render(); });
  }
  /* start / stop the preview */
  function startView(v){
    var a = A(); if (!a || !me || me.role !== 'owner') return;
    if (!VA) { try { X.uiBefore = sessionStorage.getItem('gm.ui'); } catch(e){ X.uiBefore = null; } try { sessionStorage.setItem('gm.ui.before', X.uiBefore || ''); } catch(e){} }
    /* a mechanic works on his phone: on a computer, show his phone screen first (a button switches to the computer screen) */
    VA = {role:v.role, mechanic:v.mechanic || null, name:v.name || ROLE[v.role], fmt:v.role === 'mecano' ? 'phone' : 'pc'};
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
  /* the guided tour of the first visit, for each role (what that person can really do) */
  function tourSteps(){
    var m = eff(); if (!m || m.role === 'owner') return [];
    var a = A(), inst = !(a && a.isStandalone && a.isStandalone()), out = [];
    var hi = function(icon, t, p){ out.push({icon:icon, t:t, p:p}); };
    if (m.role === 'mecano'){
      hi('👋', 'L\'app du garage', 'Ici, tu vois tes jobs, tu avises le client quand tu pars et tu fais la facture sur place. Voici l\'essentiel, en quelques étapes.');
      hi('☀️', 'Le matin : « Commencer ma journée »', 'Touche ce bouton en partant. Le bureau voit où tu es <b>seulement pendant ta journée</b> : rien n\'est envoyé avant, ni après « Fin de journée ».');
      hi('🔧', 'Une job, un seul gros bouton', 'Ouvre une job : le gros bouton noir te dit quoi faire. <b>« Je pars »</b> (le client reçoit un texto pour suivre ton trajet), <b>« Je suis arrivé »</b>, <b>« Terminer la job »</b>, puis <b>« Faire la facture »</b>.');
      hi('➕', 'Le « + » en bas', 'Pour une <b>facture sur place</b> (client sans rendez-vous)' + (perm('mecano', 'book') ? ', une <b>nouvelle réservation</b>' : '') + ' ou un <b>nouveau client</b>. Les petits <b>?</b> expliquent chaque chose.');
    } else if (m.role === 'tresorier'){
      var see = [];
      if (perm('tresorier', 'factures')) see.push(perm('tresorier', 'editinv') ? 'les factures (et les marquer payées)' : 'les factures');
      if (perm('tresorier', 'clients')) see.push('les clients');
      if (perm('tresorier', 'agenda')) see.push('l\'agenda');
      if (perm('tresorier', 'stock')) see.push('le stock des camions');
      hi('👋', 'Ta trésorerie', 'Ton écran, c\'est la <b>Trésorerie</b> : l\'argent qui rentre et l\'argent qui sort du garage.');
      hi('🧾', 'Une dépense = une photo du reçu', 'Touche <b>« + Dépense »</b>, prends le reçu en photo, choisis la catégorie. Tout est gardé pour les impôts.');
      hi('📊', 'Rapport et taxes', 'Le rapport du mois, du trimestre ou de l\'année, les taxes à remettre, et le fichier Excel pour le comptable.');
      if (see.length) hi('👀', 'Tu peux aussi voir', see.join(', ').replace(/, ([^,]*)$/, ' et $1') + '.');
    } else if (m.role === 'bureau'){
      hi('👋', 'L\'app du garage', 'Tu vois l\'agenda de tous les mécanos, les clients et les factures.');
      hi('📅', '« + Réservation »', 'Elle trouve un moment libre près des autres jobs du coin. Choisis le client et le service : c\'est réservé.');
      hi('🗺️', 'La carte des mécanos', 'Où est chaque mécano pendant sa journée, et qui est en route vers un client.');
      hi('🧾', 'Factures et clients', 'Les factures à encaisser, et la fiche de chaque client avec ses véhicules et ses visites. Les petits <b>?</b> expliquent chaque chose.');
    }
    if (inst && (onPhone() || previewing())) hi('📱', 'Dernière chose', 'Mets l\'app sur ton écran d\'accueil : elle s\'ouvrira d\'un seul geste, comme une vraie app. On te montre comment juste après.');
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
        if (r === 'mecano'){ var mn = mm && mm.mechanic ? mm.mechanic : api.mechanics()[0]; if (!mn){ toast('Ajoute d\'abord un mécano dans l\'agenda (Réglages).'); break; } startView({role:'mecano', mechanic:mn, name:mm && mm.mechanic === mn ? mm.name : mn}); }
        else startView({role:r, name:mm ? mm.name : ROLE[r]});
        break;
      }
      case 'pv-person': { var pm = (X.eq.list || []).filter(function(x){ return x.user_id === v; })[0]; if (pm) startView({role:pm.role, mechanic:pm.mechanic || null, name:pm.name}); break; }
      case 'pv-exit': stopView(); break;
      case 'pv-fmt': switchFmt(); break;
      case 'rp': saveRole(b.dataset.role, b.dataset.k, b.checked, b); break;
      case 'app-reload': location.reload(); break;
      case 'acct-out': {
        var pend = T.pending ? T.pending() : 0;
        if (pend && !X.outArmed){ X.outArmed = true; A().toast(pend + (pend > 1 ? ' changements pas encore envoyés' : ' changement pas encore envoyé') + ' : attends le retour du signal. Touche encore « Se déconnecter » pour les perdre.'); setTimeout(function(){ X.outArmed = false; }, 8000); break; }
        T.signOut(); break;
      }
      case 'net-send': if (T.flush) T.flush(); break;
      case 'net-ok': if (T.clearFailed) T.clearFailed(); break;
      case 'sh-start': shiftStart(); break;
      case 'sh-end': shiftEnd(); break;
      case 'sh-wake': G.wakeWant = !G.wake; lsSet('gm.team.wake', G.wakeWant ? '1' : null); wake(G.wakeWant); setTimeout(shiftLine, 300); break;
      case 'er-start': { var j1 = api.findJob(id); if (j1) startEnRoute(j1); break; }
      case 'er-resend': { var j2 = api.findJob(id); if (j2) startEnRoute(j2, {resend:true}); break; }
      case 'er-copy': { var t = X.tracks[id]; if (t && navigator.clipboard) navigator.clipboard.writeText(trackLink(t)).then(function(){ toast('Lien copié'); }, function(){ toast(trackLink(t)); }); else if (t) toast(trackLink(t)); break; }
      case 'er-open': api.S.jobId = id; api.S.screen = 'job'; api.S.backTo = null; render(); window.scrollTo(0, 0); break;
      case 'map-fit': fit(); break;
      case 'map-sel': selectMech(v, false); break;
      case 'map-path': X.showPath[v] = !X.showPath[v]; if (X.showPath[v]) loadPath(v); else { drawMap(); render(); } break;
      case 'eq-back': location.hash = onPhone() ? 'plus' : 'reglages'; break;
      case 'eq-reload': X.eq.err = ''; X.eq.list = null; eqLoad(); render(); break;
      case 'eq-edit': X.eq.editing = v; X.eq.confirm = null; render(); break;
      case 'eq-confirm': X.eq.confirm = v; X.eq.editing = null; render(); break;
      case 'eq-cancel': X.eq.editing = null; X.eq.confirm = null; render(); break;
      case 'eq-hidecred': X.eq.created = null; render(); break;
      case 'eq-copycred': { var pre = document.querySelector('.cred'); if (pre && navigator.clipboard) navigator.clipboard.writeText(pre.textContent).then(function(){ toast('Copié'); }, function(){}); break; }
      case 'eq-save': {
        var role = val('ed-role'), mech = val('ed-mech'), name = val('ed-name');
        if (role === 'mecano' && !mech){ toast('Choisis son nom dans l\'agenda.'); break; }
        b.disabled = true;
        invoke('members', {action:'update', user_id:v, name:name, role:role, mechanic:mech}).then(function(r){ X.eq.list = r.members; X.eq.editing = null; toast('Enregistré'); if (v === me.user_id) refreshMe(); render(); }, function(e){ b.disabled = false; toast(e.message); });
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
      case 'eq-remove': b.disabled = true; invoke('members', {action:'remove', user_id:v}).then(function(r){ X.eq.list = r.members; X.eq.confirm = null; toast('Compte supprimé'); render(); }, function(e){ b.disabled = false; toast(e.message); }); break;
      case 'eq-invite': {
        var inm = val('nw-name'), iem = val('nw-email'), irl = val('nw-role'), imc = val('nw-mech');
        if (!inm) return eqErr('Écris le nom de la personne.');
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(iem)) return eqErr('Écris un courriel valide.');
        if (irl === 'mecano' && !imc) return eqErr(api.mechanics().length ? 'Choisis son nom dans l\'agenda (liste des mécanos).' : 'Ajoute d\'abord le nom de ce mécano dans Réglages → Mécanos.');
        eqErr(''); b.disabled = true; b.textContent = 'Envoi…';
        invoke('members', {action:'invite', name:inm, email:iem, role:irl, mechanic:imc, base:trackBase()}).then(function(r){
          X.eq.list = r.members; X.eq.created = null; X.eq.invited = {name:inm, email:r.email || iem, link:r.link, mail:r.mail, message:r.message}; X.liveAt = 0;
          ['nw-name', 'nw-email', 'nw-mech'].forEach(function(i){ var e = document.getElementById(i); if (e) e.value = ''; });
          render(); window.scrollTo(0, 0);
        }, function(e){ b.disabled = false; b.textContent = 'Envoyer l\'invitation'; eqErr(e.message); });
        break;
      }
      case 'eq-reinvite': {
        var rm = (X.eq.list || []).filter(function(x){ return x.user_id === v; })[0];
        b.disabled = true; b.textContent = 'Envoi…';
        invoke('members', {action:'invite-resend', user_id:v, base:trackBase()}).then(function(r){
          X.eq.list = r.members; X.eq.created = null; X.eq.invited = {name:rm ? rm.name : '', email:r.email, link:r.link, mail:r.mail, message:r.message};
          render(); window.scrollTo(0, 0);
        }, function(e){ b.disabled = false; b.textContent = rm && rm.invite ? 'Renvoyer l\'invitation' : 'Envoyer une invitation'; toast(e.message); });
        break;
      }
      case 'eq-copylink': { var lk = X.eq.invited && X.eq.invited.link; if (lk && navigator.clipboard) navigator.clipboard.writeText(lk).then(function(){ toast('Lien copié'); }, function(){ toast(lk); }); else if (lk) toast(lk); break; }
      case 'eq-hideinv': X.eq.invited = null; render(); break;
      case 'eq-add': {
        var nm = val('nw-name'), em = val('nw-email'), rl = val('nw-role'), mc = val('nw-mech');
        if (!nm) return eqErr('Écris le nom de la personne.');
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(em)) return eqErr('Écris un courriel valide.');
        if (rl === 'mecano' && !mc) return eqErr(api.mechanics().length ? 'Choisis son nom dans l\'agenda (liste des mécanos).' : 'Ajoute d\'abord le nom de ce mécano dans Réglages → Mécanos.');
        eqErr(''); b.disabled = true; b.textContent = 'Création…';
        invoke('members', {action:'create', name:nm, email:em, role:rl, mechanic:mc}).then(function(r){
          X.eq.list = r.members; X.eq.invited = null; X.eq.created = {name:nm, email:em, password:r.password}; X.liveAt = 0;
          ['nw-name', 'nw-email', 'nw-mech'].forEach(function(i){ var e = document.getElementById(i); if (e) e.value = ''; });
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
        invoke('members', {action:'sms-test', phone:ph}).then(function(){ b.disabled = false; b.textContent = 'Envoyer'; toast('Texto test envoyé ✓ Vérifie ton téléphone.'); }, function(e){ b.disabled = false; b.textContent = 'Envoyer'; toast(e.message); });
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
    '.gm-map{height:min(58vh,520px);min-height:300px;width:100%}' +
    '.gm-pin-wrap{background:none;border:0}.gm-pin{display:grid;place-items:center;width:100%;height:100%;border-radius:50%;font:700 13px/1 var(--f-body);color:#fff;background:#1D4B77;border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35)}' +
    '.gm-pin.p-route{background:#B26B00}.gm-pin.p-shift{background:#1D4B77}.gm-pin.p-stale{background:#7A8794}.gm-pin.p-off{background:#B4BEC8}.gm-pin.sel{outline:3px solid #F2B200;outline-offset:1px}' +
    '.gm-pin.p-job{border-radius:8px;background:#fff;color:#14202B;border:2px solid #14202B;font-size:11px}.gm-pin.p-job.done{opacity:.55}.gm-pin.p-dest{background:#F2B200;color:#1E1600;border-radius:8px;font-size:15px}' +
    '.mc .gm-pin,.legend .gm-pin{width:36px;height:36px;flex:none}.legend{display:flex;flex-wrap:wrap;gap:6px 14px;color:var(--muted);margin:0 0 12px}.legend span{display:inline-flex;align-items:center;gap:6px}' +
    '.legend .gm-pin.mini{width:16px;height:16px;border-width:2px;display:inline-block;border-radius:50%}.legend .gm-pin.mini.p-job{border-radius:4px}' +
    '.mc{border-top:1px solid var(--line);padding-top:12px;display:grid;gap:6px}.mc:first-of-type{border-top:0;padding-top:0}.mc.sel{background:var(--steel-soft);margin:0 -10px;padding:12px 10px;border-radius:10px}' +
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
    '.pv-btns{display:flex;flex-wrap:wrap;gap:8px}.rp{border:1px solid var(--line);border-radius:14px;padding:10px 14px 6px;margin:0;display:grid;gap:2px}.rp legend{font-weight:700;padding:0 6px}' +
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
      var r = m.role;
      /* the treasurer: his own screen; the rest only as the owner ticked it (Équipe et accès) */
      if (r === 'tresorier'){
        if (w === 'tab:tresor' || w === 'expenses' || w === 'money' || w === 'tab:plus') return true;
        if (w === 'tab:clients') return perm(r, 'clients');
        if (w === 'tab:factures') return perm(r, 'factures');
        if (w === 'tab:stock' || w === 'stock') return perm(r, 'stock');
        if (w === 'tab:agenda' || w === 'tab:jour') return perm(r, 'agenda');
        if (w === 'invoice') return perm(r, 'editinv');
        return false;
      }
      if (r === 'mecano'){
        if (w === 'money') return perm(r, 'money');
        if (w === 'book') return perm(r, 'book');
        if (w === 'tab:clients') return perm(r, 'clients');
        if (w === 'tab:factures') return perm(r, 'factures');
        if (w === 'tab:stock' || w === 'stock') return perm(r, 'stock');
      }
      if (w === 'tab:tresor' || w === 'expenses') return r === 'owner';
      if (w === 'tab:reglages') return r === 'owner';
      if (w === 'tab:carte') return r !== 'mecano';
      if (w === 'tab:equipe') return r === 'owner';
      if (w === 'book' || w === 'deleteJob' || w === 'hours' || w === 'money') return r !== 'mecano';
      return undefined;
    },
    netBanner:netBanner,
    /* the client's page: invoice (and « Payer »), work to approve; texted through GoHighLevel */
    clientLink:function(j, what, extraId){ return invoke('client', {action:'link', jobId:j.id, send:what || null, extraId:extraId || null, base:trackBase()}); },
    payOn:function(){ return !!X.payOnline; },
    myMechanic:function(){ var m = eff(); return m && m.role === 'mecano' ? m.mechanic : null; },
    homeTab:function(){ var m = eff(); return m && m.role === 'tresorier' ? 'tresor' : null; },
    greetName:function(){ var m = eff(); return m ? first(m.name) : ''; },
    tellsClient:true, isMine:mineView, previewing:previewing, onUi:onUi, tourSteps:tourSteps,
    decodeVin:function(vin){ return invoke('vehicle', {vin:vin}).then(function(d){ return (d && d.r) || {}; }); },
    phoneTop:function(){ return me ? shiftCard() : ''; },
    navFoot:navFoot,
    guideItems:function(){
      if (!eff() || eff().role !== 'owner') return [];
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
      if (staffView()) out.push({href:'#carte', label:'Carte des mécanos', sub:'Où est chaque mécano, qui est en route'});
      if (eff() && eff().role === 'owner') out.push({href:'#equipe', label:'Équipe et accès', sub:'Comptes, voir comme…, mots de passe, textos'});
      return out;
    },
    accountRow:function(){ var m = eff(); return m ? '<section class="sect"><p class="small">Connecté : <b>' + esc(m.name) + '</b> · ' + esc(ROLE[m.role]) + '</p><button type="button" class="btn block" data-act="acct-out">Se déconnecter</button></section>' : ''; },
    dashTop:agendaTop, dashExtra:dashExtra,
    agendaTop:agendaTop, settingsTop:settingsTop, jobExtra:jobExtra, onStatus:onStatus, onAction:onAction,
    nextInvoiceNo:function(start){ return T.sb.rpc('next_invoice_number', {p_start:start}).then(function(r){ if (r.error || typeof r.data !== 'number') throw r.error || new Error('no number'); return r.data; }); }
  };

  /* once signed in: role, workday already running, address keys of the garage */
  T.onReady(function(){
    me = T.member;
    if (VA && me.role !== 'owner'){ VA = null; try { sessionStorage.removeItem('gm.viewas'); } catch(e){} }
    T.db.doc('config/roles').onSnapshot(function(s){ X.roles = s.exists ? (s.data() || {}) : {}; X.rolesLoaded = true; render(); }, function(){ X.rolesLoaded = true; render(); });
    if (previewing()) setTimeout(applyView, 0);
    T.db.doc('config/keys').get().then(function(s){ X.payOnline = !!(s.exists && s.data().payOnline); }, function(){});
    if (worksShifts()){
      T.sb.from('mech_live').select('*').eq('user_id', me.user_id).maybeSingle().then(function(r){
        var l = r.data; if (!l || !l.on_shift) { render(); return; }
        G.on = true; G.since = l.shift_started_at; gpsStart();
        if (l.job_id){ X.enRoute = {jobId:l.job_id, refreshedAt:0}; fetchTrack(l.job_id); }
        render();
      });
    }
    T.db.doc('config/keys').onSnapshot(function(s){
      var d = s.exists ? s.data() : {};
      lsSet('gm.web.ttkey', d.tomtom || null);
      if (d.google !== undefined) lsSet('gm.web.gkey', d.google || null);
    });
    if (isStaff()) loadLive();
    render();
  });
})();
