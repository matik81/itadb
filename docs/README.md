# Documentazione di Itadb

Il prodotto serve la popolazione sintetica verificata tramite PostgreSQL,
API v3 e web. La generazione è un workflow separato. Iniziare dal
[README](../README.md) e dalla [guida locale](local-environment.md).

| Attività | Guida |
|---|---|
| Generare, verificare e pubblicare uno snapshot | [Popolazione](population.md) |
| Comprendere priorità, assunzioni e limiti | [Fedeltà del modello](model-fidelity.md) |
| Individuare fonti, contratti e dati | [Fonti](sources.md), [contratti](../contracts/README.md), [dati](../data/README.md) |
| Comprendere componenti e database | [Architettura](architecture.md), [modello dati](data-model.md) |
| Usare le API | [Contratto e procedure](api/README.md) |
| Gestire migrazioni, retry e recupero | [Operazioni](operations.md) |
| Verificare una modifica | [Qualità](data-quality.md), [verifiche](validation.md), [strumenti](../scripts/README.md) |
| Consultare decisioni e lavoro futuro | [ADR](adr/README.md), [roadmap](roadmap.md), [piani](../PLANS.md) |

Le guide descrivono il comportamento implementato e i suoi limiti. Le nuove
integrazioni seguono la roadmap, con contratti versionati e verifiche esplicite.
