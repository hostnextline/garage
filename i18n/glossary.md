# Translating the « Carnet du garage mobile » app (Québec French → Canadian English)

The app: a mobile car-repair business in Québec (mechanics drive a truck to the client's home). The owner, office staff,
mechanics and a treasurer use it on phones and computers: bookings ("jobs"), clients and their vehicles, invoices,
expenses and receipts, GST/QST taxes, trucks' stock, a team map, availability, settings, a guided tour, help bubbles « ? ».
Some screens are seen by the garage's clients (invoice, payment, "your mechanic is on the way").

## Tone
- The French speaks to the person with « tu » (friendly, plain, short). English: plain, friendly, short, "you". No jargon.
- Keep the same length or shorter. Buttons and labels: Title-less sentence case as in the French ("Add expense", not "Add Expense"),
  except proper nouns.
- French quotes « … » become “…” (curly double quotes). Keep « ? » help references as “?”.
- Québec words: « job » (a repair visit) → "job"; « char / auto » → "car"; « courriel » → "email"; « texto » → "text" (SMS); « magasiner » → "shop".

## Glossary (use these every time)
| French | English |
|---|---|
| Carnet du garage mobile | Mobile Garage Logbook |
| carnet | logbook |
| Aujourd'hui / Ma journée | Today / My day |
| Tableau de bord | Dashboard |
| Agenda | Schedule |
| Réservation, réserver | Booking, book |
| Facture, factures | Invoice, invoices |
| Facture sur place | On-the-spot invoice |
| Soumission | Quote |
| Fiche client | Client file |
| Fiche technique (du moteur) | Spec sheet |
| Dépense, dépenses | Expense, expenses |
| Reçu | Receipt |
| Trésorerie | Finances |
| Rapport et taxes | Report and taxes |
| Taxes à remettre | Taxes to remit |
| TPS / TVQ / TVH | GST / QST / HST |
| Stock des camions | Truck stock |
| Camion | Truck |
| Carte de l'équipe | Team map |
| Disponibilités | Availability |
| Heures d'ouverture | Opening hours |
| Horaire | Schedule (hours) |
| Réglages | Settings |
| Équipe et accès | Team and access |
| Plus (the tab with everything else) | More |
| Propriétaire / Bureau / Mécano / Trésorier | Owner / Office / Mechanic / Treasurer |
| mécano, mécanos | mechanic, mechanics |
| Visite guidée | Guided tour |
| En route / Planifié / Arrivé / Terminé / Annulé / Absent | On the way / Scheduled / Arrived / Done / Cancelled / No-show |
| Payée / Non payée / Brouillon | Paid / Unpaid / Draft |
| Comptant / Débit / Crédit / Virement | Cash / Debit / Credit / E-transfer |
| Enregistrer | Save |
| Annuler | Cancel |
| Supprimer | Delete |
| Modifier | Edit |
| Fermer | Close |
| Suivant › / ‹ Retour | Next › / ‹ Back |
| Touche … | Tap … |
| Essaie : … | Try it: … |
| Hors ligne / sans réseau | Offline / no signal |
| Se déconnecter | Sign out |
| Mot de passe / Courriel | Password / Email |
| VIN, NIV | VIN |
| plaque | plate |
| Pièces / Main-d'œuvre | Parts / Labour |
| rabais | discount |
| Sous-total / Total | Subtotal / Total |
| Avant taxes | Before tax |

## Placeholders — copy them exactly
- `{s0}`, `{s1}` … are parts filled in by the app (a name, a word, a number, a date, or just "s"/"" for a French plural).
  Keep EVERY placeholder, exactly once each. You may move them where English needs them.
- A slot that is just a French plural ending (e.g. `client{s1}`, `absent{s2}`): keep the one on the noun glued to the English
  noun (`client{s1}` → `client{s1}`). If the French has an extra plural slot that has no place in English (on an adjective or a
  participle), put the value `null` for that key instead of a translation — I will rewrite those few sentences in the code.
- `{0}`, `{1}` … are numbers, money or dates: keep them, same rules.
- Keep HTML-like or code-like text unchanged.

## What NOT to translate (return the text unchanged)
- Proper names, brand names (NAPA, Esso, Stripe, GoHighLevel, Google, TomTom, Supabase, iPhone…), place names, street names.
- Things that are clearly code, file names, URLs, CSS, keys, or not words (return as is).
- Car makes and models.
