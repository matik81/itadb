# Ambiente di sviluppo Linux

La baseline è Linux, con Ubuntu e WSL2 come ambiente di riferimento. Tutti i
comandi si eseguono in Bash dalla root del clone. In WSL2 conservare clone,
virtualenv, dipendenze e dati nel filesystem Linux.

## Requisiti

| Strumento | Versione o requisito |
|---|---|
| Git | Disponibile nel PATH |
| Python | 3.13, versione fissata in `.python-version` e gestibile da uv |
| uv | 0.12.17, come nella CI e nel Dockerfile |
| Node.js | 24, versione fissata in `.node-version` |
| npm | Fornito con Node; installazione da `package-lock.json` |
| Docker | Engine raggiungibile e plugin Compose v2 o successivo |
| Bash | Shell per i comandi documentati |

Docker deve essere accessibile dall’utente della shell; in WSL2 abilitare
l’integrazione del motore con la distribuzione Ubuntu. PostgreSQL/PostGIS
sono forniti dal container: non occorre installarli sull’host. GitHub CLI
è facoltativa e non serve per build, test o avvio.

Verificare gli strumenti senza cambiare il sistema:

```sh
bash scripts/doctor.sh
```

## Primo avvio

Dopo il clone, dalla root:

```sh
cp -n .env.example .env
uv sync --locked
npm --prefix apps/web ci
docker compose up -d --build --wait
```

Il catalogo iniziale della popolazione è vuoto. Per popolarlo seguire il
[workflow della popolazione](population.md), quindi pubblicare lo snapshot
verificato con `uv run itadb publish-population --run PERCORSO`. Il comando
usa gli originali e i contratti in `ITADB_DATA_DIR`. Le fixture degli
aggregati inventati restano testabili via CLI/API v1 e non popolano la nuova web app.
Web: <http://localhost:8080>. API: <http://localhost:8080/api/docs>.
Le credenziali di esempio servono esclusivamente allo sviluppo locale.

Per lavorare sui processi applicativi nell’host, avviare solo il database:

```sh
docker compose up -d --wait db
docker compose run --rm migrate
uv run itadb serve
```

In un secondo terminale, dalla root, eseguire
`npm --prefix apps/web run dev` e aprire <http://localhost:5173>.
Se lo stack completo è già attivo, fermare prima i servizi applicativi con
`docker compose stop api web` per liberare la porta API.

La CLI Python legge `.env` nella root. Vite viene avviato in `apps/web` e usa
il backend locale sulla porta 8000 come default; per cambiarlo, impostare
`VITE_API_BASE_URL` nell’ambiente della shell o in `apps/web/.env.local`.
La build Compose usa `/api`, servito dal proxy sullo stesso host.

## Verifiche

I comandi completi per lint, tipi, test, OpenAPI e build sono nel
[README](../README.md#verifiche-di-sviluppo). Per una prima verifica:

```sh
uv run pytest -m 'not integration'
npm --prefix apps/web test
npm --prefix apps/web run build
```

## PostgreSQL dedicato ai test

Il file `compose.test.yaml` avvia un progetto Compose indipendente, con un
volume dedicato e PostgreSQL esposto solo su `127.0.0.1:55432`. Non include
API, frontend o dati dell’applicazione. Non usare gli URL applicativi nei test.

```sh
cp -n .env.test.example .env.test
set -a
source .env.test
set +a
docker compose --env-file .env.test -f compose.test.yaml up -d --wait
ITADB_ADMIN_DATABASE_URL="$ITADB_TEST_DATABASE_URL" \
  API_DB_PASSWORD="$ITADB_TEST_READER_PASSWORD" \
  uv run python scripts/migrate.py
uv run pytest -m integration
```

`.env.test` è locale e ignorato da Git. Le variabili esplicite amministrativa
e reader puntano allo stesso database di test; il ruolo amministrativo può
creare i database isolati usati dalla suite. Se la porta è occupata, cambiare
`ITADB_TEST_PORT` e la porta in entrambi gli URL in `.env.test`.
Le password negli URL devono essere percent-encoded; mantenere coerenti gli
URL e le password del container e del ruolo reader.

Il comando di migrazione si può ripetere. I test conservano i database creati
e il volume. Per fermare il server senza rimuoverli:

```sh
docker compose --env-file .env.test -f compose.test.yaml stop
```

## Certificati e rete

Le verifiche TLS restano abilitate. Se la rete richiede una CA aggiuntiva,
installare il certificato pubblico approvato nel trust store della distribuzione.
`UV_SYSTEM_CERTS=true` e `NODE_USE_SYSTEM_CA=1` consentono a uv e Node di usare
il trust store di sistema. Requests/pip-audit può richiedere `REQUESTS_CA_BUNDLE`;
Node supporta anche `NODE_EXTRA_CA_CERTS`. Configurare i percorsi del proprio
bundle nell’ambiente locale, senza versionare certificati o override della macchina.
Le build Docker usano un trust store separato e devono ricevere la CA approvata
se necessario. Non disabilitare TLS per aggirare errori di connessione.

## Dati e log

`.env`, `.env.test`, `.venv`, `node_modules`, `.tools` e gli archivi sotto `data/`
restano locali. Il filesystem `data/` e il volume Compose `evidence` sono distinti;
condividere esplicitamente gli originali quando si passa tra CLI host e pipeline
container. Non cancellare volumi o evidenze per ripetere una prova.

Per attività lunghe usare `uv run python scripts/run_logged.py --label "Fase" -- COMANDO`.
Il terminale mostra avanzamento, durata ed esito. Un secondo terminale può seguire
il log con `tail -n 30 -F .tools/task-progress.log`. Non includere credenziali o dati
personali nei comandi e nei log destinati alla condivisione.
