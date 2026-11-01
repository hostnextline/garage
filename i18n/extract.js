// Every French text the app can show, read from its code: whole sentences, and sentences with parts that change
// (a name, a number, a date) as templates « Touche « {s0} ». ». node extract.js > corpus.json
const fs = require('fs'), acorn = require('acorn'), walk = require('acorn-walk');
const G = '/home/claude/garage/';
const SRC = [['carnet.html', fs.readFileSync(G + 'carnet.html', 'utf8')], ['web/equipe.js', fs.readFileSync(G + 'web/equipe.js', 'utf8')], ['web/supa.js', fs.readFileSync(G + 'web/supa.js', 'utf8')], ['web/shim.js', fs.readFileSync(G + 'web/shim.js', 'utf8')]];
const SLOT = '\u0001';
const out = new Map();   // key -> {k, kind, where:Set}
const ent = s => s.replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&#x27;/g, "'");
const norm = s => s.replace(/[   ]/g, ' ').replace(/\s+/g, ' ').trim();
function frenchy(s){
  const t = s.replace(/\{s\d+\}/g, '').trim();
  if (!/[A-Za-zÀ-ÿ]{2,}/.test(t)) return false;
  if (/^[a-z0-9_\-]+$/.test(t)) return false;                 // identifiers, keys, classes
  if (!/\s/.test(t) && /[#.\[\]=_\/:(){}]|^[a-z]+[A-Z]/.test(t) && !/[À-ÿ]/.test(t)) return false;   // selectors, code
  if (/^(https?:|mailto:|sms:|tel:|data:|#|\.|\[)/.test(t)) return false;
  if (/function|=>|\breturn\b|\bvar\b|querySelector|getElementById|\.test\(|\bnull\b|\bundefined\b/.test(t)) return false;
  if (/^[A-Z0-9_\-]+$/.test(t) && t.length < 3) return false;
  if (/^(rgba?|hsla?|linear-gradient|radial-gradient|var)\(/.test(t) || /^\d/.test(t) && !/[a-zà-ÿ]{3}/i.test(t)) return false;
  if (/[{};]\s*$/.test(t) && /:/.test(t) && !/\s[a-zà-ÿ]{3,}\s/i.test(t)) return false;   // css
  return true;
}
function add(raw, kind, where){
  let n = 0;
  let k = norm(ent(raw)).replace(new RegExp(SLOT, 'g'), () => '{s' + (n++) + '}');
  if (!k || !frenchy(k)) return;
  if (/^\{s\d+\}$/.test(k)) return;
  const kd = n ? 'tpl' : kind;
  const o = out.get(k) || {k, kind: kd, where: new Set()};
  o.where.add(where); out.set(k, o);
}
function segments(tmpl, where){
  // attribute texts inside tags
  tmpl.replace(/<[^>]*>/g, tag => { tag.replace(/\b(placeholder|title|aria-label|alt|data-tip)="([^"]*)"/g, (m, a, v) => { add(v, 'attr', where); return m; }); return tag; });
  // the text between tags
  tmpl.split(/<[^>]*>/).forEach(seg => add(seg, 'text', where));
}
const lineOf = (src, pos) => src.slice(0, pos).split('\n').length;
for (const [file, all] of SRC){
  const scripts = [];
  if (file.endsWith('.html')){
    const re = /<script(\s[^>]*)?>([\s\S]*?)<\/script>/g; let m;
    while ((m = re.exec(all))){ if (m[1] && /application\/json/.test(m[1])) continue; scripts.push([m[2], m.index + m[0].indexOf(m[2])]); }
    // the page's own HTML (outside scripts and styles)
    const html = all.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<style[\s\S]*?<\/style>/g, '');
    segments(html, file + ':html');
  } else scripts.push([all, 0]);
  for (const [code, off] of scripts){
    let ast;
    try { ast = acorn.parse(code, {ecmaVersion: 2020, sourceType: 'script', allowReturnOutsideFunction: true}); } catch (e){ console.error('parse', file, e.message); continue; }
    const where = node => file + ':' + lineOf(all, off + node.start);
    walk.fullAncestor(ast, (node, st, anc) => {
      const parent = anc[anc.length - 2];
      if (node.type === 'BinaryExpression' && node.operator === '+'){
        if (parent && parent.type === 'BinaryExpression' && parent.operator === '+') return;   // only the whole chain
        const parts = []; (function flat(n){ if (n.type === 'BinaryExpression' && n.operator === '+'){ flat(n.left); flat(n.right); } else parts.push(n); })(node);
        if (!parts.some(p => p.type === 'Literal' && typeof p.value === 'string')) return;
        const t = parts.map(p => p.type === 'Literal' && typeof p.value === 'string' ? p.value : p.type === 'TemplateLiteral' && !p.expressions.length ? p.quasis[0].value.cooked : SLOT).join('');
        segments(t, where(node));
      } else if (node.type === 'Literal' && typeof node.value === 'string'){
        if (parent && parent.type === 'BinaryExpression' && parent.operator === '+') return;
        if (parent && parent.type === 'Property' && parent.key === node) return;   // object keys
        segments(node.value, where(node));
      } else if (node.type === 'TemplateLiteral'){
        const t = node.quasis.map((q, i) => q.value.cooked + (i < node.expressions.length ? SLOT : '')).join('');
        segments(t, where(node));
      }
    });
  }
}
const arr = [...out.values()].map(o => ({k: o.k, kind: o.kind, where: [...o.where].slice(0, 3)}));
arr.sort((a, b) => a.where[0].localeCompare(b.where[0], 'en', {numeric: true}));
process.stdout.write(JSON.stringify(arr, null, 0));
console.error('texts:', arr.filter(a => a.kind !== 'tpl').length, 'templates:', arr.filter(a => a.kind === 'tpl').length);
