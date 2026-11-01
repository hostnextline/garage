// What the app understands from a receipt's text (the part after the photo is read). node test_receipt_parse.js
const fs = require('fs');
const src = fs.readFileSync('/home/claude/garage/carnet.html', 'utf8');
const grab = (start) => { const i = src.indexOf(start); if (i < 0) throw new Error('not found: ' + start); let d = 0, j = src.indexOf('{', i); for (; j < src.length; j++) { if (src[j] === '{') d++; else if (src[j] === '}' && --d === 0) break; } return src.slice(i, j + 1); };
const line = (start) => { const i = src.indexOf(start); return src.slice(i, src.indexOf(';\n', i) + 1); };
eval(line('var RC_SHOPS =') + '\n' + line('var RC_MON =') + '\n' + grab('function parseReceipt('));
let ok = 0, n = 0;
const check = (name, got, want) => { n++; const bad = Object.keys(want).filter(k => JSON.stringify(got[k]) !== JSON.stringify(want[k])); if (!bad.length) { ok++; console.log('PASS ' + name); } else console.log('FAIL ' + name + ' -> ' + bad.map(k => k + ': got ' + JSON.stringify(got[k]) + ', want ' + JSON.stringify(want[k])).join(' | ')); };
const NOW = '2026-11-01';
check('NAPA (French, ISO date, sub-total, TPS 5 %, TVQ 9,975 %, Visa)', parseReceipt(`NAPA PIÈCES D'AUTO
1234 BOUL. DÉCARIE, MONTRÉAL
TÉL : 514 555-0199
FACTURE 004512   2026-10-28 14:32
PLAQUETTES FREIN AV     42,99
NETTOYANT FREINS         7,01
SOUS-TOTAL              50,00
TPS 5%                   2,50
TVQ 9,975%               4,99
TOTAL                   57,49
VISA                    57,49
MERCI DE VOTRE VISITE`, NOW), {vendor: 'NAPA', date: '2026-10-28', sub: 50, tps: 2.5, tvq: 4.99, total: 57.49, method: 'Crédit', cat: 'pieces'});
check('Esso gas (28/10/2026, litres, Interac)', parseReceipt(`ESSO
STATION 2231
28/10/2026 08:12
ESSENCE ORDINAIRE
45,123 L @ 1,559 $/L
TPS 3,06
TVQ 6,10
TOTAL 70,35 $
INTERAC`, NOW), {vendor: 'Esso', date: '2026-10-28', tps: 3.06, tvq: 6.10, total: 70.35, method: 'Débit', cat: 'essence'});
check('Costco (English, 10/28/2026, GST/QST, Mastercard, « total number of items » ignored)', parseReceipt(`COSTCO WHOLESALE
LAVAL #503
5W30 MOTOR OIL 12PK      54,99
SUBTOTAL                 54,99
GST                       2,75
QST                       5,49
TOTAL                    63,23
TOTAL NUMBER OF ITEMS SOLD = 1
MASTERCARD               63,23
10/28/2026 11:05`, NOW), {vendor: 'Costco', date: '2026-10-28', sub: 54.99, tps: 2.75, tvq: 5.49, total: 63.23, method: 'Crédit', cat: 'fourn'});
check('restaurant (« Oct 28, 2026 », cash)', parseReceipt(`Tim Hortons #1234
Oct 28, 2026  7:45
2 Café moyen       4,38
Total             12,50
Cash              20,00
Change             7,50`, NOW), {vendor: 'Tim Hortons', date: '2026-10-28', total: 12.5, method: 'Comptant', cat: 'repas'});
check('a shop we don\'t know: its name from the first line, « 28 octobre 2026 »', parseReceipt(`Garage Pièces Rivard inc.
3300 rue Jarry Est
28 octobre 2026
Courroie        38,00
Total           43,69`, NOW), {vendor: 'Garage Pièces Rivard Inc.', date: '2026-10-28', total: 43.69});
check('OCR mistake « T0TAL »: the total comes from the card line', parseReceipt(`CANADIAN TIRE
T0TAL 57,49
DEBIT 57,49`, NOW), {vendor: 'Canadian Tire', total: 57.49, method: 'Débit'});
check('thousands with a space « 1 234,56 $ »', parseReceipt(`PRINCESS AUTO
TOTAL 1 234,56 $`, NOW), {vendor: 'Princess Auto', total: 1234.56, cat: 'outils'});
check('only a sub-total and taxes: the total is added up', parseReceipt(`ATELIER X
SOUS-TOTAL 100,00
TPS 5,00
TVQ 9,98`, NOW), {total: 114.98, sub: 100, tps: 5, tvq: 9.98});
check('a date in the future is not taken', parseReceipt(`RONA
2027-05-01
TOTAL 10,00`, NOW), {vendor: 'Rona', date: undefined, total: 10});
check('the TPS number of the shop (no cents) is not an amount', parseReceipt(`BMR
TPS 123456789 RT0001
TVQ 1234567890 TQ0001
TOTAL 22,99`, NOW), {tps: undefined, tvq: undefined, total: 22.99});
check('OCR read « IRS » for TPS and « 10,35 » for 70,35: the TPS comes from the TVQ, the impossible total is left empty (and said)', parseReceipt(`ESSO
IRS 3,06
TVQ 6,10
TOTAL 10,35-$
INTERAC`, NOW), {tvq: 6.10, tps: 3.06, total: undefined, doubt: 'total'});
check('a total larger than its taxes (some items without tax) is kept', parseReceipt(`IGA
TPS 0,50
TVQ 1,00
TOTAL 85,00`, NOW), {total: 85, tps: 0.5, tvq: 1});
check('another province (HST): one tax, no TVQ', parseReceipt(`ESSO ONTARIO
HST 6,50
TOTAL 56,50`, NOW), {tps: 6.5, tvq: 0, total: 56.5});
check('nothing readable: nothing filled', parseReceipt(`~~ ##### ::\n|||`, NOW), {total: undefined, date: undefined, vendor: undefined});
check('a shop name inside another word is not that shop (« CAMPBELL » is not Bell), an item named like a shop is not the shop', parseReceipt(`GARAGE CAMPBELL
12 rue Principale
BOUCHON SHELL-STYLE    4,00
DIVERS                 6,00
DIVERS                 7,00
DIVERS                 8,00
DIVERS                 9,00
DIVERS                 1,00
TOTAL 35,00`, NOW), {vendor: 'Garage Campbell', total: 35});
check('« TOTAL REMIS » (the cash given) is not the total', parseReceipt(`DEPANNEUR X
TOTAL 23,45
TOTAL REMIS 50,00
MONNAIE 26,55`, NOW), {total: 23.45, method: undefined});
check('a refund (« TOTAL -57,49 »): no total filled, said', parseReceipt(`NAPA
REMBOURSEMENT
TOTAL -57,49`, NOW), {total: undefined, doubt: 'total'});
check('a doubtful total is not rebuilt from the sub-total or the card line', parseReceipt(`ESSO
SOUS-TOTAL 61,19
TPS 3,06
TVQ 6,10
TOTAL 10,35
VISA 10,35`, NOW), {total: undefined, doubt: 'total', sub: 61.19});
check('GST only (Alberta): no TVQ invented', parseReceipt(`PETRO-CANADA
GST 2,50
TOTAL 52,50`, NOW), {vendor: 'Petro-Canada', tps: 2.5, tvq: undefined, total: 52.5});
check('PST (another province) is not taken as TVQ', parseReceipt(`CANADIAN TIRE
GST 2,50
PST 3,50
TOTAL 56,00`, NOW), {tps: 2.5, tvq: undefined, total: 56});
console.log(ok + '/' + n + ' passed');
