import json
A = {(m['role'], m['dev'], m['screen']): m for m in json.load(open('audit/metrics.json', encoding='utf8'))}
B = {(m['role'], m['dev'], m['screen']): m for m in json.load(open('audit2/metrics.json', encoding='utf8'))}
rows = [('mecano', 'tel', 'onglet_jour', "Ma journée (mécano, téléphone)"), ('mecano', 'tel', 'job', 'Fiche d\'une job (mécano, téléphone)'),
        ('proprio', 'pc', 'job', 'Fiche d\'une job (ordinateur)'), ('proprio', 'pc', 'onglet_reglages', 'Réglages (ordinateur)'),
        ('proprio', 'pc', 'facture_editeur', 'Facture'), ('proprio', 'pc', 'page_equipe', 'Équipe et accès'), ('proprio', 'pc', 'onglet_agenda', 'Agenda (ordinateur)')]
def realb(m): return len([b for b in m['btns'] if b != '?' and not b.startswith('Aide')])
for k1, k2, k3, lab in rows:
    a, b = A.get((k1, k2, k3)), B.get((k1, k2, k3))
    if not a or not b: print(lab, 'manque'); continue
    print(f"{lab}: champs {a['ninp']}→{b['ninp']} · mots tech {len(a['jargon'])}→{len(b['jargon'])} ({', '.join(a['jargon'])} → {', '.join(b['jargon'])}) · écrans {a['screens']}→{b['screens']} · boutons {realb(a)}→{realb(b)}")
