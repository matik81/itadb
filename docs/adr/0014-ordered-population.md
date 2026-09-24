# ADR 0014 — cittadinanza prima della composizione familiare

Data: 24 settembre 2026. Stato: adottata su richiesta esplicita dell'utente.

## Problema

La graduatoria v5 richiede sesso/età, geografia, cittadinanza e infine famiglie.
Il precedente arricchimento aggiungeva la cittadinanza a famiglie già formate;
il solo riordino documentale non applicava la decisione agli script.

## Decisione

Il riferimento corrente `population-reference/1` usa gli stessi input ammessi
POSAS, geografia, famiglie e STR/RCS, senza dipendere da uno snapshot sintetico
precedente. `synthesize-population` e `verify-population` sono i comandi correnti.
Per ogni batch esegue i quattro passaggi in ordine, registrato sia come
priorità sia come sequenza eseguibile nel manifest e nel rapporto.

I primi tre passaggi producono `individuals.parquet`: ID, territorio,
coorte, sesso, natura sintetica e cittadinanza. Non contiene famiglia o adulto
di riferimento. Il quarto passaggio legge questo file e aggiunge soltanto
`household_id` e `reference_adult` al Parquet finale, mantenendo lo schema
finale compatibile con il precedente arricchimento.

L'audit SQL indipendente confronta ogni attributo fra individui e persone
finali. Verifica STR e RCS su entrambi, oltre agli stessi vincoli nazionali
e familiari già adottati. Il file prima delle famiglie resta nello snapshot,
inventariato e protetto da checksum. Checkpoint, retry, budget e quarantena
seguono il protocollo locale esistente; nessuna pubblicazione automatica.

## Regole e alternative

Si conservano seed, selezione STR, permutazioni RCS e regola casuale familiare.
Gli ordinali entro comune/sesso/età sono ricostruiti dagli ID prima
dell'assegnazione familiare. Il riordino deve conservare i valori del precedente
risultato a parità di input, seed e ambiente; ciò è oggetto di confronto,
non una nuova calibrazione delle relazioni familiari.

Cambiare soltanto la lista delle priorità lascerebbe inalterato l'ordine
effettivo. Sovrascrivere gli snapshot precedenti cancellerebbe la provenienza.
Si adotta quindi un nuovo riferimento eseguibile, con snapshot autonomo.
I comandi e contratti storici restano esplicitamente identificati per
riproduzione e verifica; non costituiscono riferimenti correnti alternativi.

## Conseguenze e verifiche

Un Parquet aggiuntivo per batch aumenta il disco necessario, entro il budget
da misurare a 1M, 10M e volume nazionale. L'audit certifica l'invarianza dei
primi tre passaggi durante il quarto; non la plausibilità della famiglia.
Età–singola cittadinanza e relazioni familiari restano sintetiche e non
calibrate su congiunte osservate. Nessuna nuova dipendenza, API o tabella DB.

Le prove coprono ordine effettivo, invarianti, compatibilità storica,
interruzioni fra fasi e batch, ripresa, ordine inverso, input incompatibili,
corruzione e metadati alterati. Le misure eseguite sono registrate nella
[validazione](../validation.md) e nel [piano](../plans/population-order.md).
