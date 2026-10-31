// local only: fake GoHighLevel (9200) and fake OSRM/Photon (9201)
const http = require('http');
let log = [], contacts = {}, ghlFail = null;
function body(req){ return new Promise(r => { let b = ''; req.on('data', c => b += c); req.on('end', () => { try { r(JSON.parse(b || '{}')); } catch(e){ r({}); } }); }); }
function send(res, code, o){ res.writeHead(code, {'content-type':'application/json'}); res.end(JSON.stringify(o)); }
http.createServer(async (req, res) => {
  const b = await body(req);
  if (req.url === '/__log') return send(res, 200, log);
  if (req.url === '/__reset'){ log = []; contacts = {}; ghlFail = b.fail || null; return send(res, 200, {ok:true}); }
  const auth = req.headers.authorization || '';
  log.push({path:req.url, version:req.headers.version, auth, body:b});
  if (auth !== 'Bearer pit-good-token') return send(res, 401, {statusCode:401, message:'Invalid JWT'});
  if (req.url === '/contacts/upsert'){
    if (req.headers.version !== '2021-07-28') return send(res, 400, {message:'bad version'});
    if (b.locationId !== 'loc123') return send(res, 403, {message:'The token does not have access to this location'});
    if (!/^\+1\d{10}$/.test(b.phone || '')) return send(res, 422, {message:['phone must be valid']});
    const id = contacts[b.phone] || ('ct_' + b.phone.slice(-4)); const isNew = !contacts[b.phone]; contacts[b.phone] = id;
    return send(res, 200, {new:isNew, contact:{id, phone:b.phone, firstName:b.firstName}, traceId:'t1'});
  }
  if (req.url === '/conversations/messages'){
    if (req.headers.version !== '2021-04-15') return send(res, 400, {message:'bad version'});
    if (ghlFail === 'dnd') return send(res, 400, {message:'Contact has DND enabled for SMS'});
    if (b.type !== 'SMS' || !b.contactId || !b.message) return send(res, 422, {message:'missing fields'});
    return send(res, 201, {conversationId:'cv1', messageId:'m' + log.length, msg:'Message queued'});
  }
  send(res, 404, {message:'not found'});
}).listen(9200, '127.0.0.1');
function hav(a, b){ const R = 6371000, r = Math.PI/180, x = Math.sin((b[1]-a[1])*r/2)**2 + Math.cos(a[1]*r)*Math.cos(b[1]*r)*Math.sin((b[0]-a[0])*r/2)**2; return 2*R*Math.asin(Math.sqrt(x)); }
let routeCalls = 0;
http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  if (u.pathname === '/__calls') return send(res, 200, {routeCalls});
  const m = u.pathname.match(/^\/route\/v1\/driving\/([-\d.]+),([-\d.]+);([-\d.]+),([-\d.]+)$/);
  if (m){
    routeCalls++;
    const a = [+m[1], +m[2]], b = [+m[3], +m[4]], mid = [a[0], b[1]], coords = [];
    for (let i = 0; i <= 10; i++) coords.push([a[0] + (mid[0]-a[0])*i/10, a[1] + (mid[1]-a[1])*i/10]);
    for (let i = 1; i <= 10; i++) coords.push([mid[0] + (b[0]-mid[0])*i/10, mid[1] + (b[1]-mid[1])*i/10]);
    const d = hav(a, mid) + hav(mid, b);
    return send(res, 200, {code:'Ok', routes:[{distance:d, duration:d / (36000/3600), geometry:{type:'LineString', coordinates:coords}}]});
  }
  const vp = u.pathname.match(/^\/vpic\/api\/vehicles\/DecodeVinValues\/([A-Z0-9]+)$/);
  if (vp){
    const KNOWN = {
      '2HGFC2F58JH512345': {ModelYear:'2018', Make:'HONDA', Model:'Civic', Trim:'LX', Series:'', DisplacementL:'2.0', EngineCylinders:'4', FuelTypePrimary:'Gasoline', DriveType:'FWD/Front-Wheel Drive', BodyClass:'Sedan/Saloon', TransmissionStyle:'Continuously Variable Transmission (CVT)', EngineModel:'K20C2', ElectrificationLevel:'', PlantCountry:'CANADA', ErrorCode:'0', ErrorText:'0 - VIN decoded clean. Check Digit (9th position) is correct'},
      '2T3W1RFV6LW012345': {ModelYear:'2020', Make:'TOYOTA', Model:'RAV4', Trim:'XLE', Series:'AXAA54L', DisplacementL:'2.487500', EngineCylinders:'4', FuelTypePrimary:'Gasoline', DriveType:'AWD/All-Wheel Drive', BodyClass:'Sport Utility Vehicle (SUV)/Multi-Purpose Vehicle (MPV)', TransmissionStyle:'Automatic', EngineModel:'A25A-FKS', ElectrificationLevel:'', PlantCountry:'CANADA', ErrorCode:'0', ErrorText:'0 - VIN decoded clean. Check Digit (9th position) is correct'}
    };
    const r = KNOWN[vp[1]] || {ModelYear:'', Make:'', Model:'', ErrorCode:'8', ErrorText:'8 - No detailed data available currently'};
    return send(res, 200, {Count:1, Message:'Results returned successfully', Results:[Object.assign({VIN:vp[1]}, r)]});
  }
  if (u.pathname === '/photon/api/'){
    const q = (u.searchParams.get('q') || '').toLowerCase();
    if (q.indexOf('introuvable') >= 0) return send(res, 200, {type:'FeatureCollection', features:[]});
    return send(res, 200, {type:'FeatureCollection', features:[{type:'Feature', geometry:{type:'Point', coordinates:[-73.5800, 45.5300]}, properties:{name:q}}]});
  }
  send(res, 404, {message:'not found'});
}).listen(9201, '127.0.0.1');

