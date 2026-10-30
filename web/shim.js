/* Version rapide du carnet, hors claude.ai.
   Remplace le runtime claude.ai par :
   - une base locale (localStorage de ce navigateur, synchronisée entre les onglets),
   - la recherche d'adresse en direct : TomTom (avec la clé de l'utilisateur) ou OpenStreetMap (Photon, sans clé). */
(function(){
  var DBK = 'gm.web.db', TTK = 'gm.web.ttkey';
  function lsGet(k){ try { return localStorage.getItem(k); } catch(e){ return null; } }
  function lsSet(k, v){ try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); return true; } catch(e){ return false; } }
  function clone(o){ return o == null ? o : JSON.parse(JSON.stringify(o)); }
  var store = {};
  try { store = JSON.parse(lsGet(DBK) || '{}') || {}; } catch(e){ store = {}; }
  var persistOk = true;
  function persist(){ persistOk = lsSet(DBK, JSON.stringify(store)); if (!persistOk) bar(); }

  /* ---------- db (same calls as claude.use('db')) ---------- */
  var docL = {}, colL = {}, leases = {}, seq = 0;
  function colOf(path){ return path.split('/').slice(0, -1).join('/'); }
  function snapDoc(path){ var id = path.split('/').pop(), d = store[path]; return {id:id, exists:!!d, data:function(){ return d ? clone(d) : undefined; }, metadata:{fromCache:false, hasPendingWrites:false}}; }
  function snapCol(col){ var docs = Object.keys(store).filter(function(p){ return colOf(p) === col; }).sort().map(snapDoc); return {docs:docs, size:docs.length, empty:!docs.length, docChanges:function(){ return []; }, metadata:{fromCache:false, hasPendingWrites:false}}; }
  function notify(path){ setTimeout(function(){ (docL[path] || []).forEach(function(f){ f(snapDoc(path)); }); var c = colOf(path); (colL[c] || []).forEach(function(f){ f(snapCol(c)); }); }, 0); }
  function notifyAll(){ setTimeout(function(){ Object.keys(docL).forEach(function(p){ docL[p].forEach(function(f){ f(snapDoc(p)); }); }); Object.keys(colL).forEach(function(c){ colL[c].forEach(function(f){ f(snapCol(c)); }); }); }, 0); }
  function merge(a, b){ var out = clone(a) || {}; Object.keys(b).forEach(function(k){ var v = b[k]; if (v && typeof v === 'object' && !Array.isArray(v) && out[k] && typeof out[k] === 'object' && !Array.isArray(out[k])) out[k] = merge(out[k], v); else out[k] = clone(v); }); return out; }
  function err(code){ var e = new Error(code); e.code = code; return e; }
  function docRef(path){
    return {
      id:path.split('/').pop(), path:path,
      get:function(){ return Promise.resolve(snapDoc(path)); },
      set:function(d){ store[path] = clone(d); persist(); notify(path); return Promise.resolve(); },
      update:function(d){ if (!store[path]) return Promise.reject(err('not_found')); store[path] = merge(store[path], d); persist(); notify(path); return Promise.resolve(); },
      delete:function(){ delete store[path]; persist(); notify(path); return Promise.resolve(); },
      acquire:function(o){ var now = Date.now(), l = leases[path]; if (l && l.until > now && l.holder !== o.holder) return Promise.resolve({acquired:false, expiresAt:new Date(l.until).toISOString()}); leases[path] = {holder:o.holder, until:now + (o.ttlMs || 30000)}; return Promise.resolve({acquired:true, version:1, holder:o.holder}); },
      onSnapshot:function(n){ (docL[path] = docL[path] || []).push(n); setTimeout(function(){ n(snapDoc(path)); }, 0); return function(){ docL[path] = (docL[path] || []).filter(function(f){ return f !== n; }); }; },
      collection:function(p){ return colRef(path + '/' + p); }
    };
  }
  function colRef(path){
    return {
      path:path,
      doc:function(id){ return docRef(path + '/' + (id || (Date.now().toString(36) + (++seq).toString(36) + Math.random().toString(36).slice(2, 8)))); },
      onSnapshot:function(n){ (colL[path] = colL[path] || []).push(n); setTimeout(function(){ n(snapCol(path)); }, 0); return function(){ colL[path] = (colL[path] || []).filter(function(f){ return f !== n; }); }; },
      get:function(){ return Promise.resolve(snapCol(path)); }
    };
  }
  var db = Object.freeze({doc:docRef, collection:colRef});
  window.addEventListener('storage', function(e){ if (e.key !== DBK) return; try { store = JSON.parse(e.newValue || '{}') || {}; } catch(x){ store = {}; } notifyAll(); });

  /* ---------- user: whoever opens this copy owns it ---------- */
  var user = Object.freeze({id:function(){ return Promise.resolve('local'); }, isOwner:function(){ return Promise.resolve(true); }, canEdit:function(){ return Promise.resolve(true); }, can:function(){ return Promise.resolve(true); }});

  /* ---------- downloads: a normal browser download ---------- */
  var downloads = Object.freeze({save:function(r){
    try {
      var blob = r.data instanceof Blob ? r.data : new Blob([r.data]), url = URL.createObjectURL(blob), a = document.createElement('a');
      a.href = url; a.download = r.filename || 'fichier'; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function(){ URL.revokeObjectURL(url); }, 4000);
      return Promise.resolve({status:'saved'});
    } catch(e){ return Promise.reject({code:'unavailable', message:String(e)}); }
  }});

  /* ---------- address search, direct from the browser ---------- */
  var last = {ms:null, prov:null, n:0}, keyRefused = false;
  function provider(){ return gKey() ? 'Google Maps' : lsGet(TTK) && !keyRefused ? 'TomTom' : 'OpenStreetMap'; }
  window.__addrProvider = provider;
  function q(o){ return Object.keys(o).filter(function(k){ return o[k] !== undefined && o[k] !== null && o[k] !== ''; }).map(function(k){ return encodeURIComponent(k) + '=' + encodeURIComponent(o[k]); }).join('&'); }
  var inflight = {}, cache = {}, cacheKeys = [], photonTry = 0;
  function remember(k, v){ if (!(k in cache)){ cacheKeys.push(k); if (cacheKeys.length > 300) delete cache[cacheKeys.shift()]; } cache[k] = v; }
  function tomtom(input, key, signal){
    var pos = input.position || [], url = 'https://api.tomtom.com/search/2/search/' + encodeURIComponent(String(input.query || '').replace(/[\/\\]/g, ' ')) + '.json?' +
      q({key:key, typeahead:input.typeahead === false ? 'false' : 'true', limit:input.limit || 5, countrySet:(input.countries || ['CA']).join(','), language:input.language || 'fr-CA', idxSet:input.idxSet, lon:pos[0], lat:pos[1]});
    return fetch(url, {signal:signal}).then(function(r){
      if (r.status === 401 || r.status === 403){ var e = new Error('bad key'); e.badKey = true; throw e; }
      if (!r.ok) throw new Error('TomTom ' + r.status);
      return r.json();
    });
  }
  var PROVS = {'Ontario':'ON', 'New Brunswick':'NB', 'Nouveau-Brunswick':'NB', 'Nova Scotia':'NS', 'Nouvelle-Écosse':'NS', 'Manitoba':'MB', 'Alberta':'AB', 'British Columbia':'BC', 'Colombie-Britannique':'BC', 'Saskatchewan':'SK', 'Newfoundland and Labrador':'NL', 'Terre-Neuve-et-Labrador':'NL', 'Prince Edward Island':'PE', 'Île-du-Prince-Édouard':'PE'};
  function fromPhoton(fc){
    var feats = (fc && fc.features) || [];
    return {type:'FeatureCollection', features:feats.filter(function(f){ return String((f.properties || {}).countrycode || '').toUpperCase() === 'CA'; }).map(function(f){
      var p = f.properties || {}, num = p.housenumber || '', street = p.street || ((p.osm_key === 'highway' || p.type === 'street') ? (p.name || '') : ''), city = p.city || p.locality || p.town || p.village || p.county || '';
      var prov = /qu[ée]bec/i.test(p.state || '') ? 'QC' : (PROVS[p.state] || p.state || ''), pc = String(p.postcode || '').toUpperCase().replace(/^([A-Z]\d[A-Z])\s*(\d[A-Z]\d)$/, '$1 $2');
      var kind = num && street ? 'Point Address' : street ? 'Street' : 'Geography';
      var free = (num ? num + ' ' : '') + street + (city ? ', ' + city : '') + (prov ? ' ' + prov : '') + (pc ? ' ' + pc : '');
      return {type:'Feature', geometry:f.geometry, properties:{type:kind, address:{streetNumber:num, streetName:street, municipality:city, neighbourhood:p.district || '', countrySubdivision:prov, postalCode:pc.slice(0, 3), freeformAddress:free}}};
    })};
  }
  function photon(input, signal){
    var pos = input.position || [], layer = input.idxSet === 'Str' ? 'street' : 'house';
    var plain = 'https://photon.komoot.io/api/?' + q({q:input.query, limit:Math.min(10, (input.limit || 5) + 3), lon:pos[0], lat:pos[1]});
    var tries = [plain + '&layer=' + layer + '&lang=fr', plain + '&layer=' + layer, plain];
    function go(i){ return fetch(tries[i], {signal:signal}).then(function(r){ if (r.ok){ photonTry = i; return r.json(); } if (i + 1 < tries.length && r.status >= 400 && r.status < 500) return go(i + 1); throw new Error('Photon ' + r.status); }); }
    return go(photonTry).then(fromPhoton);
  }
  /* postal code -> its point; point -> the address there */
  function ttGeocode(input, key, signal){
    var url = 'https://api.tomtom.com/search/2/geocode/' + encodeURIComponent(String(input.query || '').replace(/[\/\\]/g, ' ')) + '.json?' + q({key:key, countrySet:(input.countries || ['CA']).join(','), limit:input.limit || 1, language:input.language || 'fr-CA'});
    return fetch(url, {signal:signal}).then(function(r){ if (r.status === 401 || r.status === 403){ var e = new Error('bad key'); e.badKey = true; throw e; } if (!r.ok) throw new Error('TomTom ' + r.status); return r.json(); });
  }
  function ttReverse(input, key, signal){
    var pos = input.position || [], url = 'https://api.tomtom.com/search/2/reverseGeocode/' + (+pos[1]) + ',' + (+pos[0]) + '.json?' + q({key:key, radius:input.radius || 50, language:input.language || 'fr-CA'});
    return fetch(url, {signal:signal}).then(function(r){ if (r.status === 401 || r.status === 403){ var e = new Error('bad key'); e.badKey = true; throw e; } if (!r.ok) throw new Error('TomTom ' + r.status); return r.json(); });
  }
  function normPc(v){ return String(v || '').toUpperCase().replace(/\s+/g, ''); }
  function phGeocode(input, signal){
    var want = normPc(input.query);
    return fetch('https://photon.komoot.io/api/?' + q({q:input.query, limit:10}), {signal:signal}).then(function(r){ if (!r.ok) throw new Error('Photon ' + r.status); return r.json(); }).then(function(fc){
      var feats = ((fc && fc.features) || []).filter(function(f){ return normPc((f.properties || {}).postcode) === want; });
      return fromPhoton({features:feats.slice(0, 1)});
    });
  }
  function phReverse(input, signal){
    var pos = input.position || [], base = 'https://photon.komoot.io/reverse?' + q({lon:pos[0], lat:pos[1], radius:((input.radius || 50) / 1000), limit:1});
    return fetch(base + '&layer=house', {signal:signal}).then(function(r){ return r.ok ? r : fetch(base, {signal:signal}); }).then(function(r){ if (!r.ok) throw new Error('Photon ' + r.status); return r.json(); }).then(function(fc){ var out = fromPhoton(fc); out.features = out.features.filter(function(f){ return f.properties.type === 'Point Address'; }).slice(0, 1); return out; });
  }
  function run(tool, input, key, sig){
    if (tool === 'tomtom-geocode') return key ? ttGeocode(input, key, sig) : phGeocode(input, sig);
    if (tool === 'tomtom-reverse-geocode') return key ? ttReverse(input, key, sig) : phReverse(input, sig);
    return key ? tomtom(input, key, sig) : photon(input, sig);
  }
  /* ---------- Google Maps: suggestions as you type (Places API New, through Google's own script) ---------- */
  var GK = 'gm.web.gkey', gRefused = false, gLoad = null, gLib = null, gToken = null, gPreds = {}, gOrder = [], gSeq = 0;
  function gKey(){ return !gRefused ? lsGet(GK) : null; }
  window.__addrNoPostalList = function(){ return !!gKey(); };
  function gDenied(e){ return /denied|api ?key|apinotactivated|not been used|disabled|billing|permission|referer|invalidkey|missingkey|refus/i.test(String(e && (e.message || e) || '')); }
  function gRefusedNow(){
    gRefused = true;
    bar('Google refuse la clé. Dans Google Cloud, vérifie : facturation active, « Places API (New) » et « Maps JavaScript API » activées, et la clé permise pour ce site. En attendant : ' + provider() + '.');
  }
  function gEnsure(){
    if (gLib) return Promise.resolve(gLib);
    if (gLoad) return gLoad;
    gLoad = new Promise(function(ok, ko){
      window.__gmReady = function(){
        try { google.maps.importLibrary('places').then(function(lib){ gLib = lib; ok(lib); }, ko); } catch(e){ ko(e); }
      };
      window.gm_authFailure = function(){ gRefusedNow(); };
      var s = document.createElement('script');
      s.src = 'https://maps.googleapis.com/maps/api/js?' + q({key:lsGet(GK), v:'weekly', loading:'async', language:'fr', region:'CA', callback:'__gmReady'});
      s.async = true;
      s.onerror = function(){ gLoad = null; ko(new Error('Google Maps ne se charge pas')); };
      document.head.appendChild(s);
    });
    return gLoad;
  }
  var GPROV = /\s*,?\s+(QC|ON|NB|NS|MB|AB|BC|SK|NL|PE|YT|NT|NU)\b\s*,?\s*([A-Z]\d[A-Z] ?\d[A-Z]\d)?\s*$/i;
  function gClean(t){
    t = String(t || '').replace(/\s*,\s*(Canada|CA)\s*$/i, '').trim();
    return t.replace(/\s*,\s*(QC|ON|NB|NS|MB|AB|BC|SK|NL|PE|YT|NT|NU)\b\s*,?\s*([A-Z]\d[A-Z] ?\d[A-Z]\d)?\s*$/i, function(m, p, pc){ return ' ' + p.toUpperCase() + (pc ? ' ' + pc.toUpperCase().replace(/^(\w{3})\s?(\w{3})$/, '$1 $2') : ''); }).replace(/\s+,/g, ',').trim();
  }
  function gFeature(text, types, ref, d){
    var t = gClean(text), parts = t.split(','), first = (parts[0] || '').trim(), m = first.match(/^((?:\d+[A-Za-z]?-)?\d+[A-Za-z]?)\s+(.+)$/);
    var isAddr = !!m, isRoute = !isAddr && types.indexOf('route') >= 0;
    if (!isAddr && !isRoute) return null;
    var pm = t.match(GPROV), city = (parts[1] || '').replace(GPROV, '').trim();
    var a = {streetNumber:isAddr ? m[1].replace(/^.*-/, '') : '', streetName:isAddr ? m[2] : first, municipality:city, countrySubdivision:pm ? pm[1].toUpperCase() : '', freeformAddress:t};
    return {type:'Feature', geometry:d && isFinite(d.lat) && isFinite(d.lon) ? {type:'Point', coordinates:[d.lon, d.lat]} : null, properties:{type:isAddr ? 'Point Address' : 'Street', ref:ref, nostore:true, address:a}};
  }
  function gKeep(pp){ var ref = 'g' + (++gSeq); gPreds[ref] = pp; gOrder.push(ref); if (gOrder.length > 300) delete gPreds[gOrder.shift()]; return ref; }
  function gDetails(ref){
    var pp = gPreds[ref]; if (!pp) return Promise.resolve(null);
    return gEnsure().then(function(){
      var place = pp.toPlace();
      return place.fetchFields({fields:['formattedAddress', 'location']}).then(function(){
        gToken = null; /* the details call closes this search session (Google bills the session once) */
        var loc = place.location, lat = loc ? (typeof loc.lat === 'function' ? loc.lat() : loc.lat) : NaN, lon = loc ? (typeof loc.lng === 'function' ? loc.lng() : loc.lng) : NaN;
        return {text:gClean(place.formattedAddress), lat:+lat, lon:+lon};
      });
    });
  }
  function gSearch(input){
    return gEnsure().then(function(lib){
      if (!gToken) gToken = new lib.AutocompleteSessionToken();
      var pos = input.position || [], req = {input:String(input.query || ''), includedRegionCodes:['ca'], language:'fr-CA', region:'ca', sessionToken:gToken,
        includedPrimaryTypes:input.idxSet === 'Str' ? ['route'] : ['street_address', 'premise', 'subpremise', 'route']};
      if (isFinite(pos[0]) && isFinite(pos[1])){ req.origin = {lat:+pos[1], lng:+pos[0]}; req.locationBias = {center:{lat:+pos[1], lng:+pos[0]}, radius:50000}; }
      return lib.AutocompleteSuggestion.fetchAutocompleteSuggestions(req).catch(function(e){
        if (gDenied(e)) throw e;
        /* an option this version of Google does not take: ask again with the bare minimum */
        return lib.AutocompleteSuggestion.fetchAutocompleteSuggestions({input:req.input, includedRegionCodes:['ca'], language:'fr-CA', sessionToken:gToken});
      }).then(function(res){
        var feats = ((res && res.suggestions) || []).map(function(sg){ var pp = sg && sg.placePrediction; return pp ? gFeature(String(pp.text), pp.types || [], gKeep(pp), null) : null; }).filter(Boolean);
        if (input.typeahead !== false) return {type:'FeatureCollection', features:feats};
        /* checking an address typed by hand: full address (postal code, position) of the best match */
        var best = feats.filter(function(f){ return f.properties.type === 'Point Address'; })[0];
        if (!best) return {type:'FeatureCollection', features:[]};
        return gDetails(best.properties.ref).then(function(d){ var f = d && d.text ? gFeature(d.text, ['street_address'], null, d) : null; return {type:'FeatureCollection', features:f ? [f] : []}; });
      });
    });
  }
  var mcp = Object.freeze({resolvePlace:function(ref){ return String(ref || '').charAt(0) === 'g' && gKey() ? gDetails(ref) : Promise.resolve(null); }, callTool:function(server, tool, input){
    input = input || {};
    if (gKey() && tool === 'tomtom-fuzzy-search'){
      var g0 = (window.performance || Date).now();
      return gSearch(input).then(function(payload){
        last = {ms:Math.round((window.performance || Date).now() - g0), prov:provider(), n:last.n + 1}; bar();
        return {content:[{type:'text', text:JSON.stringify(payload)}], payload:payload};
      }, function(e){
        if (gDenied(e) || gRefused){ if (!gRefused) gRefusedNow(); return mcp.callTool(server, tool, input); }
        bar('Google Maps ne répond pas (' + (e && e.message || 'réseau') + ').');
        return Promise.reject({code:'server_unavailable', retryable:true, message:String(e && e.message || e)});
      });
    }
    var t0 = (window.performance || Date).now(), key = lsGet(TTK), useTT = !!(key && !keyRefused), ck = (useTT ? 'tt|' : 'osm|') + tool + '|' + JSON.stringify(input);
    if (cache[ck]){ last = {ms:0, prov:provider(), n:last.n + 1, cached:true}; bar(); return Promise.resolve({content:[], payload:cache[ck]}); }
    /* typing fast: the previous unfinished search is cancelled, only the latest one counts */
    var lane = tool === 'tomtom-fuzzy-search' ? (input.typeahead === false ? 'check' : 'type') : null;
    if (lane && inflight[lane]) try { inflight[lane].abort(); } catch(x){}
    var ctl = lane && window.AbortController ? new AbortController() : null; if (lane) inflight[lane] = ctl;
    var sig = ctl ? ctl.signal : undefined;
    var p = useTT ? run(tool, input, key, sig).catch(function(e){ if (e && e.badKey){ keyRefused = true; bar('Clé TomTom refusée : retour à OpenStreetMap. Vérifie la clé dans « Réglages de l\'essai ».'); return run(tool, input, null, sig); } throw e; }) : run(tool, input, null, sig);
    return p.then(function(payload){
      if (lane && inflight[lane] === ctl) inflight[lane] = null;
      remember(ck, payload);
      last = {ms:Math.round((window.performance || Date).now() - t0), prov:provider(), n:last.n + 1}; bar();
      return {content:[{type:'text', text:JSON.stringify(payload)}], payload:payload};
    }, function(e){
      if (lane && inflight[lane] === ctl) inflight[lane] = null;
      if (e && e.name === 'AbortError') return Promise.reject({code:'cancelled', message:'remplacée par une recherche plus récente'});
      bar(provider() + ' ne répond pas (' + (e && e.message || 'réseau') + ').'); return Promise.reject({code:'server_unavailable', retryable:true, message:String(e && e.message || e)});
    });
  }});

  /* the team version keeps its own notebook and sign-in; it only borrows the address search and the downloads */
  window.__addrMcp = mcp; window.__webDownloads = downloads;
  if (window.__GARAGE_TEAM) return;
  var caps = {db:db, user:user, downloads:downloads, mcp:mcp};
  window.claude = Object.freeze({use:function(name){ return new Promise(function(r){ setTimeout(function(){ r(caps[name] || null); }, 0); }); }});

  /* ---------- the "version rapide" strip ---------- */
  var note = '';
  function bar(msg){
    if (msg !== undefined) note = msg;
    var el = document.getElementById('demo-bar'); if (!el) return;
    document.getElementById('db-prov').textContent = provider() === 'OpenStreetMap' ? 'OpenStreetMap' : provider() + ' en direct';
    document.getElementById('db-ms').textContent = last.ms == null ? 'aucune recherche encore' : last.cached ? 'dernière recherche : instantanée (déjà en mémoire)' : 'dernière recherche : ' + last.ms + ' ms';
    var n = document.getElementById('db-note'); n.textContent = !persistOk ? 'Ce navigateur bloque le stockage : les données seront perdues en fermant.' : note; n.hidden = !n.textContent;
  }
  function mount(){
    var css = document.createElement('style');
    css.textContent = '#demo-bar{position:relative;z-index:5;background:var(--steel-soft);color:var(--ink);border-bottom:1px solid var(--line);font:500 13.5px/1.35 var(--f-body);padding:8px max(16px,env(safe-area-inset-left)) 8px max(16px,env(safe-area-inset-right))}' +
      '#demo-bar .db-top{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;max-width:1100px;margin:0 auto}' +
      '#demo-bar .db-tag{font-weight:700;color:var(--steel)}#demo-bar .db-info{color:var(--muted)}#demo-bar .db-info b{color:var(--ink);font-weight:600}' +
      '#demo-bar button{font:inherit;font-weight:600;border:1px solid var(--line-strong);background:var(--surface);color:var(--ink);border-radius:8px;padding:6px 10px;cursor:pointer;min-height:36px}' +
      '#demo-bar #db-open{margin-left:auto}#demo-bar .db-panel{max-width:1100px;margin:8px auto 2px;display:grid;gap:8px}#demo-bar .db-panel p{margin:0}' +
      '#demo-bar .db-row{display:flex;flex-wrap:wrap;gap:8px}#demo-bar input{flex:1 1 220px;min-width:0;font:inherit;padding:8px 10px;border:1px solid var(--line-strong);border-radius:8px;background:var(--surface);color:var(--ink)}' +
      '#demo-bar label{font-weight:600}#demo-bar .db-small{color:var(--muted);font-size:12.5px}#demo-bar .db-note{color:var(--warn);font-weight:600;max-width:1100px;margin:4px auto 0}#demo-bar .danger{color:var(--bad)}';
    document.head.appendChild(css);
    var el = document.createElement('div'); el.id = 'demo-bar'; el.setAttribute('role', 'region'); el.setAttribute('aria-label', 'Version rapide');
    el.innerHTML = '<div class="db-top"><span class="db-tag">⚡ Version rapide · essai</span><span class="db-info">Adresses : <b id="db-prov"></b> · <span id="db-ms"></span></span><button type="button" id="db-open" aria-expanded="false" aria-controls="db-panel">Réglages de l\'essai</button></div>' +
      '<p class="db-note" id="db-note" aria-live="polite" hidden></p>' +
      '<div class="db-panel" id="db-panel" hidden><p>Cette copie tourne hors de claude.ai pour sentir la vraie vitesse. <b>Les données restent dans ce navigateur, sur cet appareil</b> : elles ne sont pas partagées avec tes partenaires.</p>' +
      '<label for="db-key">Clé TomTom (optionnelle)</label><div class="db-row"><input id="db-key" type="password" autocomplete="off" spellcheck="false" placeholder="Colle ta clé de developer.tomtom.com"><button type="button" id="db-save">Enregistrer</button><button type="button" id="db-unkey">Retirer</button></div>' +
      '<label for="db-gkey">Clé Google Maps (optionnelle)</label><div class="db-row"><input id="db-gkey" type="password" autocomplete="off" spellcheck="false" placeholder="Colle ta clé de console.cloud.google.com"><button type="button" id="db-gsave">Enregistrer</button><button type="button" id="db-gunkey">Retirer</button></div>' +
      '<p class="db-small">Les clés restent dans ce navigateur. Ordre utilisé : Google Maps (suggestions comme dans Google Maps, sans la liste par code postal), sinon TomTom, sinon OpenStreetMap (gratuit, parfois sans code postal).</p>' +
      '<div class="db-row"><button type="button" id="db-reset" class="danger">Effacer les données d\'essai</button></div></div>';
    document.body.insertBefore(el, document.body.firstChild);
    var panel = document.getElementById('db-panel'), open = document.getElementById('db-open'), reset = document.getElementById('db-reset'), armed = false;
    open.addEventListener('click', function(){ panel.hidden = !panel.hidden; open.setAttribute('aria-expanded', String(!panel.hidden)); if (!panel.hidden){ document.getElementById('db-key').value = lsGet(TTK) ? '••••••••' : ''; document.getElementById('db-gkey').value = lsGet(GK) ? '••••••••' : ''; } });
    document.getElementById('db-gsave').addEventListener('click', function(){
      var v = document.getElementById('db-gkey').value.trim(); if (!v || /^•+$/.test(v)){ bar('Colle d\'abord ta clé Google Maps.'); return; }
      lsSet(GK, v); document.getElementById('db-gkey').value = '••••••••';
      if (gLoad){ bar('Clé Google enregistrée : la page se recharge…'); setTimeout(function(){ location.reload(); }, 700); return; }
      gRefused = false; bar('Clé Google enregistrée : les suggestions viennent maintenant de Google Maps.');
    });
    document.getElementById('db-gunkey').addEventListener('click', function(){
      lsSet(GK, null); document.getElementById('db-gkey').value = '';
      if (gLoad){ bar('Clé Google retirée : la page se recharge…'); setTimeout(function(){ location.reload(); }, 700); return; }
      gRefused = false; bar('Clé Google retirée : retour à ' + provider() + '.');
    });
    document.getElementById('db-save').addEventListener('click', function(){ var v = document.getElementById('db-key').value.trim(); if (!v || /^•+$/.test(v)){ bar('Colle d\'abord ta clé TomTom.'); return; } lsSet(TTK, v); keyRefused = false; document.getElementById('db-key').value = '••••••••'; bar('Clé TomTom enregistrée : les adresses viennent maintenant de TomTom en direct.'); });
    document.getElementById('db-unkey').addEventListener('click', function(){ lsSet(TTK, null); keyRefused = false; document.getElementById('db-key').value = ''; bar('Clé retirée : retour à OpenStreetMap.'); });
    reset.addEventListener('click', function(){ if (!armed){ armed = true; reset.textContent = 'Toucher encore pour tout effacer'; setTimeout(function(){ armed = false; reset.textContent = 'Effacer les données d\'essai'; }, 4000); return; } store = {}; persist(); notifyAll(); armed = false; reset.textContent = 'Effacer les données d\'essai'; bar('Données d\'essai effacées.'); });
    bar();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
})();
