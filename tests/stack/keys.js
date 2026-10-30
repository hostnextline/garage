const jwt = require('jsonwebtoken');
const secret = 'super-secret-jwt-token-with-at-least-32-characters-long';
const exp = Math.floor(Date.now()/1000) + 10*365*24*3600;
console.log(JSON.stringify({anon: jwt.sign({role:'anon', iss:'supabase', exp}, secret), service: jwt.sign({role:'service_role', iss:'supabase', exp}, secret), secret}));
