# Dati locali

| Directory | Contenuto |
|---|---|
| `raw/` | Originali e contratti archiviati per SHA-256 |
| `curated/` | Input ammessi e snapshot Parquet generati |
| `state/` | Checkpoint e pacchetti di esportazione |
| `reports/` | Rapporti e avanzamento delle generazioni |
| `quarantine/` | Tentativi falliti e controlli bloccanti |
| `published/` | Archivi DuckDB preparati, versioni immutabili e `current` |
| `serving/` | Archivi installati per l'API, versioni immutabili e `current` |

Questi dati non vanno in Git. Il repository contiene soltanto fixture inventate
ridotte in `tests/fixtures`, con licenza e natura dichiarate.
Originali, manifest e rapporti consentono riproduzione e audit del modello.
Le directory di backup sullo stesso disco non sostituiscono un backup esterno.
