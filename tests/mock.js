// In-memory stand-in for the claude.ai runtime (db, user, downloads), for local testing only.
(function(){
  var cfg = window.__MOCK || {};
  var store = JSON.parse(JSON.stringify(cfg.seed || {})); window.__store = store; window.__saved = []; window.__writes = [];
  var docL = {}, colL = {};
  function clone(o){ return o == null ? o : JSON.parse(JSON.stringify(o)); }
  function deepFreeze(o){ if (o && typeof o === 'object'){ Object.freeze(o); Object.keys(o).forEach(function(k){ deepFreeze(o[k]); }); } return o; }
  function merge(a, b){ var out = clone(a) || {}; Object.keys(b).forEach(function(k){ var v = b[k]; if (v && typeof v === 'object' && !Array.isArray(v) && out[k] && typeof out[k] === 'object' && !Array.isArray(out[k])) out[k] = merge(out[k], v); else out[k] = clone(v); }); return out; }
  function snapDoc(path){ var id = path.split('/').pop(), d = store[path]; return {id:id, exists:!!d, data:function(){ return d ? deepFreeze(clone(d)) : undefined; }, metadata:{fromCache:false, hasPendingWrites:false}}; }
  function colOf(path){ return path.split('/').slice(0, -1).join('/'); }
  function snapCol(col){ var docs = Object.keys(store).filter(function(p){ return colOf(p) === col; }).sort().map(snapDoc); return {docs:docs, size:docs.length, empty:!docs.length, docChanges:function(){ return []; }, metadata:{fromCache:false, hasPendingWrites:false}}; }
  function notify(path){ setTimeout(function(){ (docL[path]||[]).forEach(function(f){ f(snapDoc(path)); }); var c = colOf(path); (colL[c]||[]).forEach(function(f){ f(snapCol(c)); }); }, 5); }
  function deny(path){ if (cfg.readOnly) return true; if (cfg.notAdmin && (path.indexOf('config/') === 0 || path.indexOf('days/') === 0)) return true; return false; }
  function err(code){ var e = new Error(code); e.code = code; return e; }
  var leases = {}, seq = 0;
  function docRef(path){
    return {
      id:path.split('/').pop(), path:path,
      get:function(){ return Promise.resolve(snapDoc(path)); },
      set:function(d){ if (deny(path)) return Promise.reject(err('invalid_argument')); store[path] = clone(d); window.__writes.push(['set', path]); notify(path); return Promise.resolve(); },
      update:function(d){ if (deny(path)) return Promise.reject(err('invalid_argument')); if (!store[path]) return Promise.reject(err('invalid_argument')); store[path] = merge(store[path], d); window.__writes.push(['update', path]); notify(path); return Promise.resolve(); },
      delete:function(){ if (deny(path)) return Promise.reject(err('invalid_argument')); delete store[path]; window.__writes.push(['delete', path]); notify(path); return Promise.resolve(); },
      acquire:function(o){ var now = Date.now(), l = leases[path]; if (l && l.until > now && l.holder !== o.holder) return Promise.resolve({acquired:false, expiresAt:new Date(l.until).toISOString()}); leases[path] = {holder:o.holder, until:now + (o.ttlMs || 30000)}; if (!store[path]) store[path] = {}; if (o.data) store[path] = merge(store[path], o.data); return Promise.resolve({acquired:true, version:1, holder:o.holder}); },
      onSnapshot:function(n){ (docL[path] = docL[path] || []).push(n); setTimeout(function(){ n(snapDoc(path)); }, 5); return function(){}; },
      collection:function(p){ return colRef(path + '/' + p); }
    };
  }
  function colRef(path){
    return {
      path:path,
      doc:function(id){ return docRef(path + '/' + (id || ('d' + (++seq) + Math.random().toString(36).slice(2, 8)))); },
      onSnapshot:function(n){ (colL[path] = colL[path] || []).push(n); setTimeout(function(){ n(snapCol(path)); }, 5); return function(){}; },
      get:function(){ return Promise.resolve(snapCol(path)); }
    };
  }
  var db = {doc:docRef, collection:colRef};
  var user = {id:function(){ return Promise.resolve(cfg.noUid ? null : 'u_test'); }, isOwner:function(){ return Promise.resolve(!cfg.notAdmin); }, canEdit:function(){ return Promise.resolve(!cfg.notAdmin && !cfg.readOnly); }, can:function(){ return Promise.resolve(cfg.readOnly ? false : true); }};
  var downloads = {save:function(r){ return Promise.resolve(r.data instanceof Blob ? r.data.arrayBuffer() : r.data).then(function(buf){ var b = new Uint8Array(buf), s = ''; for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]); window.__saved.push({filename:r.filename, b64:btoa(s)}); return {status:'saved'}; }); }};
  // mcp stand-in: cfg.mcp = {mode:'ok'|'not_connected'|'approval'|'reauth'|'unavailable'|'declined', fixture:{...}, delays:{query:ms}}
  window.__mcpCalls = [];
  var mcp = null;
  if (cfg.mcp){
    var M = cfg.mcp, n = 0;
    mcp = Object.freeze({callTool:function(server, tool, input, opts){
      n++; window.__mcpCalls.push({server:server, tool:tool, input:clone(input), opts:clone(opts), t:Date.now()});
      var mode = M.mode || 'ok';
      if (mode === 'approval' && n === 1) return Promise.reject({code:'approval_required', message:'needs approval'});
      if (mode === 'not_connected') return Promise.reject({code:'server_not_connected', server:server, message:'no connector'});
      if (mode === 'reauth') return Promise.reject({code:'needs_reauth', server:server, message:'reauth'});
      if (mode === 'declined') return Promise.reject({code:'not_in_manifest', server:server, message:'declined'});
      if (mode === 'unavailable' && n === 1) return Promise.reject({code:'server_unavailable', retryable:true, message:'down'});
      if (tool === 'tomtom-geocode'){ var gq = M.geocode && M.geocode[input.query]; return new Promise(function(r){ setTimeout(function(){ r({content:[], payload:clone(gq || {type:'FeatureCollection', features:[]})}); }, M.geoDelay || 30); }); }
      if (tool === 'tomtom-reverse-geocode'){
        window.__mcpLive = (window.__mcpLive || 0) + 1; window.__mcpMaxLive = Math.max(window.__mcpMaxLive || 0, window.__mcpLive);
        return new Promise(function(res, rej){ setTimeout(function(){
          window.__mcpLive--;
          if (M.revFail) return rej({code:M.revFail, message:'fail'});
          var pos = input.position, kx = 111320 * Math.cos(pos[1] * Math.PI / 180), best = null, bd = 1e9;
          (M.houses || []).forEach(function(h){ var d = Math.hypot((h.lon - pos[0]) * kx, (h.lat - pos[1]) * 111320); if (d < bd){ bd = d; best = h; } });
          if (!best || bd > (input.radius || 100)) return res({content:[], payload:{type:'FeatureCollection', features:[]}});
          res({content:[], payload:{type:'Feature', geometry:{type:'Point', coordinates:pos}, properties:{type:'Point Address', address:{freeformAddress:best.num + ' ' + best.street + ', Montréal QC ' + best.pc, streetNumber:best.num, streetName:best.street, municipality:'Montréal', neighborhood:'Le Plateau', postalCode:best.pc.slice(0, 3), countryCode:'CA'}, originalPosition:[best.lon, best.lat]}}});
        }, M.revDelay || 25); });
      }
      var q = String(input && input.query || '').toLowerCase(), qq = input && input.query, ix = input && input.idxSet;
      var pick = (input && input.typeahead === false && M.verify && M.verify[qq]) || (M.byQuery && (M.byQuery[qq + '|' + ix] || M.byQuery[qq])) || (M.byIdx && M.byIdx[ix]) || M.fixture || {type:'FeatureCollection', features:[]};
      var fc = clone(pick);
      if (q.indexOf('zzzz') >= 0) fc.features = [];
      var delay = (M.delays && M.delays[input.query]) || 30;
      return new Promise(function(r){ setTimeout(function(){ r({content:[{type:'text', text:JSON.stringify(fc)}], payload:fc}); }, delay); });
    }});
  }
  if (cfg.noClaude) return;
  window.claude = {use:function(n){ return new Promise(function(r){ setTimeout(function(){ r(n === 'db' ? (cfg.noDb ? null : db) : n === 'user' ? user : n === 'downloads' ? downloads : n === 'mcp' ? mcp : null); }, 20); }); }};
})();
