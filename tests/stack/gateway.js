// local only: one door like https://<project>.supabase.co
const http = require('http');
const routes = [['/rest/v1', 3000], ['/auth/v1', 9999], ['/functions/v1/en-route', 9101], ['/functions/v1/members', 9102]];
const CORS = {'access-control-allow-origin':'*','access-control-allow-headers':'authorization, x-client-info, apikey, content-type, prefer, range, accept-profile, content-profile, x-supabase-api-version, accept','access-control-allow-methods':'GET, POST, PATCH, PUT, DELETE, OPTIONS','access-control-expose-headers':'content-range, x-total-count'};
http.createServer((req, res) => {
  if (req.method === 'OPTIONS'){ res.writeHead(204, CORS); return res.end(); }
  const r = routes.find(([p]) => req.url === p || req.url.startsWith(p + '/') || req.url.startsWith(p + '?'));
  if (!r){ res.writeHead(404, {...CORS, 'content-type':'application/json'}); return res.end('{"message":"no route"}'); }
  const path = req.url.slice(r[0].length) || '/';
  const headers = {...req.headers}; delete headers.host;
  const up = http.request({host:'127.0.0.1', port:r[1], path: path.startsWith('/') ? path : '/' + path, method:req.method, headers}, (u) => {
    const h = {...u.headers}; Object.keys(h).forEach(k => { if (k.startsWith('access-control-')) delete h[k]; });
    res.writeHead(u.statusCode, {...h, ...CORS}); u.pipe(res);
  });
  up.on('error', (e) => { res.writeHead(502, {...CORS, 'content-type':'application/json'}); res.end(JSON.stringify({message:'upstream ' + e.message})); });
  req.pipe(up);
}).listen(54321, '127.0.0.1');
