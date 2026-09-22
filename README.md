# Itadb

**Una base statistica aperta, interrogabile e verificabile della società italiana.**

Itadb mira a costruire una popolazione sintetica 1:1: individui e famiglie virtuali,
coerenti con evidenze demografiche, sociali ed economiche. Gli agenti non saranno
persone reali. Questo repository parte dal fondamento: dati territoriali aggregati,
provenienza esplicita e passaggi di elaborazione riproducibili.

## Stato: scaffold eseguibile, versione 0.1

Il percorso dimostrativo importa tre territori **fittizi**, archivia il file originale,
produce Parquet e verifiche, pubblica una versione immutabile in PostgreSQL e la espone
via API e web app. Non contiene statistiche italiane ufficiali, microdati o un generatore
di popolazione sintetica. I connettori ISTAT/Eurostat acquisiscono risposte SDMX-CSV;
la mappatura di un dataset reale richiede un contratto e la revisione delle sue dimensioni.

## Stack e motivazione

| Livello | Scelta | Responsabilità |
|---|---|---|
| Database di servizio | PostgreSQL 17 + PostGIS 3.5 | Catalogo, versioni, territori, osservazioni e API concorrenti |
| Archivio analitico | Parquet/Zstandard + DuckDB | Elaborazioni colonnari, dati originali immutabili, esportazioni |
| Pipeline | Python 3.13, uv, Psycopg COPY | Contratti, acquisizione, quality gate e pubblicazione atomica |
| Backend | FastAPI, Pydantic, Psycopg pool | API REST pubbliche, OpenAPI 3.1, limiti di query |
| Frontend | React 19, TypeScript, Vite, Node 24 | Esplorazione delle versioni e della provenienza |
| Qualità | pytest, Ruff, mypy, Vitest, GitHub Actions | Test, contratti API, migrazioni e verifiche di dipendenze |
| Sviluppo | Docker Compose | Database, migrazioni, API, frontend e proxy con rate limit |

È un monolite modulare con processi separati per API e importazione. Non servono Kafka,
Kubernetes, un cluster distribuito o un database a grafo per dimostrare la prima fase.
L'architettura prevede l'evoluzione a object storage S3 e worker di batch senza vincolare
oggi il progetto a un cloud. [Decisioni e capacità](docs/architecture.md).

## Avvio con Docker Compose

Requisiti: Git e Docker Engine/Desktop con Compose v2. I comandi non installano software
di sistema. Da PowerShell usare `Copy-Item .env.example .env`; da Linux `cp .env.example .env`.

```sh
docker compose up --build -d
docker compose run --rm pipeline itadb ingest-demo
```

- Web app: <http://localhost:8080>
- API tramite proxy: <http://localhost:8080/api/v1/sources>
- Swagger: <http://localhost:8080/api/docs> · ReDoc: <http://localhost:8080/api/redoc>
- OpenAPI versionata: [docs/api/openapi.json](docs/api/openapi.json)

Le porte sono associate solo a `127.0.0.1`. Le password in `.env.example` sono esclusivamente
per sviluppo locale. Non esporre questo Compose direttamente a Internet.
Il servizio `migrate` termina dopo migrazioni e creazione del ruolo di sola lettura.

## Sviluppo senza container applicativi

Avvia il solo database e le migrazioni con `docker compose up -d db` e
`docker compose run --rm migrate`. Installa uv e Node 24, poi:

```sh
uv sync --locked
uv run itadb ingest-demo
uv run itadb serve
# In un secondo terminale:
npm --prefix apps/web ci
npm --prefix apps/web run dev
```

Su questa macchina PowerShell blocca `npm.ps1`: usare `npm.cmd`. In presenza delle CA
aziendali usare `NODE_USE_SYSTEM_CA=1` e `uv --system-certs`; non disattivare TLS.
[Audit locale e installazioni](docs/local-environment.md).

## Verifiche

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -m "not integration"
uv run itadb export-openapi
npm --prefix apps/web run api:types
npm --prefix apps/web run typecheck
npm --prefix apps/web run format:check
npm --prefix apps/web test
npm --prefix apps/web run build
```

I test di integrazione richiedono un database **dedicato e sacrificabile**, migrato e con
ruolo reader configurato. Impostare `ITADB_TEST_DATABASE_URL` all'URL amministrativo del
database di test e `ITADB_TEST_READER_URL` al ruolo reader dello stesso database, poi
`uv run pytest -m integration`. La CI li esegue su un servizio PostGIS isolato.

## Struttura

```text
apps/web/                 web app e tipi generati dall'OpenAPI
src/itadb/api/            API pubbliche di sola lettura
src/itadb/connectors/     interfacce e acquisizione ISTAT/Eurostat
src/itadb/pipeline/       archivio, trasformazioni, verifiche, pubblicazione
migrations/              DDL PostgreSQL/PostGIS versionato con Alembic
contracts/               contratti di dati versionati
infra/                   container e proxy
scripts/                 ruoli DB, audit locale e benchmark
tests/                   unit, contratti e integrazione
docs/                    architettura, API, fonti, operazioni e roadmap
AGENTS.md                 istruzioni principali per Codex
```

## Documentazione

- [Architettura e dimensionamento](docs/architecture.md), [modello dati](docs/data-model.md)
- [Fonti e protocollo di onboarding](docs/sources.md), [quality gate](docs/data-quality.md)
- [Uso delle API](docs/api/README.md), [esercizio e sicurezza](docs/operations.md)
- [Roadmap verificabile](docs/roadmap.md), [decisioni architetturali](docs/adr/README.md)
- [Contribuire](CONTRIBUTING.md), [governance](GOVERNANCE.md), [sicurezza](SECURITY.md)
- [Lavorare con Codex](docs/codex.md), [verifiche dello scaffold](docs/validation.md)

## Licenze

Il codice è Apache-2.0: [LICENSE](LICENSE). Le fixture inventate in `tests/fixtures/`
sono rilasciate in CC0-1.0. I dati di terzi conservano le proprie licenze, registrate
per versione; la licenza del codice non concede diritti sui dati acquisiti.
