# Les tests du Carnet du garage

Tout se teste sur une **copie locale de Supabase**, jamais sur la vraie base du garage.
La copie est construite ici, avec des clés inventées et de faux GoHighLevel, Stripe et TomTom :
aucun vrai service n'est appelé, aucun vrai texto ne part.

| Étape | Commande | Durée |
|---|---|---|
| 1. Construire la copie (une seule fois) | `bash tests/stack/installer.sh` | quelques minutes |
| 2. Tout tester | `bash tests/tout_tester.sh` | environ 1 h 30 |
| 3. Arrêter la copie | `bash tests/stack/arreter.sh` | quelques secondes |

Il faut : Ubuntu 24.04 (ou semblable), Postgres 16, Node 22, Python 3 avec `playwright`, `pypdf`, `pillow`, `openpyxl`,
`cryptography`, et Chromium (`python3 -m playwright install --with-deps chromium`).

Sur GitHub, chaque envoi sur la branche `source` lance tout seul les tests essentiels (onglet *Actions*).

## Ce qu'il y a ici

| Dossier ou fichier | Rôle |
|---|---|
| `stack/` | La copie locale : Postgres, Auth (GoTrue), PostgREST, les fonctions du garage, les faux services |
| `stack/installer.sh` | Télécharge les programmes (versions fixes, vérifiées), crée la base, applique `supabase/migrations` |
| `stack/test_api.js` | Le serveur seul : droits de chaque rôle, fonctions, paiements, textos |
| `test_*.py` | L'app dans un vrai navigateur : chaque écran, chaque rôle, téléphone et ordinateur, avec de vraies écritures |
| `team_seed.py` | Le garage de test (Hassan, Saleh, Ali, Lina, Nadia, deux clients, deux jobs), remis à neuf avant chaque suite |
| `tout_tester.sh` | Lance tout et écrit un résumé ; s'arrête en erreur s'il y a un seul échec |
