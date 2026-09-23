# M4 — valutazione statistica, disclosure e distribuzione

Data: 24 settembre 2026. Valutazione tecnica riproducibile sul riferimento
`7a27c844410adf29262477114bfeecc3a55743a454dfd392d4708c8163858eb8`.
Non è una revisione scientifica esterna né una certificazione di anonimato.

## Fedeltà, nell'ordine adottato

| Priorità | Risultato misurato | Limite |
|---|---|---|
| Sesso/età | 1.594.992 celle comunali M/F esatte; errore massimo e TVD pari a zero | Sono vincoli di calibrazione; 100+ resta aperto |
| Geografia | 7.896 comuni, 107 province/UTS, 20 regioni; congiunte riconciliate fino a Italia | Snapshot 01/01/2025, non simulazione di migrazioni o storia continua |
| Famiglie | 26.670.169 famiglie; classi dimensionali comunali esatte; componenti nello stesso comune | Appartenenza casuale, senza validazione delle relazioni reali |
| Residuo | 560.159 adulti, inclusi in ogni totale demografico/territoriale | Non sono una stima degli abitanti delle convivenze |

La classe 6+ rimane fissata a 6, il seed base a 1701. Non sono stati scelti
parametri per minimizzare a posteriori il residuo. Le regole adulto/minore
risultano fattibili in tutti i comuni del riferimento.

Il rapporto registra 6.568.675 famiglie sintetiche con minori, 3.532.571 con
soli componenti di almeno 65 anni e 2.919.712 con minori e componenti di almeno
65 anni. **Sono statistiche del modello**, non evidenze osservate. In particolare,
la frequenza di composizioni miste mostra quanto la casualità vincolata lasci
indeterminate le correlazioni familiari. Non se ne deducono comportamenti,
parentela o bisogni sociali. Non sono inclusi nel contratto dati esterni per
convalidare queste composizioni; non è stata svolta sensibilità nazionale
tra seed o un'analisi di incertezza demografica. I margini osservati sono fissi.

### Confronto con M3

| Proprietà | M3 riferimento v3 | M4 riferimento v1 |
|---|---|---|
| Popolazione/data | Valle d'Aosta, 123.360 al 01/01/2022 | Italia, 58.943.464 al 01/01/2025 |
| Valle d'Aosta nella versione | 60.468 famiglie, residuo 929 | 122.532 persone, 60.908 famiglie, residuo 1.098 |
| Demografia vincolata | 202 celle regionali | 202 celle per comune; livelli superiori riconciliati |
| Geografia individuale | Solo regione del pilota | Comune, provincia/UTS, regione per ogni record |
| Famiglie | Dimensioni regionali, appartenenza casuale | Dimensioni comunali, appartenenza casuale nello stesso comune |
| Nascita | Coorte stabile, 100+ aperto | Stessa convenzione annuale |
| Capacità | Pilota con limite 200.000 persone | Run nazionale effettivamente generato e riletto |

Le differenze numeriche della Valle d'Aosta riguardano periodi differenti:
non costituiscono un confronto controllato della bontà dei due algoritmi.

## Modello di rischio

Non si usano microdati donatori, nominativi, indirizzi o identificativi di
persone reali. Gli ID sintetici identificano soltanto righe del run. Questo
non rende automaticamente sicuro distribuire record dettagliati: un soggetto
con informazioni ausiliarie su comune, sesso e coorte potrebbe attribuire
una riga a un residente raro o scambiare una famiglia generata per reale.
La riproducibilità del seed non è un meccanismo di protezione.

La diagnostica SQL considera quasi-identificatori **comune, sesso, età al
riferimento**. Nello snapshot ci sono **362.643 celle non vuote con meno di
5 persone**, contenenti **851.968 persone sintetiche (1,4454%)**.
Le celle sono conteggi aggregati osservati riprodotti dal modello: questa
misura segnala granularità e rarità, non una probabilità di re-identificazione.
Non sono stati condotti linkage con dati personali, attacchi con verità
individuale nota, prove di membership inference o una verifica formale di
privacy differenziale. Non sono dichiarate garanzie k-anonime dei microdati.

## Esito operativo e formato

1. **Microdati locali.** Parquet e checkpoint rimangono esclusi da Git, API,
   frontend e distribuzione pubblica. Il manifest registra `public_release=false`
   e il report blocca la distribuzione in attesa di revisione esterna. Le
   politiche non impediscono una copia manuale da parte del proprietario dei file:
   l'archivio non è un sistema di controllo accessi o cifratura.
2. **Aggregati preparati per condivisione.** `distribution/aggregates.json`,
   schema `m4-distribution/1`: regione, sesso, classi decennali, 90+ raggruppato,
   periodo, attribuzione e limiti. Sono 400 celle, minimo misurato **483**,
   totale **58.943.464**. Riproducono soli margini pubblici già ammessi;
   non includono ID o relazioni familiari. La soglia tecnica è 10: se una
   cella è inferiore, viene trattenuta l'intera tabella, evitando soppressioni
   selettive ricostruibili. Anche questo artefatto registra `public_release=false`.
3. **Evidenze condivisibili nel repository.** Codice, contratti, metodo,
   metriche globali, checksum e questo rapporto. Non sono caricati ZIP delle
   fonti, microdati, dump, log locali o credenziali.

Il formato implementato e l'ambito locale sono descritti nella PR per la
revisione di progetto. La creazione della PR non distribuisce i dataset.
Un rilascio pubblico di microdati richiederebbe un'altra decisione, revisori
di dominio e una valutazione disclosure appropriata al prodotto e agli
attacchi previsti, come stabilito dalla [governance](../../GOVERNANCE.md).
