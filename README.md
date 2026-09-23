# Itadb

**Una base statistica aperta, interrogabile e verificabile della società italiana.**

Itadb mira a costruire una popolazione sintetica 1:1: individui e famiglie virtuali,
coerenti con evidenze demografiche, sociali ed economiche. Gli agenti non saranno
persone reali. Questo repository parte dal fondamento: dati territoriali aggregati,
provenienza esplicita e passaggi di elaborazione riproducibili.

## Stato: evidenze M2 e sintesi pilota locale M3, versione 0.1

Il percorso dimostrativo importa tre territori **fittizi**, archivia il file originale,
produce Parquet e verifiche, pubblica una versione immutabile in PostgreSQL e la espone
via API e web app. La web app distingue la demo dai dati ufficiali; non contiene
microdati o un generatore di popolazione sintetica. I connettori ISTAT/Eurostat acquisiscono risposte
SDMX-CSV e metadati strutturali.

Il [primo onboarding ISTAT](docs/sources/istat-population.md) verifica un campione ufficiale
di popolazione al 1° gennaio 2024: 20 regioni e totale Italia, contratto versionato,
DSD/codelist archiviate e riconciliazione esatta. `itadb check-istat-population` ripete
offline i controlli e produce evidenze locali. `itadb ingest-istat-population` pubblica
una release immutabile con Parquet, metadati e licenza; le API v2 e la web app la espongono.
Le revisioni richiedono predecessore e motivazione. Il perimetro territoriale è uno
snapshot alla data verificata, non una ricostruzione storica dei confini.

[M2](docs/sources/istat-m2.md) aggiunge 22.678 osservazioni ufficiali: popolazione
per sesso/età, famiglie e abitazioni, con 24.091 versioni territoriali nei tre
snapshot 2020, 2021 e 2024. Include otto eventi amministrativi, crosswalk,
confini verificati e derivazioni documentate. La web app seleziona periodo,
indicatore e livello senza sommare categorie sovrapposte. `fetch-m2`, `check-m2`
e `ingest-m2` acquisiscono, verificano offline e pubblicano il perimetro revisionato.
Il nome di una regione, provincia o comune apre una scheda con mappa del confine,
dato selezionato, periodo, fonte e licenza. La mappa permette zoom e spostamento;
il GeoJSON si scarica da un collegamento esplicito. Chiudere la scheda conserva
filtri e pagina della tabella.
Le tabelle offrono ordinamento crescente/decrescente sull'intera selezione,
ricerca nome/codice e filtri per territorio padre e stato del dato; lo storico
filtra tipo di variazione e utilizzo. Icone accanto ai nomi distinguono regioni,
province e comuni; nelle schede identificano persone, famiglie e abitazioni.

[M3](docs/synthesis-m3.md) aggiunge un pilota locale della Valle d'Aosta:
123.360 persone virtuali per replica e 60.468 famiglie. Il riferimento unico
adottato usa **6 componenti per la classe 6+ e seed 1701**; cinque seed e tre
dimensioni restano prove di sensibilità. `fetch-m3`, `synthesize-m3` e `verify-m3`
gestiscono input ISTAT fissati, Parquet immutabili, controlli indipendenti,
calibrazione esatta delle 202 celle sesso/età e sensibilità familiare. Il rapporto
dichiara l'assenza di validazione fuori calibrazione, residuo non assegnato e
limiti. I record sintetici non sono dati osservati e
non vengono pubblicati nelle API o nella web app. Revisione scientifica
esterna e valutazione disclosure restano necessarie per distribuirli.

La [revisione umana di progetto](docs/reviews/m3-human-review.md) accetta M3
come prima versione e consente l'avvio di [M4](docs/plans/m4-national-synthesis.md).
La [graduatoria di fedeltà](docs/model-fidelity.md) privilegia **età/sesso,
geografia, composizione familiare**, in quest'ordine, ed evolve con il progetto.
In M3 la composizione familiare casuale vincolata è accettata; l'assegnazione
provinciale/comunale e la scala nazionale restano da implementare in M4.

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
- Catalogo v2 (demo e dataset ufficiali importati): <http://localhost:8080/api/v2/releases>
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
I test M1 creano database dedicati `itadb_m1_test_*` nello stesso server di test:
il ruolo amministrativo deve poter creare database. Non puntarli al server applicativo.
Database e volumi non vengono cancellati automaticamente.

## Struttura

```text
apps/web/                 web app e tipi generati dall'OpenAPI
src/itadb/api/            API pubbliche di sola lettura
src/itadb/connectors/     interfacce e acquisizione ISTAT/Eurostat
src/itadb/pipeline/       archivio, trasformazioni, verifiche, pubblicazione
src/itadb/synthesis/      pilota sintetico locale e verifica indipendente
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
- [Priorità di fedeltà](docs/model-fidelity.md), [revisione M3](docs/reviews/m3-human-review.md), [piano M4](docs/plans/m4-national-synthesis.md)
- [Contribuire](CONTRIBUTING.md), [governance](GOVERNANCE.md), [sicurezza](SECURITY.md)
- [Lavorare con Codex](docs/codex.md), [registro delle verifiche](docs/validation.md)

## Licenze

Il codice è Apache-2.0: [LICENSE](LICENSE). Le fixture inventate in `tests/fixtures/`
sono rilasciate in CC0-1.0. I dati di terzi conservano le proprie licenze, registrate
per versione; la licenza del codice non concede diritti sui dati acquisiti.
