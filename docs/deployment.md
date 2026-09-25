# Deployment senza Neon

Il servizio online usa FastAPI e DuckDB incorporato; tutte le API v1/v2/v3,
metadati, verifiche e geometrie provengono dall'archivio. Non richiede URL,
credenziali o connessioni PostgreSQL. Il workflow PostgreSQL/PostGIS di
preparazione resta locale. [Decisione](adr/0017-duckdb-serving.md).

## Preparare l'archivio completo

Sul computer che contiene il database pubblicato, `ITADB_DATABASE_URL` deve
puntare al ruolo reader locale. Scegliere directory nuove per ogni esportazione:

```sh
uv run python scripts/run_logged.py --label "Export applicazione" --log .tools/serving-export.log -- uv run itadb export-serving --output data/state/serving-export/RELEASE --evidence data/state/serving-evidence/RELEASE
uv run itadb verify-serving --archive data/state/serving-export/RELEASE
uv run itadb install-serving --archive data/state/serving-export/RELEASE --activate
```

Sostituire `RELEASE` con un nome nuovo. Sono esportate tutte le release pubblicate,
non solo l'ultimo snapshot. La lettura PostgreSQL è una transazione ripetibile;
usa solo viste pubbliche. Le geometrie conservano semplificazione, precisione e
budget di vertici delle API precedenti. Nessuna estensione spaziale è necessaria online.

L’esportatore confronta i conteggi dichiarati da PostgreSQL e i fingerprint multinsieme di tutti i campi tra
CSV tipizzato e archivio, registra gli SHA-256 dei COPY e del file DuckDB e
verifica schema e conteggi alla chiusura. Il manifest della generazione e i
controlli scientifici originali restano invariati e consultabili. I fingerprint
servono a rilevare errori di trasferimento, non sono una firma crittografica della
fonte. SHA-256 rileva alterazioni rispetto al manifest fidato.

Il pacchetto distribuibile contiene solo `application.duckdb` e `manifest.json`.
I CSV intermedi, log e sorgenti restano offline e fuori Git. Un export fallito
conserva evidenze e file parziali, senza manifest pubblicabile né cambio di
`current`. Per ripeterlo scegliere nuove directory. Un retry di un export già
completo lo verifica e lo riusa; per includere nuovi dati scegliere una nuova release.

## Avvio locale

`ITADB_SERVING_DIR` indica la root, predefinita `data/serving`. L'installazione
produce `releases/SHA256/` e un collegamento `current` relativo alla root.

```sh
uv run itadb serve
# Oppure, dopo l'installazione dell'archivio:
docker compose up --build -d --wait
```

Compose avvia solo API e web; PostgreSQL e migrazioni sono nel profilo `offline`.
Il volume host è montato in sola lettura nell'API. Una nuova installazione senza
dati può usare esplicitamente `uv run itadb init-serving`: crea un catalogo vuoto,
non una popolazione dimostrativa. Un archivio mancante o corrotto produce 503,
non viene sostituito automaticamente con un catalogo vuoto.

## Backend su Railway

Il repository include `railway.json` e `infra/api.Dockerfile`. Configurare un
servizio dal repository e un volume montato a `/app/serving`. L'immagine ascolta
su `PORT`; il controllo di disponibilità è `/health/ready`. Il volume è disponibile
all'avvio, non durante build o pre-deploy; l'installazione dell'archivio va quindi
eseguita nel container avviato. [Documentazione Railway](https://docs.railway.com/volumes).

Variabili del servizio:

| Variabile | Valore iniziale |
|---|---|
| `ITADB_SERVING_BACKEND` | `duckdb` |
| `ITADB_SERVING_DIR` | `/app/serving` |
| `ITADB_CORS_ORIGINS` | Array JSON contenente l'origine HTTPS del frontend |
| `ITADB_DUCKDB_MEMORY_MB` | `256` |
| `ITADB_DUCKDB_THREADS` | `2` (usare `1` per un budget di una CPU) |
| `ITADB_SERVING_CONCURRENCY` | `4` |
| `ITADB_SERVING_TIMEOUT_SECONDS` | `5` |
| `ITADB_ROOT_PATH` | Vuoto con accesso diretto al dominio API; `/api` dietro un proxy che lo rimuove |

Un worker Uvicorn con più lettori simultanei è il default. Il limite memoria
DuckDB non è un limite dell'intero processo: Python, risposte geografiche e cache
hanno un costo aggiuntivo. Dimensionare il servizio sulle misure dell'app completa.
Il volume deve contenere almeno archivio attuale, precedente e spazio per la copia
in installazione; non copiare i CSV intermedi sul volume di produzione.

Prima del primo avvio pubblico caricare una directory `incoming/RELEASE` sul
volume con il pacchetto verificato, usando gli strumenti di trasferimento Railway.
Per inizializzare il volume si può usare temporaneamente il comando di avvio
`sh -c 'sleep infinity'` con il controllo di disponibilità disabilitato, senza dominio
pubblico; poi eseguire nel container:

```sh
itadb install-serving --archive /app/serving/incoming/RELEASE --activate
```

Il volume Railway nasce con proprietario root: predisporre permessi per UID/GID
10001 usati dall'immagine. Durante la preparazione si può usare `RAILWAY_RUN_UID=0`,
poi assegnare la root del volume a 10001 e rimuovere l'override per il serving.
Ripristinare il comando Dockerfile e il controllo `/health/ready`, quindi avviare.
Questa configurazione cloud è predisposta, ma non equivale a un deployment già
eseguito su un account Railway. [Healthcheck](https://docs.railway.com/deployments/healthchecks).

## Frontend statico

La web app non cambia contratto. Compilare `apps/web` con
`VITE_API_BASE_URL=https://DOMINIO-API`, `npm ci` e `npm run build`.
Pubblicare `apps/web/dist` sul servizio statico scelto. Non inserire credenziali nel
bundle. CORS deve includere il dominio effettivo del frontend. Nel Compose la
stessa app usa `/api`, inoltrato da Nginx al backend.

## Aggiornamento e ripristino

Installare e verificare la nuova directory prima di attivarla. `install-serving
--activate` e `activate-serving --release SHA256` aggiornano atomicamente il
collegamento `current`. Le release precedenti restano disponibili. Ogni processo
API mantiene la release selezionata all'avvio, anche se `current` cambia; riavviare
il servizio dopo l'attivazione. Tutte le query della stessa risposta leggono così
lo stesso archivio. Il riavvio con volume può comportare una breve indisponibilità.

Per il rollback, usare `activate-serving --release SHA256-PRECEDENTE` e riavviare.
Per un ripristino su un disco nuovo, ricopiare i due file da un backup esterno,
eseguire `verify-serving`, `install-serving --activate` e controllare API e mappa.
Conservare il manifest fidato insieme al backup. Una seconda directory sullo
stesso volume non è un backup esterno. Conservare anche gli originali offline per
ricostruire e verificare nuove release. Nessun comando cancella le release precedenti.

Prima di dismettere un eventuale servizio Neon, verificare il deployment completo
senza variabili PostgreSQL e provare un ripristino. Il codice di serving non ne
ha più bisogno; questa procedura non cancella automaticamente database o account.
