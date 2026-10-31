# Sauvegardes du garage (dépôt PRIVÉ — ne jamais le rendre public)

Chaque nuit vers 3 h, GitHub copie tout le carnet du garage (Supabase) ici :

| Dossier | Contenu |
|---|---|
| `sauvegarde/AAAA-MM-JJ.json` | Le carnet de ce jour-là : jobs, clients, factures, réglages, horaire, dispos, dépenses, fiches techniques, liste de l'équipe. Les 90 derniers jours sont visibles ; les plus vieux restent dans l'historique. |
| `recus/` | Une photo de reçu par fichier. |

Pas dans la copie : les mots de passe, la clé GoHighLevel, les positions GPS, les brouillons.
Aucun mot de passe à garder : GitHub signe chaque copie, et le serveur du garage n'ouvre le carnet qu'à ce dépôt-ci (branche main).

**Copie tout de suite :** onglet *Actions* → *Sauvegarde de la nuit* → *Run workflow*.
**Si une copie échoue :** GitHub t'envoie un courriel.
**Remettre des données :** `python3 restaurer.py sauvegarde/AAAA-MM-JJ.json` (ou `--seulement clients/`) puis coller `restaurer.sql` dans Supabase → SQL Editor. Ou demande à Claude.
