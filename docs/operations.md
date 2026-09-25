# Operazioni

## Ambiente e avvio

Usare la [guida Linux](local-environment.md) per avvio, migrazione e test isolati.
Compose è un ambiente locale. API e frontend leggono l’archivio DuckDB; la generazione
usa un archivio separato scelto da `ITADB_DATA_DIR`. Il filesystem host `data/`
e il volume Compose `evidence` sono distinti.

## Archivio di consultazione

La [guida deployment](deployment.md) descrive export completo, verifica,
installazione, attivazione atomica e ripristino. Il serving non usa Neon o
PostgreSQL; tutte le procedure PostgreSQL seguenti appartengono al workflow
locale. Dopo una pubblicazione o un completamento geografico, esportare una
nuova release DuckDB per renderla visibile online. Il cambio richiede riavvio.

## Generazione, audit e pubblicazione

Seguire il [workflow corrente](population.md#pipeline-corrente): acquisire
l'inventario nazionale con `fetch-national-inputs` e STR/RCS con
`fetch-citizenship`, poi eseguire `synthesize-population`, `verify-population`
e `publish-population`. Usare i percorsi effettivamente stampati dai comandi.

```sh
uv run python scripts/run_logged.py --label "Pubblicazione popolazione" --log .tools/population-publication.log -- uv run itadb publish-population --run data/curated/population/RUN_ID
```

Ogni attività lunga deve mostrare fase, conteggi disponibili, tempo ed esito.
`run_logged.py` conserva l'output e un heartbeat ogni dieci secondi. Senza
`--log` usa `.tools/task-progress.log`; seguirlo da un altro terminale con
`tail -n 30 -F .tools/task-progress.log`. Non inserire credenziali negli argomenti.

L'importatore verifica snapshot, fonti e geografia, carica record e distribuzioni,
quindi pubblica in un'unica transazione. I retry identici non duplicano snapshot.
Un errore produce rollback e quarantena. Se fallisce soltanto il rapporto locale
dopo il commit, il diagnostico riporta `published=true` e snapshot ID: il retry
riconosce la pubblicazione già completata.

## Confini amministrativi

La revisione corrente `0002_province_boundaries`, successiva a `0001_baseline`,
aggiunge i confini provinciali della popolazione. Non va confusa con la vecchia
revisione numerica `0002` precedente al consolidamento.

Dopo la migrazione, uno snapshot già pubblicato può completare i confini senza
ricaricare individui o famiglie:

```sh
uv run python scripts/run_logged.py --label "Confini provinciali" --log .tools/population-boundaries.log -- uv run itadb publish-population-boundaries --snapshot-id 1
```

Usare l'ID effettivo. Il comando verifica checksum e corrispondenza territoriale,
importa atomicamente e conserva l'hash di origine. Ripeterlo non duplica geometrie;
fonti incomplete lasciano il DB invariato. Le nuove pubblicazioni includono il passaggio.

## Baseline consolidata

Dal 24 settembre 2026 la catena attiva ha una sola radice: `0001_baseline`.
Le revisioni 0001–0006 sono conservate nel commit
[`9cd934a`](https://github.com/matik81/itadb/tree/9cd934a/migrations).
La nuova baseline crea direttamente lo stesso schema finale, inclusi
popolazione sintetica, viste, vincoli, trigger e cataloghi iniziali.
Le successive modifiche allo schema richiedono nuove revisioni.

**Database nuovo:** `uv run python scripts/migrate.py` applica la baseline
e configura il reader; richiede le variabili amministrative e `API_DB_PASSWORD`
descritte nella guida locale. Una seconda esecuzione non modifica i dati.

**Database esistente a 0006:** non eseguire il DDL iniziale sopra le tabelle
esistenti. Verificare che lo schema non abbia modifiche manuali e conservare
il valore corrente del registro Alembic. Prima dell’allineamento confrontare lo schema effettivo con quello previsto
dalla baseline, inclusi viste, vincoli e trigger.
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

Eseguire quindi `scripts/migrate.py` e verificare con `ITADB_SERVING_BACKEND=postgres` `/health/ready`, catalogo
popolazioni e query individuali. L'allineamento non importa, cancella o
riscrive record applicativi. Non è una verifica automatica di eventuali
modifiche manuali al DDL.
Con Compose ricostruire l'immagine del servizio `migrate` prima di eseguirlo,
così che contenga la nuova storia: `docker compose --profile offline build migrate`.

**Database a 0001–0005:** completare prima l'upgrade a 0006 da un checkout
del commit `9cd934a`, poi seguire il passaggio sopra. Non marcare come baseline
uno schema incompleto. Per annullare il solo allineamento del registro,
prima di applicare ulteriori migrazioni, ripristinare `0006` nella stessa
transazione con controllo del valore atteso e usare il codice `9cd934a`.
Non rimuovere volumi, tabelle o archivi di evidenze.


## Conservazione e recupero

Conservare insieme raw, snapshot completi, inventari, contratti, sorgenti e lock
archiviati, rapporti e quarantene. Il [catalogo dei percorsi](../data/README.md)
descrive snapshot, originali e prove locali.
Non spostare file citati dai manifest o dal database senza migrare e verificare
anche tutti i riferimenti. Non eliminare checkpoint o file `pending` per far
passare un retry: una corruzione richiede indagine e una nuova root di riproduzione.

Backup verificato, upgrade in staging e confronto di schema/conteggi precedono
le modifiche al DB. Il downgrade distruttivo è rifiutato: recuperare su un database
isolato con backup e codice corrispondente, oppure con una migrazione correttiva.
Non cancellare volumi. Registrare gli esiti dei controlli in [validation.md](validation.md).

## Verifiche e CI

Gli [strumenti](../scripts/README.md) comprendono manutenzione e benchmark
della generazione e del servizio. La CI verifica Python, PostgreSQL/PostGIS, OpenAPI,
tipi client, frontend, link documentali e smoke Compose. I benchmark onerosi sono
espliciti e non vengono lanciati per controllare un import o un connettore.

Workflow e protezioni GitHub sono cose distinte: i file YAML non dimostrano che
branch protection o secret scanning siano attivi. Consultare il
[registro delle verifiche](validation.md) per ciò che è stato effettivamente controllato.

## Deployment

La configurazione Railway e la [procedura di rilascio](deployment.md) usano
FastAPI, volume persistente e frontend statico. Non serve un servizio PostgreSQL
online. Conservare backup esterni verificati degli archivi e provare il restore;
una release precedente sullo stesso disco non copre la perdita del volume.
Il deployment cloud non è stato eseguito. Le immagini fissano versioni di linea;
digest, scan e SBOM appartengono alla release produttiva. Il file lock delle
acquisizioni è locale e non coordina host diversi.
