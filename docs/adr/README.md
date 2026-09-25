# Decisioni architetturali

Le decisioni applicabili al prodotto descrivono scelta, motivazione, conseguenze
e condizioni di revisione. I nuovi cambiamenti durevoli richiedono un ADR;
la [roadmap](../roadmap.md) distingue gli obiettivi futuri da ciò che è implementato.

| Decisione | Ambito |
|---|---|
| [0006 — release ISTAT e API v2](0006-istat-publication.md) | Provenienza, revisioni immutabili e integrità temporale |
| [0007 — copertura territoriale](0007-territorial-coverage.md) | Partizioni disgiunte, geografie e acquisizioni limitate |
| [0011 — coorti di nascita](0011-stable-birth-cohorts.md) | Età derivata, convenzione annuale e classe aperta |
| [0014 — ordine delle integrazioni](0014-ordered-population.md) | Cittadinanza prima delle famiglie e audit di invarianza |
| [0015 — popolazione come prodotto](0015-population-product.md) | PostgreSQL, API v3, frontend e separazione dalla generazione |
| [0016 — esperimento sugli archivi](0016-storage-comparison-experiment.md) | Confronto isolato PostgreSQL, DuckDB e Rust per costo ed efficienza |

L'[architettura](../architecture.md) adotta un monolite modulare, PostgreSQL/PostGIS
per il servizio e Parquet/DuckDB per la generazione. Nuovi servizi, indici o
dipendenze devono rispondere a una necessità misurata.
