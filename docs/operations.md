# Esercizio e sicurezza operativa

## Sviluppo

Compose crea database PostGIS, migrazione one-shot, ruolo API, server e frontend Nginx.
`docker compose run --rm pipeline itadb ingest-demo` pubblica la fixture; ripeterlo è
idempotente. `docker compose stop` arresta i servizi; `down` rimuove i container ma conserva
i volumi. **Non usare `down -v` su dati da conservare.** Le fixture del repository sono
separate dagli originali scaricati, esclusi da Git.

Lavorare nel filesystem Linux, anche in WSL2, e creare `.venv` e `node_modules`
dai lockfile nel clone corrente. Prerequisiti e test su database isolato sono
nella [guida dell’ambiente](local-environment.md).

## Confine dello scaffold

Non è un deployment pubblico di produzione. Le immagini hanno versioni di linea ma
non digest immutabili; una release produttiva deve fissare digest, scan e SBOM, oltre ai
lockfile applicativi. Il DB owner è usato per migrazione e pipeline locale; separare
DDL owner, writer e reader in produzione. Nessun TLS pubblico, secret manager, backup
automatico, tracing distribuito o sistema di allerta è provisionato qui.

## Prima esposizione pubblica

1. TLS al gateway, solo web/API esposti, DB su rete privata. CORS esplicito.
2. Segreti generati e custoditi fuori Git; rotazione e privilegi separati. Non usare le
   password di esempio. Le password nei DSN devono essere correttamente percent-encoded.
3. Rate limit condiviso a livello edge per più repliche; la zona Nginx locale non è globale.
4. Budget connessioni/CPU/RAM, timeout, queue per i batch e un solo limiter per IP upstream.
5. Log JSON con request_id e durata, metriche di errori, latenza, pool, query lente, WAL,
   spazio libero, freschezza delle fonti e run bloccati. Evitare payload o query sensibili.
6. Conservazione e recupero: backup PostgreSQL con WAL/PITR, oggetti versionati e checksum.
   Eseguire un restore su ambiente isolato e verificare release, conteggi e gate.
7. Definire RPO/RTO e retention con il gestore; nessun valore SLA è assunto nello scaffold.

## Migrazioni e recupero

Backup verificato, upgrade in staging, verifica compatibilità API, pianificazione di lock
e tempi, rollout e monitoraggio. La migrazione iniziale è intenzionalmente irreversibile:
un downgrade distruggerebbe le evidenze. Recuperare con backup verificato o migrazione
correttiva forward. Testare l'upgrade da vuoto e da ogni versione supportata.

### Baseline consolidata

