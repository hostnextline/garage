/* Garage mobile — la page s'ouvre même sans réseau.
   La page et ses outils sont gardés sur le téléphone. Avec du réseau, on prend toujours la page la plus récente
   (et on garde la copie à jour) ; sans réseau, on sert la copie. Les données passent par l'app (copie du carnet
   + file des changements), jamais par ce fichier : les appels à la base ne sont jamais gardés ici. */
var V = '6f14909c2515';
var CORE = ['./', 'config.js', 'manifest.webmanifest', 'vendor/supabase.js', 'vendor/leaflet.js', 'vendor/leaflet.css', 'icons/icon-192.png', 'icons/icon-180.png'];
var LIBS = ['https://cdn.jsdelivr.net/npm/@zxing/library@0.21.3/umd/index.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js'];
var KEEP = /^https:\/\/(cdn\.jsdelivr\.net\/npm\/(@zxing\/|tesseract\.js|@tesseract\.js-data\/)|cdnjs\.cloudflare\.com\/ajax\/libs\/(jspdf|xlsx)\/|fonts\.googleapis\.com\/|fonts\.gstatic\.com\/)/;

self.addEventListener('install', function(e){
  e.waitUntil(caches.open('app-' + V).then(function(c){
    return c.addAll(CORE.map(function(u){ return new Request(u, {cache:'reload'}); })).then(function(){
      return Promise.all(LIBS.map(function(u){ return fetch(u, {mode:'cors'}).then(function(r){ if (r.ok) return c.put(u, r); }).catch(function(){}); }));
    });
  }).then(function(){ return self.skipWaiting(); }));
});
self.addEventListener('activate', function(e){
  e.waitUntil(caches.keys().then(function(ks){
    return Promise.all(ks.filter(function(k){ return k.indexOf('app-') === 0 && k !== 'app-' + V; }).map(function(k){ return caches.delete(k); }));
  }).then(function(){ return self.clients.claim(); }));
});

function timeout(p, ms){ return new Promise(function(res, rej){ var t = setTimeout(function(){ rej(new Error('timeout')); }, ms); p.then(function(v){ clearTimeout(t); res(v); }, function(x){ clearTimeout(t); rej(x); }); }); }
function put(req, res){ if (res && (res.ok || res.type === 'opaque')){ var copy = res.clone(); caches.open('app-' + V).then(function(c){ c.put(req, copy); }); } return res; }

self.addEventListener('fetch', function(e){
  var req = e.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url), here = new URL(self.registration.scope);
  if (url.origin === here.origin && url.pathname.indexOf(here.pathname) === 0){
    var rest = url.pathname.slice(here.pathname.length);
    /* the app itself: newest when online (5 s at most), the phone's copy otherwise */
    if (req.mode === 'navigate' && (rest === '' || rest === 'index.html')){
      e.respondWith(timeout(fetch(req), 5000).then(function(r){ return put('./', r); }).catch(function(){
        return caches.match('./', {ignoreSearch:true}).then(function(r){ return r || caches.match('index.html'); }).then(function(r){ return r || new Response('<h1>Pas de réseau</h1><p>Ouvre l\'app une première fois avec Internet.</p>', {headers:{'Content-Type':'text/html; charset=utf-8'}}); });
      }));
      return;
    }
    /* its files: the copy at once, refreshed in the background */
    if (CORE.indexOf(rest) >= 0 || /^(vendor|icons)\//.test(rest)){
      e.respondWith(caches.match(req, {ignoreSearch:true}).then(function(hit){
        var net = fetch(req).then(function(r){ return put(req, r); });
        if (hit){ net.catch(function(){}); return hit; }
        return net;
      }));
    }
    return;   /* client pages (suivi, client…) always come from the network */
  }
  /* barcode reader, receipt reader, PDF, Excel, fonts: kept after the first use */
  if (KEEP.test(req.url)){
    e.respondWith(caches.match(req).then(function(hit){
      return hit || fetch(req).then(function(r){ return put(req, r); });
    }));
  }
});
