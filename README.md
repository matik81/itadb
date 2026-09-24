# Itadb

**Una popolazione sintetica italiana, interrogabile ed esplorabile, con evidenze e
assunzioni verificabili.**

Itadb integra statistiche territoriali per costruire individui e famiglie virtuali.
Ogni snapshot conserva input, algoritmo, seed e verifiche. Gli individui non
corrispondono a persone reali; le relazioni generate sono proprietà del modello.

## Il prodotto

La popolazione verificata viene caricata **integralmente in PostgreSQL** e
interrogata tramite API. La web app ha due parti:

- **Esplora:** mappa scura a schermo intero, selezione di regioni e comuni,
  filtri individuali, istogrammi, elenco paginato degli individui e navigazione
  delle famiglie e dei loro componenti.
- **Metodo e verifiche:** fonti con collegamenti agli originali, sequenza delle
  integrazioni, assunzioni, verifiche sui record del database e confronto tra
  conteggi di origine e conteggi sintetici, anche per singolo comune.

Il riferimento corrente contiene **58.943.464 individui e 26.670.169 famiglie**,
con riferimento demografico 1° gennaio 2025, in 7.896 comuni. Ordine del modello:
**sesso/età → geografia → cittadinanza → famiglie**. I conteggi osservati ammessi
sono conservati; l'incrocio età–singola cittadinanza e la composizione familiare
restano sintetici. La classe familiare 6+ usa 6 componenti; 560.159 adulti
restano senza assegnazione familiare. [Metodo e input](docs/population.md).

La localizzazione corrente è comunale. La mappa mostra punti rappresentativi
dei comuni, **non residenze individuali**. Coordinate di residenza e densità
locale saranno una successiva integrazione del modello e un nuovo snapshot.

## Architettura

```mermaid
flowchart LR
  S[Fonti ISTAT / altre fonti] --> R[Originali e contratti versionati]
  R --> G[Generazione locale e verifica indipendente]
  G --> P[Snapshot Parquet immutabile]
  P --> I[Importazione e verifica nel DB]
  I --> D[(PostgreSQL / PostGIS)]
  D --> A[API popolazione v3]
  A --> W[Web: Esplora / Metodo e verifiche]
  A -. futuro .-> M[App mobile]
```

La generazione è un workflow CLI documentato nel repository. L'applicazione
serve solo snapshot pubblicati e non avvia generazioni durante le richieste.
API e frontend non hanno bisogno dell'archivio locale degli originali.
PostgreSQL conserva i record completi; Parquet conserva la riproduzione del run.

| Componente | Tecnologia |
|---|---|
| Database | PostgreSQL 17 + PostGIS 3.5; record tipizzati, partizioni per snapshot |
| Backend | Python 3.13, FastAPI, Pydantic, Psycopg pool, OpenAPI |
| Workflow | Python, DuckDB, Parquet/Zstandard, CLI Typer |
| Frontend | React, TypeScript, Vite; mappa vettoriale SVG/Canvas |
| Verifiche | pytest, Ruff, mypy, Vitest, test PostgreSQL reali |

La destinazione prevista è un'infrastruttura gestita (ad esempio Vercel,
Neon, Railway, Cloudflare). Il provider e il deployment sono passi successivi:
frontend statico, API stateless e PostgreSQL accessibile tramite URL sono già
confini separati. [Decisione di prodotto](docs/adr/0015-population-product.md).

## Avvio locale

Ambiente supportato: Linux, con Ubuntu/WSL2 come riferimento. Vedi la
[guida locale](docs/local-environment.md).

Per database creati con le revisioni precedenti al consolidamento, seguire
prima il [passaggio alla baseline](docs/operations.md#baseline-consolidata).

Avvio con Docker Compose:

```sh
cp -n .env.example .env
docker compose up --build -d --wait
```

- Web app: <http://localhost:8080>
- Snapshot disponibili: <http://localhost:8080/api/v3/populations>
- Swagger: <http://localhost:8080/api/docs>
- Contratto: [OpenAPI versionata](docs/api/openapi.json)

Finché non è stato pubblicato uno snapshot, l'applicazione mostra un catalogo
vuoto. Non sostituisce dati assenti o errori con una popolazione dimostrativa.

Per sviluppo senza container applicativi:

```sh
uv sync --locked
uv run itadb serve
# In un secondo terminale:
npm --prefix apps/web ci
npm --prefix apps/web run dev
```

## Generazione e pubblicazione

La [procedura completa](docs/population.md) acquisisce gli input, esegue
`synthesize-population` e verifica con `verify-population`. Per uno snapshot
completato, usando il percorso del run effettivo:

```sh
uv run python scripts/run_logged.py --label "Pubblicazione popolazione" --log .tools/population-publication.log -- uv run itadb publish-population --run data/curated/population/RUN_ID
```

L'importatore ripete l'audit, verifica provenienza e geografia, carica famiglie
e individui con COPY, confronta le distribuzioni PostgreSQL con i vincoli e
pubblica atomicamente. Errori producono rollback e rapporto di quarantena.
Un retry identico riusa lo snapshot pubblicato. Le evidenze precedenti non
vengono sovrascritte. [Operazioni e misure](docs/operations.md).

## Verifiche di sviluppo

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

I test di integrazione richiedono un server PostgreSQL/PostGIS **dedicato ai
test**, migrato e con ruolo reader. Impostare `ITADB_TEST_DATABASE_URL` e
`ITADB_TEST_READER_URL` dello stesso database, quindi `uv run pytest -m integration`.
Alcuni test creano database `itadb_m1_test_*`: il ruolo deve poterli creare.
Non usare il server applicativo. [Procedura](docs/local-environment.md#postgresql-dedicato-ai-test).

## Struttura e storia

```text
src/itadb/connectors/    acquisizione limitata delle fonti
src/itadb/synthesis/     generazione e audit riproducibili
src/itadb/population/    pubblicazione degli snapshot nel database
src/itadb/api/           API della popolazione e delle evidenze
apps/web/               mappa, esplorazione, metodo e verifiche
contracts/              contratti versionati di input e modello
migrations/             baseline PostgreSQL/PostGIS e successive revisioni immutabili
src/itadb/pipeline/      archivio e pipeline storiche degli aggregati
```

Le tappe M0–M2 hanno costruito l'archivio delle evidenze e le API v1/v2 degli
aggregati; restano compatibili e conservate. M3 è il pilota della Valle d'Aosta;
M4 e l'arricchimento di cittadinanza sono riferimenti storici riproducibili.
Il prodotto corrente usa `population-reference/1` e le API v3.

- [Architettura](docs/architecture.md), [modello dati](docs/data-model.md), [API](docs/api/README.md)
- [Popolazione e workflow](docs/population.md), [priorità di fedeltà](docs/model-fidelity.md)
- [Roadmap](docs/roadmap.md), [verifiche](docs/validation.md), [decisioni](docs/adr/README.md)
- [Contribuire](CONTRIBUTING.md), [governance](GOVERNANCE.md), [sicurezza](SECURITY.md)

Codice Apache-2.0; fixture inventate CC0-1.0. Le fonti mantengono la propria
licenza, registrata nella provenienza di ogni snapshot. Nessun dump o record
individuale viene inserito nel repository Git.
