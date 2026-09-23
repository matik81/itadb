# Decisioni architetturali

Ogni ADR registra contesto, scelta, alternative, conseguenze e condizioni di revisione.
Stato iniziale: adottate per lo scaffold, da validare sulle fonti reali.

| ADR | Scelta | Ragione e condizione di revisione |
|---|---|---|
| 0001 | Monorepo, monolite modulare | Transazioni e contratti condivisi; separare servizi solo con necessità operative misurate |
| 0002 | PostgreSQL/PostGIS + Parquet/DuckDB | Servizio concorrente distinto da batch colonnari; distribuire il lake quando un host non basta |
| 0003 | Release immutabili + provenienza | Revisioni verificabili; evitare sovrascritture e risposte dipendenti dall'ultimo import implicito |
| 0004 | API read-only/versionate | Nessun SQL pubblico e limiti espliciti; job asincroni per elaborazioni future |
| 0005 | Demo evidente, SDMX reale solo raw | Nessuna statistica inventata pubblicata come ufficiale; ogni dataflow richiede adapter e gate |
| [0006](0006-istat-publication.md) | Pubblicazione ISTAT, snapshot territoriali, API v2 | Revisioni immutabili, stati fedeli alla fonte e integrità temporale con btree_gist |
| [0007](0007-m2-coverage.md) | Copertura M2, storia e confini | Copertura esplicita, partizioni disgiunte, derivazioni geografiche tracciate; pyshp per gli originali ISTAT |
| [0008](0008-synthesis-pilot.md) | Sintesi pilota locale senza microcampione | Ricostruzione vincolata, verifica indipendente dei Parquet, incertezza esplicita; nessuna distribuzione dei record virtuali |
| [0009](0009-exact-demographic-calibration.md) | Congiunta sesso/età esatta | Tutte le 202 celle ISTAT come vincoli; audit bloccante, nuove versioni immutabili e assenza di holdout dichiarata |

Scartati ora: MongoDB come archivio primario delle osservazioni (schema/relazioni/indici),
un unico database per batch e tutte le query interattive, Kafka/Kubernetes come prerequisiti,
una tabella JSONB per 60 milioni di persone. La scelta non esclude rivalutazioni documentate.
