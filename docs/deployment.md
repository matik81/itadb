# Deployment su Vercel e Railway

Il frontend statico va su **Vercel**; **Railway** esegue FastAPI e legge il file
DuckDB da un volume persistente. Il repository contiene `apps/web/vercel.json`,
`railway.json` e `infra/api.Dockerfile`. [Verifiche effettive](validation.md).

## Pacchetto dei dati

Dopo la pubblicazione locale, scegliere directory nuove:

```sh
uv run itadb export-serving --output data/state/export/RELEASE --evidence data/state/export-evidence/RELEASE
uv run itadb verify-serving --archive data/state/export/RELEASE
```

Il pacchetto contiene `application.duckdb` e `manifest.json`, con tutte le release,
metadati, verifiche e geometrie. L'export verifica checksum, schema e conteggi;
un retry verifica e riusa lo stesso pacchetto. Per includere nuovi dati scegliere
un nome nuovo. Originali e Parquet restano sul computer di preparazione.

## Backend Railway

Creare un servizio dal repository, con root del repository e configurazione
`railway.json`. L'immagine ascolta su `PORT` con un worker. Montare un volume
persistente a `/app/serving`; mantenere una sola replica.

| Variabile | Valore |
|---|---|
| `ITADB_SERVING_DIR` | `/app/serving` |
| `ITADB_CORS_ORIGINS` | `["https://DOMINIO-FRONTEND"]` |
| `ITADB_DUCKDB_MEMORY_MB` | `256` iniziali |
| `ITADB_DUCKDB_THREADS` | `1` per un budget di una CPU |
| `ITADB_SERVING_CONCURRENCY` | `4` |
| `ITADB_SERVING_TIMEOUT_SECONDS` | `5` |
| `ITADB_ROOT_PATH` | Vuoto, per l'accesso diretto al dominio API |

Il volume va dimensionato per archivio attuale, precedente e copia di installazione:
prevedere almeno tre volte la dimensione del pacchetto, oltre a spazio libero.
Il limite DuckDB non è il limite RAM dell'intero processo.
Per il primo deployment assegnare almeno 1 GiB al container: la prova locale con
512 MiB è passata ma ha raggiunto il limite. È un margine iniziale da verificare
con le mappe e il carico effettivo, non una garanzia di capacità.

Il volume è disponibile **all'avvio**, non nella build o nel pre-deploy.
La preparazione iniziale richiede un container avviato con il volume montato.
[Volumi Railway](https://docs.railway.com/volumes).

Per il primo caricamento usare temporaneamente `sleep infinity` come comando di
avvio e rimuovere `deploy.healthcheckPath` dalla configurazione usata per quel
deployment. Non assegnare ancora un dominio pubblico. Collegarsi con Railway SSH
e trasferire i due file in `/app/serving/incoming/RELEASE`, per esempio scaricandoli
con Python da URL HTTPS temporanei di un archivio fidato. Conservare separatamente
il checksum del manifest originale e confrontarlo prima dell'installazione.
Non inserire URL firmati o credenziali nel repository o nei log.

Il volume nasce con proprietario root. Per la sola preparazione impostare
`RAILWAY_RUN_UID=0`, poi eseguire nel container:

```sh
itadb verify-serving --archive /app/serving/incoming/RELEASE
itadb install-serving --archive /app/serving/incoming/RELEASE --activate
chown -R 10001:10001 /app/serving
```

Rimuovere l'override UID, ripristinare il comando del Dockerfile e la configurazione
`railway.json` con `/health/ready`, quindi ridistribuire. L'API rifiuta di diventare
pronta se il volume è vuoto o corrotto. Il controllo di avvio Railway non sostituisce
il monitoraggio continuativo. [Healthcheck Railway](https://docs.railway.com/deployments/healthchecks).

## Frontend Vercel

Importare lo stesso repository con:

| Impostazione | Valore |
|---|---|
| Root Directory | `apps/web` |
| Framework | Vite |
| Node.js | 24.x |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| `VITE_API_BASE_URL` | `https://DOMINIO-API-RAILWAY`, senza `/api` |

`vercel.json` fissa installazione e build. L'URL API viene incluso nel bundle:
configurarlo prima della build sia per Production sia per Preview. La build Vercel
si ferma se manca un URL HTTPS, evitando di pubblicare un client rivolto a localhost.
Non inserire segreti nelle variabili `VITE_*`.
[Vite su Vercel](https://vercel.com/docs/frameworks/frontend/vite),
[Node.js supportati](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions).

Impostare in Railway l'origine esatta del frontend, senza percorso o slash finale.
Per le preview aggiungere esplicitamente le origini autorizzate. Il Compose locale
usa invece `/api`, inoltrato da Nginx sullo stesso dominio.

## Verifica del rilascio

Verificare `/health/ready`, `/v3/populations`, una mappa, una pagina individuale e
una famiglia; controllare anche i cataloghi v1/v2. Dal browser Vercel verificare
richieste HTTPS e CORS, filtri, paginazione e Metodo. Misurare memoria e latenza
sul provider con il carico atteso. Conservare un backup esterno e provarne il ripristino.

Questi passaggi richiedono i progetti e i domini effettivi: la configurazione e
le prove locali non equivalgono a un deployment cloud già eseguito.

## Aggiornamento e rollback

Installare una nuova directory verificata con `install-serving --activate` e
riavviare l'API. Ogni processo mantiene la release selezionata all'avvio.
L'aggiornamento con volume può comportare una breve indisponibilità.

Per il rollback: `itadb activate-serving --release SHA256-PRECEDENTE` e riavvio.
Per un ripristino su un volume nuovo, ricopiare database e manifest dal backup,
verificare, installare e attivare. Non cancellare le release necessarie al rollback.
Una seconda directory sullo stesso volume non è un backup esterno.
