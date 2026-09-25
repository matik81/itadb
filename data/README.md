# Archivio locale dei dati

Questa directory contiene una guida versionata; dati ed evidenze runtime
restano ignorati da Git. `ITADB_DATA_DIR` sceglie la root della CLI. Il volume
Compose `evidence` è distinto e non contiene automaticamente i file host.

| Percorso relativo alla root | Contenuto |
|---|---|
| `raw/<prefisso>/<sha256>/` | Originali, contratti, codice e lock archiviati per contenuto; manifest di acquisizione |
| `curated/population/<run_id>/` | Popolazione verificata: input, manifest, rapporto e batch Parquet |
| `state/` | Inventari, lock, checkpoint e tentativi necessari a retry e riproduzione |
| `reports/population/` | Ammissione, log e misure della generazione |
| `reports/population-publication/` | Esiti dell'importazione nel database |
| `reports/inventory/` | Inventari e mappe di ricollocazione locali |
| `quarantine/` | Fallimenti conservati per diagnosi |

Il catalogo DB e i manifest conservano percorsi e checksum. Non spostare raw,
snapshot, checkpoint o inventari senza migrare e verificare i riferimenti.
Non eliminare originali, tentativi falliti, backup o volumi per ripetere una prova.
I [contratti](../contracts/README.md) sono indicizzati per funzione.

Per nuove misure usare una root dedicata, per esempio `--root data/benchmarks/NOME`;
questa contiene a sua volta raw/curated/state/reports/quarantine. I rapporti
condivisibili sono in `docs/benchmarks/`. Le fixture ridotte versionate sono
in `tests/fixtures/`, inventate e marcate come tali. Nessun dump, Parquet o
record individuale entra in Git.

## Archivio del servizio

`data/serving/` (escluso da Git) contiene `releases/SHA256/application.duckdb`,
manifest, cronologia delle attivazioni e collegamento `current`. Include tutto
il prodotto pubblico: popolazione, aggregati, verifiche e geografia. Il volume
Compose monta questa directory in sola lettura nell’API. Esportazioni e CSV di
verifica restano in directory separate sotto `data/state/`, fuori dal pacchetto
online. [Installazione e backup](../docs/deployment.md).
