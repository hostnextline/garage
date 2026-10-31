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
