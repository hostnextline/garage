/* Version équipe : rôles, journée de travail (position), bouton « En route », carte des mécanos, équipe et accès.
   S'appuie sur supa.js (connexion, carnet partagé) et sur window.__garageApi (le carnet). */
(function(){
  var T = window.__supa; if (!T) return;
  function A(){ return window.__garageApi; }
  var me = null;
  var X = {tracks:{}, trackLoading:{}, busy:{}, live:[], members:[], active:[], mapSel:null, showPath:{}, paths:{}, eq:{list:null, err:'', created:null, secrets:null, confirm:null, editing:null}, enRoute:null, near:false, warnedNear:false};
  var ROLE = {owner:'Propriétaire', bureau:'Bureau', mecano:'Mécano'};

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
  function mineJob(j){ return !!(me && me.mechanic && (norm(j.mechanic) === norm(me.mechanic) || (!j.mechanic && me.role === 'mecano'))); }
  function isStaff(){ return me && (me.role === 'owner' || me.role === 'bureau'); }
  function worksShifts(){ return !!(me && (me.role === 'mecano' || me.mechanic)); }
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
    if (G.err === 'denied') return 'Le téléphone refuse de donner ta position. Autorise la localisation pour ce site (réglages du navigateur), puis recharge la page.';
    if (G.err === 'none') return 'Ce navigateur ne donne pas la position.';
    if (G.err && !G.last) return 'Position introuvable pour l\'instant (signal GPS faible). On réessaie tout seul.';
    if (G.sendErr && G.sentAt && Date.now() - G.sentAt > 90000) return 'La position ne part plus (connexion). On réessaie tout seul.';
    return '';
  }
  function shiftLine(){
    var el = document.getElementById('sh-line'); if (!el) return;
    var p = gpsProblem();
    el.textContent = !G.on ? '' : p ? p : !G.last ? 'Recherche de ta position…' : 'Position envoyée ' + ago(G.sentAt || null) + (G.last.acc ? ' · précision ±' + Math.round(G.last.acc) + ' m' : '');
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
    if (st === 'annule' || st === 'termine') return '';
    var c = A().cl(j), who = first(c.firstName || c.name) || 'le client', phone = c.phone || '', mine = mineJob(j), busy = X.busy[j.id];
    var h = '<section class="sect er" aria-labelledby="er-h"><h3 id="er-h">' + (st === 'route' ? 'En route vers ' + esc(who) : st === 'place' ? 'Sur place' : 'Départ vers le client') + '</h3>';
    if (st === 'planifie'){
      h += '<button type="button" class="btn primary block er-go" data-act="status" data-v="route"' + (busy ? ' disabled' : '') + '>' + (busy ? 'Envoi du texto…' : (mine ? 'Je pars : aviser ' : 'En route : aviser ') + esc(who)) + '</button>';
      h += '<p class="muted small">' + (phone ? esc(who) + ' reçoit un texto avec le lien pour suivre le trajet en direct.' : 'Pas de téléphone au dossier : le lien de suivi sera prêt à partager.') + '</p>';
      if (!mine && j.mechanic) h += '<p class="muted small">Le client suivra la position de ' + esc(j.mechanic) + ' (s\'il a commencé sa journée).</p>';
      if (mine && !G.on) h += '<p class="muted small">Ta journée commencera en même temps (ta position sera partagée).</p>';
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
      h += '<button type="button" class="btn block" data-act="status" data-v="place">Je suis arrivé</button>';
    } else if (st === 'place'){
      h += '<p class="muted small">' + (t && t.status === 'arrived' ? 'Le suivi est fermé' + (t.ended_at ? ' depuis ' + esc(clock(t.ended_at)) : '') + ' : le client ne voit plus ta position.' : 'Le client ne voit pas ta position.') + '</p>';
    }
    return h + '</section>';
  }
  function onStatus(j, v, was){
    var ST = A().ST;
    if (v === 'route') return startEnRoute(j);
    if (was === 'route') endTrack(j, v === 'annule' ? 'cancelled' : 'arrived');
    toast(ST[v]);
  }

  /* ================= haut de l'agenda : compte, journée, trajet en cours ================= */
  function agendaTop(){
    if (!me) return '';
    var h = '<div class="acct"><span>Connecté : <b>' + esc(me.name) + '</b> · ' + esc(ROLE[me.role]) + '</span><button type="button" class="linkbtn" data-act="acct-out">Se déconnecter</button></div>';
    if (worksShifts()){
      if (!G.on){
        var known = lsGet('gm.team.gpsok') === '1';
        h += '<section class="sect shift" aria-labelledby="sh-h"><h3 id="sh-h">Début de journée</h3>' +
          (known ? '<p class="muted small">Ta position est partagée avec le garage seulement entre « Commencer ma journée » et « Fin de journée ».</p>'
            : '<p class="small">Pendant ta journée, ton téléphone envoie ta position au garage (environ aux 15 secondes) : le bureau voit où tu es et le client peut suivre ton trajet quand tu pars chez lui.</p><p class="muted small">Rien n\'est envoyé avant « Commencer ma journée » ni après « Fin de journée ». Les positions sont gardées 30 jours, puis effacées.</p>') +
          '<button type="button" class="btn primary block" data-act="sh-start"' + (G.starting ? ' disabled' : '') + '>' + (G.starting ? 'Un instant…' : 'Commencer ma journée') + '</button></section>';
      } else {
        var trip = X.enRoute && A().findJob(X.enRoute.jobId), tt = trip && X.tracks[trip.id];
        h += '<section class="sect shift on" aria-labelledby="sh-h"><div class="sh-head"><span class="sh-dot" aria-hidden="true"></span><h3 id="sh-h">Journée en cours' + (G.since ? ' depuis ' + esc(clock(G.since)) : '') + '</h3></div>' +
          '<p class="sh-line" id="sh-line" aria-live="polite"></p>' +
          (trip ? '<div class="banner"><p><b>En route vers ' + esc(first(A().cl(trip).firstName || A().cl(trip).name)) + '</b>' + (tt && tt.eta_at ? ' · arrivée prévue ' + esc(clock(tt.eta_at)) : '') + '</p><button type="button" class="btn sm" data-act="er-open" data-id="' + esc(trip.id) + '">Ouvrir la job</button></div>' : '') +
          '<p class="muted small">Garde cette page ouverte : si tu fermes l\'app ou barres l\'écran, ta position arrête de partir.</p>' +
          '<div class="er-acts"><button type="button" class="btn sm" id="sh-wake" data-act="sh-wake" aria-pressed="false">Garder l\'écran allumé</button><button type="button" class="btn sm" data-act="sh-end">Fin de journée</button></div></section>';
        setTimeout(shiftLine, 0);
      }
    }
    return h;
  }
  function settingsTop(){
    if (!me || me.role !== 'owner') return '';
    return '<section class="sect"><h3>Équipe et accès</h3><p class="muted small">Comptes du bureau et des mécanos, mots de passe, textos aux clients (GoHighLevel).</p><a class="btn block" href="#equipe">Gérer l\'équipe et les accès</a></section>';
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
  function todaysJobs(){ var a = A(), d = a.today(); return a.S.jobs.filter(function(j){ return j.date === d && j.status !== 'annule'; }).sort(function(x, y){ return String(x.time).localeCompare(String(y.time)); }); }
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
    var top = '<div class="wrap top-in"><div class="brandrow"><div><div class="eyebrow">' + esc(a.bizName()) + '</div><h1>Carte</h1></div><button type="button" class="btn sm" data-act="map-fit">Tout voir</button></div></div>';
    var body = a.banners();
    body += window.L ? '<div id="map-slot" class="mapslot"></div>' : '<div class="banner warn"><p>La carte n\'a pas pu se charger. Vérifie Internet et recharge la page.</p></div>';
    body += '<p class="legend small"><span><i class="gm-pin p-route mini"></i>En route</span><span><i class="gm-pin p-shift mini"></i>En journée</span><span><i class="gm-pin p-stale mini"></i>Signal perdu</span><span><i class="gm-pin p-job mini"></i>Job d\'aujourd\'hui</span></p>';
    var list = crew();
    body += '<section class="sect"><div class="sect-head"><h3>Mécanos</h3><span class="muted small">' + (X.liveAt ? 'mis à jour ' + ago(X.liveAt) : 'chargement…') + '</span></div>';
    if (!list.length) body += '<p class="muted">Aucun mécano n\'a encore de compte. ' + (me.role === 'owner' ? '<a href="#equipe">Ajoute-les dans Équipe et accès</a>.' : 'Le propriétaire peut les ajouter.') + '</p>';
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
    if (!isStaff()) return '';
    if (!X.liveAt || Date.now() - X.liveAt > 30000) loadLive();
    var c = crew(), on = c.filter(function(x){ return mechState(x.l) !== 'off'; });
    var h = '<section class="sect" aria-labelledby="d-road"><div class="sect-head"><h3 id="d-road">Sur la route</h3><button type="button" class="btn sm" data-act="tab" data-t="carte">Voir la carte</button></div>';
    if (!c.length) return h + '<p class="muted">Aucun mécano n\'a encore de compte.' + (me.role === 'owner' ? ' <a href="#equipe">Ajouter l\'équipe</a>' : '') + '</p></section>';
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
  function roleSelect(id, val){ return '<select id="' + id + '">' + ['mecano', 'bureau', 'owner'].map(function(r){ return '<option value="' + r + '"' + (r === val ? ' selected' : '') + '>' + ROLE[r] + '</option>'; }).join('') + '</select>'; }
  function mechSelect(id, val){
    var ms = A().mechanics(), opts = '<option value="">' + (ms.length ? 'Aucun' : 'Ajoute les mécanos dans Réglages') + '</option>' + ms.map(function(m){ return '<option' + (norm(m) === norm(val) ? ' selected' : '') + '>' + esc(m) + '</option>'; }).join('');
    if (val && !ms.some(function(m){ return norm(m) === norm(val); })) opts += '<option selected>' + esc(val) + '</option>';
    return '<select id="' + id + '">' + opts + '</select>';
  }
  function viewEquipe(){
    var a = A();
    if (!me || me.role !== 'owner') return {top:a.topBack('Équipe et accès', 'eq-back'), body:'<div class="banner"><p>Seul le propriétaire gère les accès.</p></div>'};
    if (!X.eq.list && !X.eq.loading && !X.eq.err) eqLoad();
    var top = a.topBack('Équipe et accès', 'eq-back', 'Réglages');
    var b = '';
    if (X.eq.err) b += '<div class="banner warn"><p>' + esc(X.eq.err) + '</p><button type="button" class="btn sm" data-act="eq-reload">Réessayer</button></div>';
    if (X.eq.created){
      var cr = X.eq.created, txt = a.bizName() + ' : ton accès au carnet du garage\n' + trackBase() + '\nCourriel : ' + cr.email + '\nMot de passe temporaire : ' + cr.password;
      b += '<section class="sect created" aria-live="polite"><h3>' + (cr.reset ? 'Nouveau mot de passe pour ' : 'Compte créé pour ') + esc(cr.name) + '</h3><p class="small">Envoie-lui ces infos (le mot de passe ne sera plus affiché après) :</p>' +
        '<dl class="credl"><div><dt>Adresse</dt><dd class="sel">' + esc(trackBase()) + '</dd></div><div><dt>Courriel</dt><dd class="sel">' + esc(cr.email) + '</dd></div><div><dt>Mot de passe</dt><dd class="pw sel">' + esc(cr.password) + '</dd></div></dl>' +
        '<pre class="cred" hidden>' + esc(txt) + '</pre>' +
        '<div class="er-acts"><button type="button" class="btn sm steel" data-act="eq-copycred">Copier</button><a class="btn sm" href="' + esc('sms:?&body=' + encodeURIComponent(txt)) + '">Texter</a><a class="btn sm" href="' + esc('mailto:' + cr.email + '?subject=' + encodeURIComponent('Accès au carnet du garage') + '&body=' + encodeURIComponent(txt)) + '">Courriel</a><button type="button" class="btn sm" data-act="eq-hidecred">C\'est envoyé</button></div></section>';
    }
    b += '<section class="sect"><h3>Personnes</h3>';
    if (!X.eq.list) b += '<p class="muted">Chargement…</p>';
    else X.eq.list.forEach(function(m){
      var self = m.user_id === me.user_id;
      b += '<div class="eqp' + (m.active ? '' : ' off') + '"><div class="eqp-head"><div><b>' + esc(m.name) + '</b>' + (self ? ' <span class="muted small">(toi)</span>' : '') + '<div class="small muted sel">' + esc(m.email) + '</div></div><span class="pillx r-' + m.role + '">' + ROLE[m.role] + '</span></div>' +
        '<p class="small muted">' + (m.mechanic ? 'Dans l\'agenda : ' + esc(m.mechanic) + ' · ' : '') + (m.active ? (m.last_sign_in_at ? 'dernière connexion ' + esc(ago(m.last_sign_in_at)) : 'jamais connecté') : '<b>Accès désactivé</b>') + '</p>';
      if (X.eq.editing === m.user_id){
        b += '<div class="eq-form"><div class="field"><label for="ed-name">Nom</label><input id="ed-name" value="' + esc(m.name) + '" autocomplete="off"></div>' +
          '<div class="grid2"><div class="field"><label for="ed-role">Rôle</label>' + roleSelect('ed-role', m.role) + '</div><div class="field"><label for="ed-mech">Nom dans l\'agenda</label>' + mechSelect('ed-mech', m.mechanic) + '</div></div>' +
          '<div class="er-acts"><button type="button" class="btn sm primary" data-act="eq-save" data-v="' + esc(m.user_id) + '">Enregistrer</button><button type="button" class="btn sm" data-act="eq-cancel">Annuler</button></div></div>';
      } else if (X.eq.confirm === m.user_id){
        b += '<div class="banner warn"><p>Supprimer le compte de ' + esc(m.name) + ' ? Ses jobs restent au carnet.</p></div><div class="er-acts"><button type="button" class="btn sm" data-act="eq-cancel">Garder</button><button type="button" class="btn sm danger solid" data-act="eq-remove" data-v="' + esc(m.user_id) + '">Supprimer</button></div>';
      } else {
        b += '<div class="er-acts"><button type="button" class="btn sm" data-act="eq-edit" data-v="' + esc(m.user_id) + '">Modifier</button>' +
          (self ? '' : '<button type="button" class="btn sm" data-act="eq-pw" data-v="' + esc(m.user_id) + '">Nouveau mot de passe</button><button type="button" class="btn sm" data-act="eq-active" data-v="' + esc(m.user_id) + '">' + (m.active ? 'Désactiver' : 'Réactiver') + '</button><button type="button" class="btn sm danger" data-act="eq-confirm" data-v="' + esc(m.user_id) + '">Supprimer</button>') + '</div>';
      }
      b += '</div>';
    });
    b += '</section>';
    b += '<section class="sect"><h3>Ajouter une personne</h3>' +
      '<div class="field"><label for="nw-name">Nom</label><input id="nw-name" autocomplete="off"></div>' +
      '<div class="field"><label for="nw-email">Courriel</label><input id="nw-email" type="email" inputmode="email" autocapitalize="off" spellcheck="false" autocomplete="off"></div>' +
      '<div class="grid2"><div class="field"><label for="nw-role">Rôle</label>' + roleSelect('nw-role', 'mecano') + '</div><div class="field"><label for="nw-mech">Nom dans l\'agenda</label>' + mechSelect('nw-mech', '') + '</div></div>' +
      '<ul class="roles small"><li><b>Mécano</b> : seulement ses jobs, le bouton « En route », la facture sur place. Sa position est partagée pendant sa journée.</li><li><b>Bureau</b> : agenda, clients, factures et carte des mécanos. Pas les réglages.</li><li><b>Propriétaire</b> : tout, y compris les accès.</li></ul>' +
      '<p class="formerr" id="nw-err" role="alert" hidden></p><button type="button" class="btn primary block" data-act="eq-add">Créer le compte</button>' +
      '<p class="muted small">Un mot de passe temporaire est créé : tu l\'envoies à la personne.</p></section>';
    var s = X.eq.secrets || {};
    b += '<section class="sect"><h3>Textos aux clients (GoHighLevel)</h3>' +
      '<p class="small">' + (s.ghl ? '<span class="badge ok">Branché</span> Clé ' + esc(s.ghlToken) + ' · compte ' + esc(s.ghlLocation) : '<span class="badge warn">Pas branché</span> Sans GoHighLevel, le bouton « En route » prépare le texto et tu l\'envoies toi-même.') + '</p>' +
      '<div class="field"><label for="gh-token">Clé d\'intégration privée</label><input id="gh-token" type="password" autocomplete="off" spellcheck="false" placeholder="' + (s.ghl ? 'Laisse vide pour garder la clé actuelle' : 'pit-…') + '"></div>' +
      '<div class="field"><label for="gh-loc">ID du compte (Location ID)</label><input id="gh-loc" autocomplete="off" spellcheck="false" placeholder="' + (s.ghl ? 'Laisse vide pour garder l\'ID actuel' : '') + '"></div>' +
      '<details class="small"><summary>Où trouver ça dans GoHighLevel ?</summary><ol><li>Paramètres → <b>Private Integrations</b> → Créer. Coche « View/Edit Contacts » et « View/Edit Conversation Messages ». Copie la clé (elle commence par pit-).</li><li>Paramètres → <b>Business Profile</b> : copie le « Location ID ».</li><li>Colle les deux ici. La clé va directement dans ta base : personne ne peut la relire, même pas dans l\'app.</li></ol></details>' +
      '<div class="er-acts"><button type="button" class="btn sm primary" data-act="gh-save">Enregistrer</button>' + (s.ghl ? '<button type="button" class="btn sm danger" data-act="gh-clear">Débrancher</button>' : '') + '</div>' +
      (s.ghl ? '<div class="field"><label for="gh-test">Envoyer un texto test au numéro</label><div class="er-acts"><input id="gh-test" type="tel" inputmode="tel" autocomplete="off" placeholder="514 555-0123"><button type="button" class="btn sm" data-act="gh-test">Envoyer</button></div></div>' : '') + '</section>';
    b += '<section class="sect"><h3>Cartes (optionnel)</h3><p class="small muted">Avec une clé TomTom, l\'heure d\'arrivée tient compte du trafic et la recherche d\'adresse est plus précise. Sans clé : OpenStreetMap, gratuit.</p>' +
      '<p class="small">' + (s.tomtom ? '<span class="badge ok">TomTom branché</span> ' + esc(s.tomtom) : '<span class="badge">OpenStreetMap</span>') + '</p>' +
      '<div class="field"><label for="tt-key">Clé TomTom</label><input id="tt-key" type="password" autocomplete="off" spellcheck="false" placeholder="' + (s.tomtom ? 'Laisse vide pour garder la clé actuelle' : 'Clé de developer.tomtom.com') + '"></div>' +
      '<div class="er-acts"><button type="button" class="btn sm primary" data-act="tt-save">Enregistrer</button>' + (s.tomtom ? '<button type="button" class="btn sm danger" data-act="tt-clear">Retirer</button>' : '') + '</div></section>';
    b += '<section class="sect"><h3>Ton compte</h3><p class="small">' + esc(me.name) + ' · ' + ROLE[me.role] + '</p><button type="button" class="btn" data-act="acct-out">Se déconnecter</button></section>';
    return {top:top, body:b};
  }
  function val(id){ var e = document.getElementById(id); return e ? e.value.trim() : ''; }
  function eqErr(m){ var e = document.getElementById('nw-err'); if (e){ e.textContent = m; e.hidden = !m; if (m) e.scrollIntoView({block:'nearest'}); } else if (m) toast(m); }
  function keysDoc(patch){ return T.db.doc('config/keys').get().then(function(s){ var d = Object.assign({}, s.exists ? s.data() : {}, patch); return T.db.doc('config/keys').set(d); }); }

  function onAction(a, b){
    var id = b.dataset.id, v = b.dataset.v, api = A();
    switch (a){
      case 'acct-out': T.signOut(); break;
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
      case 'eq-back': location.hash = 'reglages'; break;
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
      case 'eq-add': {
        var nm = val('nw-name'), em = val('nw-email'), rl = val('nw-role'), mc = val('nw-mech');
        if (!nm) return eqErr('Écris le nom de la personne.');
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(em)) return eqErr('Écris un courriel valide.');
        if (rl === 'mecano' && !mc) return eqErr(api.mechanics().length ? 'Choisis son nom dans l\'agenda (liste des mécanos).' : 'Ajoute d\'abord le nom de ce mécano dans Réglages → Mécanos.');
        eqErr(''); b.disabled = true; b.textContent = 'Création…';
        invoke('members', {action:'create', name:nm, email:em, role:rl, mechanic:mc}).then(function(r){
          X.eq.list = r.members; X.eq.created = {name:nm, email:em, password:r.password}; X.liveAt = 0;
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
    '.leaflet-container{font:inherit}.leaflet-control-attribution{font-size:11px}';
  document.head.appendChild(css);

  var MAP_ICON = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/></svg>';
  window.__garageExt = {
    tabs:[{key:'carte', label:'Carte', icon:MAP_ICON, view:viewMap}, {key:'equipe', label:'Équipe', hidden:true, view:viewEquipe}],
    can:function(w){
      if (!me) return undefined;
      var r = me.role;
      if (w === 'tab:reglages') return r === 'owner';
      if (w === 'tab:carte') return r !== 'mecano';
      if (w === 'tab:equipe') return r === 'owner';
      if (w === 'book' || w === 'deleteJob' || w === 'hours' || w === 'money') return r !== 'mecano';
      return undefined;
    },
    myMechanic:function(){ return me && me.role === 'mecano' ? me.mechanic : null; },
    greetName:function(){ return me ? first(me.name) : ''; },
    dashTop:agendaTop, dashExtra:dashExtra,
    agendaTop:agendaTop, settingsTop:settingsTop, jobExtra:jobExtra, onStatus:onStatus, onAction:onAction,
    nextInvoiceNo:function(start){ return T.sb.rpc('next_invoice_number', {p_start:start}).then(function(r){ if (r.error || typeof r.data !== 'number') throw r.error || new Error('no number'); return r.data; }); }
  };

  /* once signed in: role, workday already running, address keys of the garage */
  T.onReady(function(){
    me = T.member;
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
