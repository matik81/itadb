# Migrazione completa della consultazione a DuckDB

## Risultato richiesto

Backend e frontend funzionano senza Neon e senza PostgreSQL online, conservando
tutte le API v1/v2/v3, release, verifiche e geografie. Branch `feat/duckdb-serving`,
derivato dall'esperimento misurato. PostgreSQL/PostGIS resta uno strumento locale
di preparazione e pubblicazione; non è un servizio del deployment.

## Decisioni

Un archivio DuckDB immutabile contiene tutte le viste pubbliche, con geometrie
GeoJSON preparate offline. Esportazione consistente tramite ruolo reader;
manifest con schema, conteggi, verifiche e SHA-256. Attivazione atomica di una
release verificata, mantenimento delle precedenti, riavvio del backend per
cambiare versione. Nessuna scrittura o SQL libero nelle API.

## Esito

Completati export completo, controlli di integrità, installazione e ripristino,
repository DuckDB, readiness, limiti, Compose senza DB, configurazione Railway e
documentazione. Il contratto OpenAPI e i tipi client sono invariati.

Verificati tutti i 58.943.464 individui e 26.670.169 famiglie durante il trasferimento,
insieme a storico, geografia e validazioni: archivio completo di 321.400.832 byte.
404 confronti API identici e 404 risposte HTTP verificate su una copia ripristinata,
senza rete e con PostgreSQL fermo, nel budget di 1 CPU / 512 MiB.

Tutte le suite richieste passano: 353 Python inclusa integrazione PostgreSQL,
43 frontend, 3 Rust; anche lint, tipi, OpenAPI, build e smoke Compose.
[Report completo](../benchmarks/duckdb-migration-2026-09-25.md).

Il deployment su un account cloud non è eseguito. PostgreSQL resta solo nella
preparazione locale; non rimangono API online da migrare. I risultati non sono
una misura di carico sostenuto su Railway né una promessa di spesa mensile.
