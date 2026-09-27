# Deployment su Vercel e Railway

Il frontend statico va su **Vercel**; **Railway** esegue FastAPI e legge il file
DuckDB da un volume persistente. Il repository contiene `apps/web/vercel.json`,
`.railway/railway.ts` e `infra/api.Dockerfile`. [Verifiche effettive](validation.md).

## CLI e accesso

Usare Bash su Linux/Ubuntu/WSL2, con Node.js 24 e npm nel `PATH`.
Installare gli strumenti globalmente, fuori dalle dipendenze del progetto:

```sh
npm install -g @railway/cli vercel
railway --version
vercel --version
```

Se i comandi non vengono trovati, aggiungere la directory `bin` del prefisso
restituito da `npm prefix -g` al `PATH` della shell. Se npm segnala script di
installazione bloccati, autorizzare solo quelli necessari indicati nell'avviso;
con npm 11.17, per le versioni verificate:

```sh
npm rebuild -g @railway/cli --allow-scripts=@railway/cli
npm rebuild -g esbuild --allow-scripts=esbuild
```

Accedere dal browser tramite il link temporaneo mostrato da ciascuna CLI:

```sh
railway login --browserless
vercel login
railway whoami
vercel whoami
railway list
vercel project ls --scope VERCEL_SCOPE
```

