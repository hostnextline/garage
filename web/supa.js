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
    if (c === 'PGRST202' || /Could not find the function/i.test(m)) return err('no_function', m);   /* (a server not yet updated) */
    if (c === '42501' || /row-level security|not_granted|permission denied/i.test(m)) return err('not_granted', m);
    if (c === 'P0002') return err('invalid_argument', m);
    if (/fetch|network|Failed to|timeout|Load failed/i.test(m)) return err('unavailable', m);
    return err('invalid_argument', m);
  }

  /* ---------- hors ligne : une copie du carnet sur le téléphone + les changements en attente ----------
     Chaque sorte de documents (jobs, clients…) est gardée dans IndexedDB après chaque chargement.
     Sans réseau, l'app s'ouvre avec cette copie ; chaque changement est appliqué tout de suite sur le
     téléphone, gardé dans une file (outbox) et envoyé dans l'ordre dès que le signal revient. */
  var IDB = null;
  function idb(){
    if (IDB) return IDB;
    IDB = new Promise(function(res, rej){
      if (!window.indexedDB) return rej(new Error('no idb'));
      var r; try { r = indexedDB.open('gm-team', 1); } catch(e){ return rej(e); }
      r.onupgradeneeded = function(){ var d = r.result; if (!d.objectStoreNames.contains('kv')) d.createObjectStore('kv'); if (!d.objectStoreNames.contains('outbox')) d.createObjectStore('outbox', {keyPath:'n', autoIncrement:true}); };
      r.onsuccess = function(){ res(r.result); }; r.onerror = function(){ rej(r.error); }; r.onblocked = function(){ rej(new Error('blocked')); };
    });
    IDB.catch(function(){});
    return IDB;
  }
  function tx(store, mode, fn){
    return idb().then(function(d){ return new Promise(function(res, rej){
      var t = d.transaction(store, mode), out, rq = fn(t.objectStore(store));
      if (rq) rq.onsuccess = function(){ out = rq.result; };
      t.oncomplete = function(){ res(out); }; t.onerror = t.onabort = function(){ rej(t.error); };
    }); });
  }
  function kvGet(k){ return tx('kv', 'readonly', function(st){ return st.get(k); }).catch(function(){ return undefined; }); }
  function kvSet(k, v){ return tx('kv', 'readwrite', function(st){ return v === undefined ? st.delete(k) : st.put(v, k); }).catch(function(){}); }
  var OB = [], failed = [], flushing = false, flushT = null, netL = [];
  var NET = {online:navigator.onLine !== false, offlineMode:false, pending:0, sending:false, failed:failed, storeErr:''};
  T.net = NET;
  T.onNet = function(f){ netL.push(f); };
  function netChanged(){ NET.pending = OB.length; netL.slice().forEach(function(f){ try { f(NET); } catch(e){} }); }
  function cacheKey(col){ return 'c|' + T.uid + '|' + col; }
  var saveT = {};
  function saveCol(col){
    clearTimeout(saveT[col]);
    saveT[col] = setTimeout(function(){ var c = C(col); if (T.uid && c.loaded) kvSet(cacheKey(col), {docs:c.docs, since:c.since, stamps:c.stamps, full:c.full, checked:c.checked, at:Date.now()}); }, 1200);
  }
  /* the copy kept on the phone: shown at once (even without network), then the server's version replaces it */
  function hydrate(col){
    var c = C(col);
    if (c.loaded || c.hydrated || !T.uid) return Promise.resolve();
    c.hydrated = kvGet(cacheKey(col)).then(function(v){
      if (!v || c.loaded || !v.docs) return;
      c.docs = v.docs; c.since = v.since || null; c.loaded = true;
      /* (when each document last changed on the server: what lets the next opening fetch only what changed) */
      if (v.stamps && typeof v.stamps === 'object'){ c.stamps = v.stamps; c.full = +v.full || 0; c.checked = +v.checked || 0; c.cached = true; }
      overlay(col); notify(col, null);
    });
    return c.hydrated;
  }
  function mergeDeep(a, b){
    var out = (a && typeof a === 'object' && !Array.isArray(a)) ? clone(a) : {};
    Object.keys(b || {}).forEach(function(k){
      var x = out[k], y = b[k];
      out[k] = (x && y && typeof x === 'object' && typeof y === 'object' && !Array.isArray(x) && !Array.isArray(y)) ? mergeDeep(x, y) : clone(y);
    });
    return out;
  }
  /* patch: only the parts given are replaced (the others stay as they are) */
  function patchObj(v, p){
    var out = (v && typeof v === 'object' && !Array.isArray(v)) ? clone(v) : {};
    ((p && p.unset) || []).forEach(function(k){ delete out[k]; });
    Object.keys((p && p.set) || {}).forEach(function(k){ out[k] = clone(p.set[k]); });
    return out;
  }
  function applyOp(v, op){ return op.kind === 'delete' ? undefined : op.kind === 'set' ? clone(op.data) : op.kind === 'patch' ? patchObj(v, op.data) : mergeDeep(v, op.data); }
  function applyLocal(op){
    var c = C(colOf(op.path)), id = idOf(op.path), v = applyOp(c.docs[id], op);
    if (v === undefined) delete c.docs[id]; else c.docs[id] = v;
    if (c.stamps) c.stamps[id] = '';   /* (changed here: the next check asks the server for its version) */
  }
  /* changes not yet on the server stay visible on top of what the server sends */
  function overlay(col){ var ids = []; OB.forEach(function(op){ if (colOf(op.path) === col){ applyLocal(op); ids.push(idOf(op.path)); } }); return ids; }

  /* ---------- the shared notebook: same calls as claude.use('db') ---------- */
  var cols = {};       // col -> {docs:{id:data}, loaded, since, listeners:[], docListeners:{id:[fn]}, loading}
  function colOf(path){ return path.split('/').slice(0, -1).join('/'); }
  function idOf(path){ return path.split('/').pop(); }
  function C(col){ return cols[col] || (cols[col] = {docs:{}, loaded:false, since:null, listeners:[], docListeners:{}, loading:null, full:0}); }
  function freeze(o){ if (o && typeof o === 'object'){ Object.freeze(o); Object.keys(o).forEach(function(k){ freeze(o[k]); }); } return o; }
  /* « Voir comme un mécano » (the owner, in preview): show only what that mechanic's account would get from the server
     (same rule as can_read_doc: his jobs, the clients and photos of his jobs, the shared settings). Nothing is deleted. */
  function lc(s){ return String(s == null ? '' : s).trim().toLowerCase(); }
  function visible(col, id, d){
    var v = T.view, rs = v ? (v.roles && v.roles.length ? v.roles : [v.role]) : [];
    if (!v || d === undefined || rs.indexOf('mecano') < 0 || rs.some(function(r){ return r !== 'mecano'; })) return true;   /* only a mechanic alone sees less */
    if (col.indexOf('data/') === 0) return true;
    var m = lc(v.mechanic);
    if (col === 'jobs') return lc(d.mechanic) === m;
    if (col === 'clients' || col === 'photos'){
      var js = C('jobs').docs, jid = id.split('__')[0];
      for (var k in js){ if (lc(js[k].mechanic) === m && (col === 'clients' ? js[k].clientId === id : k === jid)) return true; }
      return false;
    }
    return ['config','days','avail','specs','stock','hours'].indexOf(col) >= 0;
  }
  T.setView = function(v){ T.view = v || null; Object.keys(cols).forEach(function(k){ notify(k); }); };
  function snapDoc(col, id){ var d = C(col).docs[id]; if (!visible(col, id, d)) d = undefined; return {id:id, exists:d !== undefined, data:function(){ return d === undefined ? undefined : freeze(clone(d)); }, metadata:{fromCache:false, hasPendingWrites:false}}; }
  function snapCol(col){ var c = C(col), docs = Object.keys(c.docs).filter(function(id){ return visible(col, id, c.docs[id]); }).sort().map(function(id){ return snapDoc(col, id); }); return {docs:docs, size:docs.length, empty:!docs.length, docChanges:function(){ return []; }, metadata:{fromCache:false, hasPendingWrites:false}}; }
  function notify(col, ids){
    var c = C(col);
    setTimeout(function(){
      c.listeners.slice().forEach(function(f){ try { f(snapCol(col)); } catch(e){} });
      (ids || Object.keys(c.docListeners)).forEach(function(id){ (c.docListeners[id] || []).slice().forEach(function(f){ try { f(snapDoc(col, id)); } catch(e){} }); });
    }, 0);
  }
  function since(c){ return c.since ? new Date(Date.parse(c.since) - 30000).toISOString() : null; }
  /* how often the phone talks to the server (the tests make it faster) */
  var SYNC = Object.assign({tick:15000, check:10 * 60000, full:7 * 24 * 3600000, away:60000}, window.__syncCfg || {});
  T.syncCfg = SYNC;
  /* first time on this phone: everything (page by page); after: only what changed, plus what was deleted */
  function load(col, full){
    var c = C(col);
    if (c.loading){ if (!full) c.again = true; return c.loading.then(function(){ return full ? load(col, true) : null; }); }
    var sb = T.sb, start = (full || !c.loaded) ? null : since(c), changed = {}, stamp = {}, maxAt = c.since;
    function page(from){
      var q = sb.from('docs').select('id,data,updated_at').eq('col', col).order('updated_at', {ascending:true}).order('path', {ascending:true}).range(from, from + 999);
      if (start) q = q.gte('updated_at', start);
      return q.then(function(r){
        if (r.error) throw mapErr(r.error);
        r.data.forEach(function(x){ changed[x.id] = x.data; stamp[x.id] = x.updated_at; if (!maxAt || x.updated_at > maxAt) maxAt = x.updated_at; });
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
      if (!start || !c.stamps) c.stamps = {};
      if (!start){ Object.keys(c.docs).forEach(function(id){ if (!(id in changed)){ delete c.docs[id]; ids.push(id); } }); }
      Object.keys(changed).forEach(function(id){
        if (start && c.stamps[id] && stamp[id] < c.stamps[id]) return;   /* (a newer version is already here) */
        if (JSON.stringify(c.docs[id]) !== JSON.stringify(changed[id])){ c.docs[id] = changed[id]; ids.push(id); }
        c.stamps[id] = stamp[id];
      });
      /* a deletion counts only if the document was not saved again after it */
      gone.forEach(function(g){ if (c.docs[g.id] !== undefined && !(g.id in changed)){ delete c.docs[g.id]; delete c.stamps[g.id]; ids.push(g.id); } });
      if (OB.length) ids = ids.concat(overlay(col));
      c.since = maxAt || c.since || new Date().toISOString();
      var first = !c.loaded; c.loaded = true; if (!start){ c.full = Date.now(); c.checked = c.full; }
      if (ids.length || first) notify(col, first ? null : ids);
      if (ids.length || first || !start) saveCol(col);
    }, function(e){ if (!c.loaded) c.listeners.forEach(function(f){ if (f.__onErr) f.__onErr(e); }); throw e; });
    c.loading = p.then(function(){ c.loading = null; }, function(){ c.loading = null; });
    p.then(function(){ if (c.again){ c.again = false; load(col, false).catch(function(){}); } },   /* a change came in meanwhile */
      function(){ if (c.again){ c.again = false; setTimeout(function(){ load(col, false).catch(function(){}); }, 3000); } });   /* (even if this load failed: asked again a moment later) */
    return p;
  }
  /* the light check, instead of downloading everything again: the server sends only the list of what this person
     may see, with when each document last changed. The phone fetches what is new or changed, and drops what it may
     no longer see (a job moved to another truck, a deleted fiche). */
  function check(col){
    var c = C(col);
    if (!c.loaded || !c.stamps) return load(col, true);
    if (c.checking) return c.checking;
    var sb = T.sb, srv = {}, known = {}, got = {}, gotAt = {};
    Object.keys(c.docs).forEach(function(id){ known[id] = true; });   /* (what arrives during the check is not dropped) */
    function page(from){
      return sb.from('docs').select('id,updated_at').eq('col', col).order('path', {ascending:true}).range(from, from + 999).then(function(r){
        if (r.error) throw mapErr(r.error);
        r.data.forEach(function(x){ srv[x.id] = x.updated_at; });
        if (r.data.length === 1000) return page(from + 1000);
      });
    }
    var p = page(0).then(function(){
      var need = Object.keys(srv).filter(function(id){ return !(id in c.docs) || c.stamps[id] !== srv[id]; }), parts = [];
      for (var i = 0; i < need.length; i += 150) parts.push(need.slice(i, i + 150));
      return parts.reduce(function(pr, ids){ return pr.then(function(){
        return sb.from('docs').select('id,data,updated_at').eq('col', col).in('id', ids).then(function(r){
          if (r.error) throw mapErr(r.error);
          r.data.forEach(function(x){ got[x.id] = x.data; gotAt[x.id] = x.updated_at; });
        });
      }); }, Promise.resolve());
    }).then(function(){
      var ids = [];
      Object.keys(known).forEach(function(id){ if (!(id in srv) && c.docs[id] !== undefined){ delete c.docs[id]; delete c.stamps[id]; ids.push(id); } });
      Object.keys(got).forEach(function(id){
        if (c.stamps[id] && gotAt[id] < c.stamps[id]) return;   /* (a newer version came in meanwhile) */
        if (JSON.stringify(c.docs[id]) !== JSON.stringify(got[id])){ c.docs[id] = got[id]; ids.push(id); }
        c.stamps[id] = gotAt[id];
      });
      if (OB.length) ids = ids.concat(overlay(col));
      c.checked = Date.now();
      if (ids.length) notify(col, ids);
      saveCol(col);
    });
    c.checking = p.then(function(){ c.checking = null; }, function(){ c.checking = null; });
    return p;
  }
  /* the count of a block: a booking passes only if nobody booked in that block since the room was counted */
  T.blockMark = function(key){ return withTimeout(rpc('block_mark', {p_key:key}), 8000); };
  /* a finished invoice waiting for its number: the next one of the series (once, even if two phones ask) */
  /* « Je conduis : … » — a mechanic picks his truck for a day: that day's crew, and the planned jobs of that truck become his */
  T.pickTruck = function(date, truck){ return withTimeout(rpc('pick_truck', {p_date:date, p_truck:truck || ''}), 10000).then(function(r){ soon('days'); soon('jobs'); soon('clients'); return r; }); };
  T.numberInvoice = function(jobId){ return withTimeout(rpc('number_invoice', {p_path:'jobs/' + jobId}), 10000).then(function(n){ soon('jobs'); return n; }); };
  /* what is on the server right now (a load that starts after this call): for the room in a block */
  T.fresh = function(col){ var c = C(col); return (c.loading ? c.loading.catch(function(){}) : Promise.resolve()).then(function(){ return load(col, !c.loaded); }); };
  /* the first load of a collection is shared by everyone who starts listening to it (not one full download each);
     with the copy kept on the phone, only the light check (not everything again) */
  function firstLoad(col){ var c = C(col); return c.first || (c.first = hydrate(col).then(function(){ return C(col).cached ? load(col, false).then(function(){ return check(col); }) : load(col, true); }).catch(function(e){ c.first = null; throw e; })); }   /* (the changes first: what was just changed shows at once) */
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
        var kk = 'd|' + T.uid + '|' + path;
        return withTimeout(T.sb.from('docs').select('data').eq('path', path).maybeSingle().then(function(r){
          if (r.error) throw mapErr(r.error);
          if (r.data) kvSet(kk, r.data.data); else kvSet(kk, undefined);
          return {id:id, exists:!!r.data, data:function(){ return r.data ? freeze(clone(r.data.data)) : undefined; }, metadata:{fromCache:false, hasPendingWrites:false}};
        }, function(e){ throw mapErr(e); }), 12000).catch(function(e){
          if (!e || e.code !== 'unavailable') throw e;
          var mine = OB.filter(function(op){ return op.path === path; });
          return kvGet(kk).then(function(v){
            mine.forEach(function(op){ v = applyOp(v, op); });
            if (v === undefined && !mine.length) throw e;
            return {id:id, exists:v !== undefined, data:function(){ return v === undefined ? undefined : freeze(clone(v)); }, metadata:{fromCache:true, hasPendingWrites:!!mine.length}};
          });
        });
      },
      /* o.block, o.mark: a booking in a block (the server checks that nobody booked there since the room was counted) */
      set:function(d, o){ return write('set', path, d, o); },
      update:function(d, o){ return write('merge', path, d, o); },
      /* only the parts given are replaced; the others (maybe changed meanwhile by someone else) stay */
      patch:function(set, unset){ return write('patch', path, {set:set || {}, unset:unset || []}); },
      delete:function(){ return write('delete', path, null); },
      acquire:function(){ return Promise.resolve({acquired:true, version:1}); },
      onSnapshot:function(n, onErr){
        var c = C(col); (c.docListeners[id] = c.docListeners[id] || []).push(n);
        if (c.loaded) setTimeout(function(){ n(snapDoc(col, id)); }, 0); else firstLoad(col).catch(function(e){ if (onErr && !c.loaded) onErr(e); });
        return function(){ c.docListeners[id] = (c.docListeners[id] || []).filter(function(f){ return f !== n; }); };
      },
      collection:function(p){ return colRef(path + '/' + p); }
    };
  }
  function withTimeout(p, ms){ return new Promise(function(res, rej){ var t = setTimeout(function(){ rej(err('unavailable', 'timeout')); }, ms); p.then(function(v){ clearTimeout(t); res(v); }, function(e){ clearTimeout(t); rej(e); }); }); }
  /* each change, sent to the server; the answer is the document as it is now on the server */
  function plain(op){
    if (op.kind === 'set') return rpc('doc_set', {p_path:op.path, p_data:op.data}).then(function(){ return op.data; });
    if (op.kind === 'merge') return rpc('doc_merge', {p_path:op.path, p_patch:op.data});
    if (op.kind === 'patch') return rpc('doc_patch', {p_path:op.path, p_set:op.data.set, p_unset:op.data.unset || []}).catch(function(e){
      if (!e || e.code !== 'no_function') throw e;
      return rpc('doc_set', {p_path:op.path, p_data:applyOp(C(colOf(op.path)).docs[idOf(op.path)], op)}).then(function(){ return applyOp(C(colOf(op.path)).docs[idOf(op.path)], op); });   /* (a server not yet updated: the whole document, as before) */
    });
    return rpc('doc_delete', {p_path:op.path});
  }
  function send(op){
    if (!op.bk || (op.kind !== 'set' && op.kind !== 'merge') || T.noBlockBook) return plain(op);
    return rpc('block_book', {p_key:op.bk, p_mark:op.mark == null ? null : op.mark, p_path:op.path, p_data:op.data, p_merge:op.kind === 'merge'}).then(function(r){
      if (!r || r.ok !== true){ var e = err('block_changed', 'block changed'); e.mark = r && r.mark; throw e; }
      return r.data;
    }, function(e){ if (e && e.code === 'no_function'){ T.noBlockBook = true; return plain(op); } throw e; });
  }
  function landed(op, out){
    var col = colOf(op.path), id = idOf(op.path), c = C(col);
    if (op.kind === 'delete'){ if (c.docs[id] !== undefined) delete c.docs[id]; }
    else c.docs[id] = clone(out !== undefined && out !== null ? out : op.data);
    if (c.stamps) c.stamps[id] = '';   /* (the server's time of this version comes with the next update) */
    if (OB.length) overlay(col);
    notify(col, [id]); saveCol(col);
  }
  function persistOp(op){ return tx('outbox', 'readwrite', function(st){ return st.add({uid:op.uid, kind:op.kind, path:op.path, data:op.data, at:op.at, bk:op.bk || null}); }).then(function(n){ op.n = n; }).catch(function(e){ NET.storeErr = String(e && e.message || e); netChanged(); }); }
  function dropOp(op){ if (op.n != null) tx('outbox', 'readwrite', function(st){ return st.delete(op.n); }).catch(function(){}); }
  function queue(op){
    applyLocal(op); notify(colOf(op.path), [idOf(op.path)]); saveCol(colOf(op.path));
    OB.push(op); persistOp(op); netChanged(); flushSoon(1500);
    return Promise.resolve({queued:true});
  }
  function write(kind, path, d, o){
    var op = {uid:T.uid, kind:kind, path:path, data:d == null ? null : clone(d), at:Date.now()};
    if (o && o.block){ op.bk = o.block; op.mark = o.mark == null ? null : o.mark; }
    /* (a change sent later, from the waiting list: a booking made without network takes its place without the check) */
    if (OB.length || NET.offlineMode || navigator.onLine === false){ op.mark = null; return queue(op); }
    return withTimeout(send(op), 12000).then(function(out){ landed(op, out); }, function(e){
      if (e && e.code === 'unavailable'){ op.mark = null; return queue(op); }
      throw e;
    });
  }
  function flushSoon(ms){ clearTimeout(flushT); flushT = setTimeout(flush, ms); }
  /* sends the waiting changes, in order; a change the server refuses is put aside (and shown) instead of blocking the others */
  function flush(){
    if (flushing || !OB.length || navigator.onLine === false) { if (OB.length) flushSoon(20000); return Promise.resolve(); }
    flushing = true; NET.sending = true; netChanged();
    var ensure = NET.offlineMode ? T.reconnect() : T.sb.auth.getSession().then(function(r){ return !!(r.data && r.data.session); }, function(){ return false; });
    return ensure.then(function(ok){
      if (!ok) throw err('unavailable', 'no session');
      return (function next(){
        if (!OB.length) return;
        var op = OB[0];
        return withTimeout(send(op), 15000).then(function(out){ OB.shift(); dropOp(op); landed(op, out); netChanged(); return next(); }, function(e){
          if (e && (e.code === 'unavailable' || /JWT|jwt|token/.test(String(e.message)))) throw e;   /* not the change's fault: try again later */
          OB.shift(); dropOp(op);
          failed.push({path:op.path, kind:op.kind, at:op.at, msg:String(e && e.message || e), code:e && e.code});
          check(colOf(op.path)).catch(function(){});   /* (the server's version comes back on the phone) */
          netChanged(); return next();
        });
      })();
    }).then(function(){ flushing = false; NET.sending = false; netChanged(); T.resync(false); },
            function(){ flushing = false; NET.sending = false; netChanged(); flushSoon(20000); });
  }
  T.flush = flush;
  T.pending = function(){ return OB.length; };
  T.clearFailed = function(){ failed.length = 0; netChanged(); };
  function loadOutbox(){
    return tx('outbox', 'readonly', function(st){ return st.getAll(); }).then(function(all){
      (all || []).filter(function(op){ return op.uid === T.uid; }).sort(function(a, b){ return a.n - b.n; }).forEach(function(op){ OB.push(op); });
      netChanged(); if (OB.length) flushSoon(500);
    }).catch(function(){});
  }

  function newId(){ var a = 'abcdefghijklmnopqrstuvwxyz0123456789', b = new Uint8Array(20), s = ''; (window.crypto || {}).getRandomValues ? crypto.getRandomValues(b) : b.forEach(function(_, i){ b[i] = Math.random() * 256; }); for (var i = 0; i < 20; i++) s += a[b[i] % 36]; return s; }
  function colRef(path){
    return {
      path:path,
      doc:function(id){ return docRef(path + '/' + (id || newId())); },
      onSnapshot:function(n, onErr){
        var c = C(path); if (onErr) n.__onErr = onErr; c.listeners.push(n);
        if (c.loaded) setTimeout(function(){ n(snapCol(path)); }, 0); else firstLoad(path).catch(function(e){ if (onErr && !c.loaded) onErr(e); });
        return function(){ c.listeners = c.listeners.filter(function(f){ return f !== n; }); };
      },
      get:function(){ return load(path, !C(path).loaded).then(function(){ return snapCol(path); }); }
    };
  }
  var db = Object.freeze({doc:docRef, collection:colRef});
  T.db = db;
  /* deep: also the light check (what appeared or may no longer be seen) — never everything again */
  T.resync = function(deep){ return Promise.all(watched().map(function(col){ return (deep ? check(col) : load(col, false)).catch(function(){}); })); };

  /* live updates: instant when the realtime service answers, otherwise every 15 s */
  var live = false, hiddenAt = 0;
  function startSync(){
    try {
      T.sb.channel('carnet').on('postgres_changes', {event:'*', schema:'public', table:'docs'}, function(p){
        var path = (p.new && p.new.path) || (p.old && p.old.path); if (path) soon(colOf(path));
      }).subscribe(function(st){ live = st === 'SUBSCRIBED'; });
    } catch(e){ live = false; }
    /* while the app is open: the changes (instant, or each minute as a safety), the light check every 10 minutes,
       and a whole new copy only once a week (it used to be every 10 minutes, and each time the app came back) */
    setInterval(function(){
      if (document.visibilityState === 'hidden') return;
      watched().forEach(function(col){
        var c = C(col), now = Date.now();
        if (!c.stamps || now - (c.full || 0) > SYNC.full) load(col, true).catch(function(){});
        else if (now - (c.checked || 0) > SYNC.check) check(col).catch(function(){});
        else if (!live || now % 60000 < SYNC.tick) load(col, false).catch(function(){});
      });
    }, SYNC.tick);
    document.addEventListener('visibilitychange', function(){
      if (document.visibilityState === 'hidden'){ hiddenAt = Date.now(); return; }
      T.resync(hiddenAt && Date.now() - hiddenAt > SYNC.away);
    });
    window.addEventListener('online', function(){ NET.online = true; netChanged(); if (NET.offlineMode) return; flush(); T.resync(false); });
    window.addEventListener('offline', function(){ NET.online = false; netChanged(); });
    setInterval(function(){ if (OB.length && !flushing) flush(); }, 30000);
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
      '#gate .g-lang{display:flex;gap:6px;justify-content:center}#gate .g-lang .chip{min-height:36px;padding:0 12px}' +
      '#gate .g-help{color:var(--muted);font-size:14.5px}#gate .g-link{background:none;border:0;color:var(--steel);font-weight:600;text-decoration:underline;padding:6px 0;cursor:pointer;justify-self:start;min-height:40px}' +
      '#gate .g-go{min-height:50px;border-radius:10px;border:1px solid var(--signal);background:var(--signal);color:var(--on-signal);font-weight:700;font-size:17px;cursor:pointer}' +
      '#gate .g-go[disabled]{opacity:.6;cursor:wait}' +
      '#gate .g-or{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:14px}#gate .g-or::before,#gate .g-or::after{content:"";flex:1;height:1px;background:var(--line)}' +
      '#gate .g-gg{min-height:50px;border-radius:10px;border:1px solid var(--line-strong);background:var(--surface);color:var(--ink);font-weight:700;font-size:16.5px;cursor:pointer;width:100%}#gate .g-gg[disabled]{opacity:.6;cursor:wait}';
    document.head.appendChild(st);
  }
  var LOGO = '<svg viewBox="0 0 64 64" width="30" height="30" aria-hidden="true"><path d="M18 44l8-8m10-10l10-10M26 36a8 8 0 1 0 10-10" stroke="#F2B200" stroke-width="6" fill="none" stroke-linecap="round"/></svg>';
  function gate(html){
    var g = document.getElementById('gate');
    if (!g){ g = document.createElement('div'); g.id = 'gate'; g.setAttribute('role', 'dialog'); g.setAttribute('aria-modal', 'true'); g.setAttribute('aria-labelledby', 'g-title'); document.body.appendChild(g); }
    g.innerHTML = '<div class="g-box"><div class="g-brand"><div class="g-logo">' + LOGO + '</div><div><div class="eyebrow">Garage mobile · équipe</div><h1 id="g-title">' + html.title + '</h1></div></div>' + html.body + langSw() + '</div>';
    g.hidden = false; document.body.classList.add('locked');
    var f = g.querySelector('input:not([readonly])'); if (f) setTimeout(function(){ try { f.focus(); } catch(e){} }, 30);
    return g;
  }
  /* the language, chosen before signing in too (the app's own buttons: data-act="lang") */
  function langSw(){
    var l = window.I18N ? window.I18N.lang : 'fr';
    return '<p class="g-lang langsw" role="group" aria-label="Langue / Language" translate="no">' + [['fr', 'Français'], ['en', 'English']].map(function(x){ return '<button type="button" class="chip' + (l === x[0] ? ' on' : '') + '" data-act="lang" data-v="' + x[0] + '" aria-pressed="' + (l === x[0]) + '" lang="' + x[0] + '">' + x[1] + '</button>'; }).join('') + '</p>';
  }
  window.addEventListener('i18n', function(){ var g = document.querySelector('#gate .g-lang'); if (g) g.outerHTML = langSw(); });
  function closeGate(){ var g = document.getElementById('gate'); if (g) g.remove(); document.body.classList.remove('locked'); }
  function msg(text, ok){ var m = document.getElementById('g-msg'); if (!m) return; m.textContent = text || ''; m.hidden = !text; m.className = 'g-msg' + (ok ? ' ok' : ''); }
  function busy(on){ var b = document.getElementById('g-go'); if (b){ b.disabled = on; b.textContent = on ? 'Un instant…' : b.dataset.label; } }

  /* ---- sign in with Google (Gmail): only for people the owner invited with that same address.
     The button shows only once Google is turned on for the garage's server (Supabase → Authentication → Google). ---- */
  var GOOGLE = null;
  function googleOn(){
    if (GOOGLE) return GOOGLE;
    GOOGLE = withTimeout(fetch(CFG.url + '/auth/v1/settings', {headers:{apikey:CFG.key}}).then(function(r){ return r.ok ? r.json() : {}; }), 5000)
      .then(function(j){ return !!(j && j.external && j.external.google); }, function(){ GOOGLE = null; return false; });
    return GOOGLE;
  }
  function googleBlock(id, note){
    return '<div id="' + id + '" hidden><p class="g-or">ou</p><button type="button" class="g-gg" id="' + id + '-go">Continuer avec Google</button>' + (note ? '<p class="g-help">' + note + '</p>' : '') + '</div>';
  }
  function googleWire(id){
    var box = document.getElementById(id), b = document.getElementById(id + '-go'); if (!box || !b) return;
    /* the app added to an iPhone's home screen keeps its own storage, apart from Safari where Google sends back: there, the courriel and password only */
    if (window.navigator.standalone === true) return;
    googleOn().then(function(on){ if (on && box.isConnected) box.hidden = false; });
    b.onclick = function(){
      b.disabled = true; b.textContent = 'Un instant…';
      T.sb.auth.signInWithOAuth({provider:'google', options:{redirectTo:location.origin + location.pathname, queryParams:{prompt:'select_account'}}}).then(function(r){
        if (r && r.error){ b.disabled = false; b.textContent = 'Continuer avec Google'; msg('Google ne répond pas : ' + r.error.message); }
      }, function(){ b.disabled = false; b.textContent = 'Continuer avec Google'; msg('Pas de connexion au serveur. Vérifie Internet.'); });
    };
  }
  /* back from Google: ?code=… (or an error) in the address */
  function googleReturn(){
    var q = new URLSearchParams(location.search), hq = new URLSearchParams(String(location.hash).replace(/^#/, ''));
    var code = q.get('code'), er = q.get('error_description') || q.get('error') || (hq.get('error') ? hq.get('error_description') || hq.get('error') : '');
    if (!code && !er) return false;
    try { history.replaceState(null, '', location.pathname); } catch(e){}
    if (er){ showLogin(/not enabled|unsupported provider/i.test(er) ? 'La connexion avec Google n\'est pas encore activée pour le garage.' : /signup|sign ups|not allowed/i.test(er) ? 'Ce compte Google n\'est pas invité au garage. Demande au propriétaire de t\'inviter avec ce courriel.' : /access_denied|cancel/i.test(er) ? 'Connexion avec Google annulée.' : 'La connexion avec Google n\'a pas marché (' + er + ').'); return true; }
    gate({title:'Connexion', body:'<p class="g-help">Connexion avec Google…</p>'});
    withTimeout(T.sb.auth.exchangeCodeForSession(code), 12000).then(function(r){
      if (r.error || !r.data || !r.data.session){ showLogin('La connexion avec Google n\'a pas marché. Réessaie.'); return; }
      T.viaGoogle = true; lsSet('gm.team.email', r.data.session.user.email || '');
      afterSession(r.data.session);
    }, function(){ showLogin('Pas de connexion au serveur. Vérifie Internet.'); });
    return true;
  }
  function standalone(){ try { return !!(navigator.standalone || (window.matchMedia && matchMedia('(display-mode: standalone)').matches)); } catch(e){ return false; } }
  function showLogin(note){
    gate({title:'Connexion', body:
      (standalone() && !lsGet('gm.team.email') ? '<p class="g-help" id="g-first">Première ouverture de l\'app : connecte-toi une fois avec ton courriel et ton mot de passe. Ensuite, elle se souvient de toi.</p>' : '') +
      '<form id="g-form" novalidate><div class="g-f"><label for="g-email">Courriel</label><input id="g-email" type="email" autocomplete="username" inputmode="email" autocapitalize="off" spellcheck="false" value="' + esc(lsGet('gm.team.email') || '') + '"></div>' +
      '<div class="g-f"><label for="g-pw">Mot de passe</label><input id="g-pw" type="password" autocomplete="current-password"></div>' +
      '<p class="g-msg" id="g-msg" role="alert" hidden></p><button class="g-go" id="g-go" data-label="Se connecter" type="submit">Se connecter</button>' +
      '<button type="button" class="g-link" id="g-forgot">Mot de passe oublié ?</button><p class="g-help" id="g-forgot-help" hidden>Demande au propriétaire du garage : il te donne un nouveau mot de passe dans Réglages → Équipe et accès.</p>' +
      googleBlock('g-google', '') + '</form>'});
    if (note) msg(note, false);
    googleWire('g-google');
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
  /* the invitation link (#invite=…): the person chooses a password, then is signed in */
  function errJson(r){ return (r.error && r.error.context && r.error.context.json ? r.error.context.json() : Promise.resolve({})).then(function(j){ return j || {}; }, function(){ return {}; }); }
  function showInvite(token){
    gate({title:'Bienvenue', body:'<p class="g-help">Un instant…</p>'});
    var bad = function(text){
      gate({title:'Invitation', body:'<div class="g-msg">' + esc(text) + '</div><button class="g-go" id="g-go" data-label="Aller à la connexion" type="button">Aller à la connexion</button>'});
      document.getElementById('g-go').onclick = function(){ showLogin(); };
    };
    T.sb.functions.invoke('members', {body:{action:'invite-info', token:token}}).then(function(r){
      if (r.error) return errJson(r).then(function(j){ bad(j.message || (netMsg(r.error.message) ? 'Pas de connexion au serveur. Vérifie Internet, puis rouvre le lien.' : 'Cette invitation n\'est plus valide. Demande au propriétaire de t\'en renvoyer une.')); });
      var d = r.data || {}, first = String(d.name || '').trim().split(/\s+/)[0];
      gate({title:'Bonjour' + (first ? ' ' + esc(first) : '') + ' !', body:
        '<p class="g-help">Tu es invité dans le carnet de <b>' + esc(d.garage || 'Garage mobile') + '</b>. Choisis ton mot de passe : il servira à te connecter.</p>' +
        '<form id="g-form" novalidate><div class="g-f"><label for="g-email">Ton courriel</label><input id="g-email" type="email" autocomplete="username" value="' + esc(d.email) + '" readonly></div>' +
        '<div class="g-f"><label for="g-pw">Choisis ton mot de passe <span class="g-help">(8 caractères ou plus)</span></label><input id="g-pw" type="password" autocomplete="new-password"></div>' +
        '<div class="g-f"><label for="g-pw2">Écris-le encore une fois</label><input id="g-pw2" type="password" autocomplete="new-password"></div>' +
        '<p class="g-msg" id="g-msg" role="alert" hidden></p><button class="g-go" id="g-go" data-label="Activer mon compte" type="submit">Activer mon compte</button>' +
        googleBlock('g-google', 'Seulement si <b>' + esc(d.email) + '</b> est ton compte Google : pas besoin de mot de passe.') + '</form>'});
      googleWire('g-google');
      document.getElementById('g-form').onsubmit = function(e){
        e.preventDefault();
        var pw = document.getElementById('g-pw').value, pw2 = document.getElementById('g-pw2').value;
        if (pw.length < 8){ msg('Le mot de passe doit avoir au moins 8 caractères.'); return; }
        if (pw !== pw2){ msg('Les deux mots de passe ne sont pas pareils. Écris-les encore.'); return; }
        busy(true); msg('');
        T.sb.functions.invoke('members', {body:{action:'invite-accept', token:token, password:pw}}).then(function(r2){
          if (r2.error) return errJson(r2).then(function(j){ busy(false); msg(j.message || 'L\'activation n\'a pas passé. Réessaie.'); });
          return T.sb.auth.signInWithPassword({email:d.email, password:pw}).then(function(s){
            busy(false);
            if (s.error){ showLogin('Compte activé. Connecte-toi avec ton courriel et ton mot de passe.'); return; }
            lsSet('gm.team.email', d.email); lsSet('gm.welcome', '1');
            afterSession(s.data.session);
          });
        }, function(){ busy(false); msg('Pas de connexion au serveur. Vérifie Internet.'); });
      };
    }, function(){ bad('Pas de connexion au serveur. Vérifie Internet, puis rouvre le lien.'); });
  }
  function showNoAccess(){
    var em = T.session && T.session.user && T.session.user.email;
    gate({title:'Pas d\'accès', body:'<div class="g-msg">' + (em ? 'Le compte <b>' + esc(em) + '</b>' : 'Ce compte') + ' n\'a pas (ou plus) accès au carnet du garage.</div>' +
      '<p class="g-help">' + (T.viaGoogle ? 'Avec Google, il faut que le propriétaire t\'invite avec ce même courriel (Réglages → Équipe et accès).' : 'Parle au propriétaire du garage.') + '</p><button class="g-go" id="g-go" data-label="Changer de compte" type="button">Changer de compte</button>'});
    document.getElementById('g-go').onclick = function(){ T.sb.auth.signOut().then(function(){ showLogin(); }, function(){ showLogin(); }); };
  }
  function showConfigMissing(){
    gate({title:'Pas encore branché', body:'<div class="g-msg">Cette copie n\'est pas encore reliée à la base de données du garage.</div><p class="g-help">Il manque l\'adresse du serveur (fichier config.js).</p>'});
  }

  var started = false;
  function netMsg(m){ return /fetch|network|Failed to|timeout|Load failed|NetworkError/i.test(String(m || '')); }
  function cachedMember(uid){ try { var o = JSON.parse(lsGet('gm.team.member') || 'null'); return o && o.uid === uid && o.member && o.member.active ? o.member : null; } catch(e){ return null; } }
  function storedUser(){ try { var o = JSON.parse(lsGet('gm.team.auth') || 'null'); return (o && o.user) || (o && o.currentSession && o.currentSession.user) || null; } catch(e){ return null; } }
  function go(){
    closeGate();
    if (!started){ started = true; loadOutbox(); startSync(); setReady(T); T.listeners.forEach(function(f){ try { f(T); } catch(e){} }); }
    netChanged();
  }
  /* no network at all: open with the copy kept on this phone (only for someone who already signed in here) */
  function offlineStart(uid){
    var m = cachedMember(uid);
    if (!m){ showLogin('Pas de connexion au serveur. La première connexion sur ce téléphone doit se faire avec Internet.'); return; }
    T.uid = uid; T.member = m; NET.offlineMode = true; NET.online = false;
    go();
  }
  /* back online after an offline start: a fresh session, then the waiting changes go out */
  var reconnecting = null;
  T.reconnect = function(){
    if (!NET.offlineMode) return Promise.resolve(true);
    if (reconnecting) return reconnecting;
    reconnecting = T.sb.auth.getSession().then(function(r){
      var s = r.data && r.data.session;
      if (!s){
        if (r.error && netMsg(r.error.message)) return false;
        NET.offlineMode = false; showLogin('Reconnecte-toi : tes changements faits sans réseau seront envoyés ensuite.'); return false;
      }
      return T.sb.from('members').select('*').eq('user_id', s.user.id).maybeSingle().then(function(m){
        if (m.error) return false;
        if (!m.data || !m.data.active || s.user.id !== T.uid){ NET.offlineMode = false; showNoAccess(); return false; }
        T.session = s; T.member = m.data; lsSet('gm.team.member', JSON.stringify({uid:T.uid, member:m.data}));
        NET.offlineMode = false; NET.online = true; netChanged(); T.resync(true);
        return true;
      });
    }, function(){ return false; }).then(function(ok){ reconnecting = null; return ok; }, function(){ reconnecting = null; return false; });
    return reconnecting;
  };
  function afterSession(session){
    T.session = session; T.uid = session.user.id;
    if (navigator.onLine === false && cachedMember(T.uid)) return offlineStart(T.uid);
    return withTimeout(T.sb.from('members').select('*').eq('user_id', T.uid).maybeSingle(), 6000).then(function(r){
      if (r.error){ if (netMsg(r.error.message) && cachedMember(T.uid)) return offlineStart(T.uid); showLogin(netMsg(r.error.message) ? 'Pas de connexion au serveur. Vérifie Internet.' : 'Connexion refusée : ' + r.error.message); return; }
      if (!r.data || !r.data.active){ lsSet('gm.team.member', null); showNoAccess(); return; }
      T.member = r.data; lsSet('gm.team.member', JSON.stringify({uid:T.uid, member:r.data}));
      NET.offlineMode = false;
      go();
    }, function(){ if (cachedMember(T.uid)) return offlineStart(T.uid); showLogin('Pas de connexion au serveur. Vérifie Internet.'); });
  }
  setInterval(function(){ if (NET.offlineMode && navigator.onLine !== false) T.reconnect().then(function(ok){ if (ok) flush(); }); }, 15000);
  window.addEventListener('online', function(){ if (NET.offlineMode) T.reconnect().then(function(ok){ if (ok) flush(); }); });
  T.onReady = function(f){ if (started) f(T); else T.listeners.push(f); };
  function forgetPhone(){
    lsSet('gm.team.member', null);
    return new Promise(function(res){ try { (IDB || Promise.reject()).then(function(d){ d.close(); }, function(){}).then(function(){ var r = indexedDB.deleteDatabase('gm-team'); r.onsuccess = r.onerror = r.onblocked = function(){ res(); }; }); } catch(e){ res(); } });
  }
  T.signOut = function(){ return forgetPhone().then(function(){ return T.sb.auth.signOut(); }).then(function(){ location.reload(); }, function(){ location.reload(); }); };

  function start(){
    css();
    if (!CFG.url || !CFG.key || !window.supabase){ showConfigMissing(); failReady(err('no_config')); return; }
    T.sb = window.supabase.createClient(CFG.url, CFG.key, {auth:{persistSession:true, autoRefreshToken:true, storageKey:'gm.team.auth', detectSessionInUrl:false, flowType:'pkce'}});
    T.sb.auth.onAuthStateChange(function(ev){ if (ev === 'SIGNED_OUT' && started) location.reload(); });
    if (googleReturn()) return;
    var inv = (String(location.hash).match(/^#invite=([A-Za-z0-9_-]{20,80})(?:&l=(?:en|fr))?$/) || [])[1];   /* (&l=: the language the invitation was written in) */
    if (inv){ try { history.replaceState(null, '', location.pathname + location.search); } catch(e){} showInvite(inv); return; }
    var su = storedUser();
    if (navigator.onLine === false && su && su.id && cachedMember(su.id)){ offlineStart(su.id); return; }
    withTimeout(T.sb.auth.getSession(), 6000).then(function(r){
      var s = r.data && r.data.session;
      if (s) return afterSession(s);
      if (su && su.id && (navigator.onLine === false || (r.error && netMsg(r.error.message)))) return offlineStart(su.id);
      return T.sb.rpc('setup_needed').then(function(x){
        if (x.error && su && su.id && netMsg(x.error.message)) return offlineStart(su.id);
        if (x.data === true) showSetup(); else showLogin();
      }, function(){ if (su && su.id) offlineStart(su.id); else showLogin(); });
    }, function(){ if (su && su.id) offlineStart(su.id); else showLogin(); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
