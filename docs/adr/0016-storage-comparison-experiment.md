# ADR 0016 — esperimento sugli archivi di consultazione

Data: 25 settembre 2026. Stato: esperimento autorizzato, nessuna migrazione adottata.

## Problema

Lo schema della popolazione nel benchmark esistente occupa circa 17,1 GB.
L'utente richiede un confronto completo che privilegi riduzione dei costi di
deployment Neon/Railway ed efficienza computazionale.

## Decisione

Confrontare in ambienti isolati PostgreSQL attuale e ottimizzato, DuckDB già
presente nelle dipendenze e un prototipo Rust di sola lettura. Rust è confinato
agli strumenti sperimentali: non si aggiungono servizi né dipendenze all'API.
Le eventuali dipendenze del prototipo sono bloccate nel relativo Cargo.lock.
I Parquet verificati restano l'origine immutabile; nessun record viene generato
virtualmente durante una richiesta. Le API v1/v2 e PostgreSQL applicativo restano
operativi secondo ADR 0015.

## Esito dell'esperimento

Il [report del 25 settembre](../benchmarks/storage-comparison-2026-09-25.md)
confronta tutti i record nazionali, verifica la parità integrale e misura
latenza, concorrenza, CPU, memoria e spazio. DuckDB è il candidato raccomandato
per costo e semplicità; Rust offre più capacità sugli accessi indicizzati ma
richiede più memoria e manutenzione. Il prototipo usa memmap2, serde/serde_json,
csv e sha2 con versioni bloccate, una CLI di build e un'ABI C chiamata da ctypes;
non aggiunge un servizio né una dipendenza al backend di prodotto.

L'adozione richiederà una decisione successiva con copertura delle API residue,
misure cloud e costo delle API storiche. Le medie locali non sono promesse
di costo o prestazioni online. La decisione applicativa di ADR 0015 rimane valida.