// ---------- fake Stripe (9202): webhooks, Checkout Sessions, a payment page that signs and sends the « paid » notice ----------
const crypto = require('crypto');
let ST = {hooks:{}, sessions:{}, calls:[], n:0, delivered:[]};
const GOOD_KEYS = ['sk_test_good1234567890', 'sk_live_good1234567890', 'rk_live_good1234567890'];
function raw(req){ return new Promise(r => { let b = ''; req.on('data', c => b += c); req.on('end', () => r(b)); }); }
function formParse(s){ const o = {}; new URLSearchParams(s).forEach((v, k) => { const parts = k.replace(/\]/g, '').split('['); let cur = o; parts.forEach((p, i) => { if (i === parts.length - 1) cur[p] = v; else cur = cur[p] = cur[p] || {}; }); }); return o; }
function post(url, data, headers){ return new Promise((res) => { try { const u = new URL(url); const rq = http.request({host:u.hostname, port:u.port, path:u.pathname + u.search, method:'POST', headers:Object.assign({'content-type':'application/json', 'content-length':Buffer.byteLength(data)}, headers)}, (r) => { let b = ''; r.on('data', c => b += c); r.on('end', () => res({status:r.statusCode, body:b})); }); rq.on('error', (e) => res({status:0, body:String(e)})); rq.end(data); } catch(e){ res({status:0, body:String(e)}); } }); }
http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://x'), text = await raw(req);
  if (u.pathname === '/__log') return send(res, 200, ST);
  if (u.pathname === '/__reset'){ ST = {hooks:{}, sessions:{}, calls:[], n:0, delivered:[]}; return send(res, 200, {ok:true}); }
  // the page Stripe would show to the client
  let pm = u.pathname.match(/^\/pay\/(cs_[a-z0-9_]+)$/);
  if (pm){
    const s = ST.sessions[pm[1]]; if (!s){ res.writeHead(404); return res.end('no session'); }
    if (req.method === 'GET'){
      res.writeHead(200, {'content-type':'text/html; charset=utf-8'});
      return res.end('<!doctype html><title>Stripe (test)</title><h1>Paiement</h1><p id="amt">' + (s.amount_total / 100).toFixed(2) + ' $ CAD</p><p>' + s.line_items[0].price_data.product_data.name + '</p>' +
        '<form method="post"><button id="pay" type="submit">Payer</button></form><form method="post" action="?hook=off"><button id="pay-nohook" type="submit">Payer (sans avis)</button></form><a id="cancel" href="' + s.cancel_url + '">Retour</a>');
    }
    s.payment_status = 'paid'; s.status = 'complete';
    if (u.searchParams.get('hook') !== 'off'){
      for (const h of Object.values(ST.hooks)){
        const ev = {id:'evt_' + (++ST.n), type:'checkout.session.completed', data:{object:s}}, payload = JSON.stringify(ev), t = Math.floor(Date.now() / 1000);
        const sig = crypto.createHmac('sha256', h.secret).update(t + '.' + payload).digest('hex');
        const r = await post(h.url, payload, {'stripe-signature':'t=' + t + ',v1=' + sig});
        ST.delivered.push({to:h.url, status:r.status, body:r.body.slice(0, 300), event:ev.id});
        if (u.searchParams.get('twice') === '1') { const r2 = await post(h.url, payload, {'stripe-signature':'t=' + t + ',v1=' + sig}); ST.delivered.push({to:h.url, status:r2.status, body:r2.body.slice(0, 300), event:ev.id, again:true}); }
      }
    }
    res.writeHead(303, {location:s.success_url}); return res.end();
  }
  const auth = (req.headers.authorization || '').replace(/^Bearer\s+/, '');
  ST.calls.push({method:req.method, path:u.pathname, auth:auth.slice(0, 8)});
  if (!GOOD_KEYS.includes(auth)) return send(res, 401, {error:{message:'Invalid API Key provided', type:'invalid_request_error'}});
  const b = formParse(text);
  if (u.pathname === '/v1/webhook_endpoints' && req.method === 'POST'){
    if (auth.startsWith('rk_')) return send(res, 403, {error:{message:'The provided key does not have the required permissions for this endpoint'}});
    const id = 'we_' + (++ST.n), secret = 'whsec_' + crypto.randomBytes(12).toString('hex');
    ST.hooks[id] = {id, url:b.url, secret, events:Object.values(b.enabled_events || {})};
    return send(res, 200, {id, object:'webhook_endpoint', url:b.url, secret, enabled_events:ST.hooks[id].events});
  }
  let wm = u.pathname.match(/^\/v1\/webhook_endpoints\/(we_\d+)$/);
  if (wm && req.method === 'DELETE'){ delete ST.hooks[wm[1]]; return send(res, 200, {id:wm[1], deleted:true}); }
  if (u.pathname === '/v1/checkout/sessions' && req.method === 'POST'){
    const li = (b.line_items || {})[0] || {}, cents = +((li.price_data || {}).unit_amount || 0) * (+li.quantity || 1);
    if (!cents) return send(res, 400, {error:{message:'Missing amount'}});
    const id = 'cs_test_' + (++ST.n);
    ST.sessions[id] = {id, object:'checkout.session', url:'http://127.0.0.1:9202/pay/' + id, amount_total:cents, currency:(li.price_data || {}).currency, payment_status:'unpaid', status:'open', mode:b.mode, locale:b.locale,
      metadata:b.metadata || {}, client_reference_id:b.client_reference_id, success_url:b.success_url, cancel_url:b.cancel_url, line_items:[li]};
    return send(res, 200, ST.sessions[id]);
  }
  let sm = u.pathname.match(/^\/v1\/checkout\/sessions\/(cs_[a-z0-9_]+)$/);
  if (sm && req.method === 'GET'){ const s = ST.sessions[sm[1]]; return s ? send(res, 200, s) : send(res, 404, {error:{message:'No such checkout.session'}}); }
  send(res, 404, {error:{message:'Unrecognized request URL'}});
}).listen(9202, '127.0.0.1');
