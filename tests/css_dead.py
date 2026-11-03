"""Find CSS rules in carnet.html that never apply: every declaration is overridden by a LATER rule with the exact same
selector in the same @media/@supports context (same specificity, later wins). Fallback-sensitive values are kept.
Usage: python3 css_dead.py [--apply]  (apply removes fully dead rules and dead declarations, keeps everything else as is)."""
import sys, re, tinycss2
from chemins import GARAGE, SAUVEGARDES   # (où est l'app : ici ou dans le dépôt)

P = GARAGE + '/carnet.html'
src = open(P, encoding='utf8').read()
a = src.index('<style>') + len('<style>'); b = src.index('</style>', a)
css = src[a:b]
RISKY = re.compile(r'color-mix|dvh|svh|lvh|@supports|-webkit-|env\(|min\(|max\(|clamp\(|:has|backdrop', re.I)

rules = []   # (ctx, selectors tuple, start, end, [(prop, important, value, decl_start, decl_end)])
def walk(nodes, ctx, base):
    for n in nodes:
        if n.type == 'qualified-rule':
            sel = tinycss2.serialize(n.prelude).strip()
            sels = tuple(sorted(re.sub(r'\s+', ' ', x.strip()) for x in sel.split(',')))
            decls = []
            for d in tinycss2.parse_blocks_contents(n.content, skip_whitespace=True, skip_comments=True):
                if d.type == 'declaration':
                    decls.append((d.lower_name, d.important, tinycss2.serialize(d.value).strip()))
            rules.append({'ctx': ctx, 'sels': sels, 'start': base + n.source_column if False else None, 'node': n, 'decls': decls})
        elif n.type == 'at-rule' and n.content is not None and n.lower_at_keyword in ('media', 'supports'):
            inner = tinycss2.parse_rule_list(n.content, skip_whitespace=True, skip_comments=True)
            walk(inner, ctx + ('@' + n.lower_at_keyword + ' ' + re.sub(r'\s+', ' ', tinycss2.serialize(n.prelude).strip()),), base)
top = tinycss2.parse_stylesheet(css, skip_whitespace=True, skip_comments=True)
walk(top, (), 0)

# later wins: for each (ctx, single selector, prop) remember the index of the last rule setting it
last = {}
for i, r in enumerate(rules):
    for s in r['sels']:
        for (p, imp, v) in r['decls']:
            last[(r['ctx'], s, p, imp)] = i
dead_rules, dead_decl = [], 0
for i, r in enumerate(rules):
    if not r['decls'] or any(c.startswith('@supports') for c in r['ctx']): continue
    alive = False
    for (p, imp, v) in r['decls']:
        for s in r['sels']:
            j = last.get((r['ctx'], s, p, imp), i)
            if j == i: alive = True; break
            # the later value might not be understood by an older browser: then this one is its fallback
            later_vals = [vv for (pp, ii, vv) in rules[j]['decls'] if pp == p and ii == imp]
            if any(RISKY.search(vv) for vv in later_vals) or RISKY.search(p): alive = True; break
            # the later rule must cover every selector of this rule for this property, else it still applies somewhere
        if alive: break
    if not alive: dead_rules.append(i)

# declarations that never apply, inside rules that otherwise stay
partial = {}
for i, r in enumerate(rules):
    if i in dead_rules or not r['decls'] or any(c.startswith('@supports') for c in r['ctx']): continue
    keep = []
    for (p, imp, v) in r['decls']:
        live = False
        for s_ in r['sels']:
            j = last.get((r['ctx'], s_, p, imp), i)
            later_vals = [vv for (pp, ii, vv) in rules[j]['decls'] if pp == p and ii == imp] if j != i else []
            if j == i or any(RISKY.search(vv) for vv in later_vals) or RISKY.search(p): live = True; break
        keep.append(live)
    # a property set twice in the same rule is a deliberate fallback: keep both
    names = [p for (p, _, _) in r['decls']]
    keep = [k or names.count(p) > 1 for k, (p, _, _) in zip(keep, r['decls'])]
    if not all(keep): partial[i] = keep
print('rules:', len(rules), 'fully dead:', len(dead_rules), 'rules with dead declarations:', len(partial), 'dead declarations:', sum(k.count(False) for k in partial.values()))
for i in dead_rules:
    r = rules[i]; print(' ', r['ctx'] or '', ', '.join(r['sels'])[:90], '|', '; '.join(p + ':' + v[:30] for p, _, v in r['decls'])[:120])

if '--apply' in sys.argv and dead_rules:
    # remove the exact text of each dead top-level rule (only rules outside @media, to keep it simple and safe)
    out = css; removed = 0
    for i in dead_rules:
        r = rules[i]
        if r['ctx']: continue
        txt = tinycss2.serialize([r['node']])
        k = out.find(txt)
        if k < 0 or out.count(txt) > 2: continue   # identical twice: the first copy is the one that never applies
        out = out[:k] + out[k + len(txt):]; removed += 1
    for i, keep in partial.items():
        r = rules[i]; n = r['node']
        if any(t.type == 'comment' for t in n.content): continue
        txt = tinycss2.serialize([n])
        if out.count(txt) != 1: continue
        decls = [d for d in tinycss2.parse_blocks_contents(n.content, skip_whitespace=True, skip_comments=True) if d.type == 'declaration']
        body = ';'.join(tinycss2.serialize([d]).strip() for d, k in zip(decls, keep) if k)
        new = tinycss2.serialize(n.prelude).strip() + '{' + body + '}'
        out = out.replace(txt, new); removed += 1
    out = re.sub(r'\n[ \t]*\n', '\n', out)
    open(P, 'w', encoding='utf8').write(src[:a] + out + src[b:])
    print('removed', removed)
