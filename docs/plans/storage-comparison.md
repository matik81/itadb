# Confronto degli archivi e costi di deployment

## Obiettivo e ambito

Sul branch `experiment/population-storage-costs`, confrontare PostgreSQL attuale,
PostgreSQL ottimizzato, DuckDB e un archivio di consultazione Rust sul riferimento
nazionale verificato. Priorità: costo mensile Neon/Railway ed efficienza di CPU,
memoria, spazio e latenza. Le API e il database applicativo restano invariati.
Gli archivi sperimentali sono derivati locali, esclusi da Git; il report conserva
metodo, risultati aggregati, versioni, provenienza e limiti.

## Fasi

1. Inventario dei dati, ripristino accesso Docker, ambiente e baseline.
2. Harness riproducibile, query comuni e controlli di equivalenza dei risultati.
3. Archivi isolati PostgreSQL ottimizzato e DuckDB; misure sul volume nazionale.
4. Prototipo Rust delle operazioni rappresentative e misure equivalenti.
5. Concorrenza, consumo risorse, spazio, costruzione e controlli di errore.
6. Modello economico con tariffe ufficiali, report conclusivo e verifiche.

## Criteri

- Identici snapshot, attributi, nulli, classe 100+, identità e relazioni familiari.
- Limiti di risorse espliciti; distinguere avvio di processo, cache OS e cache motore.
- Conteggiare indici e dati ausiliari, memoria dell'intero servizio e costo di build.
- Conservare gli aggregati precalcolati comparabili e dichiarare le differenze.
- Log seguiti e heartbeat per operazioni lunghe; output senza credenziali o record.
- Nessuna promessa di riduzione costo senza ipotesi esplicite e misure pertinenti.

## Stato

Completato il 25 settembre 2026. Docker Desktop avviato e configurazione del
container PostgreSQL ripristinata dopo le prove. Audit indipendente nazionale,
checksum dei 214 Parquet e parità integrale dei record superati. Creati DuckDB,
PostgreSQL compatto e archivio Rust su tutti i record; 25 casi prestazionali e
352 casi aggiuntivi equivalenti. Misurati carichi sostenuti a 1, 4 e 8 client,
mix esteso e DuckDB anche con 1 CPU/512 MiB. Verificate ricostruzione deterministica,
corruzione, rifiuto dell'overwrite e mancata pubblicazione degli archivi incompleti.

Il [report conclusivo](../benchmarks/storage-comparison-2026-09-25.md) include
risorse, piani, formula dei costi, tariffe ufficiali, raccomandazione e limiti.
Le prove non sono un deployment cloud o una migrazione dell'applicazione:
adozione e copertura delle API residue sono il lavoro successivo, distinto
dall'esperimento richiesto. Le evidenze e gli archivi precedenti sono conservati.
