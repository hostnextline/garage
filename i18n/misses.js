// Which texts shown during the tests would stay in French: runs the app's own language engine (from carnet.html) on each one.
// node misses.js runtime.jsonl [more files…] > misses.json      (each line of a .jsonl file: a JSON list of texts)
const fs = require('fs');
const src = fs.readFileSync('/home/claude/garage/carnet.html', 'utf8');
const dictTxt = src.match(/<script type="application\/json" id="i18n-en">([\s\S]*?)<\/script>/)[1].replace(/<\\\//g, '</');
const eng = src.match(/<script>\n(\/\* ===== Langue de l.app[\s\S]*?)<\/script>/)[1];
global.window = {}; global.location = {hash: '', search: ''};
global.document = {documentElement: {setAttribute(){}}, getElementById(){ return {textContent: dictTxt}; }, addEventListener(){}, querySelector(){ return null; }, querySelectorAll(){ return []; }};
global.localStorage = {getItem(){ return 'en'; }, setItem(){}, removeItem(){}}; global.navigator = {language: 'en'};
global.MutationObserver = function(){ this.observe = function(){}; };
eval(eng.replace('if (busy()) all();', ''));
const I = window.I18N;
// the test data (names, places, cars…): these are the person's own words, never translated
const seedSrc = ['team_seed.py', 'test_team.py', 'test_client.py', 'test_map.py', 'test_sched.py', 'test_receipt.py', 'test_tour.py', 'test_invite.py'].map(f => { try { return fs.readFileSync('/tmp/claude-0/-home-claude/a3bd0a01-f5c0-5b1c-a92a-e2ade1101bff/scratchpad/' + f, 'utf8'); } catch (e){ return ''; } }).join('\n');
const DATA = new Set();
seedSrc.replace(/'([^'\n]{3,90})'|"([^"\n]{3,90})"/g, (m, a, b) => { const t = (a || b).trim(); if (/[A-Za-zÀ-ÿ]{2}/.test(t) && !/[{}<>=$\\]|^[a-z_\-.#]+$/.test(t)) DATA.add(t); return m; });
['Hassan', 'Saleh', 'Ali', 'Lina', 'Nadia', 'Karim', 'Marie', 'Paul', 'Garage NextLine', 'Camion 1', 'Camion 2', 'Honda', 'Toyota', 'Civic', 'Corolla'].forEach(x => DATA.add(x));
// names replaced by a slot: only the people, places and cars of the test garage (not every word quoted in the tests)
const seedOnly = fs.readFileSync('/tmp/claude-0/-home-claude/a3bd0a01-f5c0-5b1c-a92a-e2ade1101bff/scratchpad/team_seed.py', 'utf8'), NM = new Set(['Hassan', 'Saleh', 'Ali', 'Lina', 'Nadia', 'Karim', 'Marie', 'Paul', 'Garage NextLine', 'Honda', 'Toyota', 'Civic', 'Corolla', 'Tremblay', 'Gagnon', 'Roy']);
seedOnly.replace(/'([A-ZÀ-Ý][A-Za-zÀ-ÿ'\- ]{2,40})'/g, (m, t) => { NM.add(t.trim()); return m; });
const names = [...NM].filter(x => x.length >= 3 && !/^(Camion|Plus|Client|Service|Total|Notes|Description|Signature|Garage)$/.test(x)).sort((a, b) => b.length - a.length);
const all = new Set();
for (const f of process.argv.slice(2)) for (const line of fs.readFileSync(f, 'utf8').split('\n')) { if (!line.trim()) continue; try { JSON.parse(line).forEach(s => all.add(s)); } catch (e){} }
const out = new Map();
for (const s of all){
  if (!/[a-zà-ÿ]{2}/i.test(s)) continue;
  const en = I.t(s, 'en');
  if (en !== s) continue;
  let k = I.tokens(s.replace(/\s+/g, ' ').trim()).k, n = 0;
  if (DATA.has(s.trim()) || names.includes(k) || /^\{\d+\}( ?[-·:,]? ?\{\d+\})*$/.test(k)) continue;
  if (/\b[A-Z]\d[A-Z] ?\d[A-Z]\d\b/.test(s) && /\d/.test(s)) continue;   // an address (with its postal code)
  for (const nm of names){ const re = new RegExp('(^|[^A-Za-zÀ-ÿ])' + nm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![A-Za-zÀ-ÿ])', 'g'); k = k.replace(re, (m, p) => p + '\u0001'); }
  k = k.replace(/\u0001/g, () => '{s' + (n++) + '}');
  if (/^(\{s\d+\}[ ·,\-]*)+$/.test(k)) continue;   // only names
  if (!/[a-zà-ÿ]{2}/i.test(k.replace(/\{s?\d+\}/g, ''))) continue;   // nothing but names and numbers
  if (!out.has(k)) out.set(k, s);
}
const arr = [...out].map(([k, ex]) => ({k, kind: /\{s\d+\}/.test(k) ? 'tpl' : 'text', where: ['seen: ' + ex.slice(0, 120)]}));
process.stdout.write(JSON.stringify(arr, null, 0));
console.error('texts seen', all.size, '→ not translated', arr.length);