`VERCEL_SCOPE`, `VERCEL_PROJECT`, `RAILWAY_PROJECT_ID`, `RAILWAY_SERVICE`,
`RAILWAY_ENVIRONMENT`, `RELEASE` e i domini `DOMINIO-*` sono segnaposto:
sostituirli localmente. I nomi delle variabili di configurazione restano invariati.
Se la sessione è già valida, bastano i
controlli di identità e accesso. Non conservare in Git output di login, identità,
email, codici temporanei, token o configurazioni locali delle CLI. La directory
`.vercel/` contiene il collegamento locale ed è esclusa da Git.
[CLI Railway](https://docs.railway.com/cli), [CLI Vercel](https://vercel.com/docs/cli).

Il 25 settembre 2026 sono state verificate Railway CLI **5.62.1** e Vercel CLI
**60.0.1**. Lo stato dei deployment e dei collegamenti GitHub è registrato nelle
[verifiche](validation.md#prontezza-al-deployment).

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

Creare un progetto dedicato a Itadb e un servizio API inizialmente vuoto, dalla
root del clone. Prima controllare `railway list`: se esistono già, collegarli
senza ricrearli.

```sh
railway init --name itadb --workspace RAILWAY_WORKSPACE_ID --json
railway add --service api --json
```

Per collegare risorse esistenti:

```sh
railway link --project RAILWAY_PROJECT_ID --environment RAILWAY_ENVIRONMENT --service RAILWAY_SERVICE
railway status
```

Verificare progetto, servizio e ambiente prima di distribuire. L'immagine ascolta
su `PORT` con un worker. Montare un volume persistente a `/app/serving` e mantenere
una sola replica.

Per un nuovo servizio applicare questi valori tramite CLI/API:

| Impostazione | Valore |
|---|---|
| Root Directory | Root del repository |
| Dockerfile | `infra/api.Dockerfile`, tramite `RAILWAY_DOCKERFILE_PATH` |
| Start Command | `uvicorn itadb.api.app:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log` |
| Healthcheck Path | `/health/ready`, dopo l'installazione dei dati |
| Healthcheck Timeout | `300` secondi |
| Restart Policy | `ON_FAILURE`, massimo `3` retry |
| Repliche | `1` |

La configurazione corrente è in [`.railway/railway.ts`](../.railway/railway.ts),
con SDK isolato e lockfile; il file legacy `railway.json` è stato rimosso.
Vedere la [decisione tecnica](adr-railway-iac.md). Sul progetto già collegato:

```sh
npm --prefix .railway ci --ignore-scripts
export ITADB_GITHUB_REPOSITORY=GITHUB_OWNER/GITHUB_REPOSITORY
railway config plan
railway config apply --yes
railway config plan --detailed-exit-code
```

Impostare il repository effettivo solo nell'ambiente locale. Il piano deve
mantenere API, volume e GitHub: non applicare cancellazioni o cambi regione.
Il partial `itadb` conserva i valori CORS e il dominio generato del provider.
`ON_FAILURE` e `sleepApplication=false` sono default Railway: nella CLI 5.62.1
sono omessi dall'importazione e dichiararli esplicitamente provoca un diff
permanente. Verificarli anche tramite `serviceInstance` della GraphQL API.
I piani possono contenere identificativi: conservarli solo in `.tools/`.

Il codice viene distribuito automaticamente da GitHub; modificare il file IaC
richiede invece `plan` e `apply` dalla CLI autenticata. Non sono memorizzati token
Railway in GitHub Actions.
[Migrazione Railway](https://docs.railway.com/infrastructure-as-code#migrating-from-config-as-code),
[Dockerfile personalizzato](https://docs.railway.com/builds/dockerfiles).

| Variabile | Valore |
|---|---|
| `RAILWAY_DOCKERFILE_PATH` | `infra/api.Dockerfile` |
| `PORT` | `8000` |
| `ITADB_SERVING_DIR` | `/app/serving` |
| `ITADB_CORS_ORIGINS` | `["https://DOMINIO-FRONTEND"]` |
| `ITADB_DUCKDB_MEMORY_MB` | `256` iniziali |
| `ITADB_DUCKDB_THREADS` | `1` per un budget di una CPU |
| `ITADB_SERVING_CONCURRENCY` | `4` |
| `ITADB_SERVING_TIMEOUT_SECONDS` | `5` |
| `ITADB_ROOT_PATH` | Vuoto, per l'accesso diretto al dominio API |

`railway variable set --service api --skip-deploys KEY=VALUE` imposta le
variabili prima del primo avvio. Per esempio:

```sh
railway variable set --service api --skip-deploys RAILWAY_DOCKERFILE_PATH=infra/api.Dockerfile ITADB_SERVING_DIR=/app/serving PORT=8000 ITADB_DUCKDB_MEMORY_MB=256 ITADB_DUCKDB_THREADS=1 ITADB_SERVING_CONCURRENCY=4 ITADB_SERVING_TIMEOUT_SECONDS=5
```

Le impostazioni del servizio sono accessibili con `railway api`. Consultare
`railway api describe ServiceInstanceUpdateInput` e usare `serviceInstanceUpdate`
con gli ID del servizio e dell'ambiente; `serviceInstanceLimitsUpdate` imposta
`memoryGB: 1` e `vCPUs: 1`. Per la regione usare `multiRegionConfig` con una sola
replica, passando l'oggetto JSON tramite `--variables`; il solo campo `region`
non ha aggiornato la regione effettiva nella prova eseguita.

Creare il volume con `volumeCreate`, specificando `projectId`, `serviceId`,
`environmentId`, `mountPath: "/app/serving"` e la stessa regione del servizio.
Questo è il percorso verificato con la CLI 5.62.1: `railway volume add` ha
restituito un errore interno. `railway volume list --json` verifica il risultato.

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
avvio e disattivare il healthcheck; per un servizio legacy rimuovere
anche `deploy.healthcheckPath` dalla configurazione usata per quel deployment.
Non assegnare ancora un dominio pubblico. Il volume nasce con proprietario root:
per la sola preparazione impostare `RAILWAY_RUN_UID=0`, quindi distribuire dalla
root del clone, seguendo e conservando il log:

```sh
uv run python scripts/run_logged.py --label "Deployment API" --log .tools/deploy-api-bootstrap.log -- railway up --service RAILWAY_SERVICE --environment RAILWAY_ENVIRONMENT
railway ssh --service RAILWAY_SERVICE --environment RAILWAY_ENVIRONMENT
```

Per SSH, se manca una chiave locale, generarne una dedicata con `ssh-keygen` e
registrare soltanto quella pubblica con
`railway ssh keys add --key PUBLIC_KEY_PATH --name itadb-deployment`.
La chiave privata resta fuori dal repository; `railway ssh -i PRIVATE_KEY_PATH`
permette di selezionarla esplicitamente.

Trasferire il pacchetto in una nuova directory del volume. Nei comandi
`volume files` i percorsi sono relativi alla radice del volume, quindi
`/incoming/RELEASE` corrisponde a `/app/serving/incoming/RELEASE` nel container:

```sh
uv run python scripts/run_logged.py --label "Upload dati" --log .tools/deploy-data-upload.log -- railway volume --service api files --volume RAILWAY_VOLUME_ID upload data/state/export/RELEASE /incoming/RELEASE --json
```

Non usare `--overwrite`. Conservare separatamente il checksum del manifest
originale e confrontarlo nel container prima dell'installazione.

Eseguire nel container raggiunto tramite SSH:

```sh
itadb verify-serving --archive /app/serving/incoming/RELEASE
itadb install-serving --archive /app/serving/incoming/RELEASE --activate
chown -R 10001:10001 /app/serving
```

Rimuovere l'override UID con `railway variable delete RAILWAY_RUN_UID --service api`.
Impostare tramite `serviceInstanceUpdate` il comando Uvicorn della tabella e il
healthcheck `/health/ready`, con timeout 300 secondi. Nel test, `startCommand: null`
non ha eliminato `sleep infinity`: verificare sempre il valore remoto effettivo.
Uscire dalla sessione SSH e ridistribuire dalla root locale:

```sh
uv run python scripts/run_logged.py --label "Deployment API" --log .tools/deploy-api.log -- railway redeploy --service RAILWAY_SERVICE --environment RAILWAY_ENVIRONMENT --from-source --yes --json
railway logs --service RAILWAY_SERVICE --environment RAILWAY_ENVIRONMENT --lines 100
```

`--from-source` usa GitHub e le impostazioni aggiornate; un semplice `redeploy`
può riutilizzare la configurazione del deployment precedente. Il codice zero
conferma l'avvio dell'operazione, non la readiness: controllare lo stato con
`railway deployment list --json` e i log.

L'API rifiuta di diventare pronta se il volume è vuoto o corrotto. Quando il
deployment è pronto, assegnare un dominio con `railway domain --service api --port 8000`
e verificare `https://DOMINIO-API-RAILWAY/health/ready`. Usare questo dominio nella
configurazione del frontend. Il controllo di avvio Railway non sostituisce il
monitoraggio continuativo. [Healthcheck Railway](https://docs.railway.com/deployments/healthchecks).

## Frontend Vercel

Creare e configurare un progetto dedicato al frontend, oppure selezionare quello
Itadb già predisposto:

```sh
vercel project add itadb --scope VERCEL_SCOPE
vercel project update itadb --scope VERCEL_SCOPE --framework vite --root-directory apps/web --node-version 24.x --install-command 'npm ci' --build-command 'npm run build' --output-directory dist --yes
```

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

Per operare tramite CLI, eseguire i comandi dalla **root del repository**, con
Root Directory del progetto Vercel impostata a `apps/web`. Non combinare questa
impostazione con `--cwd apps/web`, che cambierebbe la radice dei file inviati.
[Monorepo Vercel](https://vercel.com/docs/monorepos),
[Collegamento CLI](https://vercel.com/docs/cli/link).

Il file `.vercelignore` nella root ammette soltanto il frontend ed esclude
dipendenze, build, file ambiente e dati locali. La CLI non usa `.gitignore` come
elenco di esclusione dell'upload. Prima di ogni invio locale controllare:

```sh
vercel deploy --dry --scope VERCEL_SCOPE
```

La verifica iniziale con il filtro ha elencato **37 file, 358.029 byte**. Fermarsi
se compaiono `data/`, `.tools/`, `.env*` o dimensioni incompatibili con il frontend.
[Esclusioni Vercel](https://vercel.com/docs/deployments/vercel-ignore).

```sh
vercel link --project VERCEL_PROJECT --scope VERCEL_SCOPE
vercel env add VITE_API_BASE_URL production --scope VERCEL_SCOPE
vercel env add VITE_API_BASE_URL preview --scope VERCEL_SCOPE
```

Inserire l'URL HTTPS del backend ai prompt. Se la variabile esiste già, aggiornarla
nel dashboard. Dopo che il backend risponde e CORS è configurato, creare una preview:

```sh
uv run python scripts/run_logged.py --label "Preview web" --log .tools/deploy-web-preview.log -- vercel deploy --scope VERCEL_SCOPE --logs
```

Autorizzare in CORS l'origine esatta della preview e verificarla dal browser.
Per pubblicare in produzione, dopo le verifiche:

```sh
uv run python scripts/run_logged.py --label "Deployment web" --log .tools/deploy-web-production.log -- vercel deploy --prod --scope VERCEL_SCOPE --logs
```

Una modifica a `VITE_API_BASE_URL` richiede una nuova build. I log restano locali
in `.tools/`; prima di condividerli rimuovere identità, credenziali e dati personali.

## Aggiornamenti automatici da GitHub

Entrambi i progetti devono usare il repository del clone. Collegare Railway dopo
aver impostato il servizio: il collegamento può avviare subito una build.

```sh
railway service source connect --service api --repo GITHUB_OWNER/GITHUB_REPOSITORY --branch main --json
vercel git connect https://github.com/GITHUB_OWNER/GITHUB_REPOSITORY.git --scope VERCEL_SCOPE --yes
```

Le GitHub App dei provider devono avere accesso al repository. Se Vercel risponde
`Install GitHub App`, autorizzare il repository nell'app ufficiale
[Vercel per GitHub](https://github.com/apps/vercel), poi ripetere il collegamento.
Il login alla CLI da solo non concede questo accesso.

Per Railway verificare `service.repoTriggers`: branch `main` e `checkSuites: true`
abilitano l'attesa dei controlli GitHub. L'opzione si imposta tramite
`deploymentTriggerUpdate`. Per Vercel verificare il collegamento Git e il branch
di produzione `main`; gli altri branch possono produrre preview, le cui origini
CORS vanno autorizzate esplicitamente.

Vercel deve attendere i quattro job GitHub prima di assegnare il dominio di
produzione: `Python and contracts`, `DuckDB publication`, `Web app`, `Compose smoke`.
Le specifiche sono in [`infra/vercel-checks.json`](../infra/vercel-checks.json).
Ogni controllo usa `source.kind=git-provider`, `requires=none`,
`blocks=deployment-alias`, target `production` e timeout di 1.800 secondi.
L'aggiunta via `vercel project checks add` usa una singola specifica JSON per volta;
`vercel project checks itadb --json` permette di confrontare la configurazione remota.
Non duplicare controlli con lo stesso nome. Le preview restano protette dal login Vercel.
[Deployment checks Vercel](https://vercel.com/docs/deployment-checks).

Dopo un push confrontare il commit dei deployment con quello di GitHub e ripetere
le verifiche HTTP. Le build aggiornano il codice, mantenendo il volume Railway;
la generazione e l'installazione di nuove release dei dati restano operazioni
separate. Il solo collegamento Git non dimostra un aggiornamento riuscito da push.

## Monitoraggio della disponibilità

Il workflow [Deployment availability](../.github/workflows/availability.yml)
controlla ogni 15 minuti readiness, catalogo non vuoto, CORS, homepage e asset
JavaScript. Configurare le variabili repository GitHub `ITADB_API_URL` e
`ITADB_WEB_URL` con le origini HTTPS effettive, senza percorsi o credenziali.
È disponibile anche l'avvio manuale da Actions. Non serve un token dei provider.

```sh
python3 scripts/check_deployment.py --api-url https://DOMINIO-API-RAILWAY --web-url https://DOMINIO-FRONTEND
```

Sono previste quattro richieste per tentativo, timeout di 15 secondi e al massimo
tre tentativi. Il job fallisce se i controlli non passano; le notifiche seguono
le preferenze GitHub Actions dell'account. La consegna email non è configurata
né provata dal repository. Gli orari schedulati GitHub possono subire ritardi;
questo è un controllo periodico, non una garanzia di disponibilità o latenza.
Il workflow schedulato diventa operativo quando il file entra nel branch `main`.

## Verifica del rilascio

Verificare `/health/ready`, `/v3/populations`, una mappa, una pagina individuale e
una famiglia; controllare anche i cataloghi v1/v2. Dal browser Vercel verificare
richieste HTTPS e CORS, filtri, paginazione e Metodo. Misurare memoria e latenza
sul provider con il carico atteso. Il recupero usa la popolazione preparata localmente;
non è previsto un backup cloud.

Questi passaggi richiedono i progetti e i domini effettivi: la configurazione e
le prove locali non equivalgono a un deployment cloud già eseguito.

## Aggiornamento e rollback

Installare una nuova directory verificata con `install-serving --activate` e
riavviare l'API. Ogni processo mantiene la release selezionata all'avvio.
L'aggiornamento con volume può comportare una breve indisponibilità.

Per il rollback: `itadb activate-serving --release SHA256-PRECEDENTE` e riavvio.
Per un ripristino su un volume nuovo, ricopiare il pacchetto locale verificato
oppure rigenerarlo con il metodo versionato e gli input conservati. Verificare,
installare e attivare la nuova release. Git contiene il metodo, non i dati;
conservare localmente input, manifest ed evidenze. Non cancellare le release
necessarie al rollback.
