// local only: invents the keys of the test copy (never the garage's real keys). Prints {anon, service, secret}.
const jwt = require('jsonwebtoken'), crypto = require('crypto');
const secret = crypto.randomBytes(40).toString('base64url');
const exp = Math.floor(Date.now()/1000) + 10*365*24*3600;
console.log(JSON.stringify({anon: jwt.sign({role:'anon', iss:'supabase', exp}, secret), service: jwt.sign({role:'service_role', iss:'supabase', exp}, secret), secret}));