Dal 24 settembre 2026 la catena attiva ha una sola radice: `0001_baseline`.
Le revisioni 0001–0006 sono conservate nel commit
[`9cd934a`](https://github.com/matik81/itadb/tree/9cd934a/migrations).
La nuova baseline crea direttamente lo stesso schema finale, inclusi
popolazione sintetica, viste, vincoli, trigger e cataloghi iniziali.
Il consolidamento della storia è stato richiesto esplicitamente; le prossime
modifiche richiedono nuove revisioni. I riferimenti numerici nelle sezioni
M1/M2 sotto descrivono le operazioni precedenti a questo consolidamento.

**Database nuovo:** `uv run python scripts/migrate.py` applica la baseline
e configura il reader; richiede le variabili amministrative e `API_DB_PASSWORD`
descritte nella guida locale. Una seconda esecuzione non modifica i dati.

**Database esistente a 0006:** non eseguire il DDL iniziale sopra le tabelle
esistenti. Verificare che lo schema non abbia modifiche manuali e conservare
il valore corrente del registro Alembic. Il confronto tra la catena storica
e la baseline è documentato nel [piano](plans/migration-baseline.md).
Con i processi di migrazione fermi e `ITADB_ADMIN_DATABASE_URL` rivolto al
database corretto, allineare solo il registro, in una transazione:

```sh
uv run python - <<'PY'
import psycopg
from itadb.config import Settings

with psycopg.connect(Settings().admin_database_url) as db:
    db.execute("LOCK TABLE public.alembic_version IN ACCESS EXCLUSIVE MODE")
    versions = db.execute("SELECT version_num FROM public.alembic_version").fetchall()
    if versions == [("0006",)]:
        db.execute("UPDATE public.alembic_version SET version_num='0001_baseline' WHERE version_num='0006'")
    elif versions != [("0001_baseline",)]:
        raise RuntimeError("È richiesto lo schema storico completo a 0006")
print("Registro Alembic allineato alla baseline; dati applicativi invariati")
PY
```

Eseguire quindi `scripts/migrate.py` e verificare `/health/ready`, catalogo
popolazioni e query individuali. L'allineamento non importa, cancella o
riscrive record applicativi. Non è una verifica automatica di eventuali
modifiche manuali al DDL.
Con Compose ricostruire l'immagine del servizio `migrate` prima di eseguirlo,
così che contenga la nuova storia: `docker compose build migrate`.

**Database a 0001–0005:** completare prima l'upgrade a 0006 da un checkout
del commit `9cd934a`, poi seguire il passaggio sopra. Non marcare come baseline
uno schema incompleto. Per annullare il solo allineamento del registro,
prima di applicare ulteriori migrazioni, ripristinare `0006` nella stessa
transazione con controllo del valore atteso e usare il codice `9cd934a`.
Non rimuovere volumi, tabelle o archivi di evidenze.

Per file orfani confrontare `catalog.artifact` e archivio; proporre un report di garbage
collection prima della rimozione, con retention dei fallimenti. Non eliminare originali
automaticamente in caso di importazione fallita. In caso di corruzione fermare la pubblicazione,
conservare evidenza del guasto e ripristinare contenuti verificati.

La migrazione 0002 abilita `btree_gist`, aggiunge vincoli temporali e viste v2,
senza riscrivere le release pubblicate. Il ruolo di migrazione deve poter creare
l'estensione. Rieseguire `scripts/migrate.py` applica anche i grant alle nuove viste.
I test M1 creano database isolati: richiedono CREATEDB sul server **di test**.

Per la prima pubblicazione locale è stato conservato un backup pre-0002 in
`.tools/backups/itadb-before-0002-20260923.dump`, fuori Git. Il recupero consiste
nel ripristino in un nuovo database isolato e nella verifica degli artefatti,
non nel downgrade distruttivo del catalogo. Ripristinare anche la corrispondente
versione dell'applicazione quando si recupera lo schema precedente.
Il restore del backup è stato eseguito in `itadb_m1_restore_20260923` sul server
di test: schema 0001 e identità, checksum e conteggio della demo corrispondono.
Questa prova non configura un sistema automatico di backup o un obiettivo RPO/RTO.

Le acquisizioni, i manifest, i contratti e la pagina licenza della release ISTAT
sono nel volume `itadb_evidence`. Il filesystem `data/` del repository e il volume
Compose sono archivi distinti: non presumere che un file locale sia già nel container.
Non utilizzare la fixture `istat-population-invented.csv` nel catalogo applicativo:
serve esclusivamente ai test isolati. [Procedura ISTAT](sources/istat-population.md).

## Operazioni M2 e avanzamento

Le migrazioni 0003/0004 aggiungono copertura, geografie e controlli alla pubblicazione.
Prima dell'upgrade locale è stato creato e ripristinato un backup in un nuovo DB
di test; le tre release precedenti e i conteggi sono stati conservati anche dopo
due upgrade consecutivi. Il rapporto è `data/reports/m2-backup-restore.json`.
Originali e artefatti M2 sono nel volume condiviso `itadb_evidence`.

La revisione correttiva 0005 ripete i controlli di contesto degli eventi e di
contenimento geometrico immediatamente prima della pubblicazione. Non modifica
le revisioni applicate o le evidenze pubblicate. Aggiornare anche la pipeline:
le nuove pubblicazioni dichiarano la politica geometrica nel dettaglio del gate;
senza questa informazione il DB rifiuta la pubblicazione. Il backup pre-0005 e
il suo ripristino isolato sono registrati in `data/reports/m2-review-backup-restore.json`.
Per recuperare usare il backup in un nuovo DB e il codice corrispondente, oppure
una correzione forward; non eliminare volumi o forzare un downgrade.

Per le attività lunghe usare `scripts/run_logged.py --label "Fase" -- COMANDO`:
output seguito in tempo reale, heartbeat ogni dieci secondi, durata e codice
finale nel log `.tools/m2-progress.log`. Non passare credenziali negli argomenti
e non registrare payload personali. Un terminale dedicato può seguire
`tail -n 30 -F .tools/m2-progress.log`. La direttiva è anche in AGENTS.md.

Il benchmark `scripts/benchmark_m2.py` richiede `ITADB_TEST_DATABASE_URL`, schema
migrato e catalogo vuoto. Produce solo aggregati inventati su un server di test:
non usarlo nel catalogo applicativo. Non rimuove evidenze o database. Il rapporto
misura caricamento, query, dimensione DB, WAL e piano; non è un test di sintesi 1:1.

## GitHub

CI su push main/PR: lint, tipi, unit, contratto OpenAPI,
test PostGIS e smoke Compose. Workflow con permessi contents:read e action fissate a SHA.
Dependabot propone aggiornamenti; audit dipendenze settimanale. Richiedere i controlli e
una revisione sulle PR, vietare force push, abilitare segnalazioni private, secret scanning
e push protection dove disponibili. Le impostazioni effettivamente applicate sono registrate
in docs/validation.md: un file YAML non prova che una protezione GitHub sia abilitata.
## Popolazione corrente: cittadinanza prima delle famiglie

Seguire [la pipeline corrente](population.md#pipeline-corrente) con
`synthesize-population --inputs INVENTARIO_M4 --citizenship-inputs INVENTARIO_STR_RCS`.
Il riferimento è `contracts/population-reference-v1.json`; il budget resta
`contracts/m4-budget-v1.json`. `verify-population --run SNAPSHOT` rilegge
autonomamente le evidenze delle quattro fasi, senza `--base-run`.

Conservare l'intera directory `data/curated/population/<run_id>`, compresi
gli `individuals.parquet` prima delle famiglie, insieme a raw, inventari,
contratti, sorgenti e lock archiviati. Report e misure sono in
`data/reports/population`; log visibile `.tools/population-progress.log`.
Gli stessi obblighi di conservazione, budget, checkpoint e quarantena
si applicano ai riferimenti storici seguenti. Non cancellarli durante la migrazione.

## Snapshot sintetici locali M4 — storico

Il percorso [M4](synthesis-m4.md) usa l'archivio locale e non pubblica nel
database di servizio. Eseguire da root `fetch-m4`, poi `synthesize-m4 --inputs
INVENTARIO` sotto `scripts/run_logged.py`, conservando il terminale di progresso.
Budget e riferimento sono in `contracts/m4-budget-v1.json` e
`contracts/m4-reference-v1.json`. Usare `verify-m4 --run SNAPSHOT` per la rilettura.

Ripetere la stessa sintesi recupera i checkpoint verificati in `data/state/`;
una directory in `data/curated/m4/` è visibile soltanto dopo il completamento.
Non cancellare file `pending`, tentativi interrotti, quarantene o checkpoint
per far passare un retry. Gli hash alterati richiedono un'indagine e una nuova
root di riproduzione; non una riparazione dello snapshot esistente.

Conservare originali e relativi manifest, codice/lock archiviati e snapshot
nello stesso piano di backup. Il file lock è locale: non montare questo
protocollo come coordinatore multi-host. RSS e disco della macchina devono
avere margine anche per altre applicazioni; il limite DuckDB non equivale
al picco RSS del processo. Gli ID rappresentano record sintetici; nessun
microdato deve entrare in Git o nelle API. La sola tabella in `distribution/`
rispetta il formato aggregato documentato, senza pubblicazione automatica.

## Cittadinanza: conservazione dello snapshot derivato storico

`fetch-citizenship`, `synthesize-citizenship` e `verify-citizenship` seguono il
[percorso documentato](citizenship.md). I risultati sono in
`data/curated/citizenship/<run_id>` e dipendono dalla base M4 identificata nel
manifest. Salvare e ripristinare **entrambi gli snapshot**, gli originali raw,
i contratti e i sorgenti archiviati. L'audit richiede esplicitamente `--base-run`.

I retry controllano gli inventari e rileggono i dati. Checkpoint integri sono
riusati; file corrotti vengono conservati e bloccano il run. I batch temporanei
interrotti vengono spostati nello stato con un nome distinto. Non cancellare
evidenze per forzare la ripresa: per una ricostruzione usare una nuova root.
Misure e log dei tentativi sono in `data/reports/citizenship`; le quarantene
sono in `data/quarantine`. Il log seguito nel terminale è
`.tools/citizenship-progress.log`. Nessuna distribuzione pubblica automatica.


## Popolazione nel database applicativo

`itadb publish-population --run PERCORSO` importa uno snapshot corrente già
completato. Richiede `ITADB_ADMIN_DATABASE_URL`, schema migrato e archivio
originali/contratti nello stesso `ITADB_DATA_DIR`. Il comando verifica prima
lo snapshot e conserva avanzamento ed esito in `reports/population-publication`.
Famiglie, individui e distribuzioni diventano visibili in una sola transazione.
Un retry identico non duplica dati. Le partizioni pubblicate sono immutabili.

API e frontend non montano l'archivio della generazione. Il ruolo reader accede
solo alle viste. La sezione Metodo legge prove e provenienza dallo stesso DB,
quindi non dipende dalla macchina dove sono stati generati i Parquet.

La precedente esclusione dei microdati dalle API riguarda il percorso storico
M4; per il prodotto corrente è superata dall'ADR 0015. Nessun record sintetico
entra in Git. La destinazione prevista è su servizi gestiti: nessun deployment
Internet o provider è stato configurato in questa fase.

Un errore di scrittura del rapporto locale dopo il commit viene distinto da
un rollback: il diagnostico riporta `published=true` e lo snapshot ID. Il
retry riconosce la pubblicazione già completata. File e database non
partecipano a una transazione distribuita.
